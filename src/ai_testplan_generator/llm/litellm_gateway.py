"""LiteLLM-backed gateway.

LiteLLM speaks 100+ providers through the OpenAI-Chat schema, which is
why we picked it - the brain ends up provider-agnostic for free.

Nothing in this file is user-visible except `LiteLLMGateway`. If/when the
project standardises on LangChain ChatModels, or moves to a local
inference server, swap in a new class implementing `LLMGateway`.
"""

from __future__ import annotations

import asyncio
import json
import math
import time
from collections.abc import AsyncIterator, Sequence
from functools import lru_cache
from hashlib import sha256
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
    EmbeddingInputType,
    LLMGateway,
    LLMResponse,
    ModelRole,
    ToolCall,
)

T = TypeVar("T", bound=BaseModel)
_MAX_EMBEDDING_BATCH_SIZE = 100


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
        self._embedding_window_started_at = 0.0
        self._embedding_window_count = 0

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

        import time as _time

        from ai_testplan_generator.telemetry.otel import get_tracer as _get_tracer

        _tracer = _get_tracer(__name__)
        _t0 = _time.perf_counter()

        with _tracer.start_as_current_span("llm.complete") as _span:
            _span.set_attribute("llm.model", resolved_model)
            _span.set_attribute("llm.role", str(role))
            async for attempt in self._retryer():
                with attempt:
                    raw = await self._litellm.acompletion(**payload)
            resp = self._normalise_response(raw, resolved_model)
            _span.set_attribute("llm.input_tokens", resp.input_tokens)
            _span.set_attribute("llm.output_tokens", resp.output_tokens)

        _elapsed = _time.perf_counter() - _t0

        # Prometheus metrics
        try:
            from ai_testplan_generator.telemetry import metrics as _m

            if _m._registry is not None:
                _m.llm_calls_total().labels(
                    model=resp.model, role=str(role), outcome="success"
                ).inc()
                _m.llm_tokens_total().labels(
                    model=resp.model, role=str(role), direction="input"
                ).inc(resp.input_tokens)
                _m.llm_tokens_total().labels(
                    model=resp.model, role=str(role), direction="output"
                ).inc(resp.output_tokens)
                _m.llm_latency_seconds().labels(
                    model=resp.model, role=str(role)
                ).observe(_elapsed)
        except Exception:  # noqa: BLE001
            pass

        # Fire-and-forget cost tracking
        if self._settings.cost_tracking_enabled:
            try:
                import asyncio as _asyncio

                import structlog.contextvars as _sc_ctx

                from ai_testplan_generator.telemetry.cost import record_usage as _record_usage

                _ctx = _sc_ctx.get_contextvars()
                _sid = _ctx.get("session_id")
                _pid = _ctx.get("project_id")
                _uid = _ctx.get("user_id")
                _asyncio.create_task(
                    _record_usage(
                        self._settings.app_db_path,
                        session_id=str(_sid) if _sid is not None else None,
                        project_id=str(_pid) if _pid is not None else None,
                        user_id=str(_uid) if _uid is not None else None,
                        model=resp.model,
                        role=str(role),
                        input_tokens=resp.input_tokens,
                        output_tokens=resp.output_tokens,
                    )
                )
            except Exception:  # noqa: BLE001
                pass

        return resp

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
        response_format = {"type": "json_object"}

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

    async def embed(
        self,
        texts: Sequence[str],
        *,
        model: str | None = None,
        input_type: EmbeddingInputType = "passage",
    ) -> list[list[float]]:
        resolved_model = model or self._settings.models.embedding
        if resolved_model in {"local/hash", "local/deterministic", "mock-model"}:
            return self._local_hash_embeddings(texts)
        vectors: list[list[float]] = []
        for batch in self._embedding_batches(texts, model=resolved_model):
            await self._throttle_embedding_batch(len(batch))
            async for attempt in self._retryer():
                with attempt:
                    if self._is_nvidia_embedding_model(resolved_model):
                        vectors.extend(
                            await self._nvidia_embeddings(
                                batch,
                                model=resolved_model,
                                input_type=input_type,
                            )
                        )
                    else:
                        raw = await self._litellm.aembedding(
                            model=resolved_model,
                            input=batch,
                        )
                        vectors.extend(d["embedding"] for d in raw["data"])
        return vectors

    def _embedding_batches(self, texts: Sequence[str], *, model: str) -> list[list[str]]:
        items = list(texts)
        batch_size = _MAX_EMBEDDING_BATCH_SIZE
        if self._is_nvidia_embedding_model(model):
            batch_size = min(batch_size, max(1, self._settings.nvidia_embedding_batch_size))
        if self._settings.embedding_rate_limit_per_minute > 0:
            batch_size = min(batch_size, self._settings.embedding_rate_limit_per_minute)
        return [
            items[i : i + batch_size]
            for i in range(0, len(items), batch_size)
        ]

    @staticmethod
    def _is_nvidia_embedding_model(model: str) -> bool:
        return model.startswith("nvidia/")

    async def _nvidia_embeddings(
        self,
        texts: Sequence[str],
        *,
        model: str,
        input_type: EmbeddingInputType,
    ) -> list[list[float]]:
        if not self._settings.nvidia_api_key:
            raise ValueError("NVIDIA_API_KEY must be set when using NVIDIA embeddings.")

        from openai import AsyncOpenAI  # noqa: PLC0415

        client = AsyncOpenAI(
            api_key=self._settings.nvidia_api_key,
            base_url=self._settings.nvidia_base_url,
        )
        response = await client.embeddings.create(
            input=list(texts),
            model=model,
            encoding_format="float",
            extra_body={
                "input_type": input_type,
                "truncate": self._settings.nvidia_embedding_truncate,
            },
            timeout=self._settings.request_timeout_s,
        )
        return [list(item.embedding) for item in response.data]

    async def _throttle_embedding_batch(self, batch_size: int) -> None:
        limit = self._settings.embedding_rate_limit_per_minute
        if limit <= 0:
            return

        now = time.monotonic()
        elapsed = now - self._embedding_window_started_at
        if self._embedding_window_started_at == 0.0 or elapsed >= 60:
            self._embedding_window_started_at = now
            self._embedding_window_count = 0
            elapsed = 0.0

        if self._embedding_window_count + batch_size > limit:
            await asyncio.sleep(max(60.0 - elapsed, 0.0) + 0.25)
            self._embedding_window_started_at = time.monotonic()
            self._embedding_window_count = 0

        self._embedding_window_count += batch_size

    def _local_hash_embeddings(self, texts: Sequence[str]) -> list[list[float]]:
        """Deterministic local embeddings for tests and offline demos.

        These vectors are not semantic embeddings. They exist so ingestion,
        storage, and traceability flows can be exercised without a live
        embedding provider.
        """
        dim = self._settings.qdrant_embedding_dim
        vectors: list[list[float]] = []
        for text in texts:
            values: list[float] = []
            seed = text.encode("utf-8", errors="ignore") or b" "
            counter = 0
            while len(values) < dim:
                digest = sha256(seed + counter.to_bytes(4, "big")).digest()
                values.extend((byte / 127.5) - 1.0 for byte in digest)
                counter += 1
            vec = values[:dim]
            norm = math.sqrt(sum(v * v for v in vec)) or 1.0
            vectors.append([v / norm for v in vec])
        return vectors

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
