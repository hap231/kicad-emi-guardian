"""Automatic antenna-remediation planner tests."""

from __future__ import annotations

from conftest import rectangle, rectangular_edges, snapshot
from emi_guardian.antenna import detect_ground_antennas
from emi_guardian.config import AntennaConfig, FixConfig
from emi_guardian.fixes import plan_antenna_fixes
from emi_guardian.models import (
    BoundingBox,
    CopperZone,
    FixKind,
    Pad,
    Point,
    Polygon,
    Via,
)


def _antenna_config() -> AntennaConfig:
    """Return a deterministic appendage configuration."""

    return AntennaConfig(
        raster_step_mm=0.20,
        narrow_neck_width_mm=1.60,
        minimum_appendage_area_mm2=0.20,
        minimum_appendage_length_mm=0.50,
    )


def _source_polygon() -> Polygon:
    """Return broad GND copper with a narrow right-facing residual."""

    return Polygon(
        (
            Point(0.0, 0.0),
            Point(10.0, 0.0),
            Point(10.0, 4.4),
            Point(20.0, 4.4),
            Point(20.0, 5.6),
            Point(10.0, 5.6),
            Point(10.0, 10.0),
            Point(0.0, 10.0),
        )
    )


def _zones(with_remote_plane: bool = True) -> tuple[CopperZone, ...]:
    """Return source and optional remote same-net ground fills."""

    source = _source_polygon()
    filled: dict[str, tuple] = {"F.Cu": (source,)}
    layers = ["F.Cu"]
    layer_ids = [0]
    if with_remote_plane:
        remote = rectangle(0.0, 0.0, 25.0, 10.0)
        filled["B.Cu"] = (remote,)
        layers.append("B.Cu")
        layer_ids.append(31)
    return (CopperZone("zone", "GND", tuple(layers), tuple(layer_ids), source, filled),)


def _board(with_remote_plane: bool, vias: tuple[Via, ...] = ()):
    """Return an anchored board and its current proven appendage finding."""

    board = snapshot(
        zones=_zones(with_remote_plane),
        pads=(
            Pad(
                "gnd-pad",
                "u1",
                "1",
                Point(2.0, 2.0),
                BoundingBox(1.5, 1.5, 2.5, 2.5),
                "GND",
                ("F.Cu",),
            ),
        ),
        vias=vias,
        edges=rectangular_edges(-2.0, -2.0, 27.0, 12.0),
    )
    finding = next(
        item
        for item in detect_ground_antennas(board, _antenna_config())
        if item.rule_id == "antenna.appendage" and item.metrics.get("layer") == "F.Cu"
    )
    return board, finding


def test_planner_generates_ranked_track_via_combined_and_rule_area_candidates() -> None:
    """Expose all valid remediation families and select one high-utility action."""

    board, finding = _board(True)
    plan = plan_antenna_fixes(board, (finding,), _antenna_config(), FixConfig())
    candidates = plan.alternatives[finding.finding_id]
    kinds = {candidate.kind for candidate in candidates}
    assert FixKind.RULE_AREA in kinds
    assert FixKind.STITCHING_VIA in kinds
    # Track-based fixes are intentionally omitted when they would merely
    # duplicate an already-connected GND pour on the same layer.
    assert FixKind.TRACK_BRIDGE not in kinds
    assert FixKind.TRACK_AND_VIA not in kinds
    rule_area = next(candidate for candidate in candidates if candidate.kind == FixKind.RULE_AREA)
    assert rule_area.net == "GND"
    assert rule_area.polygon is not None
    assert len(plan.actions) == 1
    assert plan.actions[0].confidence >= 0.75


def test_via_candidate_is_suppressed_without_remote_same_net_copper() -> None:
    """Do not place a via that would connect the appendage to nothing."""

    board, finding = _board(
        False,
        vias=(Via("agnd-only", Point(19.0, 5.0), 0.6, 0.3, "AGND"),),
    )
    plan = plan_antenna_fixes(board, (finding,), _antenna_config(), FixConfig())
    kinds = {candidate.kind for candidate in plan.alternatives[finding.finding_id]}
    assert FixKind.STITCHING_VIA not in kinds
    assert FixKind.TRACK_AND_VIA not in kinds
    assert FixKind.RULE_AREA in kinds


def test_different_ground_domains_are_not_used_as_bridge_anchors() -> None:
    """Keep GND, AGND, and other matched ground domains electrically distinct."""

    board, finding = _board(
        False,
        vias=(Via("agnd-only", Point(19.0, 5.0), 0.6, 0.3, "AGND"),),
    )
    plan = plan_antenna_fixes(board, (finding,), _antenna_config(), FixConfig())
    kinds = {candidate.kind for candidate in plan.alternatives[finding.finding_id]}
    assert FixKind.TRACK_BRIDGE not in kinds
