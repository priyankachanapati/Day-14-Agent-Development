# Day 14 – AI06 Agent Development

Python 3.12 · Pydantic v2 · Groq `openai/gpt-oss-120b` (temperature 0) · pytest · ruff. Each deliverable is a separate package.

| Deliverable | Folder | Status |
|---|---|---|
| Lab – IT Helpdesk Agent | [`lab_it_helpdesk/`](lab_it_helpdesk/), tests [`tests/lab/`](tests/lab/), results [`results/lab/`](results/lab/) | Completed – Pending Review |
| Activity 1 – Agent loop / ReAct | `activity1_agent_loop/` | Not started |
| Activity 2 – LangGraph | `activity2_langgraph/` | Not started |
| Activity 3 – Workflow patterns | `activity3_workflows/` | Not started |

## Setup
```bash
uv venv --python 3.12 .venv && uv pip install --python .venv/bin/python pydantic groq python-dotenv pytest ruff langgraph langchain-core langchain-groq
cp .env.example .env   # then add your own GROQ_API_KEY (never commit .env)
.venv/bin/python -m pytest          # deterministic tests, no API calls
```

## Lab – IT Helpdesk Agent

A tool-using agent with guardrails over a **mock** IT backend (no real systems are contacted).

| Module | Role |
|---|---|
| `schemas.py` | Pydantic input/output schemas for each tool; `Permission` = read / write |
| `tools.py` | Tool registry: purpose, schemas, permission level, timeout (1.0 s); OpenAI-style JSON schema |
| `backend.py` | In-memory mock IT system with fault injection (timeout / error / malformed) and a write record |
| `approval.py` | Human approval: pending → approved / denied / no_response (terminal or scenario-declared) |
| `executor.py` | Guarded execution: structure → schema validation → permission → account scope → approval (writes) → timeout → output validation |
| `agent.py` | Agent loop (max 6 steps), model-error handling, false-success guard; system prompt treats tool output as untrusted |
| `trajectory.py` | JSONL trajectory log (observable actions only; no private reasoning) |
| `scenarios.py`, `run_scenarios.py` | 10 scenarios with automatic checks; runner writes results and trajectories |
| `inspect_results.py` | Read-only viewers for schemas, results and trajectories |

```bash
.venv/bin/python -m lab_it_helpdesk.run_scenarios                          # all 10 scenarios (real model)
.venv/bin/python -m lab_it_helpdesk.run_scenarios --only S06 --interactive # a person approves at the terminal
.venv/bin/python -m lab_it_helpdesk.inspect_results summary                # saved results, no API call
```

### Results (official run 1, 2026-11-27 09:56 UTC – not repeated)
**9/10 scenarios passed, 0 unapproved writes**, 20 model calls, 15,350 + 1,697 tokens, no API errors.
S05 failed on a **checker false negative** (the agent answered correctly with a curly apostrophe the regex did not
match); the checker was corrected after the run and the official score stays 9/10 – see
`Day-14/02-Documentation/day14-lab-s05-checker-fix.md`. Files: `results/lab/scenario-results.json`,
`results/lab/trajectories/S01–S10.jsonl` (hashes in `results/lab/official-run-1.sha256`). Interactive approval runs
(screenshots) are in `results/lab/extra-runs/interactive/`.

Tests: 30 deterministic tests (23 guardrail + 7 checker regression), ruff clean.
