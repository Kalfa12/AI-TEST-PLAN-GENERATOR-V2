"""Interactive copilot demo.

Run:
    pip install -e .
    export ANTHROPIC_API_KEY=...     # or any other provider
    python examples/run_interactive.py path/to/spec.pdf
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

from ai_testplan_generator import Brain, InteractivePipeline


async def main(paths: list[Path]) -> None:
    brain = Brain.build()
    kb = brain.project_kb("demo_project")
    for p in paths:
        await kb.ingest(p)

    chat = InteractivePipeline(brain)
    session = chat.session(project_id="demo_project")

    # Simple REPL - replace with a websocket loop in production.
    print("Copilot ready. Type 'quit' to exit.\n")
    while True:
        try:
            user = input("you > ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if not user or user.lower() in {"quit", "exit"}:
            break
        reply = await session.ask(user)
        print(f"bot > {reply.assistant_message}")
        if reply.pending_action:
            print(f"     (pending action awaiting confirmation: {reply.pending_action})")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: run_interactive.py <doc> [<doc> ...]", file=sys.stderr)
        sys.exit(2)
    asyncio.run(main([Path(p) for p in sys.argv[1:]]))
