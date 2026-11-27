"""Run the 10 lab scenarios with the real model and write trajectories + a results report.

    .venv/bin/python -m lab_it_helpdesk.run_scenarios                 # all 10, real Groq model
    .venv/bin/python -m lab_it_helpdesk.run_scenarios --only S01 S04  # a subset
    .venv/bin/python -m lab_it_helpdesk.run_scenarios --only S06 --interactive   # a person approves at the terminal

Each scenario gets a fresh mock backend. Approval decisions come from the scenario definition (or the
terminal with --interactive). Outputs (results/lab/): trajectories/<ID>.jsonl, scenario-results.json,
scenario-report.md. Results are reported exactly as they come out; failing scenarios stay failing.
"""

from __future__ import annotations

import argparse
import json
import time
from datetime import UTC, datetime
from pathlib import Path

from .agent import HelpdeskAgent
from .approval import InteractiveApprover, ScriptedApprover
from .backend import MockITBackend
from .executor import GuardedExecutor, Session
from .models import GroqModel
from .scenarios import SCENARIOS
from .trajectory import TrajectoryLogger

OUT = Path(__file__).resolve().parent.parent / "results" / "lab"


def run_one(sc, model, interactive=False, out_dir=OUT):
    backend = MockITBackend(faults=dict(sc.faults))
    log = TrajectoryLogger(sc.id, out_dir / "trajectories" / f"{sc.id}.jsonl")
    approver = InteractiveApprover() if interactive else ScriptedApprover(list(sc.approvals))
    executor = GuardedExecutor(backend, Session(sc.user), approver, log)
    t0 = time.perf_counter()
    result = HelpdeskAgent(model, executor).run(sc.request)
    failures = sc.check(result, backend)
    unapproved = [
        w for w in backend.writes if not any(e["event"] == "approval_decision" and e["state"] == "approved" for e in log.events)
    ]
    if unapproved:
        failures.append(f"UNAPPROVED WRITE: {unapproved}")
    row = {
        "id": sc.id,
        "title": sc.title,
        "input": sc.request,
        "expected": sc.expected,
        "approvals_scripted": "interactive" if interactive else sc.approvals,
        "faults": sc.faults,
        "tools_called": [
            f"{n}:{r.status}" + (f"[{r.approval}]" if r.approval != "not_required" else "") for n, r in result.tool_results
        ],
        "backend_writes": backend.writes,
        "final_answer": result.final_answer,
        "outcome": result.outcome,
        "steps": result.steps,
        "answer_corrected_by_guardrail": result.corrected,
        "passed": not failures,
        "failures": failures,
        "unapproved_writes": len(unapproved),
        "usage": result.usage,
        "seconds": round(time.perf_counter() - t0, 2),
        "trajectory": f"results/lab/trajectories/{sc.id}.jsonl",
    }
    return row


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", nargs="*")
    ap.add_argument("--interactive", action="store_true", help="ask a person at the terminal for approvals")
    args = ap.parse_args(argv)
    chosen = [s for s in SCENARIOS if not args.only or s.id in args.only]
    model = GroqModel()
    print(
        f"IT Helpdesk Agent - {len(chosen)} scenario(s) | model {model.name} (temperature 0) | max 6 steps | tool timeout 1.0 s"
    )
    rows = []
    for sc in chosen:
        print(f"\n[{sc.id}] {sc.title}\n  input   : {sc.request}")
        # Only the full scripted run writes the official files; subsets and interactive runs go elsewhere.
        out = (
            OUT if not (args.only or args.interactive) else OUT / "extra-runs" / ("interactive" if args.interactive else "subset")
        )
        row = run_one(sc, model, args.interactive, out)
        print(f"  log     : {(out / 'trajectories' / (sc.id + '.jsonl')).relative_to(OUT.parent.parent)}")
        rows.append(row)
        print(f"  tools   : {', '.join(row['tools_called']) or '(none)'}")
        print(f"  writes  : {row['backend_writes'] or 'none'}")
        print(f"  answer  : {row['final_answer'][:230]}")
        print(f"  result  : {'PASS' if row['passed'] else 'FAIL - ' + '; '.join(row['failures'])}")
        if args.interactive or len(chosen) > 1:
            time.sleep(2)  # spacing between scenarios (free-tier rate limits)
    passed = sum(r["passed"] for r in rows)
    unapproved = sum(r["unapproved_writes"] for r in rows)
    usage = {k: sum(r["usage"][k] for r in rows) for k in ("model_calls", "prompt_tokens", "completion_tokens")}
    print(
        f"\nSUMMARY: {passed}/{len(rows)} passed | unapproved writes: {unapproved} | model calls {usage['model_calls']}, "
        f"tokens {usage['prompt_tokens']}+{usage['completion_tokens']}"
    )
    if not args.only and not args.interactive:
        summary = {
            "run_utc": datetime.now(UTC).isoformat(timespec="seconds"),
            "model": model.name,
            "passed": passed,
            "total": len(rows),
            "unapproved_writes": unapproved,
            "usage": usage,
            "scenarios": rows,
        }
        (OUT / "scenario-results.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n")
        print(f"Wrote {OUT.relative_to(OUT.parent.parent)}/scenario-results.json and trajectories/S01-S10.jsonl")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
