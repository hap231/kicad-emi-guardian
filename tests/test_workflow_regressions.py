"""Workflow regression tests for EMI Guardian.

These tests focus on the failures reported against the pre-release dashboard
and on the safety properties of newly added planners.  They intentionally use
KiCad-independent snapshots except for a narrow protobuf-adapter contract test.
"""

from __future__ import annotations

import math
import sys
import types
from pathlib import Path

import pytest

from conftest import footprint, rectangle, rectangular_edges, snapshot, text
from emi_guardian.antenna import detect_ground_antennas
from emi_guardian.config import (
    AntennaConfig,
    AppConfig,
    EdgeConfig,
    FixConfig,
    PlacementConfig,
    SilkscreenConfig,
    StitchingConfig,
)
from emi_guardian.edge_optimizer import propose_edge_outline
from emi_guardian.fixes import plan_antenna_fixes
from emi_guardian.geometry import polygon_area
from emi_guardian.ground_connectivity import build_ground_connectivity
from emi_guardian.kicad_adapter import KicadIpcAdapter, _kiid_messages
from emi_guardian.models import (
    BoardEdge,
    BoundingBox,
    CopperZone,
    FixKind,
    FootprintSnapshot,
    Pad,
    Point,
    Polygon,
    TrackSegment,
    Via,
)
from emi_guardian.noise import analyze_noise
from emi_guardian.placement import plan_component_placement
from emi_guardian.raster import cells_to_outline, detect_narrow_features
from emi_guardian.silkscreen import plan_silkscreen
from emi_guardian.stitching import _via_disk_inside_polygons, plan_via_stitching


def _zone(
    item_id: str,
    net: str,
    layers: tuple[str, ...],
    filled: dict[str, tuple[Polygon, ...]],
) -> CopperZone:
    """Build a filled-zone fixture using the first polygon as its outline."""

    first = next(iter(next(iter(filled.values()))))
    ids = tuple(0 if layer == "F.Cu" else 31 for layer in layers)
    return CopperZone(item_id, net, layers, ids, first, filled)


def _polygon_edges(points: tuple[Point, ...]) -> tuple[BoardEdge, ...]:
    """Return a closed edge loop for an arbitrary polygon."""

    return tuple(
        BoardEdge(f"edge-{index}", points[index], points[(index + 1) % len(points)])
        for index in range(len(points))
    )


def test_kicad_locator_passes_kiid_messages_not_strings(monkeypatch: pytest.MonkeyPatch) -> None:
    """Protect the exact API contract that caused the reported locate failure."""

    class FakeKIID:
        def __init__(self, *, value: str) -> None:
            self.value = value

    common = types.ModuleType("kipy.proto.common.types")
    common.KIID = FakeKIID  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "kipy", types.ModuleType("kipy"))
    monkeypatch.setitem(sys.modules, "kipy.proto", types.ModuleType("kipy.proto"))
    monkeypatch.setitem(sys.modules, "kipy.proto.common", types.ModuleType("kipy.proto.common"))
    monkeypatch.setitem(sys.modules, "kipy.proto.common.types", common)

    messages = _kiid_messages(("b7e92463-757b-4d6a-aa6f-2c890adecb11", "second"))
    assert all(isinstance(item, FakeKIID) for item in messages)
    assert [item.value for item in messages] == [
        "b7e92463-757b-4d6a-aa6f-2c890adecb11",
        "second",
    ]


class _MessageCheckingBoard:
    def __init__(self) -> None:
        self.received = []
        self.selected = []

    def clear_selection(self) -> None:
        self.selected.clear()

    def get_items_by_id(self, ids):
        self.received = list(ids)
        assert all(not isinstance(item, str) for item in self.received)
        return [object() for _ in self.received]

    def add_to_selection(self, items):
        self.selected = list(items)


class _MessageCheckingKiCad:
    def ping(self) -> None:
        return None

    def run_action(self, _name: str) -> None:
        return None


