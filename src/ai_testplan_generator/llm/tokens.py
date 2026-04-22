"""Tokenisation helpers.

Works provider-agnostically: tries `litellm.token_counter` first (which
picks the right tokenizer for the configured model), falls back to a
character-heuristic for offline / test contexts.
"""

from __future__ import annotations


def count_tokens(text: str, model: str | None = None) -> int:
    if not text:
        return 0
    try:  # pragma: no cover - depends on optional runtime
        import litellm  # noqa: PLC0415

        return int(litellm.token_counter(model=model or "gpt-4o", text=text))
    except Exception:
        # 4 chars/token is a classic, well-calibrated approximation.
        return max(1, len(text) // 4)
