"""Bilingual documentation completeness tests."""

from __future__ import annotations

import ast
import io
import re
import tokenize
from pathlib import Path

from tools.project_metadata import project_version

ROOT = Path(__file__).resolve().parents[1]
JAPANESE_TEXT = re.compile(r"[ぁ-んァ-ヶ一-龯々]")
PRODUCT_VERSION_TEXT = re.compile(r"(?<![\d.])v?0[.]0[.]\d+(?![\d.])")


def test_required_bilingual_documentation_exists_and_is_indexed() -> None:
    """Keep user, technical, safety, and acceptance guidance in both languages."""

    pages = {
        "guide/user-manual.md",
        "guide/manufacturing-jlcpcb.md",
        "guide/safety-and-limitations.md",
        "reference/architecture.md",
        "reference/algorithms.md",
        "reference/configuration.md",
        "development/index.md",
        "development/acceptance-test.md",
    }
    for language in ("en", "ja"):
        directory = ROOT / "docs" / language
        index = (directory / "index.md").read_text(encoding="utf-8")
        for page in pages:
            assert (directory / page).is_file()
            assert page in index


def test_documentation_language_trees_have_identical_markdown_paths() -> None:
    """Keep every English documentation source paired with a Japanese source."""

    english_root = ROOT / "docs" / "en"
    japanese_root = ROOT / "docs" / "ja"
    english_paths = {path.relative_to(english_root) for path in english_root.rglob("*.md")}
    japanese_paths = {path.relative_to(japanese_root) for path in japanese_root.rglob("*.md")}
    assert english_paths == japanese_paths
    for relative in sorted(english_paths):
        english = (english_root / relative).read_text(encoding="utf-8")
        japanese = (japanese_root / relative).read_text(encoding="utf-8")
        assert english.strip()
        assert JAPANESE_TEXT.search(japanese)


def test_project_documents_are_indexed_in_both_languages() -> None:
    """Keep the compact set of durable project documents visible."""

    pages = {"changelog.md", "contributing.md", "security.md", "third-party-notices.md"}
    removed = {
        "release-checklist.md",
        "release-notes.md",
        "verification-report.md",
        "github-release.md",
        "implementation-status.md",
    }
    for language in ("en", "ja"):
        root = ROOT / "docs" / language
        index = (root / "index.md").read_text(encoding="utf-8")
        for page in pages:
            assert f"project/{page}" in index
        for page in removed:
            assert not tuple(root.rglob(page))


def test_product_version_text_is_limited_to_metadata_and_changelogs() -> None:
    """Keep frequently changing product versions out of prose and source comments."""

    allowed = {
        ROOT / "pyproject.toml",
        ROOT / "metadata.json",
        ROOT / "docs" / "en" / "project" / "changelog.md",
        ROOT / "docs" / "ja" / "project" / "changelog.md",
    }
    ignored_directories = {
        ".git",
        ".mypy_cache",
        ".pytest_cache",
        ".ruff_cache",
        ".venv",
        "__pycache__",
        "_build",
        "_generated",
        "build",
        "dist",
        "htmlcov",
        "site",
    }
    unexpected: list[str] = []
    for path in ROOT.rglob("*"):
        if (
            not path.is_file()
            or ignored_directories.intersection(path.parts)
            or any(part.endswith((".egg-info", ".dist-info")) for part in path.parts)
            or path in allowed
        ):
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        if PRODUCT_VERSION_TEXT.search(text):
            unexpected.append(str(path.relative_to(ROOT)))
    assert not unexpected, f"Product version text outside metadata/changelogs: {unexpected}"

    expected = project_version()
    for language in ("en", "ja"):
        changelog = (ROOT / "docs" / language / "project" / "changelog.md").read_text(encoding="utf-8")
        current = re.search(r"^##\s+(\d+\.\d+\.\d+)\b", changelog, flags=re.MULTILINE)
        assert current and current.group(1) == expected


def test_python_comments_and_docstrings_are_english() -> None:
    """Reject Japanese prose in Python comments while allowing localized runtime strings."""

    roots = (ROOT / "plugin", ROOT / "tools", ROOT / "tests")
    for directory in roots:
        for path in directory.rglob("*.py"):
            source = path.read_text(encoding="utf-8")
            tokens = tokenize.generate_tokens(io.StringIO(source).readline)
            japanese_comments = [
                token.string
                for token in tokens
                if token.type == tokenize.COMMENT and JAPANESE_TEXT.search(token.string)
            ]
            assert not japanese_comments, f"Japanese comment in {path}: {japanese_comments[0]}"
            tree = ast.parse(source, filename=str(path))
            for node in ast.walk(tree):
                if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
                    docstring = ast.get_docstring(node, clean=False)
                    assert not (docstring and JAPANESE_TEXT.search(docstring)), (
                        f"Japanese docstring in {path}:{getattr(node, 'lineno', 1)}"
                    )