def test_locate_items_normalizes_arc_suffix_and_selects_objects(monkeypatch: pytest.MonkeyPatch) -> None:
    """Resolve source UUIDs from split arc segments before selection."""

    class FakeKIID:
        def __init__(self, *, value: str) -> None:
            self.value = value

    common = types.ModuleType("kipy.proto.common.types")
    common.KIID = FakeKIID  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "kipy", types.ModuleType("kipy"))
    monkeypatch.setitem(sys.modules, "kipy.proto", types.ModuleType("kipy.proto"))
    monkeypatch.setitem(sys.modules, "kipy.proto.common", types.ModuleType("kipy.proto.common"))
    monkeypatch.setitem(sys.modules, "kipy.proto.common.types", common)

    adapter = object.__new__(KicadIpcAdapter)
    adapter._board = _MessageCheckingBoard()  # type: ignore[attr-defined]
    adapter._kicad = _MessageCheckingKiCad()  # type: ignore[attr-defined]
    adapter._retry_count = 0  # type: ignore[attr-defined]
    adapter._timeout_ms = 5000  # type: ignore[attr-defined]
    result = adapter.locate_items(("uuid-one:a", "uuid-one:b", "uuid-two"))
    assert [item.value for item in adapter._board.received] == ["uuid-one", "uuid-two"]  # type: ignore[attr-defined]
    assert result["selected_count"] == 2


def test_ground_connectivity_treats_through_hole_wildcard_pad_as_anchor() -> None:
    """Do not report an island when a THT pad uses KiCad's wildcard Cu layer."""

    main = rectangle(0, 0, 10, 10)
    remote = rectangle(20, 0, 24, 4)
    zone = _zone("gnd-zone", "GND", ("F.Cu", "B.Cu"), {"F.Cu": (main, remote), "B.Cu": (main,)})
    pad = Pad("gnd-pad", "j1", "1", Point(2, 2), BoundingBox(1.5, 1.5, 2.5, 2.5), "GND", ("*.Cu",))
    via = Via("gnd-via", Point(8, 8), 0.6, 0.3, "GND")
    graph = build_ground_connectivity(snapshot(zones=(zone,), pads=(pad,), vias=(via,)), r"^GND$")
    anchored = [item for item in graph.components.values() if item.anchored]
    unanchored = [item for item in graph.components.values() if item.regions and not item.anchored]
    assert len(anchored) == 1
    assert "gnd-pad" in anchored[0].pad_ids
    assert "gnd-via" in anchored[0].via_ids
    assert len(unanchored) == 1
    assert math.isclose(unanchored[0].area_mm2, polygon_area(remote), rel_tol=1.0e-6)


def test_connected_multilayer_ground_fill_is_not_reported_as_island() -> None:
    """Union zones, a through via, and an anchored pad before island classification."""

    copper = rectangle(0, 0, 12, 8)
    zone = _zone("gnd", "GND", ("F.Cu", "B.Cu"), {"F.Cu": (copper,), "B.Cu": (copper,)})
    pad = Pad("p-gnd", "u1", "1", Point(1, 1), BoundingBox(0.6, 0.6, 1.4, 1.4), "GND", ("*.Cu",))
    via = Via("v-gnd", Point(10, 6), 0.6, 0.3, "GND")
    board = snapshot(zones=(zone,), pads=(pad,), vias=(via,))
    findings = detect_ground_antennas(board, AntennaConfig(minimum_appendage_length_mm=50.0))
    assert not [item for item in findings if item.rule_id == "antenna.island"]


