"""Activity 2 - tests of the LangGraph port (scripted model, no API calls)."""

from langchain_core.messages import AIMessage

from activity2_langgraph.graph_agent import DEMOS, MAX_STEPS, ScriptedChatModel, build_graph, run


def demo(name):
    question, replies = DEMOS[name]
    model = ScriptedChatModel(list(replies))
    return run(question, model, verbose=False), model


def test_graph_structure_has_toolnode_and_conditional_routing():
    g = build_graph(ScriptedChatModel([AIMessage("x")])).get_graph()
    assert {"agent", "tools", "step_limit"} <= set(g.nodes)
    conditional = {(e.source, e.target) for e in g.edges if e.conditional}
    assert conditional == {("agent", "tools"), ("agent", "step_limit"), ("agent", "__end__")}
    assert ("tools", "agent") in {(e.source, e.target) for e in g.edges if not e.conditional}


def test_success_tool_call_then_final_answer():
    out, model = demo("success")
    assert out == {"answer": "Ticket TCK-1042 is in progress.", "steps": 2, "stopped": "final_answer", "tool_errors": 0}
    assert model.calls == 2


def test_tool_error_becomes_error_tool_message():
    out, _ = demo("tool-error")
    assert out["tool_errors"] == 1 and "could not" in out["answer"] and out["stopped"] == "final_answer"


def test_step_limit_routes_to_step_limit_node():
    out, model = demo("max-steps")
    assert MAX_STEPS == 5 and out["stopped"] == "max_steps" and model.calls == 5 and "No result is claimed" in out["answer"]
