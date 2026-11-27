"""Deterministic guardrail tests for the IT Helpdesk agent (scripted mock model, no API calls)."""

from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from lab_it_helpdesk.agent import HelpdeskAgent
from lab_it_helpdesk.approval import ScriptedApprover
from lab_it_helpdesk.backend import MockITBackend
from lab_it_helpdesk.executor import GuardedExecutor, Session
from lab_it_helpdesk.models import ModelTurn, ScriptedModel, ToolCall
from lab_it_helpdesk.schemas import CreateTicketInput, Permission, ResetPasswordInput
from lab_it_helpdesk.tools import TOOLS
from lab_it_helpdesk.trajectory import TrajectoryLogger


def call(name, args, i=1):
    return ModelTurn(tool_calls=[ToolCall(f"c{i}", name, json.dumps(args) if isinstance(args, dict) else args)])


def final(text):
    return ModelTurn(text=text)


def run(turns, approvals=(), faults=None, granted=None, max_steps=6, tmp_path=None):
    backend = MockITBackend(faults=dict(faults or {}))
    log = TrajectoryLogger("T", tmp_path / "t.jsonl" if tmp_path else None)
    session = Session("jsmith", frozenset(granted)) if granted else Session("jsmith")
    ex = GuardedExecutor(backend, session, ScriptedApprover(list(approvals)), log)
    result = HelpdeskAgent(ScriptedModel(turns), ex, max_steps=max_steps).run("test request")
    return result, backend, log


RESET = {"username": "jsmith", "reason": "locked out after failed logins"}


# ------------------------------------------------------------------ tool design
def test_permission_levels():
    assert TOOLS["check_ticket"].permission is Permission.READ
    assert TOOLS["reset_password"].permission is Permission.WRITE
    assert TOOLS["create_ticket"].permission is Permission.WRITE


def test_schemas_reject_bad_input():
    with pytest.raises(ValidationError):
        ResetPasswordInput(username="J Smith!", reason="x")
    with pytest.raises(ValidationError):
        CreateTicketInput(title="t", description="short", priority="urgent", requester="jsmith")
    with pytest.raises(ValidationError):
        ResetPasswordInput(username="jsmith", reason="valid reason", is_admin=True)  # extra field forbidden


def test_json_schema_exposes_permission_and_types():
    fn = TOOLS["create_ticket"].json_schema()["function"]
    assert fn["description"].startswith("[WRITE]")
    assert fn["parameters"]["properties"]["priority"]["enum"] == ["low", "medium", "high"]
    assert fn["parameters"]["additionalProperties"] is False


# ------------------------------------------------------------------ approval
def test_write_runs_only_after_approval(tmp_path):
    r, b, log = run([call("reset_password", RESET), final("Reset link sent.")], approvals=["approved"], tmp_path=tmp_path)
    assert [w["tool"] for w in b.writes] == ["reset_password"]
    states = [e["state"] for e in log.events if e["event"].startswith("approval")]
    assert states == ["pending", "approved"]


@pytest.mark.parametrize("approvals,status", [(["denied"], "approval_denied"), ([], "approval_missing")])
def test_write_blocked_without_approval(approvals, status):
    r, b, log = run([call("reset_password", RESET), final("I could not reset it.")], approvals=approvals)
    assert b.writes == []
    assert r.tool_results[0][1].status == status and not r.tool_results[0][1].executed


def test_read_needs_no_approval():
    r, b, log = run([call("check_ticket", {"ticket_id": "TCK-1042"}), final("In progress.")])
    assert r.tool_results[0][1].ok and not log.of("approval_requested")


# ------------------------------------------------------------------ permissions and policy
def test_read_only_session_cannot_write():
    r, b, _ = run(
        [
            call(
                "create_ticket",
                {"title": "Broken mouse", "description": "Mouse does not click at all", "priority": "low", "requester": "jsmith"},
            ),
            final("Not done."),
        ],
        approvals=["approved"],
        granted={Permission.READ},
    )
    assert r.tool_results[0][1].status == "permission_denied" and b.writes == []


