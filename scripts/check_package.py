#!/usr/bin/env python3
"""Validate manifests, source invariants, installers, and release archives."""

from __future__ import annotations

import argparse
import ast
import json
import re
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PLUGIN_DIR = ROOT / "plugin"
VERSION = "0.0.2"

PLUGIN_IDENTIFIER_PATTERN = re.compile(r"^[a-zA-Z][-_a-zA-Z0-9.]{0,98}[a-zA-Z0-9]$")
ACTION_IDENTIFIER_PATTERN = re.compile(r"^[a-zA-Z][-_a-zA-Z0-9.]{0,48}[a-zA-Z0-9]$")
PCM_IDENTIFIER_PATTERN = re.compile(r"^[a-zA-Z][-a-zA-Z0-9.]{0,98}[a-zA-Z0-9]$")
VERSION_PATTERN = re.compile(r"^\d{1,4}(?:\.\d{1,4}(?:\.\d{1,6})?)?$")
KICAD_VERSION_PATTERN = re.compile(r"^\d{1,2}(?:\.\d{1,2}(?:\.\d{1,2})?)?$")


def require(condition: bool, message: str) -> None:
    """Raise a stable validation error when a condition is false."""

    if not condition:
        raise ValueError(message)


def validate_plugin_manifest() -> None:
    """Validate the KiCad IPC plugin manifest surface used by this project."""

    path = PLUGIN_DIR / "plugin.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    require(data.get("$schema") == "https://go.kicad.org/api/schemas/v1", "Unexpected plugin schema")
    require(
        bool(PLUGIN_IDENTIFIER_PATTERN.fullmatch(str(data.get("identifier", "")))),
        "Invalid plugin identifier",
    )
    runtime = data.get("runtime", {})
    require(runtime.get("type") == "python", "Plugin runtime must be python")
    require(runtime.get("min_version") == "3.9", "Plugin runtime must support KiCad's Python 3.9 environment")
    require(isinstance(data.get("actions"), list) and data["actions"], "At least one action is required")
    for action in data["actions"]:
        require(
            bool(ACTION_IDENTIFIER_PATTERN.fullmatch(str(action.get("identifier", "")))),
            "Invalid action identifier",
        )
        require(action.get("scopes") == ["pcb"], "Every action must be PCB-scoped")
        entrypoint = PLUGIN_DIR / str(action.get("entrypoint", ""))
        require(entrypoint.is_file(), f"Missing action entrypoint: {entrypoint.name}")
        for field in ("icons-light", "icons-dark"):
            icons = action.get(field, [])
            require(isinstance(icons, list) and icons, f"{field} must contain icons")
            for icon in icons:
                require(str(icon).endswith(".png"), f"Invalid icon extension: {icon}")
                require((PLUGIN_DIR / icon).is_file(), f"Missing icon: {icon}")


def validate_pcm_metadata() -> None:
    """Validate the PCM v2 metadata fields used by this package."""

    data = json.loads((ROOT / "metadata.json").read_text(encoding="utf-8"))
    required = {
        "name",
        "description",
        "description_full",
        "identifier",
        "type",
        "author",
        "license",
        "resources",
        "versions",
    }
    require(required.issubset(data), "PCM metadata is missing required fields")
    require(data.get("$schema") == "https://go.kicad.org/pcm/schemas/v2", "Unexpected PCM schema")
    require(bool(PCM_IDENTIFIER_PATTERN.fullmatch(str(data["identifier"]))), "Invalid PCM identifier")
    require(data["type"] == "plugin", "PCM type must be plugin")
    require(isinstance(data["author"].get("contact"), dict), "Author contact must be an object")
    require(isinstance(data["resources"], dict), "Resources must be an object")
    require(isinstance(data["versions"], list) and data["versions"], "PCM versions are required")
    latest = data["versions"][0]
    require(latest.get("version") == VERSION, "PCM version is not synchronized")
    require(latest.get("status") == "testing", "v0.0.2 PCM status must be testing")
    for version in data["versions"]:
        require(bool(VERSION_PATTERN.fullmatch(str(version.get("version", "")))), "Invalid package version")
        require(version.get("status") in {"stable", "testing", "development", "deprecated"}, "Invalid status")
        require(version.get("runtime") == "ipc", "PCM runtime must be ipc")
        require(
            bool(KICAD_VERSION_PATTERN.fullmatch(str(version.get("kicad_version", "")))),
            "Invalid KiCad version",
        )
        require(
            not any(key.startswith("download_") for key in version),
            "Archive metadata must not contain download_* fields",
        )


