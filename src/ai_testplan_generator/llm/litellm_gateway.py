"""LiteLLM-backed gateway.

LiteLLM speaks 100+ providers through the OpenAI-Chat schema, which is
why we picked it - the brain ends up provider-agnostic for free.

Nothing in this file is user-visible except `LiteLLMGateway`. If/when the
project standardises on LangChain ChatModels, or moves to a local
inference server, swap in a new class implementing `LLMGateway`.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator, Sequence
from functools import lru_cache
from typing import Any, TypeVar, cast

from pydantic import BaseModel
from tenacity import (
    AsyncRetrying,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from ai_testplan_generator.config import Settings, get_settings
from ai_testplan_generator.llm.base import (
    ChatMessage,
    LLMGateway,
    LLMResponse,
    ModelRole,
    ToolCall,
)

T = TypeVar("T", bound=BaseModel)


class LiteLLMGateway(LLMGateway):
    """Thin, typed wrapper around `litellm.acompletion` + `litellm.aembedding`.

    Responsibilities:
      - resolve semantic role ("smart" / "balanced" / "fast") to a concrete
        provider-qualified model id;
      - retry transient failures with exponential backoff;
      - coerce structured outputs into Pydantic models;
      - normalise the wildly-varying provider payloads to `LLMResponse`.
    """

    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()
        # Import lazily so `import ai_testplan_generator` doesn't force litellm.
        import litellm  # noqa: PLC0415

        litellm.drop_params = True  # quietly drop params unsupported by the target provider
        litellm.telemetry = False
        self._litellm = litellm

    # -- model tier resolution -------------------------------------------------

    def _resolve_model(self, role: ModelRole, override: str | None) -> str:
        if override:
            return override
        tier = self._settings.models
        return {"smart": tier.smart, "balanced": tier.balanced, "fast": tier.fast}[role]

    # -- message formatting ----------------------------------------------------

    @staticmethod
    def _to_openai_messages(messages: Sequence[ChatMessage]) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for m in messages:
            payload: dict[str, Any] = {"role": m.role, "content": m.content}
            if m.name:
                payload["name"] = m.name
            if m.tool_call_id:
                payload["tool_call_id"] = m.tool_call_id
            if m.extra:
                payload.update(m.extra)
            out.append(payload)
        return out

    # -- retry policy ----------------------------------------------------------

    def _retryer(self) -> AsyncRetrying:
        # litellm exceptions (rate limit / timeout / api connection) all inherit
        # from the base `Exception`; we catch broadly and let tenacity stop
        # after max_retries - the gateway is called from agents that surface
        # the error to the supervisor anyway.
        return AsyncRetrying(
            reraise=True,
            stop=stop_after_attempt(self._settings.max_retries),
            wait=wait_exponential(multiplier=1, min=1, max=20),
            retry=retry_if_exception_type(Exception),
        )

    # -- completion ------------------------------------------------------------

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
    ) -> LLMResponse:
        resolved_model = self._resolve_model(role, model)
        payload: dict[str, Any] = {
            "model": resolved_model,
            "messages": self._to_openai_messages(messages),
            "temperature": (
                temperature if temperature is not None else self._settings.default_temperature
            ),
            "timeout": self._settings.request_timeout_s,
        }
        if max_tokens is not None:
            payload["max_tokens"] = max_tokens
        if tools:
            payload["tools"] = list(tools)
        if response_format:
            payload["response_format"] = response_format
        if stop:
            payload["stop"] = list(stop)

        async for attempt in self._retryer():
            with attempt:
                raw = await self._litellm.acompletion(**payload)
        return self._normalise_response(raw, resolved_model)

    # -- structured output -----------------------------------------------------

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
        json_schema = schema.model_json_schema()
        # OpenAI / Azure / many compatible endpoints accept `response_format`;
        # providers that don't support JSON mode get `drop_params` treatment
        # and fall back to prompt-steering + tolerant parsing below.
        response_format = {
            "type": "json_schema",
            "json_schema": {"name": schema.__name__, "schema": json_schema, "strict": True},
        }

        # Belt-and-braces: inject a system directive about the required shape.
        steered: list[ChatMessage] = list(messages)
        steered.append(
            ChatMessage(
                role="system",
                content=(
                    "Respond with a single JSON object that strictly conforms to this JSON "
                    f"schema. Do not wrap it in prose or code fences. Schema: {json.dumps(json_schema)}"
                ),
            )
        )

        resp = await self.complete(
            steered,
            role=role,
            model=model,
            temperature=temperature if temperature is not None else 0.0,
            max_tokens=max_tokens,
            response_format=response_format,
        )
        return self._parse_structured(resp.text, schema)

    @staticmethod
    def _parse_structured(text: str, schema: type[T]) -> T:
        """Parse tolerantly - some providers wrap JSON in markdown fences."""
        candidate = text.strip()
        if candidate.startswith("```"):
            # Strip the first fence line and the trailing fence.
            candidate = candidate.split("\n", 1)[1] if "\n" in candidate else candidate
            if candidate.endswith("```"):
                candidate = candidate.rsplit("```", 1)[0]
            candidate = candidate.strip()
            # Drop optional "json" language tag.
            if candidate.lower().startswith("json\n"):
                candidate = candidate[5:]
        try:
            data = json.loads(candidate)
        except json.JSONDecodeError as e:
            # Last-ditch: find the first {...} balanced block.
            start = candidate.find("{")
            end = candidate.rfind("}")
            if start != -1 and end != -1 and end > start:
                data = json.loads(candidate[start : end + 1])
            else:
                raise ValueError(f"LLM did not return valid JSON: {e}\n---\n{text[:400]}") from e
        return schema.model_validate(data)

    # -- streaming -------------------------------------------------------------

    async def stream(
        self,
        messages: Sequence[ChatMessage],
        *,
        role: ModelRole = "balanced",
        model: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> AsyncIterator[str]:
        resolved_model = self._resolve_model(role, model)
        payload: dict[str, Any] = {
            "model": resolved_model,
            "messages": self._to_openai_messages(messages),
            "temperature": (
                temperature if temperature is not None else self._settings.default_temperature
            ),
            "stream": True,
            "timeout": self._settings.request_timeout_s,
        }
        if max_tokens is not None:
            payload["max_tokens"] = max_tokens

        stream = await self._litellm.acompletion(**payload)
        async for chunk in stream:
            delta = self._chunk_text(chunk)
            if delta:
                yield delta

    @staticmethod
    def _chunk_text(chunk: Any) -> str:
        try:
            choices = chunk["choices"] if isinstance(chunk, dict) else chunk.choices
            first = choices[0]
            delta = first["delta"] if isinstance(first, dict) else first.delta
            content = delta["content"] if isinstance(delta, dict) else getattr(delta, "content", None)
            return content or ""
        except (KeyError, IndexError, AttributeError):
            return ""

    # -- embeddings ------------------------------------------------------------

    async def embed(self, texts: Sequence[str], *, model: str | None = None) -> list[list[float]]:
        resolved_model = model or self._settings.models.embedding
        async for attempt in self._retryer():
            with attempt:
                raw = await self._litellm.aembedding(model=resolved_model, input=list(texts))
        return [d["embedding"] for d in raw["data"]]

    # -- normalisation ---------------------------------------------------------

    @staticmethod
    def _normalise_response(raw: Any, model_id: str) -> LLMResponse:
        # LiteLLM returns a ModelResponse that supports both attribute and
        # dict-style access. We take the dict view where available so the
        # code is provider-agnostic.
        d: dict[str, Any] = raw if isinstance(raw, dict) else raw.model_dump()
        choice = d.get("choices", [{}])[0]
        message = choice.get("message", {}) or {}
        text = message.get("content") or ""
        tool_calls_raw = message.get("tool_calls") or []
        tool_calls: list[ToolCall] = []
        for tc in tool_calls_raw:
            fn = tc.get("function", {}) or {}
            args_raw = fn.get("arguments", "{}")
            try:
                args = json.loads(args_raw) if isinstance(args_raw, str) else dict(args_raw)
            except json.JSONDecodeError:
                args = {"_raw": args_raw}
            tool_calls.append(
                ToolCall(
                    id=tc.get("id", ""),
                    name=fn.get("name", ""),
                    arguments=args,
                )
            )
        usage = d.get("usage") or {}
        return LLMResponse(
            text=text,
            tool_calls=tool_calls,
            model=d.get("model") or model_id,
            input_tokens=int(usage.get("prompt_tokens") or 0),
            output_tokens=int(usage.get("completion_tokens") or 0),
            finish_reason=choice.get("finish_reason"),
            raw=cast(dict[str, Any], d),
        )


@lru_cache(maxsize=1)
def get_gateway() -> LiteLLMGateway:
    return LiteLLMGateway()
