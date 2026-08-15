"""Sphinx configuration for the bilingual EMI Guardian documentation."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "plugin"))

project = "EMI Guardian"
author = "Ryo Nishikawa and EMI Guardian contributors"
release = "0.0.2"

extensions = [
    "myst_parser",
    "sphinx.ext.autodoc",
    "sphinx.ext.autosummary",
    "sphinx.ext.napoleon",
    "sphinx.ext.viewcode",
]
source_suffix = {".rst": "restructuredtext", ".md": "markdown"}
master_doc = "index"
exclude_patterns = ["_build", "sphinx/README.md"]
html_theme = "alabaster"
html_title = "EMI Guardian 0.0.2"
autodoc_typehints = "description"
autosummary_generate = True
napoleon_google_docstring = True
napoleon_numpy_docstring = False
myst_enable_extensions = ["colon_fence", "deflist"]