def validate_default_config() -> None:
    """Validate the distributed machine-readable default configuration."""

    path = PLUGIN_DIR / "default-config.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    require(isinstance(data, dict), "Default configuration root must be an object")
    required_sections = {
        "schema_version",
        "antenna",
        "fixes",
        "noise",
        "quantitative",
        "silkscreen",
        "edge",
        "stitching",
        "placement",
        "manufacturing",
        "ui",
    }
    require(required_sections.issubset(data), "Default configuration is missing sections")
    require(data["schema_version"] == 5, "Unexpected default configuration schema version")
    require(data["fixes"].get("dry_run") is True, "Default configuration must enable Dry-run")
    require(
        data["edge"].get("allow_destructive_edge_replacement") is False,
        "Destructive Edge.Cuts replacement must default off",
    )
    require(
        data["edge"].get("outline_strategy") == "convex_preserve_existing_concavities",
        "Default outline must be convex-first",
    )
    require(data["edge"].get("target_vertex_count") == 8, "Default target outline must use eight vertices")
    require(data["noise"].get("corner_pad_exclusion") is True, "Pad-area corner exclusion must default on")
    require(
        data["noise"].get("acute_corner_warning_deg") == 75.0,
        "Ordinary 90-degree corners must not be flagged by default",
    )
    require(data["noise"].get("long_net_diameter_scan_limit") == 32, "Unexpected route-diameter scan budget")
    require(
        data["antenna"].get("required_ground_connection_width_mm") == 1.0,
        "Required GND width-t default changed unexpectedly",
    )
    require(
        data["antenna"].get("pad_protection_margin_mm") == 0.3, "Pad-protection margin changed unexpectedly"
    )
    require(data["antenna"].get("protect_perimeter_ground") is True, "Perimeter GND must be protected")
    require(data["fixes"].get("rule_area_margin_mm") == 0.0, "Safe keepouts must not be expanded")
    require(
        data["fixes"].get("require_board_outline_for_new_copper") is True, "New copper must require Edge.Cuts"
    )
    require(
        data["fixes"].get("require_proven_safe_rule_area") is True,
        "Rule areas must require connectivity proof",
    )
    require(
        data["noise"].get("reference_gap_min_fraction") == 0.3,
        "Reference-gap false-positive guard changed unexpectedly",
    )
    require(
        data["noise"].get("ground_detour_warning_ratio") == 4.0, "Ground-detour default changed unexpectedly"
    )
    require(
        data["ui"].get("inactivity_timeout_minutes") == 0,
        "Long-running dashboards must not expire by default",
    )
    require(data["ui"].get("heartbeat_seconds") == 20, "Dashboard heartbeat default changed unexpectedly")
    manufacturing = data["manufacturing"]
    require(manufacturing.get("profile_id") == "jlcpcb_2l_economy", "Economy profile must be the default")
    require(manufacturing.get("layer_count") == 2, "JLCPCB default must use two copper layers")
    require(manufacturing.get("board_thickness_mm") == 1.6, "JLCPCB default thickness must be 1.6 mm")
    require(manufacturing.get("solder_mask_color") == "green", "JLCPCB default mask must be green")
    require(manufacturing.get("selected_track_width_mm") == 0.2, "JLCPCB default track width must be 0.2 mm")
    require(
        manufacturing.get("selected_track_widths_mm") == [0.2], "Default multi-track selection is invalid"
    )
    require(
        manufacturing.get("selected_via_preset_id") == "kicad_default", "KiCad default via must be selected"
    )
    require(
        manufacturing.get("selected_via_preset_ids") == ["kicad_default"],
        "Default multi-via selection is invalid",
    )
    require(
        data["fixes"].get("track_width_mm") == 0.2,
        "Automatic-fix track width must follow the default profile",
    )
    require(data["fixes"].get("via_diameter_mm") == 0.6, "Automatic-fix via diameter must be 0.6 mm")
    require(data["fixes"].get("via_drill_mm") == 0.3, "Automatic-fix via drill must be 0.3 mm")
    require(
        data["silkscreen"].get("text_width_mm") == 0.8,
        "Requested 0.8 mm silkscreen width must remain the default",
    )
    require(
        data["silkscreen"].get("text_height_mm") == 0.8,
        "Requested 0.8 mm silkscreen height must remain the default",
    )
    require(
        data["silkscreen"].get("text_thickness_mm") == 0.1,
        "Requested 0.10 mm silkscreen stroke must remain the default",
    )


