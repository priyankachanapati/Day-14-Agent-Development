"""Activity 1 - tests of the framework-free agent loop (scripted model, no API calls)."""

from activity1_agent_loop.agent_loop import DEMOS, MAX_STEPS, ScriptedModel, call, run_agent, run_tool


def demo(name):
    question, replies = DEMOS[name]
    model = ScriptedModel(list(replies))
    return run_agent(question, model), model


def test_successful_tool_call_then_final_answer():
    out, model = demo("success")
    assert out["stopped"] == "final_answer" and out["steps"] == 2 and model.calls == 2
    assert "in progress" in out["answer"] and out["tool_errors"] == 0


def test_tool_error_is_observed_and_reported():
    out, _ = demo("tool-error")
    assert out["tool_errors"] == 1 and "could not" in out["answer"]


def test_stops_after_max_steps():
    out, model = demo("max-steps")
    assert MAX_STEPS == 5
    assert out["stopped"] == "max_steps" and model.calls == 5 and "No result is claimed" in out["answer"]


def test_unknown_tool_and_bad_arguments_become_observations():
    assert "unknown tool" in run_tool("delete_everything", "{}")["error"]
    assert "bad arguments" in run_tool("check_ticket", "{not json")["error"]
    assert "bad arguments" in run_tool("check_ticket", '{"wrong": 1}')["error"]
    assert "not found" in run_tool("check_ticket", '{"ticket_id": "TCK-0000"}')["error"]


def test_observation_is_passed_back_to_the_model():
    seen = []

    class Spy(ScriptedModel):
        def __call__(self, messages):
            seen.append([m["role"] for m in messages])
            return super().__call__(messages)

    run_agent("q", Spy([call(1, "check_ticket", {"ticket_id": "TCK-1042"}), {"content": "done", "tool_calls": []}]))
    assert seen[1][-2:] == ["assistant", "tool"]  # the second model call sees the tool observation