def test_narrow_ground_appendage_is_detected_and_rule_area_is_preferred() -> None:
    """Detect a real pour stub and avoid a redundant track laid on its own fill."""

    appendage = Polygon(
        (
            Point(0, 0),
            Point(10, 0),
            Point(10, 4.4),
            Point(17, 4.4),
            Point(17, 5.6),
            Point(10, 5.6),
            Point(10, 10),
            Point(0, 10),
        )
    )
    zone = _zone(
        "gnd-stub", "GND", ("F.Cu", "B.Cu"), {"F.Cu": (appendage,), "B.Cu": (rectangle(0, 0, 10, 10),)}
    )
    pad = Pad("gnd-pad", "u1", "1", Point(2, 2), BoundingBox(1.5, 1.5, 2.5, 2.5), "GND", ("F.Cu",))
    board = snapshot(
        zones=(zone,),
        pads=(pad,),
        edges=rectangular_edges(-2, -2, 22, 12),
    )
    config = AntennaConfig(
        raster_step_mm=0.20,
        narrow_neck_width_mm=1.60,
        minimum_appendage_area_mm2=0.50,
        minimum_appendage_length_mm=2.0,
    )
    findings = [item for item in detect_ground_antennas(board, config) if item.rule_id == "antenna.appendage"]
    assert findings
    plan = plan_antenna_fixes(board, findings, config, FixConfig())
    assert plan.actions
    assert all(action.kind == FixKind.RULE_AREA for action in plan.actions)
    assert all(
        alternative.kind != FixKind.TRACK_BRIDGE
        for alternatives in plan.alternatives.values()
        for alternative in alternatives
    )
    chosen = plan.actions[0]
    assert chosen.polygon is not None
    assert len(chosen.polygon.outline) >= 4
    assert chosen.parameters["shape_source"] == "safe_keepout_polygon"


def test_raster_rule_area_preserves_non_rectangular_feature_shape() -> None:
    """Create an orthogonal cell-union outline rather than a destructive bbox."""

    l_shape = Polygon((Point(0, 0), Point(8, 0), Point(8, 1), Point(2, 1), Point(2, 5), Point(0, 5)))
    features = detect_narrow_features(l_shape, 0.25, 2.0, 100_000)
    assert features
    outline = cells_to_outline(max(features, key=lambda item: item.area_mm2))
    bounds_area = (max(point.x for point in outline.outline) - min(point.x for point in outline.outline)) * (
        max(point.y for point in outline.outline) - min(point.y for point in outline.outline)
    )
    assert len(outline.outline) > 4
    assert polygon_area(outline) < bounds_area * 0.9


def test_silkscreen_hides_mounting_holes_and_logos_and_uses_010_stroke() -> None:
    """Apply the requested field policy without moving decorative values far away."""

    mounting = FootprintSnapshot(
        "mh1",
        "H1",
        "MountingHole_3.2mm",
        Point(2, 2),
        "F.Cu",
        BoundingBox(1, 1, 3, 3),
        text("H1", Point(2, 1)),
        text("MountingHole_3.2mm", Point(2, 3)),
        library_id="MountingHole:MountingHole_3.2mm_M3",
    )
    logo = FootprintSnapshot(
        "logo1",
        "G***",
        "LOGO_company",
        Point(6, 2),
        "F.Cu",
        BoundingBox(5, 1, 7, 3),
        text("G***", Point(6, 1)),
        text("LOGO_company", Point(6, 3)),
        library_id="Symbol:LOGO_company",
    )
    resistor = footprint("r1", "R1", "10k", BoundingBox(4, 5, 6, 7))
    plan = plan_silkscreen(
        snapshot(footprints=(mounting, logo, resistor), edges=rectangular_edges(0, 0, 10, 10)),
        SilkscreenConfig(),
    )
    hidden = {item.footprint_id for item in plan.placements if not item.show_value}
    assert hidden == {"mh1", "logo1"}
    value = next(item for item in plan.placements if item.footprint_id == "r1")
    assert value.text_thickness_mm == 0.10
    assert value.reference_layer == "F.Fab"
    assert value.angle_deg in {0.0, 90.0, 45.0, -45.0}
    assert value.distance_from_footprint_mm <= 2.5 + 1.0e-9


