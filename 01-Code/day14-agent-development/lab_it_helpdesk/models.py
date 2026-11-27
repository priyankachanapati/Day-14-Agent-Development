"""Model clients. The agent only needs: messages + tool schemas in -> text and/or tool calls out.

* GroqModel     - real LLM (openai/gpt-oss-120b on Groq, temperature 0) with native tool calling.
* ScriptedModel - deterministic stand-in for unit tests: replays pre-written turns, no API call.
Neither client asks for or stores the model's private reasoning; only the visible reply and tool calls.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field


@dataclass
class ToolCall:
    id: str
    name: str
    arguments: object  # raw: usually a JSON string from the model; validated later by the executor


@dataclass
class ModelTurn:
    text: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)
    usage: dict = field(default_factory=dict)


class ModelError(RuntimeError):
    """The model API failed or produced an unusable response."""


class ScriptedModel:
    """Replays turns. Each item is a ModelTurn; once exhausted it keeps returning the last turn."""

    name = "scripted-mock"

    def __init__(self, turns: list[ModelTurn]):
        self.turns = list(turns)
        self.calls = 0

    def next(self, messages: list[dict], tools: list[dict]) -> ModelTurn:
        self.calls += 1
        return self.turns.pop(0) if len(self.turns) > 1 else self.turns[0]


class GroqModel:
    def __init__(self, model: str = "openai/gpt-oss-120b", temperature: float = 0.0):
        from dotenv import load_dotenv
        from groq import Groq

        load_dotenv()
        if not os.getenv("GROQ_API_KEY"):
            raise ModelError("GROQ_API_KEY is not set (create .env from .env.example)")
        self.client = Groq(max_retries=2, timeout=60)
        self.name = model
        self.temperature = temperature
        self.calls = 0

    def next(self, messages: list[dict], tools: list[dict]) -> ModelTurn:
        self.calls += 1
        try:
            resp = self.client.chat.completions.create(
                model=self.name,
                messages=messages,
                tools=tools,
                tool_choice="auto",
                temperature=self.temperature,
                max_completion_tokens=1024,
            )
        except Exception as exc:  # noqa: BLE001 - API/rate-limit/bad tool-call generation
            raise ModelError(f"{type(exc).__name__}: {str(exc)[:300]}") from exc
        msg = resp.choices[0].message
        calls = [ToolCall(tc.id, tc.function.name, tc.function.arguments) for tc in (msg.tool_calls or [])]
        usage = {"prompt_tokens": resp.usage.prompt_tokens, "completion_tokens": resp.usage.completion_tokens}
        return ModelTurn(text=msg.content or "", tool_calls=calls, usage=usage)


def assistant_message(turn: ModelTurn) -> dict:
    """The assistant turn as it is sent back to the model (OpenAI chat format)."""
    msg: dict = {"role": "assistant", "content": turn.text or ""}
    if turn.tool_calls:
        msg["tool_calls"] = [
            {
                "id": c.id,
                "type": "function",
                "function": {
                    "name": c.name,
                    "arguments": c.arguments if isinstance(c.arguments, str) else json.dumps(c.arguments),
                },
            }
            for c in turn.tool_calls
        ]
    return msg
