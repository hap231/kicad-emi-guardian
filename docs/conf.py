"""Sphinx configuration for the bilingual EMI Guardian documentation site."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

project = "EMI Guardian"
author = "Ryo Nishikawa and EMI Guardian contributors"

extensions = ["myst_parser"]
source_suffix = {".rst": "restructuredtext", ".md": "markdown"}
master_doc = "index"
exclude_patterns = ["_build"]
html_theme = "furo"
html_title = "EMI Guardian"
html_baseurl = "https://hap231.github.io/kicad-emi-guardian/"
html_static_path = ["_static"]
html_css_files = ["site.css"]
html_js_files = ["language-switcher.js"]
html_favicon = str(ROOT / "resources" / "icon.png")
html_theme_options = {
    "light_css_variables": {
        "color-brand-primary": "#2563eb",
        "color-brand-content": "#1d4ed8",
        "color-api-name": "#1e40af",
    },
    "dark_css_variables": {
        "color-brand-primary": "#93c5fd",
        "color-brand-content": "#60a5fa",
        "color-api-name": "#bfdbfe",
    },
    "source_repository": "https://github.com/hap231/kicad-emi-guardian/",
    "source_branch": "main",
    "source_directory": "docs/",
}
myst_enable_extensions = ["colon_fence", "deflist"]
