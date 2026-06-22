"""Compatibility shim for local development imports.

This keeps `ai_testplan_generator` importable from the repository root and
ensures the `src/` tree is used even when an older installed copy exists in the
current Python environment.
"""

from __future__ import annotations

from pathlib import Path
from pkgutil import extend_path

__path__ = extend_path(__path__, __name__)  # type: ignore[name-defined]

_src_package = Path(__file__).resolve().parent.parent / "src" / "ai_testplan_generator"
if _src_package.is_dir():
    __path__.append(str(_src_package))
