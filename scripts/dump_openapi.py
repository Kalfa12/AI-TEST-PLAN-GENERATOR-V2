"""Dump the FastAPI OpenAPI schema to a JSON file.

Used by the frontend `npm run gen:openapi` script to produce an
input file for openapi-typescript-codegen without requiring a running
HTTP server.

Usage:
    python scripts/dump_openapi.py [output_path]
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

# Make the `src/` layout importable when run from the frontend/ directory.
_REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO_ROOT / "src"))

from ai_testplan_generator.api.app import create_app  # noqa: E402


def main() -> int:
    output = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("openapi.json")
    if not output.is_absolute():
        output = Path.cwd() / output
    schema = create_app().openapi()
    output.write_text(json.dumps(schema, indent=2), encoding="utf-8")
    print(f"wrote {output} ({output.stat().st_size} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
