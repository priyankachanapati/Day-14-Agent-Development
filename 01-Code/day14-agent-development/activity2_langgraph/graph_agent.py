"""Activity 2 - the Activity 1 agent loop ported to LangGraph.

Graph:  START -> agent --(route)--> tools -> agent ...
                        \\--(route)--> step_limit -> END
                        \\--(route)--> END            (no tool call = final answer)

* State      : messages (with LangGraph's add_messages reducer) + steps (model calls so far)
* agent node : calls the chat model with the tools bound; increments steps
* ToolNode   : runs the requested tools; handle_tool_errors=True turns exceptions into error ToolMessages
* route      : conditional edge - tools if the last AI message has tool calls and steps < MAX_STEPS,
               step_limit if the limit is reached, otherwise END
Same tools and same three scripted runs as Activity 1, so the two implementations can be compared.

    python -m activity2_langgraph.graph_agent --demo success|tool-error|max-steps   # scripted model, no API call
    python -m activity2_langgraph.graph_agent --live "Is ticket TCK-1042 resolved, and is the email service working?"
    python -m activity2_langgraph.graph_agent --mermaid                              # print the graph
"""

from __future__ import annotations

import argparse
import json
from typing import Annotated, TypedDict

from langchain_core.messages import AIMessage, AnyMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.tools import tool
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode

from activity1_agent_loop import agent_loop as a1  # reuse the same tool functions and system prompt

MAX_STEPS = 5


# ------------------------------------------------------------------ tools (LangChain wrappers of the Activity 1 functions)
@tool
def check_ticket(ticket_id: str) -> dict:
    """Get the status of an IT ticket (format TCK-0000)."""
    return a1.check_ticket(ticket_id)


@tool
def service_status(service: str) -> dict:
    """Get the status of an IT service."""
    return a1.service_status(service)


TOOLS = [check_ticket, service_status]


# ------------------------------------------------------------------ state
class AgentState(TypedDict):
    messages: Annotated[list[AnyMessage], add_messages]
    steps: int


# ------------------------------------------------------------------ models
class ScriptedChatModel:
    """Repeatable stand-in for a chat model: returns pre-written AIMessages (the last one repeats)."""

    def __init__(self, replies: list[AIMessage]):
        self.replies, self.calls = list(replies), 0

    def invoke(self, messages):
        self.calls += 1
        msg = self.replies.pop(0) if len(self.replies) > 1 else self.replies[0]
        return msg.model_copy(update={"id": None})


def ai_call(i: int, name: str, args: dict) -> AIMessage:
    return AIMessage(content="", tool_calls=[{"id": f"call_{i}", "name": name, "args": args, "type": "tool_call"}])


DEMOS = {
    "success": (
        "What is the status of ticket TCK-1042?",
        [ai_call(1, "check_ticket", {"ticket_id": "TCK-1042"}), AIMessage("Ticket TCK-1042 is in progress.")],
    ),
    "tool-error": (
        "Is the email service working?",
        [
            ai_call(1, "service_status", {"service": "email"}),
            AIMessage(
                "I could not check the email service: the status API returned an error (timeout). "
                "Its status is unknown, please try again later."
            ),
        ],
    ),
    "max-steps": ("Keep checking ticket TCK-1077 until it is resolved.", [ai_call(1, "check_ticket", {"ticket_id": "TCK-1077"})]),
}


# ------------------------------------------------------------------ graph
def build_graph(model):
    def agent(state: AgentState) -> dict:
        return {"messages": [model.invoke(state["messages"])], "steps": state["steps"] + 1}

    def route(state: AgentState) -> str:
        last = state["messages"][-1]
        if isinstance(last, AIMessage) and last.tool_calls:
            return "tools" if state["steps"] < MAX_STEPS else "step_limit"
        return END

    def step_limit(state: AgentState) -> dict:
        return {
            "messages": [
                AIMessage(f"Stopped: reached the maximum of {MAX_STEPS} steps without a final answer. No result is claimed.")
            ]
        }

    g = StateGraph(AgentState)
    g.add_node("agent", agent)
    g.add_node("tools", ToolNode(TOOLS, handle_tool_errors=True))
    g.add_node("step_limit", step_limit)
    g.add_edge(START, "agent")
    g.add_conditional_edges("agent", route, {"tools": "tools", "step_limit": "step_limit", END: END})
    g.add_edge("tools", "agent")
    g.add_edge("step_limit", END)
    return g.compile()


def run(question: str, model, verbose: bool = True) -> dict:
    graph = build_graph(model)
    state = {"messages": [SystemMessage(a1.SYSTEM), HumanMessage(question)], "steps": 0}
    final, tool_errors, last_steps = None, 0, 0
    if verbose:
        print(f"USER: {question}")
    for update in graph.stream(state, {"recursion_limit": 2 * MAX_STEPS + 4}, stream_mode="updates"):
        for node, delta in update.items():
            last_steps = delta.get("steps", last_steps)
            for m in delta.get("messages", []):
                if isinstance(m, AIMessage) and m.tool_calls:
                    for c in m.tool_calls:
                        verbose and print(
                            f"Step {last_steps} | node={node:<10} | ACTION  | tool={c['name']} input={json.dumps(c['args'])}"
                        )
                elif isinstance(m, ToolMessage):
                    tool_errors += m.status == "error"
                    verbose and print(
                        f"Step {last_steps} | node={node:<10} | OBSERVE | [{m.status}] {' '.join(str(m.content).split())}"
                    )
                else:
                    final = m.content
                    label = "STOP   " if node == "step_limit" else "FINAL  "
                    verbose and print(f"Step {last_steps} | node={node:<10} | {label} | {m.content}")
    stopped = "max_steps" if final and final.startswith("Stopped: reached the maximum") else "final_answer"
    return {"answer": final, "steps": last_steps, "stopped": stopped, "tool_errors": tool_errors}


def live_model():
    from dotenv import load_dotenv
    from langchain_groq import ChatGroq

    load_dotenv()
    return ChatGroq(model="openai/gpt-oss-120b", temperature=0).bind_tools(TOOLS)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--demo", choices=DEMOS)
    g.add_argument("--live", metavar="QUESTION")
    g.add_argument("--mermaid", action="store_true")
    a = ap.parse_args(argv)
    if a.mermaid:
        print(build_graph(ScriptedChatModel([AIMessage("x")])).get_graph().draw_mermaid())
        return 0
    if a.demo:
        question, replies = DEMOS[a.demo]
        model = ScriptedChatModel(replies)
        print(f"=== Activity 2 LangGraph agent | run '{a.demo}' | scripted model (no API call) | max {MAX_STEPS} steps ===")
        out = run(question, model)
        calls = model.calls
    else:
        model = live_model()
        print(f"=== Activity 2 LangGraph agent | live | openai/gpt-oss-120b via ChatGroq | max {MAX_STEPS} steps ===")
        out = run(a.live, model)
        calls = out["steps"]
    print(f"RESULT: stopped={out['stopped']} steps={out['steps']} tool_errors={out['tool_errors']} model_calls={calls}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