def test_silkscreen_fallback_stays_on_owner_and_requires_manual_review() -> None:
    """Prefer an unambiguous on-footprint fallback over a distant orphan label."""

    fp = footprint("u1", "U1", "MCU", BoundingBox(4, 4, 8, 8))
    blocker = Pad("block", "other", "1", Point(6, 6), BoundingBox(-50, -50, 50, 50), "SIG", ("F.Cu",))
    plan = plan_silkscreen(
        snapshot(footprints=(fp,), pads=(blocker,), edges=rectangular_edges(0, 0, 12, 12)), SilkscreenConfig()
    )
    proposal = next(item for item in plan.placements if item.footprint_id == "u1")
    assert proposal.manual_review is True
    assert proposal.default_selected is False
    assert proposal.position == fp.bounds.center
    assert proposal.distance_from_footprint_mm == 0.0


def test_outline_optimizer_never_replaces_compact_pentagon_with_larger_rectangle() -> None:
    """Regression for the photographed 1329.7 mm2 to 2071.1 mm2 expansion."""

    points = (Point(0, 10), Point(12, 0), Point(34, 0), Point(42, 12), Point(36, 34), Point(0, 34))
    board = snapshot(
        footprints=(footprint(bounds=BoundingBox(5, 5, 32, 30)),),
        edges=_polygon_edges(points),
    )
    config = EdgeConfig(
        mode="orthogonal",
        allow_diagonal_edges=False,
        target_vertex_count=4,
        fillet_radius_mm=1.0,
        minimum_ground_band_mm=0.1,
        maximum_area_reduction_percent=50.0,
        reject_area_increase=True,
        maximum_area_increase_percent=0.0,
    )
    proposal = propose_edge_outline(board, config, r"^GND$")
    assert proposal.proposed_area_mm2 <= proposal.original_area_mm2 + 1.0e-6
    assert proposal.reduction_percent >= -1.0e-8
    if proposal.operation == "preserve_current":
        assert proposal.area_guard_applied is True


def test_smooth_and_fillet_operations_keep_grid_snapped_polygon_vertices() -> None:
    """Keep the pre-fillet line-intersection polygon on the selected grid."""

    board = snapshot(edges=rectangular_edges(0, 0, 20, 10))
    for operation in ("smooth", "fillet"):
        proposal = propose_edge_outline(
            board,
            EdgeConfig(grid_mm=0.5, fillet_radius_mm=1.0, minimum_ground_band_mm=0.1),
            r"^GND$",
            operation=operation,
        )
        assert proposal.operation == operation
        assert all(abs(point.x / 0.5 - round(point.x / 0.5)) < 1.0e-8 for point in proposal.polygon.outline)
        assert all(abs(point.y / 0.5 - round(point.y / 0.5)) < 1.0e-8 for point in proposal.polygon.outline)
        assert any(item.kind == "arc" for item in proposal.primitives)


def test_stitching_requires_full_via_disk_inside_copper() -> None:
    """Reject centers whose annulus would hang outside a fill or into a hole."""

    polygon = rectangle(0, 0, 10, 10)
    assert _via_disk_inside_polygons(Point(5, 5), 0.3, (polygon,))
    assert not _via_disk_inside_polygons(Point(0.15, 5), 0.3, (polygon,))


def test_stitching_prioritizes_vertices_and_partial_selection_disables_removal() -> None:
    """Protect corner stitching and never remove a full old ring for a partial replacement."""

    copper = rectangle(0, 0, 30, 20)
    zone = _zone("gnd", "GND", ("F.Cu", "B.Cu"), {"F.Cu": (copper,), "B.Cu": (copper,)})
    board = snapshot(zones=(zone,), edges=rectangular_edges(0, 0, 30, 20))
    config = StitchingConfig(edge_offset_mm=1.2, vertex_offset_mm=1.2, spacing_mm=6.0, minimum_spacing_mm=2.5)
    plan = plan_via_stitching(board, config, rebuild_perimeter=True)
    assert plan.candidates
    assert any(item.critical_vertex for item in plan.candidates)
    selected = plan.selected((plan.candidates[0].candidate_id,), rebuild_perimeter=True)
    assert selected.rebuild_perimeter is False
    assert selected.removable_via_ids == ()
    assert any("only part" in warning for warning in selected.warnings)


