"""Provider-agnostic LLM gateway protocol.

Agents depend on this protocol, never on a concrete SDK. Swap the
implementation (LiteLLM, LangChain ChatModels, a local vLLM server, a
mock for tests) without touching any agent.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Sequence
from typing import Any, Literal, Protocol, TypeVar, runtime_checkable

from pydantic import BaseModel, Field

ModelRole = Literal["smart", "balanced", "fast"]
"""Semantic tier - the gateway maps this to an actual model id."""

Role = Literal["system", "user", "assistant", "tool"]


class ChatMessage(BaseModel):
    role: Role
    content: str
    name: str | None = None
    tool_call_id: str | None = None
    # Opaque metadata used by some providers (cache hints, image parts, ...).
    extra: dict[str, Any] = Field(default_factory=dict)


class ToolCall(BaseModel):
    id: str
    name: str
    arguments: dict[str, Any]


class LLMResponse(BaseModel):
    text: str
    tool_calls: list[ToolCall] = Field(default_factory=list)
    model: str
    input_tokens: int = 0
    output_tokens: int = 0
    finish_reason: str | None = None
    # Raw provider payload for debugging / advanced use.
    raw: dict[str, Any] = Field(default_factory=dict)


T = TypeVar("T", bound=BaseModel)


@runtime_checkable
class LLMGateway(Protocol):
    """The only LLM surface the brain depends on."""

    async def complete(
        self,
        messages: Sequence[ChatMessage],
        *,
        role: ModelRole = "balanced",
        model: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
        tools: Sequence[dict[str, Any]] | None = None,
        response_format: dict[str, Any] | None = None,
        stop: Sequence[str] | None = None,
    ) -> LLMResponse: ...

    async def complete_structured(
        self,
        messages: Sequence[ChatMessage],
        schema: type[T],
        *,
        role: ModelRole = "balanced",
        model: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> T:
        """Force structured JSON output conforming to a Pydantic schema."""
        ...

    async def stream(
        self,
        messages: Sequence[ChatMessage],
        *,
        role: ModelRole = "balanced",
        model: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> AsyncIterator[str]: ...

    async def embed(self, texts: Sequence[str], *, model: str | None = None) -> list[list[float]]:
        ...
