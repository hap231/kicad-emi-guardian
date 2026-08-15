"""KiCad plugin manifest and packaging-surface tests."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_plugin_manifest_declares_two_pcb_actions_and_existing_entrypoints() -> None:
    """Keep the IPC plugin discoverable by KiCad 10+ without legacy SWIG hooks."""

    manifest_path = ROOT / "plugin" / "plugin.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["identifier"] == "com.openai.kicad.emi-guardian"
    assert manifest["runtime"]["type"] == "python"
    assert len(manifest["actions"]) == 2
    for action in manifest["actions"]:
        assert action["scopes"] == ["pcb"]
        assert (manifest_path.parent / action["entrypoint"]).is_file()


def test_source_uses_official_ipc_adapter_not_legacy_pcbnew_swig() -> None:
    """Prevent accidental reintroduction of the deprecated in-process API."""

    python_source = "\n".join(path.read_text(encoding="utf-8") for path in (ROOT / "plugin").rglob("*.py"))
    assert "import pcbnew" not in python_source
    assert "from pcbnew" not in python_source
    assert "from kipy import KiCad" in python_source


def test_manifest_icons_and_pcm_metadata_are_complete() -> None:
    """Keep toolbar and PCM packaging assets aligned with KiCad 10 schemas."""

    manifest = json.loads((ROOT / "plugin" / "plugin.json").read_text(encoding="utf-8"))
    for action in manifest["actions"]:
        for field in ("icons-light", "icons-dark"):
            assert action[field]
            assert all((ROOT / "plugin" / icon).is_file() for icon in action[field])
    metadata = json.loads((ROOT / "metadata.json").read_text(encoding="utf-8"))
    assert metadata["$schema"].endswith("/pcm/schemas/v2")
    assert metadata["type"] == "plugin"
    assert metadata["versions"][0]["runtime"] == "ipc"
    assert metadata["versions"][0]["kicad_version"] == "10.0.5"
    assert metadata["versions"][0]["version"] == "0.0.2"
    assert "jlcpcb" in metadata["tags"]
    assert (ROOT / "resources" / "icon.png").is_file()


def test_runtime_requirement_is_consistent_across_package_surfaces() -> None:
    """Keep the managed-environment dependency declaration synchronized."""

    requirement = (ROOT / "plugin" / "requirements.txt").read_text(encoding="utf-8").strip()
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert requirement == "kicad-python>=0.7.1,<1.0"
    assert requirement in pyproject