def test_initial_placement_groups_by_sheet_and_puts_capacitor_near_matching_pad() -> None:
    """Use schematic blocks and net evidence for a useful unrouted starting layout."""

    u_pad = Pad("u-vdd", "u1", "2", Point(10, 10), BoundingBox(9.6, 9.6, 10.4, 10.4), "3V3", ("F.Cu",))
    c_pad = Pad("c-vdd", "c1", "1", Point(30, 30), BoundingBox(29.6, 29.6, 30.4, 30.4), "3V3", ("F.Cu",))
    u1 = FootprintSnapshot(
        "u1",
        "U1",
        "MCU",
        Point(10, 10),
        "F.Cu",
        BoundingBox(7, 7, 13, 13),
        text("U1", Point(10, 6)),
        text("MCU", Point(10, 14)),
        pads=(u_pad,),
        sheet_path="/control/",
    )
    c1 = FootprintSnapshot(
        "c1",
        "C1",
        "100nF",
        Point(30, 30),
        "F.Cu",
        BoundingBox(29, 29, 31, 31),
        text("C1", Point(30, 28)),
        text("100nF", Point(30, 32)),
        pads=(c_pad,),
        sheet_path="/control/",
    )
    locked = FootprintSnapshot(
        "j1",
        "J1",
        "USB",
        Point(45, 5),
        "F.Cu",
        BoundingBox(42, 2, 48, 8),
        text("J1", Point(45, 1)),
        text("USB", Point(45, 9)),
        locked=True,
        sheet_path="/io/",
    )
    plan = plan_component_placement(
        snapshot(footprints=(u1, c1, locked), pads=(u_pad, c_pad), edges=rectangular_edges(0, 0, 60, 40)),
        PlacementConfig(),
    )
    assert {group.group_id for group in plan.groups} == {"/control/", "/io/"}
    cap = next(item for item in plan.placements if item.footprint_id == "c1")
    core = next(item for item in plan.placements if item.footprint_id == "u1")
    lock = next(item for item in plan.placements if item.footprint_id == "j1")
    assert cap.reason == "capacitor_near_matching_pad"
    assert cap.associated_footprint_id == "u1"
    assert cap.associated_pad_id == "u-vdd"
    assert math.dist((cap.position.x, cap.position.y), (core.position.x, core.position.y)) < 15.0
    assert lock.position == lock.old_position
    assert lock.default_selected is False


def test_two_layer_noise_uses_reference_continuity_not_generic_return_via_rule() -> None:
    """Suppress the multi-layer transition heuristic while retaining plane-gap analysis."""

    signal = TrackSegment("sig", Point(1, 5), Point(19, 5), 0.2, "F.Cu", 0, "CLK")
    # Ground exists only on the left side of the opposite layer, so the trace
    # spends a substantial length without a continuous reference plane.
    gnd = _zone("gnd", "GND", ("B.Cu",), {"B.Cu": (rectangle(0, 0, 8, 10),)})
    board = snapshot(tracks=(signal,), zones=(gnd,), edges=rectangular_edges(0, 0, 20, 10))
    findings = analyze_noise(board, AppConfig().noise, r"^GND$")
    rules = {item.rule_id for item in findings}
    assert "noise.return_via" not in rules
    assert "noise.reference_gap" in rules


def test_dashboard_contains_click_hover_preview_location_and_layer_bulk_controls() -> None:
    """Prevent regressions in the interactive finding workflow."""

    root = Path(__file__).resolve().parents[1] / "plugin" / "emi_guardian" / "web"
    javascript = (root / "app.js").read_text(encoding="utf-8")
    html = (root / "index.html").read_text(encoding="utf-8")
    assert "data-preview-finding=" in javascript
    assert "data-locate-finding=" in javascript
    assert "showPreviewTooltip" in javascript
    assert "setHoverFinding" in javascript
    assert "openFinding(marker.dataset.findingId)" in javascript
    assert 'data-layer-action="all"' in javascript
    assert 'data-layer-action="none"' in javascript
    assert "state.layerVisibility.Findings = true" in javascript
    assert 'id="edgeLayerToggles"' in html
    assert "appendPreviewGeometry(fragment, { stitching: true })" in javascript


