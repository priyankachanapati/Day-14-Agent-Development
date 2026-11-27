"""Tool registry: each tool = name, purpose, typed input/output schema, permission level, timeout."""

from __future__ import annotations

from dataclasses import dataclass

from pydantic import BaseModel

from .schemas import (
    CheckTicketInput,
    CheckTicketOutput,
    CreateTicketInput,
    CreateTicketOutput,
    Permission,
    ResetPasswordInput,
    ResetPasswordOutput,
)


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    input_model: type[BaseModel]
    output_model: type[BaseModel]
    permission: Permission
    timeout_s: float = 1.0

    def json_schema(self) -> dict:
        """OpenAI-style function definition generated from the Pydantic input model."""
        schema = self.input_model.model_json_schema()
        schema.pop("title", None)
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": f"[{self.permission.value.upper()}] {self.description}",
                "parameters": schema,
            },
        }


TOOLS: dict[str, ToolSpec] = {
    t.name: t
    for t in (
        ToolSpec(
            "reset_password",
            "Send a password-reset link to the user's registered email. Changes account state, so it "
            "always requires explicit human approval. Users may only reset their own account.",
            ResetPasswordInput,
            ResetPasswordOutput,
            Permission.WRITE,
        ),
        ToolSpec(
            "check_ticket",
            "Look up the status of an existing IT ticket by its ID (format TCK-0000). Read-only.",
            CheckTicketInput,
            CheckTicketOutput,
            Permission.READ,
        ),
        ToolSpec(
            "create_ticket",
            "Open a new IT support ticket. Changes state, so it always requires explicit human approval.",
            CreateTicketInput,
            CreateTicketOutput,
            Permission.WRITE,
        ),
    )
}
