# Day 14 – AI06 Agent Development

Python 3.12 · Pydantic v2 · Groq `openai/gpt-oss-120b` (temperature 0) · pytest · ruff. Each deliverable is a separate package.

| Deliverable | Folder | Status |
|---|---|---|
| Lab – IT Helpdesk Agent | [`lab_it_helpdesk/`](lab_it_helpdesk/), tests [`tests/lab/`](tests/lab/), results [`results/lab/`](results/lab/) | Completed – Pending Review |
| Activity 1 – Agent loop / ReAct | [`activity1_agent_loop/`](activity1_agent_loop/), tests [`tests/activity1/`](tests/activity1/) | Completed – Pending Review |
| Activity 2 – LangGraph | [`activity2_langgraph/`](activity2_langgraph/), tests [`tests/activity2/`](tests/activity2/), graph [`results/activity2/graph.mmd`](results/activity2/graph.mmd) | Completed – Pending Review |
| Activity 3 – Workflow patterns | [`activity3_workflows/`](activity3_workflows/), tests [`tests/activity3/`](tests/activity3/), results [`results/activity3/`](results/activity3/) | Completed – Pending Review |

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

## Activity 1 – Minimal agent loop (no framework)

[`activity1_agent_loop/agent_loop.py`](activity1_agent_loop/agent_loop.py): call the model → tool call? → execute the tool →
append the observation → call again → final answer; at most 5 steps. Tool failures (unknown tool, bad JSON/arguments,
exceptions) become observations. Prints step number, ACTION (tool + input), OBSERVE, FINAL / STOP; no private reasoning.

```bash
.venv/bin/python -m activity1_agent_loop.agent_loop --demo success|tool-error|max-steps   # scripted model, no API call
.venv/bin/python -m activity1_agent_loop.agent_loop --live "Is ticket TCK-1042 resolved, and is the email service working?"
```
Results: success (2 steps), tool error reported honestly, stop at exactly 5 steps ("No result is claimed"); live run with
the real model: both tools chosen, timeout reported as "status is unknown", 3 model calls, 781 + 166 tokens. 5 tests.

## Activity 2 – LangGraph port

[`activity2_langgraph/graph_agent.py`](activity2_langgraph/graph_agent.py): `AgentState` (messages with `add_messages` +
`steps`), `agent` node, `ToolNode(handle_tool_errors=True)`, conditional `route` → tools / step_limit / END, max 5 steps.
Same tools, prompt and scripted runs as Activity 1.

```bash
.venv/bin/python -m activity2_langgraph.graph_agent --demo success|tool-error|max-steps   # scripted model, no API call
.venv/bin/python -m activity2_langgraph.graph_agent --live "Is ticket TCK-1042 resolved, and is the email service working?"
.venv/bin/python -m activity2_langgraph.graph_agent --mermaid
```
Results: same outcomes as Activity 1 (success 2 steps; tool error reported; stop at 5 – LangGraph stops before running
the 5th tool call). Live: 3 model calls, honest timeout report. Comparison: `Day-14/02-Documentation/day14-activity2-comparison.md`. 4 tests.

## Activity 3 – Workflow patterns (plain Python)

[`activity3_workflows/router.py`](activity3_workflows/router.py): prompt chain classify → route → handler → gate; Pydantic
`Classification` (billing / tech / other, confidence 0–1, reason) validated before routing, invalid output → `other`;
three handlers; `asyncio.gather` for two independent handlers with timing.

```bash
.venv/bin/python -m activity3_workflows.router --scripted   # scripted model, 1.0 s simulated latency, no API call
.venv/bin/python -m activity3_workflows.router --live       # real model (AsyncGroq)
```
Results: scripted – 4/4 routed as expected, invalid output → other, parallel 2.0 s → 1.0 s (x2.0); live – 4/4 classified
correctly (confidence 0.97–0.99), parallel 1.51 s → 0.94 s (x1.6), 12 model calls, 1,602 + 1,368 tokens. 9 tests.
Pattern comparison: `Day-14/02-Documentation/day14-activity3-workflow-patterns.md`.
