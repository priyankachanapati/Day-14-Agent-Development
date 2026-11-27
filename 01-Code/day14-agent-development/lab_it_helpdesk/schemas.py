"""Typed input/output schemas for the three mock IT tools (Pydantic v2).

Every tool argument is validated *before* execution and every tool result is validated *after*
execution, so a malformed tool call or a malformed tool response is caught and reported as an error
instead of silently propagating.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

USERNAME = r"^[a-z][a-z0-9._-]{2,31}$"  # e.g. "jsmith", "a.kumar"
TICKET_ID = r"^TCK-\d{4}$"  # e.g. "TCK-1042"


class Permission(StrEnum):
    """Permission level of a tool. READ tools never change state; WRITE tools always need approval."""

    READ = "read"
    WRITE = "write"


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


# ------------------------------------------------------------------ reset_password (WRITE)
class ResetPasswordInput(Strict):
    username: str = Field(pattern=USERNAME, description="Account to reset (lowercase username).")
    reason: str = Field(min_length=5, max_length=200, description="Why the reset is needed.")


class ResetPasswordOutput(Strict):
    status: Literal["reset_link_sent"]
    username: str = Field(pattern=USERNAME)
    reset_id: str = Field(pattern=r"^RST-\d{4}$")
    delivery: Literal["registered_email"]


# ------------------------------------------------------------------ check_ticket (READ)
class CheckTicketInput(Strict):
    ticket_id: str = Field(pattern=TICKET_ID, description="Ticket identifier, format TCK-0000.")


class CheckTicketOutput(Strict):
    ticket_id: str = Field(pattern=TICKET_ID)
    title: str
    status: Literal["open", "in_progress", "resolved", "closed"]
    priority: Literal["low", "medium", "high"]
    requester: str = Field(pattern=USERNAME)
    last_update: str


# ------------------------------------------------------------------ create_ticket (WRITE)
class CreateTicketInput(Strict):
    title: str = Field(min_length=5, max_length=120, description="One-line summary of the problem.")
    description: str = Field(min_length=10, max_length=2000, description="Details of the problem.")
    priority: Literal["low", "medium", "high"] = Field(description="Business impact.")
    requester: str = Field(pattern=USERNAME, description="Username of the person reporting it.")


class CreateTicketOutput(Strict):
    ticket_id: str = Field(pattern=TICKET_ID)
    status: Literal["open"]
    priority: Literal["low", "medium", "high"]
