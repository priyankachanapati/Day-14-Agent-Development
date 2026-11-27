"""Activity 1 - a minimal agent loop (ReAct style) in plain Python, without any agent framework.

    1. call the model                      4. append the tool result as an observation
    2. does the reply contain a tool call?  5. call the model again
    3. yes -> execute the tool              6. no tool call -> return the final answer
    7. stop after at most MAX_STEPS = 5 model calls

Each step prints a short action label, the tool, its input and the observation. The model's private
reasoning is never requested or printed - only observable actions and results.

    python -m activity1_agent_loop.agent_loop --demo success      # scripted model, repeatable, no API call
    python -m activity1_agent_loop.agent_loop --demo tool-error
    python -m activity1_agent_loop.agent_loop --demo max-steps
    python -m activity1_agent_loop.agent_loop --live "Is ticket TCK-1042 resolved?"   # real Groq model
"""

from __future__ import annotations

import argparse
import json
import os
import re

MAX_STEPS = 5

# ------------------------------------------------------------------ tools (plain functions + JSON schemas)
TICKETS = {"TCK-1042": "in_progress", "TCK-1077": "open"}


def check_ticket(ticket_id: str) -> dict:
    if ticket_id not in TICKETS:
        raise KeyError(f"ticket {ticket_id} not found")
    return {"ticket_id": ticket_id, "status": TICKETS[ticket_id]}


def service_status(service: str) -> dict:
    if service == "email":
        raise TimeoutError("status API did not respond (simulated outage)")
    return {"service": service, "status": "operational"}


TOOLS = {"check_ticket": check_ticket, "service_status": service_status}
TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "check_ticket",
            "description": "Get the status of an IT ticket (TCK-0000).",
            "parameters": {"type": "object", "properties": {"ticket_id": {"type": "string"}}, "required": ["ticket_id"]},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "service_status",
            "description": "Get the status of an IT service.",
            "parameters": {"type": "object", "properties": {"service": {"type": "string"}}, "required": ["service"]},
        },
    },
]
SYSTEM = (
    "You are an IT helpdesk assistant. Use the tools when needed. If a tool returns an error, say so honestly; "
    "never claim something succeeded or invent a status the tools did not return. Answer briefly."
)


def run_tool(name: str, raw_args) -> dict:
    """Execute a tool; every failure becomes an observation instead of a crash."""
    if name not in TOOLS:
        return {"error": f"unknown tool '{name}'"}
    try:
        args = json.loads(raw_args) if isinstance(raw_args, str) else dict(raw_args)
        return {"result": TOOLS[name](**args)}
    except (json.JSONDecodeError, TypeError) as exc:
        return {"error": f"bad arguments for {name}: {exc}"}
    except Exception as exc:  # noqa: BLE001 - tool failure is reported to the model
        return {"error": f"{type(exc).__name__}: {exc}"}


# ------------------------------------------------------------------ models: a reply = {"content": str, "tool_calls": [...]}
class ScriptedModel:
    """Repeatable stand-in for an LLM: replays pre-written replies (the last one repeats)."""

    def __init__(self, replies: list[dict]):
        self.replies, self.calls = list(replies), 0

    def __call__(self, messages: list[dict]) -> dict:
        self.calls += 1
        return self.replies.pop(0) if len(self.replies) > 1 else self.replies[0]


class GroqModel:
    def __init__(self, model: str = "openai/gpt-oss-120b"):
        from dotenv import load_dotenv
        from groq import Groq

        load_dotenv()
        if not os.getenv("GROQ_API_KEY"):
            raise SystemExit("GROQ_API_KEY not set")
        self.client, self.model, self.calls, self.tokens = Groq(), model, 0, [0, 0]

    def __call__(self, messages: list[dict]) -> dict:
        self.calls += 1
        r = self.client.chat.completions.create(
            model=self.model, messages=messages, tools=TOOL_SCHEMAS, tool_choice="auto", temperature=0
        )
        self.tokens[0] += r.usage.prompt_tokens
        self.tokens[1] += r.usage.completion_tokens
        m = r.choices[0].message
        calls = [{"id": c.id, "name": c.function.name, "arguments": c.function.arguments} for c in (m.tool_calls or [])]
        return {"content": m.content or "", "tool_calls": calls}


