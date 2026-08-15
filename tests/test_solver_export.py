"""External-solver interchange export tests."""

from __future__ import annotations

import json

from conftest import snapshot
from emi_guardian.config import QuantitativeConfig
from emi_guardian.models import Point, TrackSegment
from emi_guardian.solver_export import export_solver_manifest


def test_solver_export_is_explicitly_unsolved_and_has_no_implicit_ports(tmp_path) -> None:
    """Prevent geometry export from being mistaken for a validated EM result."""

    board = snapshot(tracks=(TrackSegment("t1", Point(0.0, 0.0), Point(10.0, 0.0), 0.2, "F.Cu", 0, "SIG"),))
    paths = export_solver_manifest(board, tmp_path, QuantitativeConfig(external_solver="openems"))
    manifest = json.loads(paths["manifest"].read_text(encoding="utf-8"))
    assert manifest["ports"] == []
    assert "must be defined" in manifest["solver"]["status"]
    assert "not a solved model" in paths["readme"].read_text(encoding="utf-8").lower()