def validate_python_sources() -> None:
    """Parse Python files, enforce Python 3.9 syntax, and guard IPC boundaries."""

    plugin_trees: list[ast.AST] = []
    paths = sorted(
        (*PLUGIN_DIR.rglob("*.py"), *(ROOT / "scripts").rglob("*.py"), *(ROOT / "tests").rglob("*.py"))
    )
    for path in paths:
        source = path.read_text(encoding="utf-8")
        feature_version = 9 if path.is_relative_to(PLUGIN_DIR) else None
        tree = ast.parse(source, filename=str(path), feature_version=feature_version)
        if path.is_relative_to(PLUGIN_DIR):
            plugin_trees.append(tree)
            if " | " in source:
                require(
                    "from __future__ import annotations" in source,
                    f"Python 3.9 union annotation requires postponed evaluation: {path}",
                )
    for tree in plugin_trees:
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                require(
                    all(alias.name != "pcbnew" for alias in node.names), "Legacy pcbnew/SWIG import found"
                )
            elif isinstance(node, ast.ImportFrom):
                require(node.module != "pcbnew", "Legacy pcbnew/SWIG import found")
            elif isinstance(node, ast.Match):
                raise ValueError("Python 3.10 pattern matching found in the Python 3.9 plugin surface")
    adapter = (PLUGIN_DIR / "emi_guardian" / "kicad_adapter.py").read_text(encoding="utf-8")
    require("from kipy import KiCad" in adapter, "Official IPC adapter import missing")
    require("from kipy.proto.common.types import KIID" in adapter, "KIID protobuf conversion is missing")
    require("get_items_by_id(list(kiids))" in adapter, "Finding navigation must pass KIID messages")
    require("common.Control.zoomFitSelection" in adapter, "KiCad finding navigation action missing")
    for module in ("ground_connectivity.py", "stitching.py", "placement.py"):
        require((PLUGIN_DIR / "emi_guardian" / module).is_file(), f"Required v0.0.2 module missing: {module}")


def validate_release_safety_contracts() -> None:
    """Guard v0.0.2's installer and antenna-apply safety invariants."""

    controller = (PLUGIN_DIR / "emi_guardian" / "controller.py").read_text(encoding="utf-8")
    require(
        "current_snapshot = self._adapter.snapshot()" in controller,
        "Antenna apply must reread the active board",
    )
    require(
        "current_report = analyze_board(current_snapshot" in controller, "Antenna apply must rerun analysis"
    )
    require("current_plan = plan_antenna_fixes(" in controller, "Antenna apply must rebuild the fix plan")
    require("_fix_action_safety_signature" in controller, "Antenna apply safety signature is missing")
    require("no changes were applied" in controller, "Stale antenna plans must fail without mutation")

    installer_paths = (
        ROOT / "installers" / "linux" / "install-or-update.sh",
        ROOT / "installers" / "macos" / "install-or-update.command",
        ROOT / "installers" / "windows" / "install-or-update.ps1",
    )
    for path in installer_paths:
        source = path.read_text(encoding="utf-8")
        lowered = source.lower()
        require(
            "without creating a backup copy" in lowered,
            f"Zero-backup installer contract missing: {path.name}",
        )
        require(
            "old_payload" not in lowered and "oldpayload" not in lowered,
            f"Old-plugin staging variable found: {path.name}",
        )
        require("rollback" not in lowered, f"Automatic rollback implementation found: {path.name}")
    require(
        'cp -R "$DESTINATION"' not in installer_paths[0].read_text(encoding="utf-8"),
        "Linux installer copies the old plugin",
    )
    require(
        'cp -R "$DESTINATION"' not in installer_paths[1].read_text(encoding="utf-8"),
        "macOS installer copies the old plugin",
    )
    require(
        "Copy-Item -LiteralPath $Destination -Destination"
        not in installer_paths[2].read_text(encoding="utf-8"),
        "Windows installer copies the old plugin",
    )


def _validate_safe_names(names: set[str]) -> None:
    """Reject cache files and archive path traversal."""

    for name in names:
        require(
            "__pycache__" not in name and not name.endswith(".pyc"), f"Cached bytecode in archive: {name}"
        )
        require(".." not in Path(name).parts, f"Unsafe archive path: {name}")
        require(not name.startswith(("/", "\\")), f"Absolute archive path: {name}")


