"""Human approval for write actions.

States: pending (request raised) -> approved | denied | no_response.
Only an explicit "approved" decision lets a write run. "denied" and "no_response" (missing approval)
both block it. Every request and decision is written to the trajectory log by the executor.

Two approvers:
* InteractiveApprover - asks a real person at the terminal (y/n).
* ScriptedApprover    - for automated scenario tests: the scenario states the human's decision up
                        front (approve / deny / no response). It is never a silent default: the
                        decision comes from the scenario definition and is logged with its source.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal, Protocol

Decision = Literal["approved", "denied", "no_response"]


@dataclass(frozen=True)
class ApprovalRequest:
    tool: str
    arguments: dict
    requested_by: str
    summary: str


@dataclass(frozen=True)
class ApprovalDecision:
    status: Decision
    approver: str
    note: str
    decided_utc: str


class Approver(Protocol):
    def decide(self, request: ApprovalRequest) -> ApprovalDecision: ...


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


class ScriptedApprover:
    """Returns pre-declared human decisions in order; 'no_response' once the script is exhausted."""

    def __init__(self, decisions: list[Decision], approver: str = "scenario-script (simulated human reviewer)"):
        self._decisions = list(decisions)
        self.approver = approver
        self.requests: list[ApprovalRequest] = []

    def decide(self, request: ApprovalRequest) -> ApprovalDecision:
        self.requests.append(request)
        status: Decision = self._decisions.pop(0) if self._decisions else "no_response"
        return ApprovalDecision(status, self.approver, "decision declared in scenario definition", _now())


class InteractiveApprover:
    """Asks the operator at the terminal. Anything other than 'y'/'yes' is a denial; EOF = no response."""

    def __init__(self, approver: str = "terminal operator"):
        self.approver = approver

    def decide(self, request: ApprovalRequest) -> ApprovalDecision:
        print(f"\n  APPROVAL REQUIRED  {request.summary}")
        print(f"  tool={request.tool} args={request.arguments} requested_by={request.requested_by}")
        try:
            answer = input("  Approve this write action? [y/N]: ").strip().lower()
        except EOFError:
            return ApprovalDecision("no_response", self.approver, "no input received", _now())
        status: Decision = "approved" if answer in {"y", "yes"} else "denied"
        return ApprovalDecision(status, self.approver, f"operator typed {answer!r}", _now())
