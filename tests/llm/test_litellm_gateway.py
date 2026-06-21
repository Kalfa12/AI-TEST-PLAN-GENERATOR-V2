import math
from typing import Any

import pytest

from ai_testplan_generator.config import Settings
from ai_testplan_generator.llm.litellm_gateway import LiteLLMGateway


@pytest.mark.asyncio
async def test_local_hash_embeddings_are_deterministic_and_normalized(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("LLM_MODEL_EMBEDDING", "local/hash")
    gateway = LiteLLMGateway(
        Settings(
            QDRANT_EMBEDDING_DIM=12,
        )
    )

    first = await gateway.embed(["pump pressure", "temperature alarm"])
    second = await gateway.embed(["pump pressure", "temperature alarm"])

    assert first == second
    assert len(first) == 2
    assert all(len(vector) == 12 for vector in first)
    assert first[0] != first[1]
    assert all(math.isclose(sum(value * value for value in vector), 1.0) for vector in first)


@pytest.mark.asyncio
async def test_provider_embeddings_are_batched_at_100_items() -> None:
    class FakeLiteLLM:
        def __init__(self) -> None:
            self.batch_sizes: list[int] = []

        async def aembedding(self, **payload: Any) -> dict[str, list[dict[str, list[float]]]]:
            inputs = payload["input"]
            self.batch_sizes.append(len(inputs))
            return {"data": [{"embedding": [float(len(text))]} for text in inputs]}

    gateway = LiteLLMGateway(Settings(LLM_EMBEDDING_RATE_LIMIT_PER_MINUTE=0))
    fake = FakeLiteLLM()
    gateway._litellm = fake  # type: ignore[attr-defined]

    vectors = await gateway.embed([f"text {i}" for i in range(205)], model="provider/model")

    assert fake.batch_sizes == [100, 100, 5]
    assert len(vectors) == 205
    assert vectors[0] == [6.0]
    assert vectors[-1] == [8.0]


@pytest.mark.asyncio
async def test_provider_embeddings_respect_configured_rate_limit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeLiteLLM:
        def __init__(self) -> None:
            self.batch_sizes: list[int] = []

        async def aembedding(self, **payload: Any) -> dict[str, list[dict[str, list[float]]]]:
            inputs = payload["input"]
            self.batch_sizes.append(len(inputs))
            return {"data": [{"embedding": [1.0]} for _ in inputs]}

    sleeps: list[float] = []

    async def fake_sleep(seconds: float) -> None:
        sleeps.append(seconds)

    monkeypatch.setattr("ai_testplan_generator.llm.litellm_gateway.asyncio.sleep", fake_sleep)

    gateway = LiteLLMGateway(Settings(LLM_EMBEDDING_RATE_LIMIT_PER_MINUTE=3))
    fake = FakeLiteLLM()
    gateway._litellm = fake  # type: ignore[attr-defined]

    vectors = await gateway.embed([f"text {i}" for i in range(7)], model="provider/model")

    assert fake.batch_sizes == [3, 3, 1]
    assert len(sleeps) == 2
    assert len(vectors) == 7


@pytest.mark.asyncio
async def test_nvidia_embeddings_use_openai_compatible_payload() -> None:
    captured: dict[str, Any] = {}

    class FakeEmbedding:
        def __init__(self, value: float) -> None:
            self.embedding = [value]

    class FakeEmbeddings:
        async def create(self, **payload: Any) -> Any:
            captured.update(payload)
            return type(
                "EmbeddingResponse",
                (),
                {"data": [FakeEmbedding(0.25), FakeEmbedding(0.75)]},
            )()

    class FakeClient:
        def __init__(self) -> None:
            self.embeddings = FakeEmbeddings()

    class TestGateway(LiteLLMGateway):
        async def _nvidia_embeddings(
            self,
            texts: Any,
            *,
            model: str,
            input_type: str,
        ) -> list[list[float]]:
            response = await FakeClient().embeddings.create(
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

    gateway = TestGateway(
        Settings(
            LLM_MODEL_EMBEDDING="nvidia/nv-embed-v1",
            NVIDIA_API_KEY="test-key",
            NVIDIA_EMBEDDING_BATCH_SIZE=50,
            NVIDIA_EMBEDDING_TRUNCATE="NONE",
        )
    )

    vectors = await gateway.embed(["stored chunk", "stored requirement"], input_type="passage")

    assert vectors == [[0.25], [0.75]]
    assert captured["model"] == "nvidia/nv-embed-v1"
    assert captured["input"] == ["stored chunk", "stored requirement"]
    assert captured["encoding_format"] == "float"
    assert captured["extra_body"] == {"input_type": "passage", "truncate": "NONE"}


@pytest.mark.asyncio
async def test_nvidia_embeddings_are_batched_at_configured_size() -> None:
    class TestGateway(LiteLLMGateway):
        async def _nvidia_embeddings(
            self,
            texts: Any,
            *,
            model: str,
            input_type: str,
        ) -> list[list[float]]:
            batches.append(len(texts))
            return [[1.0] for _ in texts]

    batches: list[int] = []
    gateway = TestGateway(
        Settings(
            LLM_MODEL_EMBEDDING="nvidia/nv-embed-v1",
            NVIDIA_API_KEY="test-key",
            NVIDIA_EMBEDDING_BATCH_SIZE=50,
            LLM_EMBEDDING_RATE_LIMIT_PER_MINUTE=0,
        )
    )

    vectors = await gateway.embed([f"text {i}" for i in range(121)])

    assert batches == [50, 50, 21]
    assert len(vectors) == 121
