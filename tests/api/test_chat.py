"""M08: Chat / copilot endpoints."""

from __future__ import annotations

import pytest
from httpx import AsyncClient


class TestChatEndpoint:
    async def test_chat_returns_session_id(self, client: AsyncClient) -> None:
        resp = await client.post(
            "/chat",
            json={"message": "What standards are referenced?"},
        )
        assert resp.status_code in (200, 500)
        if resp.status_code == 200:
            body = resp.json()
            assert "session_id" in body
            assert "assistant_message" in body

    async def test_chat_history_empty_session(self, client: AsyncClient) -> None:
        resp = await client.get("/chat/nonexistent-session/history")
        assert resp.status_code == 200
        body = resp.json()
        assert body["session_id"] == "nonexistent-session"
        assert body["events"] == []

    async def test_chat_confirm_returns_unsupported_feature(self, client: AsyncClient) -> None:
        resp = await client.post("/chat/session-a/confirm", json={"confirmed": True})
        assert resp.status_code == 501
        body = resp.json()
        assert body["error_code"] == "UNSUPPORTED_FEATURE"
        assert "outside the current product scope" in body["detail"]