def test_diagonal_configuration_auto_enables_diagonal_edges() -> None:
    """Avoid the contradictory UI state reported by the user."""

    from emi_guardian.config import config_from_mapping

    config = config_from_mapping({"edge": {"mode": "diagonal", "allow_diagonal_edges": False}})
    assert config.edge.mode == "diagonal"
    assert config.edge.allow_diagonal_edges is True


def test_partial_fix_and_silkscreen_adoption_only_keeps_selected_ids() -> None:
    """Verify the backend contract used by dashboard checkboxes."""

    appendage = Polygon(
        (
            Point(0, 0),
            Point(10, 0),
            Point(10, 4.4),
            Point(17, 4.4),
            Point(17, 5.6),
            Point(10, 5.6),
            Point(10, 10),
            Point(0, 10),
        )
    )
    zone = _zone("z1", "GND", ("F.Cu",), {"F.Cu": (appendage,)})
    pad = Pad("gnd-pad", "u1", "1", Point(2, 2), BoundingBox(1.5, 1.5, 2.5, 2.5), "GND", ("F.Cu",))
    board = snapshot(
        zones=(zone,),
        pads=(pad,),
        edges=rectangular_edges(-2, -2, 22, 12),
    )
    antenna_config = AntennaConfig(
        raster_step_mm=0.20,
        narrow_neck_width_mm=1.60,
        minimum_appendage_area_mm2=0.50,
        minimum_appendage_length_mm=2.0,
    )
    finding = next(
        item for item in detect_ground_antennas(board, antenna_config) if item.rule_id == "antenna.appendage"
    )
    fix_plan = plan_antenna_fixes(board, (finding,), antenna_config, FixConfig())
    selected_fix = fix_plan.selected((fix_plan.actions[0].action_id,))
    assert len(selected_fix.actions) == 1

    silk = plan_silkscreen(
        snapshot(
            footprints=(footprint("r1"), footprint("r2", "R2", "20k", BoundingBox(8, 4, 10, 6))),
            edges=rectangular_edges(0, 0, 14, 10),
        ),
        SilkscreenConfig(),
    )
    chosen = silk.placements[0].placement_id
    selected_silk = silk.selected((chosen,))
    assert [item.placement_id for item in selected_silk.placements] == [chosen]


def test_fix_planner_uses_wildcard_through_hole_pad_as_same_layer_anchor() -> None:
    """Treat ``*.Cu`` pads as valid anchors on the source layer in fix planning."""

    appendage = Polygon(
        (
            Point(0, 0),
            Point(10, 0),
            Point(10, 4.4),
            Point(17, 4.4),
            Point(17, 5.6),
            Point(10, 5.6),
            Point(10, 10),
            Point(0, 10),
        )
    )
    zone = _zone(
        "gnd-stub", "GND", ("F.Cu", "B.Cu"), {"F.Cu": (appendage,), "B.Cu": (rectangle(0, 0, 10, 10),)}
    )
    pad = Pad("gnd-pad", "j1", "1", Point(2, 2), BoundingBox(1.5, 1.5, 2.5, 2.5), "GND", ("*.Cu",))
    board = snapshot(
        zones=(zone,),
        pads=(pad,),
        edges=rectangular_edges(-2, -2, 22, 12),
    )
    antenna_config = AntennaConfig(
        raster_step_mm=0.20,
        narrow_neck_width_mm=1.60,
        minimum_appendage_area_mm2=0.50,
        minimum_appendage_length_mm=2.0,
    )
    finding = next(
        item for item in detect_ground_antennas(board, antenna_config) if item.rule_id == "antenna.appendage"
    )
    plan = plan_antenna_fixes(board, (finding,), antenna_config, FixConfig())
    assert plan.actions
    assert plan.actions[0].net == "GND"