def test_pages_and_renovate_configuration_replace_dependabot() -> None:
    """Keep Pages publication and Renovate dependency management configured."""

    assert not (ROOT / ".github" / "dependabot.yml").exists()
    renovate = (ROOT / ".github" / "renovate.json5").read_text(encoding="utf-8")
    pages = (ROOT / ".github" / "workflows" / "pages.yml").read_text(encoding="utf-8")
    build_tool = (ROOT / "tools" / "build_site.py").read_text(encoding="utf-8")
    assert "config:recommended" in renovate
    assert "osvVulnerabilityAlerts" in renovate
    assert "actions/deploy-pages" in pages
    assert "python tools/build_site.py --output site" in pages
    assert "validate_language_mirror" in build_tool
    assert "validate_generated_site" in build_tool


def test_safety_guides_state_the_engineering_screening_limit() -> None:
    """Prevent documentation from implying an unsupported EMC guarantee."""

    english = (ROOT / "docs" / "en" / "guide" / "safety-and-limitations.md").read_text(encoding="utf-8")
    japanese = (ROOT / "docs" / "ja" / "guide" / "safety-and-limitations.md").read_text(encoding="utf-8")
    assert "engineering screening" in english.lower()
    assert "not proof" in english.lower()
    assert "エンジニアリングスクリーニング" in japanese
    assert "不存在証明ではありません" in japanese


def test_bilingual_user_manuals_cover_jlcpcb_presets_and_kicad_limit() -> None:
    """Keep the requested operator guidance in both manuals."""

    english = (ROOT / "docs" / "en" / "guide" / "user-manual.md").read_text(encoding="utf-8")
    japanese = (ROOT / "docs" / "ja" / "guide" / "user-manual.md").read_text(encoding="utf-8")
    for text in (english, japanese):
        assert "0.1, 0.2, 0.3, 0.4, 0.5, 0.8, 1.0, 1.5, 2.0, 3.0, 5.0" in text
        assert "0.25 / 0.15" in text or "0.25／0.15" in text
        assert "0.60 / 0.30" in text or "0.60／0.30" in text
        assert "1.6" in text
    assert "public IPC" in english
    assert "公開IPC" in japanese


def test_configuration_documents_match_schema_five() -> None:
    """Keep the bilingual configuration reference synchronized with the runtime schema."""

    english = (ROOT / "docs" / "en" / "reference" / "configuration.md").read_text(encoding="utf-8")
    japanese = (ROOT / "docs" / "ja" / "reference" / "configuration.md").read_text(encoding="utf-8")
    assert "schema version is **5**" in english
    assert "スキーマ版は**5**" in japanese


def test_installation_docs_forbid_old_plugin_backup_and_rollback() -> None:
    """Prevent installation guidance from reintroducing the crash-prone backup workflow."""

    english_files = (
        ROOT / "README.md",
        ROOT / "docs" / "en" / "guide" / "user-manual.md",
        ROOT / "installers" / "README-EN.md",
    )
    japanese_files = (
        ROOT / "docs" / "ja" / "guide" / "user-manual.md",
        ROOT / "installers" / "README-JA.md",
    )
    for path in english_files:
        text = path.read_text(encoding="utf-8").lower()
        assert "no backup" in text or "no installer backup" in text
        assert "rollback" in text
        assert "intentionally" in text or "must be run again" in text
    for path in japanese_files:
        text = path.read_text(encoding="utf-8")
        assert "バックアップを作" in text
        assert "ロールバック" in text
        assert "行いません" in text


def test_antenna_docs_require_apply_time_revalidation() -> None:
    """Document that a preview is never trusted after the board has changed."""

    english_algorithm = (ROOT / "docs" / "en" / "reference" / "algorithms.md").read_text(encoding="utf-8")
    english_manual = (ROOT / "docs" / "en" / "guide" / "user-manual.md").read_text(encoding="utf-8")
    japanese_algorithm = (ROOT / "docs" / "ja" / "reference" / "algorithms.md").read_text(encoding="utf-8")
    japanese_manual = (ROOT / "docs" / "ja" / "guide" / "user-manual.md").read_text(encoding="utf-8")

    for text in (english_algorithm, english_manual):
        lowered = text.lower()
        assert "immediately before" in lowered or "just before" in lowered
        assert "active board" in lowered
        assert "without mutation" in lowered or "without modifying" in lowered
    for text in (japanese_algorithm, japanese_manual):
        assert "適用直前" in text or "適用する直前" in text
        assert "アクティブ基板" in text
        assert "基板を変更せず" in text
