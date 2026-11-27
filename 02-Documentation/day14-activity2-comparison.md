# Activity 2 – Plain Python loop (Activity 1) vs LangGraph (Activity 2)

Both implementations use the same two tools, the same system prompt, the same three scripted runs and the same live
question, so the differences below come from the implementation style. Figures are measured in this project.

| Dimension | Activity 1 – plain Python loop | Activity 2 – LangGraph |
|---|---|---|
| Code structure | One `for` loop in one function (`run_agent`) | Declared graph: `AgentState`, nodes `agent` / `tools` / `step_limit`, a `route` function, edges |
| Approximate size (code lines, excluding blank lines and docstrings) | 150 (includes both tools, both model clients and the system prompt) | 126 (reuses Activity 1's tool functions and prompt) |
| State management | A local `messages` list and counters | Typed state; `add_messages` reducer merges each node's output; `steps` counter in the state |
| Tool execution | Own `run_tool`: lookup, JSON parsing, try/except | Prebuilt `ToolNode` executes the model's tool calls (incl. parallel calls) |
| Conditional routing | `if not reply["tool_calls"]: return` | `add_conditional_edges("agent", route, …)` → tools / step_limit / END |
| Error handling | Every failure becomes an `{"error": …}` observation | `ToolNode(handle_tool_errors=True)` returns an error `ToolMessage` (adds "Please fix your mistakes.") |
| Step limit | `for step in range(1, 6)`; the 5th tool call is executed, then the loop stops | `route` sends step 5 to `step_limit`; the 5th tool call is not executed. `recursion_limit` is a second safety net |
| Debuggability | Plain prints; easy to step through in a debugger | Node-by-node `stream` updates; graph can be rendered (Mermaid); adds framework layers to step through |
| Maintainability | Fine while the flow is linear; branching and persistence must be hand-written | New nodes/branches are added declaratively; checkpointing, human-in-the-loop interrupts and streaming are available |
| Dependencies and overhead | `groq` client: 15 packages; import ≈ 4 ms | `langgraph` + `langchain-groq`: 41 packages; import ≈ 276 ms; framework APIs to learn and keep up to date |
| Behaviour in the tests | success 2 steps; tool error reported; stop at 5 | identical outcomes (same answers, same step counts) |

**What LangGraph adds:** an explicit, inspectable control-flow graph; typed shared state with reducers; prebuilt tool
execution with error handling; built-in streaming, checkpointing/persistence and interrupts for human approval; easier
growth into multi-step or multi-agent flows.

**What it costs:** more dependencies, slower start-up, framework concepts to learn, and some behaviour hidden in prebuilt
components (for example the default error text added by `ToolNode`).

**When to use which:** a simple tool-calling loop with one model and a few tools is fully served by ~40 lines of Python
(Activity 1). LangGraph becomes worth its overhead when the flow branches, needs to pause for approval and resume,
must persist state between turns, or combines several agents – it is not automatically better.
