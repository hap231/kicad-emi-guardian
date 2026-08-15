"""Bilingual documentation completeness tests."""

from __future__ import annotations

import ast
import io
import re
import tokenize
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
JAPANESE_TEXT = re.compile(r"[ぁ-んァ-ヶ一-龯々]")


def test_required_bilingual_documentation_exists_and_is_indexed() -> None:
    """Keep user, implementation, safety, and acceptance guidance in both languages."""

    pages = {
        "user-manual.md",
        "manufacturing-jlcpcb.md",
        "installation.md",
        "usage.md",
        "architecture.md",
        "algorithms.md",
        "configuration.md",
        "safety-and-limitations.md",
        "development.md",
        "implementation-status.md",
        "acceptance-test.md",
        "github-release.md",
    }
    for language in ("en", "ja"):
        directory = ROOT / "docs" / language
        index = (directory / "index.md").read_text(encoding="utf-8")
        for page in pages:
            assert (directory / page).is_file()
            assert page in index


def test_repository_documents_have_japanese_counterparts() -> None:
    """Keep repository-facing policy and release documents bilingual."""

    pairs = {
        "CHANGELOG.md": "CHANGELOG.ja.md",
        "CONTRIBUTING.md": "CONTRIBUTING.ja.md",
        "RELEASE_CHECKLIST.md": "RELEASE_CHECKLIST.ja.md",
        "RELEASE_NOTES.md": "RELEASE_NOTES.ja.md",
        "SECURITY.md": "SECURITY.ja.md",
        "THIRD_PARTY_NOTICES.md": "THIRD_PARTY_NOTICES.ja.md",
        "VERIFICATION_REPORT.md": "VERIFICATION_REPORT.ja.md",
    }
    for english_name, japanese_name in pairs.items():
        english = (ROOT / english_name).read_text(encoding="utf-8")
        japanese = (ROOT / japanese_name).read_text(encoding="utf-8")
        assert japanese_name in english
        assert english_name in japanese
        assert JAPANESE_TEXT.search(japanese)


def test_python_comments_and_docstrings_are_english() -> None:
    """Reject Japanese prose in Python comments while allowing localized runtime strings."""

    roots = (ROOT / "plugin", ROOT / "scripts", ROOT / "tests")
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


def test_implementation_status_states_engineering_screening_limit() -> None:
    """Prevent the documentation from implying an unsupported EMC guarantee."""

    english = (ROOT / "docs" / "en" / "implementation-status.md").read_text(encoding="utf-8")
    japanese = (ROOT / "docs" / "ja" / "implementation-status.md").read_text(encoding="utf-8")
    assert "engineering screening" in english.lower()
    assert "not proof" in english.lower()
    assert "エンジニアリングスクリーニング" in japanese
    assert "不存在証明ではありません" in japanese


def test_bilingual_user_manuals_cover_jlcpcb_presets_and_kicad_limit() -> None:
    """Keep the requested operator guidance in both manuals."""

    english = (ROOT / "docs" / "en" / "user-manual.md").read_text(encoding="utf-8")
    japanese = (ROOT / "docs" / "ja" / "user-manual.md").read_text(encoding="utf-8")
    for text in (english, japanese):
        assert "0.1, 0.2, 0.3, 0.4, 0.5, 0.8, 1.0, 1.5, 2.0, 3.0, 5.0" in text
        assert "0.25 / 0.15" in text or "0.25／0.15" in text
        assert "0.60 / 0.30" in text or "0.60／0.30" in text
        assert "1.6" in text
    assert "public IPC" in english
    assert "公開IPC" in japanese


def test_v002_configuration_documents_match_schema_five() -> None:
    """Keep the bilingual configuration reference synchronized with the runtime schema."""

    english = (ROOT / "docs" / "en" / "configuration.md").read_text(encoding="utf-8")
    japanese = (ROOT / "docs" / "ja" / "configuration.md").read_text(encoding="utf-8")
    assert "schema version is **5**" in english
    assert "スキーマ版は**5**" in japanese


def test_installation_docs_forbid_old_plugin_backup_and_rollback() -> None:
    """Prevent release documentation from reintroducing the crash-prone backup workflow."""

    english_files = (
        ROOT / "README.md",
        ROOT / "docs" / "en" / "installation.md",
        ROOT / "docs" / "en" / "user-manual.md",
        ROOT / "installers" / "README-EN.md",
    )
    japanese_files = (
        ROOT / "docs" / "ja" / "installation.md",
        ROOT / "docs" / "ja" / "user-manual.md",
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

    english_algorithm = (ROOT / "docs" / "en" / "algorithms.md").read_text(encoding="utf-8")
    english_manual = (ROOT / "docs" / "en" / "user-manual.md").read_text(encoding="utf-8")
    japanese_algorithm = (ROOT / "docs" / "ja" / "algorithms.md").read_text(encoding="utf-8")
    japanese_manual = (ROOT / "docs" / "ja" / "user-manual.md").read_text(encoding="utf-8")

    for text in (english_algorithm, english_manual):
        lowered = text.lower()
        assert "immediately before" in lowered or "just before" in lowered
        assert "active board" in lowered
        assert "without mutation" in lowered or "without modifying" in lowered
    for text in (japanese_algorithm, japanese_manual):
        assert "適用直前" in text or "適用する直前" in text
        assert "アクティブ基板" in text
        assert "基板を変更せず" in text