def validate_archive(path: Path) -> None:
    """Validate the exact PCM ZIP directory structure."""

    require(path.is_file(), f"Archive not found: {path}")
    with zipfile.ZipFile(path) as archive:
        names = set(archive.namelist())
        require("metadata.json" in names, "PCM ZIP lacks metadata.json")
        require("plugins/plugin.json" in names, "PCM ZIP lacks plugins/plugin.json")
        require("plugins/default-config.json" in names, "PCM ZIP lacks plugins/default-config.json")
        require("plugins/open_dashboard.py" in names, "PCM ZIP lacks dashboard entrypoint")
        require("plugins/emi_guardian/__init__.py" in names, "PCM ZIP lacks package source")
        require("resources/icon.png" in names, "PCM ZIP lacks PCM icon")
        for name in names:
            require(
                name.startswith(("plugins/", "resources/")) or name == "metadata.json",
                f"Unexpected PCM root entry: {name}",
            )
        _validate_safe_names(names)


def validate_manual_archive(path: Path) -> None:
    """Validate the direct-extraction manual-install ZIP structure."""

    require(path.is_file(), f"Archive not found: {path}")
    root = "emi-guardian/"
    with zipfile.ZipFile(path) as archive:
        names = set(archive.namelist())
        require(root + "plugin.json" in names, "Manual ZIP lacks emi-guardian/plugin.json")
        require(root + "default-config.json" in names, "Manual ZIP lacks the default configuration")
        require(root + "open_dashboard.py" in names, "Manual ZIP lacks dashboard entrypoint")
        require(root + "emi_guardian/__init__.py" in names, "Manual ZIP lacks package source")
        require(root + "docs/EMI-Guardian-User-Manual-JA.html" in names, "Manual ZIP lacks Japanese manual")
        require(root + "docs/EMI-Guardian-User-Manual-EN.html" in names, "Manual ZIP lacks English manual")
        for name in names:
            require(name.startswith(root), f"Unexpected manual ZIP root entry: {name}")
        _validate_safe_names(names)


def validate_user_manual_archive(path: Path) -> None:
    """Validate the standalone bilingual user-manual archive."""

    require(path.is_file(), f"Archive not found: {path}")
    root = "emi-guardian-user-manuals/"
    required = {
        root + "EMI-Guardian-User-Manual-JA.html",
        root + "EMI-Guardian-User-Manual-EN.html",
        root + "EMI-Guardian-User-Manual-JA.md",
        root + "EMI-Guardian-User-Manual-EN.md",
        root + "README.txt",
    }
    with zipfile.ZipFile(path) as archive:
        names = set(archive.namelist())
        require(required.issubset(names), "User-manual ZIP is incomplete")
        for name in names:
            require(name.startswith(root), f"Unexpected user-manual ZIP root entry: {name}")
        _validate_safe_names(names)


def validate_installer_archive(path: Path, platform: str) -> None:
    """Validate one self-contained platform installer archive."""

    require(platform in {"windows", "macos", "linux"}, f"Unknown installer platform: {platform}")
    require(path.is_file(), f"Installer not found: {path}")
    root = f"emi-guardian-{VERSION}-{platform}/"
    payload = root + "payload/emi-guardian/"
    required = {
        root + "README-JA.md",
        root + "README-EN.md",
        payload + "plugin.json",
        payload + "requirements.txt",
        payload + "open_dashboard.py",
        payload + "emi_guardian/__init__.py",
    }
    platform_required = {
        "windows": {
            root + "Install-or-Update.cmd",
            root + "Uninstall.cmd",
            root + "install-or-update.ps1",
            root + "uninstall.ps1",
        },
        "macos": {root + "install-or-update.command", root + "uninstall.command"},
        "linux": {root + "install-or-update.sh", root + "uninstall.sh"},
    }
    with zipfile.ZipFile(path) as archive:
        names = set(archive.namelist())
        require(required.issubset(names), f"{platform} installer payload is incomplete")
        require(platform_required[platform].issubset(names), f"{platform} installer scripts are incomplete")
        for name in names:
            require(name.startswith(root), f"Unexpected installer root entry: {name}")
        if platform in {"macos", "linux"}:
            for name in platform_required[platform]:
                mode = archive.getinfo(name).external_attr >> 16
                require(mode & 0o111, f"Installer script is not executable: {name}")
        _validate_safe_names(names)


