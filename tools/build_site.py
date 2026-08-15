#!/usr/bin/env python3
"""Build and validate the bilingual GitHub Pages documentation site."""

from __future__ import annotations

import argparse
import shutil
import sys
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urlsplit

from sphinx.cmd.build import main as sphinx_main

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"
DEFAULT_OUTPUT = ROOT / "site"
IGNORED_SCHEMES = {"data", "http", "https", "mailto", "tel"}


class _LocalReferenceParser(HTMLParser):
    """Collect local links and assets from one generated HTML document."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.references: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        """Record attributes that can refer to another generated file."""

        for name, value in attrs:
            if value and name in {"href", "src"}:
                self.references.append(value)


def _markdown_pages(language: str) -> set[Path]:
    """Return relative Markdown paths for one language tree."""

    root = DOCS / language
    return {path.relative_to(root) for path in root.rglob("*.md")}


def validate_language_mirror() -> None:
    """Require the English and Japanese documentation trees to match exactly."""

    english = _markdown_pages("en")
    japanese = _markdown_pages("ja")
    if english != japanese:
        english_only = sorted(str(path) for path in english - japanese)
        japanese_only = sorted(str(path) for path in japanese - english)
        details = []
        if english_only:
            details.append(f"English only: {', '.join(english_only)}")
        if japanese_only:
            details.append(f"Japanese only: {', '.join(japanese_only)}")
        raise RuntimeError("Documentation language trees differ. " + " ".join(details))


def _resolve_reference(page: Path, reference: str, site_root: Path) -> Path | None:
    """Resolve a generated-page reference when it points inside the site."""

    parsed = urlsplit(reference)
    if parsed.scheme in IGNORED_SCHEMES or parsed.netloc or not parsed.path:
        return None
    path_text = unquote(parsed.path)
    target = site_root / path_text.lstrip("/") if path_text.startswith("/") else page.parent / path_text
    if path_text.endswith("/"):
        target /= "index.html"
    return target.resolve()


def validate_generated_site(site_root: Path) -> None:
    """Check required pages, mirrored output, and every local HTML reference."""

    site_root = site_root.resolve()
    required = {
        site_root / "index.html",
        site_root / "en" / "index.html",
        site_root / "ja" / "index.html",
        site_root / "_static" / "site.css",
        site_root / "_static" / "language-switcher.js",
    }
    missing = sorted(str(path.relative_to(site_root)) for path in required if not path.is_file())
    if missing:
        raise RuntimeError(f"Generated site is incomplete: {', '.join(missing)}")

    for relative in _markdown_pages("en"):
        generated = relative.with_suffix(".html")
        for language in ("en", "ja"):
            path = site_root / language / generated
            if not path.is_file():
                raise RuntimeError(f"Missing generated language page: {path.relative_to(site_root)}")

    broken: list[str] = []
    for page in sorted(site_root.rglob("*.html")):
        parser = _LocalReferenceParser()
        parser.feed(page.read_text(encoding="utf-8"))
        for reference in parser.references:
            target = _resolve_reference(page, reference, site_root)
            if target is None:
                continue
            try:
                target.relative_to(site_root)
            except ValueError:
                broken.append(f"{page.relative_to(site_root)} -> {reference} (outside site)")
                continue
            if not target.exists():
                broken.append(f"{page.relative_to(site_root)} -> {reference}")
    if broken:
        preview = "\n".join(broken[:25])
        suffix = f"\n... and {len(broken) - 25} more" if len(broken) > 25 else ""
        raise RuntimeError(f"Broken generated-site references:\n{preview}{suffix}")


def build_site(output: Path) -> None:
    """Build a fresh Sphinx site and validate the deployable result."""

    output = output.resolve()
    if output == ROOT or ROOT not in output.parents:
        raise RuntimeError(f"Refusing unsafe site output path: {output}")
    if output.exists():
        shutil.rmtree(output)
    generated_api = DOCS / "_generated"
    if generated_api.exists():
        shutil.rmtree(generated_api)
    validate_language_mirror()
    result = sphinx_main(
        [
            "-W",
            "--keep-going",
            "--fresh-env",
            "-b",
            "html",
            str(DOCS),
            str(output),
        ]
    )
    if result:
        raise RuntimeError(f"Sphinx exited with status {result}")
    (output / ".nojekyll").touch()
    validate_generated_site(output)


def main() -> int:
    """Build the documentation site from the command line."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    try:
        build_site(args.output)
    except RuntimeError as error:
        print(error, file=sys.stderr)
        return 1
    print(f"Validated site: {args.output.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
