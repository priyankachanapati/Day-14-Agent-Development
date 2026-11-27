"""Activity 3 - workflow patterns in plain Python: prompt chaining, routing and parallelization.

Workflow for one request (prompt chain):
    1. classify   - the model returns JSON; it is validated against the Classification schema (Pydantic).
                    Invalid JSON or an unexpected category is never routed blindly: it falls back to "other".
    2. route      - the validated category selects one of three handlers (billing / tech / other).
    3. handle     - the chosen handler prompt drafts the reply.
    4. gate       - a programmatic check of the draft (non-empty, no promised refunds) before it is returned.
Parallelization: independent sub-requests are handled concurrently with asyncio.gather and timed.

    python -m activity3_workflows.router --scripted   # scripted model with fixed latency: repeatable timing, no API call
    python -m activity3_workflows.router --live       # real Groq model (AsyncGroq)
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import time
from typing import Literal

from pydantic import BaseModel, Field, ValidationError

Category = Literal["billing", "tech", "other"]


class Classification(BaseModel):
    """Structured output schema for the router."""

    category: Category
    confidence: float = Field(ge=0, le=1)
    reason: str = Field(min_length=3, max_length=200)


CLASSIFY_PROMPT = (
    "Classify the customer request into exactly one category: billing (invoices, charges, refunds, payment), "
    "tech (software, hardware, accounts, network, errors) or other. Reply ONLY with JSON: "
    '{"category": "billing|tech|other", "confidence": 0.0-1.0, "reason": "<short reason>"}'
)
HANDLER_PROMPTS = {
    "billing": "You are a billing support agent. Reply in at most 3 sentences. "
    "Never promise a refund; say the billing team will review.",
    "tech": "You are a technical support agent. Give at most 3 short troubleshooting steps, then offer to open a ticket.",
    "other": "You are a general helpdesk agent. Reply briefly and point the user to the right team if needed.",
}


# ------------------------------------------------------------------ models
class ScriptedLLM:
    """Deterministic stand-in: keyword classifier + canned replies, each call takes `latency` seconds."""

    def __init__(self, latency: float = 1.0, classify_override: str | None = None):
        self.latency, self.override, self.calls = latency, classify_override, 0

    async def complete(self, system: str, user: str, json_mode: bool = False) -> str:
        self.calls += 1
        await asyncio.sleep(self.latency)
        if json_mode:
            if self.override is not None:
                return self.override
            text = user.lower()
            cat = (
                "billing"
                if re.search(r"invoice|charge|refund|bill|payment", text)
                else "tech"
                if re.search(r"vpn|laptop|password|error|crash|wifi|printer", text)
                else "other"
            )
            return json.dumps({"category": cat, "confidence": 0.9, "reason": f"keywords suggest {cat}"})
        role = next(k for k, v in HANDLER_PROMPTS.items() if v == system)
        return {
            "billing": "Thanks for flagging this. The billing team will review the charge and contact you within 2 working days.",
            "tech": "Please restart the device, check the cable or Wi-Fi, and try again. If it persists I can open a ticket.",
            "other": "Thanks for your message. The office team handles this; I have passed it on.",
        }[role]


class GroqLLM:
    def __init__(self, model: str = "openai/gpt-oss-120b"):
        from dotenv import load_dotenv
        from groq import AsyncGroq

        load_dotenv()
        if not os.getenv("GROQ_API_KEY"):
            raise SystemExit("GROQ_API_KEY not set")
        self.client, self.model, self.calls, self.tokens = AsyncGroq(), model, 0, [0, 0]

    async def complete(self, system: str, user: str, json_mode: bool = False) -> str:
        self.calls += 1
        r = await self.client.chat.completions.create(
            model=self.model,
            temperature=0,
            messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
            **({"response_format": {"type": "json_object"}} if json_mode else {}),
        )
        self.tokens[0] += r.usage.prompt_tokens
        self.tokens[1] += r.usage.completion_tokens
        return (r.choices[0].message.content or "").strip()


# ------------------------------------------------------------------ workflow steps
async def classify(llm, request: str) -> tuple[Classification, str | None]:
    """Step 1: structured classification. Returns (validated classification, fallback reason or None)."""
    raw = await llm.complete(CLASSIFY_PROMPT, request, json_mode=True)
    try:
        return Classification.model_validate_json(raw), None
    except ValidationError as exc:
        problem = "; ".join(f"{'.'.join(map(str, e['loc'])) or 'json'}: {e['msg']}" for e in exc.errors()[:2])
        return Classification(
            category="other", confidence=0.0, reason="fallback after invalid classification"
        ), f"invalid classifier output {raw[:80]!r} ({problem}) -> routed to 'other'"


async def billing_handler(llm, request: str) -> str:
    return await llm.complete(HANDLER_PROMPTS["billing"], request)


async def tech_handler(llm, request: str) -> str:
    return await llm.complete(HANDLER_PROMPTS["tech"], request)


async def general_handler(llm, request: str) -> str:
    return await llm.complete(HANDLER_PROMPTS["other"], request)


HANDLERS = {"billing": billing_handler, "tech": tech_handler, "other": general_handler}


def gate(draft: str) -> tuple[bool, str]:
    """Step 4: programmatic quality gate on the draft reply."""
    if not draft.strip():
        return False, "empty reply"
    if re.search(r"\b(you will (get|receive) a refund|refund (has been|is) (issued|approved))\b", draft, re.I):
        return False, "reply promises a refund"
    return True, "ok"


async def handle_request(llm, request: str) -> dict:
    """Prompt chain: classify -> route -> handler -> gate."""
    t0 = time.perf_counter()
    cls, fallback = await classify(llm, request)
    draft = await HANDLERS[cls.category](llm, request)
    ok, why = gate(draft)
    return {
        "request": request,
        "classification": cls.model_dump(),
        "fallback": fallback,
        "handler": HANDLERS[cls.category].__name__,
        "reply": draft if ok else "A support agent will get back to you shortly.",
        "gate": why,
        "seconds": round(time.perf_counter() - t0, 2),
    }


async def parallel_demo(llm, parts: dict[str, str]) -> dict:
    """Run two independent handlers sequentially, then concurrently with asyncio.gather; time both."""
    t0 = time.perf_counter()
    seq = [await HANDLERS[c](llm, text) for c, text in parts.items()]
    t_seq = time.perf_counter() - t0
    t1 = time.perf_counter()
    par = await asyncio.gather(*(HANDLERS[c](llm, text) for c, text in parts.items()))
    t_par = time.perf_counter() - t1
    return {
        "sequential_s": round(t_seq, 2),
        "parallel_s": round(t_par, 2),
        "speedup": round(t_seq / t_par, 2),
        "results": dict(zip(parts, par, strict=True)),
        "sequential_results": dict(zip(parts, seq, strict=True)),
    }


REQUESTS = [
    "I was charged twice for my November invoice.",
    "My VPN keeps disconnecting every few minutes.",
    "Where can I find the parking rules for the new office?",
    "My laptop shows a blue screen error after the update.",
]
PARALLEL_PARTS = {"billing": "My invoice shows a duplicate charge of 49 EUR.", "tech": "Also, my laptop Wi-Fi drops every hour."}


async def main_async(mode: str) -> dict:
    llm = ScriptedLLM(latency=1.0) if mode == "scripted" else GroqLLM()
    label = "scripted model, 1.0 s simulated latency per call, no API call" if mode == "scripted" else f"real model {llm.model}"
    print(f"=== Activity 3 workflows | {label} ===")
    print("\n[1] Routing + prompt chain (classify -> route -> handler -> gate)")
    out = {"mode": mode, "routed": []}
    for req in REQUESTS:
        r = await handle_request(llm, req)
        out["routed"].append(r)
        c = r["classification"]
        print(f"- {req}")
        print(f"    classified: {c['category']} ({c['confidence']}) -> {r['handler']} | gate {r['gate']} | {r['seconds']} s")
        print(f"    reply: {r['reply'][:160]}")
    print("\n[2] Invalid classifier output is not routed blindly")
    bad = ScriptedLLM(latency=0.0, classify_override='{"category": "refunds", "confidence": 2}')
    r = await handle_request(bad, "Please cancel my subscription.")
    out["invalid_case"] = r
    print(f"    {r['fallback']}\n    handler used: {r['handler']}")
    print("\n[3] Parallelization: two independent handlers")
    p = await parallel_demo(llm, PARALLEL_PARTS)
    out["parallel"] = p
    print(f"    sequential (await one after the other): {p['sequential_s']} s")
    print(f"    parallel   (asyncio.gather)           : {p['parallel_s']} s  -> speed-up x{p['speedup']}")
    for k, v in p["results"].items():
        print(f"    {k:<7}: {v[:140]}")
    calls = llm.calls
    tok = getattr(llm, "tokens", None)
    print(
        f"\nRESULT: {len(REQUESTS)} requests routed, invalid output handled, parallel speed-up x{p['speedup']} "
        f"| model calls {calls}" + (f" | tokens {tok[0]}+{tok[1]}" if tok else "")
    )
    out["model_calls"], out["tokens"] = calls, tok
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--scripted", action="store_true")
    g.add_argument("--live", action="store_true")
    a = ap.parse_args(argv)
    out = asyncio.run(main_async("scripted" if a.scripted else "live"))
    path = os.path.join(os.path.dirname(__file__), "..", "results", "activity3", f"workflow-{out['mode']}.json")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(out, fh, indent=2, ensure_ascii=False)
    print(f"Wrote results/activity3/workflow-{out['mode']}.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
