# Day 14 – Evidence Index

Screenshots are manual captures by the project owner of real terminal output. "Saved" = a stored result displayed
without re-running; "live" = run at capture time.

## Lab – IT Helpdesk Agent

| File | Shows | Live / saved |
|---|---|---|
| `01-lab-scenario-run-output.txt` | Console output of the official 10-scenario run (2026-11-27 09:56 UTC): 9/10, 0 unapproved writes | saved log |
| `02-lab-project-structure.png` | Lab files: package, tests, results, trajectories, config (no `.env`, no venv) | live |
| `03-lab-tool-schemas-permissions.png` | 3 tools: permission READ/WRITE, approval requirement, timeout, typed input rules, output schemas | live (reads the Pydantic models) |
| `04-lab-approval-approved-interactive.png` | S06 with the real model; operator typed `y` → `create_ticket:ok[approved]`, TCK-1101 | live (2 model calls) |
| `05-lab-approval-denied-interactive.png` | S01 with the real model; `n` piped to the approval prompt with `printf 'n\n' \|` (command line not visible because the command began with `clear`) → `approval_denied[denied]`, writes none; FAIL is expected (S01's check is for the approved case). Log: `results/lab/extra-runs/interactive/trajectories/S01-denied.jsonl` (`operator typed 'n'`) | live (2 model calls) |
| `05a-lab-approval-reset-approved-interactive.png` | Extra: S01 with the operator typing `y` → reset approved and executed. Three such approved runs happened while retaking the denial shot; logs `S01-approved-attempt*.jsonl` | live |
| `06-lab-scenario-results-summary.png` | All 10 scenarios: tools, approval states, writes, PASS/FAIL; 9/10, 0 unapproved writes, tokens; S05 note | saved results |
| `07-lab-trajectory-s09-prompt-injection.png` | S09 trajectory: injected instructions in tool output; agent reports status only; no write attempted | saved log |
| `08-lab-trajectory-s08-ambiguous-s10-timeout.png` | S08: clarifying question, no tool; S10: timeout observed, one retry, real status reported | saved logs |
| `09-lab-trajectory-approval-states.png` | S02 pending → no_response → approval_missing; S03 pending → denied → approval_denied; executed false | saved logs |
| `10-lab-tests-and-lint.png` | 30 deterministic tests passed, ruff clean, official run files unchanged (12/12 hashes) | live |

## Activity 1 – Agent loop without a framework

| File | Shows | Live / saved |
|---|---|---|
| `11-act1-agent-loop-demos.png` / `.txt` | Scripted-model demos: success (2 steps), tool error reported honestly, stop at the 5-step maximum | live (no API call) |
| `12-act1-agent-loop-live.png` / `.txt` | Real model: check_ticket → in_progress, service_status → TimeoutError, honest final answer; 3 calls, 781 + 166 tokens | live (real model) |

## Activity 2 – LangGraph

| File | Shows | Live / saved |
|---|---|---|
| `13-act2-langgraph-graph-structure.png` | Graph edges (conditional agent → tools / step_limit / END, tools → agent) and the code for state, nodes, ToolNode, edges | live (no API call) |
| `14-act2-langgraph-scripted-runs.png` / `.txt` | Scripted runs through the graph: success, error ToolMessage, step_limit node at 5 steps | live (no API call) |
| `15-act2-langgraph-live.png` / `.txt` | Real model via ChatGroq: check_ticket success, service_status error, honest answer; 3 model calls (token usage not recorded) | live (real model) |

## Activity 3 – Workflow patterns

| File | Shows | Live / saved |
|---|---|---|
| `16-act3-workflows-scripted.png` / `.txt` | Routing + prompt chain for 4 requests, invalid classifier output → other, asyncio.gather 2.0 s → 1.0 s | live (no API call, 1.0 s simulated latency) |
| `17-act3-workflows-live.png` / `.txt` | Real model: 4/4 correct classifications, model-written replies, gather 1.51 s → 0.94 s (x1.6); 12 calls, 1,602 + 1,368 tokens | live (real model) |
