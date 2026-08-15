#!/usr/bin/env python3
"""Build standalone Japanese and English EMI Guardian user manuals."""

from __future__ import annotations

import argparse
import re
import shutil
import unicodedata
from html import escape
from pathlib import Path

from markdown_it import MarkdownIt
from markdown_it.token import Token

ROOT = Path(__file__).resolve().parents[1]

MANUALS = (
    {
        "language": "ja",
        "title": "EMI Guardian 取扱説明書",
        "source": ROOT / "docs" / "ja" / "guide" / "user-manual.md",
        "html_name": "EMI-Guardian-User-Manual-JA.html",
        "markdown_name": "EMI-Guardian-User-Manual-JA.md",
    },
    {
        "language": "en",
        "title": "EMI Guardian User Manual",
        "source": ROOT / "docs" / "en" / "guide" / "user-manual.md",
        "html_name": "EMI-Guardian-User-Manual-EN.html",
        "markdown_name": "EMI-Guardian-User-Manual-EN.md",
    },
)


def _slug(value: str, fallback: str) -> str:
    """Return a stable HTML fragment identifier for a heading."""

    normalized = unicodedata.normalize("NFKC", value).strip().lower()
    normalized = re.sub(r"[^\w\-\u3040-\u30ff\u3400-\u9fff]+", "-", normalized)
    normalized = normalized.strip("-")
    return normalized or fallback


def _render_document(markdown_text: str) -> tuple[str, list[tuple[int, str, str]]]:
    """Render Markdown and return HTML plus a level-two/three table of contents."""

    renderer = MarkdownIt("commonmark", {"html": False, "linkify": False, "typographer": False})
    renderer.enable("table")
    tokens = renderer.parse(markdown_text)
    headings: list[tuple[int, str, str]] = []
    used: dict[str, int] = {}

    for index, token in enumerate(tokens):
        if token.type != "heading_open" or index + 1 >= len(tokens):
            continue
        level = int(token.tag[1:])
        inline: Token = tokens[index + 1]
        title = inline.content.strip()
        base = _slug(title, f"section-{len(headings) + 1}")
        count = used.get(base, 0)
        used[base] = count + 1
        identifier = base if count == 0 else f"{base}-{count + 1}"
        token.attrSet("id", identifier)
        if level in {2, 3}:
            headings.append((level, title, identifier))

    return renderer.renderer.render(tokens, renderer.options, {}), headings


def _toc_html(headings: list[tuple[int, str, str]]) -> str:
    """Render a compact navigation list."""

    items = []
    for level, title, identifier in headings:
        class_name = "toc-subitem" if level == 3 else "toc-item"
        items.append(f'<li class="{class_name}"><a href="#{escape(identifier)}">{escape(title)}</a></li>')
    return "\n".join(items)


