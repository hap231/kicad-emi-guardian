"""Read canonical project metadata without adding a TOML dependency."""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VERSION_PATTERN = re.compile(r'^version\s*=\s*"(?P<version>\d+\.\d+\.\d+)"\s*$')


def project_version(pyproject: Path = ROOT / "pyproject.toml") -> str:
    """Return the version declared in the PEP 621 project table."""

    in_project_table = False
    versions: list[str] = []
    for raw_line in pyproject.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if line.startswith("[") and line.endswith("]"):
            in_project_table = line == "[project]"
            continue
        if in_project_table and (match := VERSION_PATTERN.fullmatch(line)):
            versions.append(match.group("version"))
    if len(versions) != 1:
        raise ValueError(f"Expected one [project] version in {pyproject}, found {len(versions)}")
    return versions[0]
