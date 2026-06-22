"""Sphinx configuration for AI Test Plan Generator documentation."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

project = "AI Test Plan Generator"
author = "Mohamed Taha El Younsi, Amine Amllal"
copyright = f"{datetime.now().year}, ENSAM Meknes"
release = "0.1.0"

extensions = [
    "myst_parser",
    "sphinx.ext.autodoc",
    "sphinx.ext.autosummary",
    "sphinx.ext.napoleon",
    "sphinx.ext.viewcode",
    "sphinxcontrib.mermaid",
]

source_suffix = {
    ".rst": "restructuredtext",
    ".md": "markdown",
}

templates_path = ["_templates"]
exclude_patterns = ["_build", "Thumbs.db", ".DS_Store"]

html_theme = "sphinx_rtd_theme"
html_static_path = ["_static"]
html_title = "AI Test Plan Generator Documentation"
html_logo = "../assets/logo-umi-ensam.png"
html_theme_options = {
    "collapse_navigation": False,
    "navigation_depth": 3,
    "sticky_navigation": True,
}

myst_enable_extensions = [
    "colon_fence",
    "deflist",
    "fieldlist",
    "linkify",
    "substitution",
    "tasklist",
]
myst_heading_anchors = 3

autosummary_generate = True
autodoc_typehints = "description"

mermaid_version = "10.9.1"

latex_engine = "xelatex"
latex_documents = [
    ("index", "ai-test-plan-generator.tex", "AI Test Plan Generator Documentation", author, "manual"),
]
