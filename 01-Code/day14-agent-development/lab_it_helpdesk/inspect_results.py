"""Read-only viewers for the lab evidence (no model calls, no writes).

python -m lab_it_helpdesk.inspect_results schemas          # tools, permission levels, typed schemas
python -m lab_it_helpdesk.inspect_results summary          # official 10-scenario results table
python -m lab_it_helpdesk.inspect_results trajectory S09   # one trajectory log, event by event
"""

from __future__ import annotations

import json
import sys
import textwrap
from pathlib import Path

from .tools import TOOLS

LAB = Path(__file__).resolve().parent.parent / "results" / "lab"


def schemas() -> None:
    for t in TOOLS.values():
        approval = "REQUIRED" if t.permission.value == "write" else "not needed"
        props = t.input_model.model_json_schema()["properties"]
        print(f"{t.name}  permission={t.permission.value.upper()}  approval={approval}  timeout={t.timeout_s}s")
        print(f"  purpose : {t.description}")
        for name, p in props.items():
            rule = p.get("pattern") or p.get("enum") or {k: p[k] for k in ("minLength", "maxLength") if k in p}
            print(f"  in  {name:<12} {p.get('type', 'enum'):<7} {rule}")
        print(f"  out {t.output_model.__name__}: {', '.join(t.output_model.model_fields)}  (extra fields forbidden)\n")


def summary() -> None:
    d = json.loads((LAB / "scenario-results.json").read_text())
    print(f"Official run {d['run_utc']} | model {d['model']} | saved results (displayed, not re-run)\n")
    print(f"{'ID':<4} {'Scenario':<34} {'Tools (status [approval])':<52} {'Writes':<7} Result")
    for s in d["scenarios"]:
        print(
            f"{s['id']:<4} {s['title']:<34} {', '.join(s['tools_called']) or '(none)':<52} {len(s['backend_writes']):<7} "
            f"{'PASS' if s['passed'] else 'FAIL'}"
        )
    print(
        f"\nPassed {d['passed']}/{d['total']} | unapproved writes {d['unapproved_writes']} | model calls "
        f"{d['usage']['model_calls']} | tokens {d['usage']['prompt_tokens']}+{d['usage']['completion_tokens']}"
    )
    print(
        "S05: checker false negative (correct behaviour; see 02-Documentation/day14-lab-s05-checker-fix.md). "
        "Official score stays 9/10."
    )


def trajectory(sid: str) -> None:
    path = LAB / "trajectories" / f"{sid}.jsonl"
    print(f"{path.relative_to(LAB.parent.parent)} (saved log, displayed, not re-run)")
    for e in map(json.loads, path.read_text().splitlines()):
        skip = {"scenario_id", "seq", "time_utc", "event"}
        body = {k: v for k, v in e.items() if k not in skip and v not in (None, [], {})}
        print(f"#{e['seq']:<2} {e['event']}")
        print(textwrap.indent(textwrap.fill(json.dumps(body, ensure_ascii=False), 150), "    "))


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "summary"
    {"schemas": schemas, "summary": summary}.get(cmd, lambda: trajectory(sys.argv[2]))()