def validate_all_installers_archive(path: Path) -> None:
    """Validate the convenience archive containing all platform ZIPs."""

    require(path.is_file(), f"Installer bundle not found: {path}")
    root = f"emi-guardian-{VERSION}-installers/"
    required = {
        root + f"emi-guardian-{VERSION}-windows-installer.zip",
        root + f"emi-guardian-{VERSION}-macos-installer.zip",
        root + f"emi-guardian-{VERSION}-linux-installer.zip",
        root + "SHA256SUMS-installers",
    }
    with zipfile.ZipFile(path) as archive:
        names = set(archive.namelist())
        require(required.issubset(names), "All-platform installer bundle is incomplete")
        _validate_safe_names(names)


def validate_source_archive(path: Path) -> None:
    """Validate source-release structure and reject local development artifacts."""

    require(path.is_file(), f"Source archive not found: {path}")
    root = f"kicad-emi-guardian-{VERSION}/"
    required = {
        root + "LICENSE",
        root + "README.md",
        root + "pyproject.toml",
        root + ".github/workflows/ci.yml",
        root + "plugin/plugin.json",
        root + "plugin/emi_guardian/__init__.py",
        root + "scripts/build_package.py",
        root + "tests/test_plugin_metadata.py",
    }
    forbidden_parts = {
        ".venv",
        "venv",
        "build",
        "dist",
        ".git",
        ".pytest_cache",
        ".ruff_cache",
        ".mypy_cache",
        "_build",
        "_generated",
        "__pycache__",
    }
    with zipfile.ZipFile(path) as archive:
        names = set(archive.namelist())
        require(required.issubset(names), "Source archive is incomplete")
        for name in names:
            require(name.startswith(root), f"Unexpected source archive root entry: {name}")
            parts = Path(name).parts
            require(not forbidden_parts.intersection(parts), f"Local artifact in source archive: {name}")
            require(
                not any(part.endswith((".egg-info", ".dist-info")) for part in parts),
                f"Build metadata in source archive: {name}",
            )
            require(
                not name.endswith((".pyc", ".pyo", ".DS_Store", "Thumbs.db")),
                f"Generated file in source archive: {name}",
            )
        _validate_safe_names(names)


def run_optional_checks() -> None:
    """Run syntax tools that are available in the release environment."""

    subprocess.run(
        [sys.executable, "-m", "compileall", "-q", "plugin", "tests", "scripts"], cwd=ROOT, check=True
    )
    node = shutil.which("node")
    if node:
        subprocess.run([node, "--check", "plugin/emi_guardian/web/app.js"], cwd=ROOT, check=True)
    bash = shutil.which("bash")
    if bash:
        for path in sorted((ROOT / "installers" / "linux").glob("*.sh")):
            subprocess.run([bash, "-n", str(path)], check=True)
        for path in sorted((ROOT / "installers" / "macos").glob("*.command")):
            subprocess.run([bash, "-n", str(path)], check=True)
    pwsh = shutil.which("pwsh")
    if pwsh:
        for path in sorted((ROOT / "installers" / "windows").glob("*.ps1")):
            command = (
                "$errors=$null;$tokens=$null;"
                f"[System.Management.Automation.Language.Parser]::ParseFile('{path}',[ref]$tokens,[ref]$errors)>$null;"
                "if($errors.Count){$errors|ForEach-Object{Write-Error $_};exit 1}"
            )
            subprocess.run([pwsh, "-NoProfile", "-Command", command], check=True)


def main() -> int:
    """Command-line entry point."""

    parser = argparse.ArgumentParser()
    parser.add_argument("archive", nargs="?", type=Path)
    args = parser.parse_args()
    validate_plugin_manifest()
    validate_pcm_metadata()
    validate_default_config()
    validate_python_sources()
    validate_release_safety_contracts()
    run_optional_checks()
    if args.archive is not None:
        archive = args.archive.resolve()
        if "all-platform-installers" in archive.name:
            validate_all_installers_archive(archive)
        elif "windows-installer" in archive.name:
            validate_installer_archive(archive, "windows")
        elif "macos-installer" in archive.name:
            validate_installer_archive(archive, "macos")
        elif "linux-installer" in archive.name:
            validate_installer_archive(archive, "linux")
        elif "user-manuals" in archive.name:
            validate_user_manual_archive(archive)
        elif "manual-install" in archive.name:
            validate_manual_archive(archive)
        elif "source" in archive.name:
            validate_source_archive(archive)
        else:
            validate_archive(archive)
    print("Package validation passed.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ValueError as exc:
        print(f"Package validation failed: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