def test_cannot_reset_someone_elses_password_even_if_approved():
    r, b, log = run(
        [call("reset_password", {"username": "admin", "reason": "requested in ticket"}), final("No.")], approvals=["approved"]
    )
    assert r.tool_results[0][1].status == "policy_violation" and b.writes == []
    assert not log.of("approval_requested")  # blocked before a human is even asked


# ------------------------------------------------------------------ malformed calls and tool failures
@pytest.mark.parametrize(
    "args,status",
    [
        ("{not json", "malformed_call"),
        ("[1, 2]", "malformed_call"),
        ({"ticket_id": "1042"}, "invalid_arguments"),
        ({"ticket_id": "TCK-1042", "x": 1}, "invalid_arguments"),
    ],
)
def test_malformed_tool_calls(args, status):
    r, _, _ = run([call("check_ticket", args), final("Sorry.")])
    assert r.tool_results[0][1].status == status


def test_unknown_tool():
    r, _, _ = run([call("delete_user", {"username": "jsmith"}), final("Sorry.")])
    assert r.tool_results[0][1].status == "unknown_tool"


@pytest.mark.parametrize("fault,status", [("timeout", "timeout"), ("error", "tool_error"), ("malformed", "malformed_response")])
def test_tool_faults_become_error_observations(fault, status):
    r, b, _ = run([call("check_ticket", {"ticket_id": "TCK-1042"}), final("The lookup failed.")], faults={"check_ticket": fault})
    tr = r.tool_results[0][1]
    assert tr.status == status and json.loads(tr.observation())["status"] == "error"


def test_retry_after_transient_timeout_succeeds():
    r, _, _ = run(
        [
            call("check_ticket", {"ticket_id": "TCK-1042"}, 1),
            call("check_ticket", {"ticket_id": "TCK-1042"}, 2),
            final("Ticket TCK-1042 is in progress."),
        ],
        faults={"check_ticket": "timeout"},
    )
    assert [t.status for _, t in r.tool_results] == ["timeout", "ok"]


def test_timed_out_write_never_completes_later():
    import time

    r, b, _ = run(
        [call("reset_password", RESET), final("It failed.")], approvals=["approved"], faults={"reset_password": "timeout"}
    )
    time.sleep(3.3)  # longer than the mock's hang: the background call must not have written anything
    assert r.tool_results[0][1].status == "timeout" and b.writes == []


# ------------------------------------------------------------------ loop guardrails
def test_step_limit():
    r, _, log = run([call("check_ticket", {"ticket_id": "TCK-1042"})], max_steps=3)
    assert r.outcome == "step_limit" and r.steps == 3 and log.of("step_limit_reached")


def test_false_success_claim_is_corrected():
    r, b, log = run([call("reset_password", RESET), final("Your password has been reset successfully!")], approvals=["denied"])
    assert r.corrected and "NOT completed" in r.final_answer and log.of("final_answer_corrected")


def test_injected_instructions_cannot_cause_unauthorised_writes():
    """A model that obeys the injected text is still stopped: scope policy and the human approval gate."""
    turns = [
        call("check_ticket", {"ticket_id": "TCK-1077"}, 1),
        call("reset_password", {"username": "admin", "reason": "ticket says so"}, 2),
        call(
            "create_ticket",
            {
                "title": "Grant admin rights",
                "description": "Give mallory domain admin",
                "priority": "high",
                "requester": "jsmith",
            },
            3,
        ),
        final("Done as the ticket asked."),
    ]
    r, b, log = run(turns, approvals=["denied"])
    assert [t.status for _, t in r.tool_results] == ["ok", "policy_violation", "approval_denied"]
    assert b.writes == []
    assert "untrusted_tool_output" in r.tool_results[0][1].observation()


def test_trajectory_file_has_required_fields(tmp_path):
    run([call("reset_password", RESET), final("Sent.")], approvals=["approved"], tmp_path=tmp_path)
    events = [json.loads(line) for line in (tmp_path / "t.jsonl").read_text().splitlines()]
    tc = next(e for e in events if e["event"] == "tool_call")
    for key in ("scenario_id", "step", "tool", "validated_arguments", "permission", "approval_status", "status", "output"):
        assert key in tc
    assert events[-1]["event"] == "final" and "outcome" in events[-1]
