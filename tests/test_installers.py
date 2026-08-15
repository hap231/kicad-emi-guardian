"""Cross-platform installer and release-surface tests."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def test_installer_scripts_have_required_update_and_safety_guards() -> None:
    """Keep install, update, zero-backup replacement, cache refresh, and uninstall explicit."""

    windows = (ROOT / "installers" / "windows" / "install-or-update.ps1").read_text(encoding="utf-8")
    windows_uninstall = (ROOT / "installers" / "windows" / "uninstall.ps1").read_text(encoding="utf-8")
    linux = (ROOT / "installers" / "linux" / "install-or-update.sh").read_text(encoding="utf-8")
    macos = (ROOT / "installers" / "macos" / "install-or-update.command").read_text(encoding="utf-8")
    for text in (windows, linux, macos):
        assert "payload" in text.lower()
        assert "plugin.json" in text
        assert "python-environments" in text
        assert "emi-guardian" in text
        assert "External Plugins" in text
        assert "without creating a backup copy" in text
        assert "Previous version backup" not in text
        # Legacy backup directories may be named only so the installer can
        # remove them; no persistent backup destination may be created.
        assert "_emi-guardian-backups" in text
        assert "OLD_PAYLOAD" not in text
        assert "OldPayload" not in text
        assert "rollback" not in text.lower()
    assert 'cp -R "$DESTINATION"' not in linux
    assert 'cp -R "$DESTINATION"' not in macos
    assert "Copy-Item -LiteralPath $Destination -Destination" not in windows
    assert "MyDocuments" in windows
    assert "LOCALAPPDATA" in windows
    assert "-ErrorAction Stop" in windows
    assert "GetTempPath" in windows
    assert "XDG_DATA_HOME" in linux
    assert "XDG_CACHE_HOME" in linux
    assert "mktemp -d" in linux
    assert "Library/Caches/KiCad" in macos
    assert "Persistent settings" in windows_uninstall
    assert "RemoveBackups" not in windows_uninstall


def test_posix_installers_pass_bash_syntax_check() -> None:
    """Parse every Linux and macOS script with Bash when available."""

    bash = shutil.which("bash")
    if bash is None:
        pytest.skip("bash is unavailable")
    scripts = sorted((ROOT / "installers" / "linux").glob("*.sh"))
    scripts.extend(sorted((ROOT / "installers" / "macos").glob("*.command")))
    assert scripts
    for script in scripts:
        subprocess.run([bash, "-n", str(script)], check=True)
        assert script.stat().st_mode & 0o111


def test_release_versions_and_python_runtime_are_synchronized() -> None:
    """Prevent a package that advertises a different runtime or release number."""

    manifest = json.loads((ROOT / "plugin" / "plugin.json").read_text(encoding="utf-8"))
    metadata = json.loads((ROOT / "metadata.json").read_text(encoding="utf-8"))
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    package_init = (ROOT / "plugin" / "emi_guardian" / "__init__.py").read_text(encoding="utf-8")
    assert manifest["runtime"]["min_version"] == "3.9"
    assert metadata["versions"][0]["version"] == "0.0.2"
    assert metadata["versions"][0]["status"] == "testing"
    assert 'version = "0.0.2"' in pyproject
    assert 'requires-python = ">=3.9"' in pyproject
    assert '__version__ = "0.0.2"' in package_init


@pytest.mark.parametrize(
    ("platform", "install_name", "uninstall_name"),
    (
        ("linux", "install-or-update.sh", "uninstall.sh"),
        ("macos", "install-or-update.command", "uninstall.command"),
    ),
)
def test_posix_installer_lifecycle_in_isolated_home(
    tmp_path: Path,
    platform: str,
    install_name: str,
    uninstall_name: str,
) -> None:
    """Exercise install, replacement update, cache refresh, and backup-free uninstall."""

    bash = shutil.which("bash")
    if bash is None:
        pytest.skip("bash is unavailable")
    package = tmp_path / platform
    package.mkdir()
    install = package / install_name
    uninstall = package / uninstall_name
    shutil.copy2(ROOT / "installers" / platform / install_name, install)
    shutil.copy2(ROOT / "installers" / platform / uninstall_name, uninstall)
    payload = package / "payload" / "emi-guardian"
    shutil.copytree(ROOT / "plugin", payload)

    home = tmp_path / "home"
    home.mkdir()
    environment = os.environ.copy()
    environment["HOME"] = str(home)
    input_text = "\n" if platform == "macos" else None
    if platform == "linux":
        data_home = tmp_path / "data"
        cache_home = tmp_path / "cache"
        environment["XDG_DATA_HOME"] = str(data_home)
        environment["XDG_CACHE_HOME"] = str(cache_home)
        plugins_root = data_home / "KiCad" / "10.0" / "plugins"
        cache = cache_home / "KiCad" / "10.0" / "python-environments" / "com.openai.kicad.emi-guardian"
    else:
        plugins_root = home / "Documents" / "KiCad" / "10.0" / "plugins"
        cache = (
            home
            / "Library"
            / "Caches"
            / "KiCad"
            / "10.0"
            / "python-environments"
            / "com.openai.kicad.emi-guardian"
        )
    destination = plugins_root / "emi-guardian"
    backup_root = plugins_root / "_emi-guardian-backups"

    command = [bash, str(install), "--force"]
    subprocess.run(command, check=True, env=environment, input=input_text, text=True, capture_output=True)
    assert (destination / "plugin.json").is_file()
    (destination / "previous-version-marker.txt").write_text("old", encoding="utf-8")
    backup_root.mkdir(parents=True)
    (backup_root / "stale-plugin.json").write_text("{}", encoding="utf-8")
    cache.mkdir(parents=True)
    (cache / "stale.txt").write_text("stale", encoding="utf-8")

    subprocess.run(command, check=True, env=environment, input=input_text, text=True, capture_output=True)
    assert not cache.exists()
    assert not backup_root.exists()
    assert not (destination / "previous-version-marker.txt").exists()
    assert [item.name for item in plugins_root.iterdir() if item.is_dir()] == ["emi-guardian"]

    subprocess.run(
        [bash, str(uninstall), "--force"],
        check=True,
        env=environment,
        input=input_text,
        text=True,
        capture_output=True,
    )
    assert not destination.exists()
    assert not backup_root.exists()


def test_source_builder_excludes_local_analysis_artifacts() -> None:
    """Keep coverage and tool caches out of GitHub/source release archives."""

    source = (ROOT / "scripts" / "build_package.py").read_text(encoding="utf-8")
    assert '".coverage"' in source
    assert '".ruff_cache"' in source
    assert '".mypy_cache"' in source
    assert '"htmlcov"' in source
    assert '".venv"' in source
    assert '"build"' in source
    assert '".DS_Store"' in source
    assert '".egg-info"' in source
    assert '"_generated"' in source
    assert "validate_source_archive(source)" in source