def call(i: int, name: str, args: dict) -> dict:
    return {"content": "", "tool_calls": [{"id": f"call_{i}", "name": name, "arguments": json.dumps(args)}]}


# ------------------------------------------------------------------ the loop
def run_agent(question: str, model, max_steps: int = MAX_STEPS) -> dict:
    messages = [{"role": "system", "content": SYSTEM}, {"role": "user", "content": question}]
    print(f"USER: {question}")
    tool_errors = 0
    for step in range(1, max_steps + 1):
        reply = model(messages)  # 1. call the model
        if not reply["tool_calls"]:  # 2. no tool call -> final answer
            answer = reply["content"].strip()
            if (
                tool_errors
                and re.search(r"\b(success|resolved|operational|done)\b", answer, re.I)
                and "error" not in answer.lower()
            ):
                print(f"Step {step} | WARNING   | final answer may overstate success after {tool_errors} tool error(s)")
            print(f"Step {step} | FINAL     | {answer}")
            return {"answer": answer, "steps": step, "stopped": "final_answer", "tool_errors": tool_errors}
        messages.append(
            {
                "role": "assistant",
                "content": reply["content"],
                "tool_calls": [
                    {"id": c["id"], "type": "function", "function": {"name": c["name"], "arguments": c["arguments"]}}
                    for c in reply["tool_calls"]
                ],
            }
        )
        for c in reply["tool_calls"]:  # 3. execute each tool, 4. append the observation
            obs = run_tool(c["name"], c["arguments"])
            tool_errors += "error" in obs
            print(f"Step {step} | ACTION    | tool={c['name']} input={c['arguments']}")
            print(f"Step {step} | OBSERVE   | {json.dumps(obs)}")
            messages.append({"role": "tool", "tool_call_id": c["id"], "content": json.dumps(obs)})
        # 5. loop: call the model again with the observation
    answer = f"Stopped: reached the maximum of {max_steps} steps without a final answer. No result is claimed."
    print(f"STOP      | {answer}")
    return {"answer": answer, "steps": max_steps, "stopped": "max_steps", "tool_errors": tool_errors}


DEMOS = {
    "success": (
        "What is the status of ticket TCK-1042?",
        [call(1, "check_ticket", {"ticket_id": "TCK-1042"}), {"content": "Ticket TCK-1042 is in progress.", "tool_calls": []}],
    ),
    "tool-error": (
        "Is the email service working?",
        [
            call(1, "service_status", {"service": "email"}),
            {
                "content": "I could not check the email service: the status API returned an error (timeout). "
                "Its status is unknown, please try again later.",
                "tool_calls": [],
            },
        ],
    ),
    "max-steps": (
        "Keep checking ticket TCK-1077 until it is resolved.",
        [call(1, "check_ticket", {"ticket_id": "TCK-1077"})],
    ),  # this model never stops calling the tool
}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--demo", choices=DEMOS)
    g.add_argument("--live", metavar="QUESTION")
    a = ap.parse_args(argv)
    if a.demo:
        question, replies = DEMOS[a.demo]
        model = ScriptedModel(replies)
        print(f"=== Activity 1 agent loop | demo '{a.demo}' | scripted model (no API call) | max {MAX_STEPS} steps ===")
        out = run_agent(question, model)
    else:
        model = GroqModel()
        print(f"=== Activity 1 agent loop | live | {model.model} | max {MAX_STEPS} steps ===")
        out = run_agent(a.live, model)
        print(f"model calls {model.calls}, tokens {model.tokens[0]}+{model.tokens[1]}")
    print(f"RESULT: stopped={out['stopped']} steps={out['steps']} tool_errors={out['tool_errors']} model_calls={model.calls}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