def _page(title: str, language: str, body: str, toc: str) -> str:
    """Return a self-contained, printable HTML manual."""

    label = "目次" if language == "ja" else "Contents"
    notice = (
        "JLCPCBの製造条件と価格は変更される可能性があります。発注前に最新見積とDFMを確認してください。"
        if language == "ja"
        else "JLCPCB capabilities and pricing can change. Confirm the live quote and DFM result before ordering."
    )
    return f"""<!doctype html>
<html lang="{escape(language)}">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{escape(title)}</title>
<style>
:root {{ color-scheme: light dark; --bg:#f4f6f8; --surface:#ffffff; --text:#17202a; --muted:#5d6874; --line:#d8dee6; --accent:#0b6bcb; --accent-soft:#e7f2ff; --code:#eef2f6; --warn:#fff4d6; --shadow:0 12px 40px rgba(15,35,55,.10); }}
* {{ box-sizing:border-box; }}
html {{ scroll-behavior:smooth; }}
body {{ margin:0; background:var(--bg); color:var(--text); font-family:Inter, "Noto Sans JP", "Yu Gothic UI", "Hiragino Kaku Gothic ProN", system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; line-height:1.72; }}
a {{ color:var(--accent); text-decoration-thickness:.08em; text-underline-offset:.16em; }}
.layout {{ display:grid; grid-template-columns:minmax(240px,300px) minmax(0,920px); gap:28px; justify-content:center; padding:28px; }}
.sidebar {{ position:sticky; top:20px; align-self:start; max-height:calc(100vh - 40px); overflow:auto; background:var(--surface); border:1px solid var(--line); border-radius:18px; box-shadow:var(--shadow); padding:22px; }}
.brand {{ font-size:1.18rem; font-weight:760; letter-spacing:-.02em; margin-bottom:4px; }}
.sidebar h2 {{ font-size:.86rem; text-transform:uppercase; letter-spacing:.08em; color:var(--muted); border:0; margin:0 0 10px; padding:0; }}
.sidebar ul {{ list-style:none; margin:0; padding:0; }}
.sidebar li {{ margin:0; }}
.sidebar a {{ display:block; padding:6px 8px; border-radius:9px; color:var(--text); text-decoration:none; font-size:.9rem; }}
.sidebar a:hover {{ background:var(--accent-soft); color:var(--accent); }}
.sidebar .toc-subitem a {{ padding-left:22px; color:var(--muted); font-size:.84rem; }}
main {{ min-width:0; background:var(--surface); border:1px solid var(--line); border-radius:22px; box-shadow:var(--shadow); padding:clamp(28px,6vw,68px); }}
.notice {{ background:var(--warn); border:1px solid #e5c66d; border-radius:14px; padding:14px 16px; margin:0 0 30px; font-weight:620; }}
h1 {{ font-size:clamp(2rem,5vw,3.25rem); line-height:1.12; letter-spacing:-.04em; margin:.1em 0 .8em; }}
h2 {{ font-size:1.55rem; line-height:1.3; margin:2.2em 0 .7em; padding-bottom:.35em; border-bottom:1px solid var(--line); scroll-margin-top:22px; }}
h3 {{ font-size:1.16rem; margin:1.7em 0 .45em; scroll-margin-top:22px; }}
h4 {{ font-size:1rem; margin:1.35em 0 .35em; }}
p, ul, ol {{ margin:.75em 0 1.1em; }}
li + li {{ margin-top:.32em; }}
blockquote {{ margin:1.4em 0; border-left:4px solid var(--accent); background:var(--accent-soft); padding:12px 18px; border-radius:0 12px 12px 0; }}
code {{ background:var(--code); border:1px solid var(--line); border-radius:6px; padding:.12em .35em; font-family:"SFMono-Regular", Consolas, "Liberation Mono", monospace; font-size:.9em; }}
pre {{ overflow:auto; background:#121820; color:#edf4fb; border-radius:14px; padding:18px; line-height:1.5; }}
pre code {{ background:transparent; border:0; padding:0; color:inherit; }}
table {{ width:100%; border-collapse:separate; border-spacing:0; margin:1.2em 0 1.7em; border:1px solid var(--line); border-radius:12px; overflow:hidden; font-size:.94rem; }}
th, td {{ text-align:left; vertical-align:top; padding:10px 12px; border-bottom:1px solid var(--line); border-right:1px solid var(--line); }}
th {{ background:var(--code); font-weight:700; }}
tr:last-child td {{ border-bottom:0; }}
th:last-child, td:last-child {{ border-right:0; }}
hr {{ border:0; border-top:1px solid var(--line); margin:2.5em 0; }}
footer {{ color:var(--muted); border-top:1px solid var(--line); margin-top:3.5em; padding-top:1.4em; font-size:.86rem; }}
@media (max-width:900px) {{ .layout {{ grid-template-columns:1fr; padding:14px; }} .sidebar {{ position:relative; top:0; max-height:none; }} main {{ padding:28px 22px; }} }}
@media print {{ :root {{ --bg:#fff; --surface:#fff; --text:#000; --muted:#444; --line:#bbb; }} .layout {{ display:block; padding:0; }} .sidebar {{ display:none; }} main {{ border:0; box-shadow:none; border-radius:0; padding:0; }} a {{ color:inherit; text-decoration:none; }} h2, h3 {{ break-after:avoid; }} table, pre, blockquote {{ break-inside:avoid; }} }}
@media (prefers-color-scheme:dark) {{ :root {{ --bg:#0f141a; --surface:#171e26; --text:#e8edf2; --muted:#a8b3bf; --line:#34404c; --accent:#7db8ff; --accent-soft:#172d45; --code:#222c36; --warn:#3a3019; --shadow:0 12px 40px rgba(0,0,0,.30); }} }}
</style>
</head>
<body>
<div class="layout">
<aside class="sidebar" aria-label="{escape(label)}">
<div class="brand">EMI Guardian</div>
<h2>{escape(label)}</h2>
<ul>{toc}</ul>
</aside>
<main>
<div class="notice">{escape(notice)}</div>
{body}
<footer>Pre-release engineering preview · Generated from the bilingual source documentation.</footer>
</main>
</div>
</body>
</html>
"""


def build_manual_files(output_directory: Path) -> dict[str, Path]:
    """Build standalone HTML and copied Markdown manuals."""

    output_directory.mkdir(parents=True, exist_ok=True)
    outputs: dict[str, Path] = {}
    for manual in MANUALS:
        source = Path(manual["source"])
        markdown_text = source.read_text(encoding="utf-8")
        body, headings = _render_document(markdown_text)
        html_path = output_directory / str(manual["html_name"])
        html_path.write_text(
            _page(str(manual["title"]), str(manual["language"]), body, _toc_html(headings)),
            encoding="utf-8",
        )
        markdown_path = output_directory / str(manual["markdown_name"])
        shutil.copyfile(source, markdown_path)
        outputs[f"{manual['language']}_html"] = html_path
        outputs[f"{manual['language']}_markdown"] = markdown_path

    readme = output_directory / "README.txt"
    readme.write_text(
        "EMI Guardian user manuals\n"
        "=========================\n\n"
        "Open the JA or EN HTML file in a modern browser. The Markdown copies are\n"
        "provided for source review and version control. Manufacturing data was\n"
        "verified on 2026-08-13 and must be rechecked against the live quote before\n"
        "ordering.\n",
        encoding="utf-8",
    )
    outputs["readme"] = readme
    return outputs


def main() -> int:
    """Command-line entry point."""

    parser = argparse.ArgumentParser()
    parser.add_argument(
        "output_directory",
        nargs="?",
        type=Path,
        default=ROOT / "dist" / "manuals",
    )
    args = parser.parse_args()
    for name, path in build_manual_files(args.output_directory.resolve()).items():
        print(f"{name}: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
