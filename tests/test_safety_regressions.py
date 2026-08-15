"""Safety and regression tests for EMI Guardian."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest
from tools.project_metadata import project_version

from conftest import rectangle, rectangular_edges, snapshot, text
from emi_guardian.antenna import detect_ground_antennas
from emi_guardian.antenna_geometry import _flood
from emi_guardian.config import AntennaConfig, FixConfig, NoiseConfig, PlacementConfig
from emi_guardian.fixes import (
    _polygon_intersects_box,
    _track_clear,
    _track_inside_board,
    plan_antenna_fixes,
)
from emi_guardian.models import (
    BoardEdge,
    BoundingBox,
    CopperZone,
    Finding,
    FixKind,
    FootprintSnapshot,
    Pad,
    Point,
    Polygon,
    Severity,
    TrackSegment,
)
from emi_guardian.noise import analyze_noise
from emi_guardian.placement import plan_component_placement

ROOT = Path(__file__).resolve().parents[1]


def _zone(item_id: str, polygon: Polygon, *, layers: tuple[str, ...] = ("F.Cu",)) -> CopperZone:
    """Build a same-net filled GND zone fixture."""

    ids = tuple(0 if layer == "F.Cu" else 31 for layer in layers)
    return CopperZone(
        item_id,
        "GND",
        layers,
        ids,
        polygon,
        {layer: (polygon,) for layer in layers},
    )


def _tail_polygon() -> Polygon:
    """Return a broad body with a 1.2 mm wide right-facing appendage."""

    return Polygon(
        (
            Point(0.0, 0.0),
            Point(10.0, 0.0),
            Point(10.0, 4.4),
            Point(17.0, 4.4),
            Point(17.0, 5.6),
            Point(10.0, 5.6),
            Point(10.0, 10.0),
            Point(0.0, 10.0),
        )
    )


def _antenna_config() -> AntennaConfig:
    """Return a fine deterministic configuration for safety fixtures."""

    return AntennaConfig(
        raster_step_mm=0.20,
        narrow_neck_width_mm=1.60,
        minimum_appendage_area_mm2=0.20,
        minimum_appendage_length_mm=0.50,
        required_ground_connection_width_mm=1.00,
        pad_protection_margin_mm=0.30,
        perimeter_ground_protection_mm=1.00,
    )


def test_pad_and_width_t_corridor_are_never_reported_as_antenna() -> None:
    """Only copper beyond a required pad connection may become removable."""

    polygon = _tail_polygon()
    pad = Pad(
        "pad-gnd",
        "u1",
        "1",
        Point(13.0, 5.0),
        BoundingBox(12.5, 4.6, 13.5, 5.4),
        "GND",
        ("F.Cu",),
    )
    board = snapshot(
        zones=(_zone("zone-gnd", polygon),),
        pads=(pad,),
        edges=rectangular_edges(-2.0, -2.0, 25.0, 12.0),
    )
    findings = [
        item
        for item in detect_ground_antennas(board, _antenna_config())
        if item.rule_id == "antenna.appendage"
    ]
    assert findings
    for finding in findings:
        assert finding.metrics["pad_overlap"] is False
        assert finding.metrics["critical_connectivity_preserved"] is True
        assert finding.metrics["safe_keepout"] is True
        raw = finding.metrics["safe_keepout_polygon"]
        keepout = Polygon(tuple(Point(float(p["x"]), float(p["y"])) for p in raw["outline"]))
        assert not _polygon_intersects_box(keepout, pad.bounds)
        # The removable residual starts beyond the inflated pad and leaves the
        # one-millimetre mandatory connection corridor intact.
        assert min(point.x for point in keepout.outline) >= pad.bounds.max_x + 0.29


def test_all_physical_pad_geometry_is_excluded_from_antenna_candidates() -> None:
    """Never report or remove copper cells occupied by any footprint pad."""

    polygon = _tail_polygon()
    # The non-GND pad deliberately overlaps the simplified filled-polygon
    # fixture.  Real KiCad fill normally has a clearance void, but protecting
    # every pad makes the detector safe even when imported geometry is coarse.
    pad = Pad(
        "pad-signal",
        "u1",
        "2",
        Point(16.2, 5.0),
        BoundingBox(15.7, 4.5, 16.7, 5.5),
        "SIG",
        ("F.Cu",),
    )
    board = snapshot(
        zones=(_zone("zone-gnd", polygon),),
        pads=(pad,),
        edges=rectangular_edges(-2.0, -2.0, 25.0, 12.0),
    )
    findings = detect_ground_antennas(board, _antenna_config())
    for finding in findings:
        raw = finding.metrics.get("safe_keepout_polygon")
        if not isinstance(raw, dict):
            continue
        keepout = Polygon(tuple(Point(float(item["x"]), float(item["y"])) for item in raw["outline"]))
        assert not _polygon_intersects_box(keepout, pad.bounds)


def test_explicit_ground_trace_and_pad_escape_are_protected_backbone() -> None:
    """Do not keep out an intentional GND trace or the pad path it serves."""

    polygon = _tail_polygon()
    pad = Pad(
        "pad-gnd",
        "u1",
        "1",
        Point(16.0, 5.0),
        BoundingBox(15.5, 4.5, 16.5, 5.5),
        "GND",
        ("F.Cu",),
    )
    trace = TrackSegment(
        "gnd-escape",
        Point(9.0, 5.0),
        Point(16.0, 5.0),
        0.8,
        "F.Cu",
        0,
        "GND",
    )
    board = snapshot(
        zones=(_zone("zone-gnd", polygon),),
        pads=(pad,),
        tracks=(trace,),
        edges=rectangular_edges(-2.0, -2.0, 25.0, 12.0),
    )
    appendages = [
        item
        for item in detect_ground_antennas(board, _antenna_config())
        if item.rule_id == "antenna.appendage"
    ]
    assert not appendages


def test_track_containment_rejects_sub_sample_edge_notch() -> None:
    """Reject bridges crossing a narrow Edge.Cuts notch that sampling can miss."""

    outline = (
        Point(0.0, 0.0),
        Point(20.0, 0.0),
        Point(20.0, 20.0),
        Point(10.05, 20.0),
        Point(10.05, 9.0),
        Point(9.95, 9.0),
        Point(9.95, 20.0),
        Point(0.0, 20.0),
    )
    edges = tuple(
        BoardEdge(f"n{index}", outline[index], outline[(index + 1) % len(outline)])
        for index in range(len(outline))
    )
    board = snapshot(edges=edges)
    assert not _track_inside_board(
        board,
        Point(5.0, 15.0),
        Point(15.0, 15.0),
        0.20,
        FixConfig(board_edge_clearance_mm=0.0),
    )


def test_new_ground_bridge_clears_other_net_zone_fill() -> None:
    """Do not route an automatic GND bridge through another filled net."""

    obstacle = CopperZone(
        "vcc-zone",
        "VCC",
        ("F.Cu",),
        (0,),
        rectangle(4.0, 0.0, 6.0, 10.0),
        {"F.Cu": (rectangle(4.0, 0.0, 6.0, 10.0),)},
    )
    board = snapshot(
        zones=(obstacle,),
        edges=rectangular_edges(0.0, 0.0, 10.0, 10.0),
    )
    assert not _track_clear(
        board,
        Point(2.0, 5.0),
        Point(8.0, 5.0),
        "GND",
        "F.Cu",
        0.40,
        0.20,
        FixConfig(),
    )


def test_pad_at_appendage_end_suppresses_destructive_keepout() -> None:
    """Do not classify a tail as removable when it is the pad's only GND path."""

    polygon = _tail_polygon()
    pad = Pad(
        "pad-gnd",
        "u1",
        "1",
        Point(16.3, 5.0),
        BoundingBox(15.8, 4.6, 16.8, 5.4),
        "GND",
        ("F.Cu",),
    )
    board = snapshot(
        zones=(_zone("zone-gnd", polygon),),
        pads=(pad,),
        edges=rectangular_edges(-2.0, -2.0, 25.0, 12.0),
    )
    appendages = [
        item
        for item in detect_ground_antennas(board, _antenna_config())
        if item.rule_id == "antenna.appendage"
    ]
    assert not appendages


def test_existing_perimeter_ground_band_is_protected() -> None:
    """Do not remove a narrow appendage that is the existing outer GND band."""

    polygon = _tail_polygon()
    pad = Pad(
        "pad-gnd",
        "u1",
        "1",
        Point(2.0, 2.0),
        BoundingBox(1.5, 1.5, 2.5, 2.5),
        "GND",
        ("F.Cu",),
    )
    # The right edge is one millimetre from the tail, so the tail is part of
    # the mandatory perimeter band rather than a removable overhang.
    board = snapshot(
        zones=(_zone("zone-gnd", polygon),),
        pads=(pad,),
        edges=rectangular_edges(-1.0, -1.0, 18.0, 11.0),
    )
    appendages = [
        item
        for item in detect_ground_antennas(board, _antenna_config())
        if item.rule_id == "antenna.appendage"
    ]
    assert not appendages


def test_appendage_removal_fails_closed_without_valid_edge_cuts() -> None:
    """Do not guess which copper is perimeter GND when Edge.Cuts is absent."""

    polygon = _tail_polygon()
    pad = Pad(
        "pad-gnd",
        "u1",
        "1",
        Point(2.0, 2.0),
        BoundingBox(1.5, 1.5, 2.5, 2.5),
        "GND",
        ("F.Cu",),
    )
    board = snapshot(zones=(_zone("zone-gnd", polygon),), pads=(pad,))
    appendages = [
        item
        for item in detect_ground_antennas(board, _antenna_config())
        if item.rule_id == "antenna.appendage"
    ]
    assert not appendages


def test_raster_connectivity_does_not_use_zero_width_diagonal_contact() -> None:
    """A single corner touch is not a proven electrical GND connection."""

    occupied = {(0, 0), (1, 1)}
    assert _flood(occupied, {(0, 0)}) == {(0, 0)}


def test_narrow_bridge_between_two_broad_ground_regions_is_mandatory() -> None:
    """Do not remove the only connection between two substantial GND regions."""

    polygon = Polygon(
        (
            Point(0.0, 0.0),
            Point(8.0, 0.0),
            Point(8.0, 4.5),
            Point(12.0, 4.5),
            Point(12.0, 0.0),
            Point(20.0, 0.0),
            Point(20.0, 10.0),
            Point(12.0, 10.0),
            Point(12.0, 5.5),
            Point(8.0, 5.5),
            Point(8.0, 10.0),
            Point(0.0, 10.0),
        )
    )
    pad = Pad(
        "pad-gnd",
        "j1",
        "1",
        Point(2.0, 2.0),
        BoundingBox(1.5, 1.5, 2.5, 2.5),
        "GND",
        ("F.Cu",),
    )
    board = snapshot(
        zones=(_zone("zone-gnd", polygon),),
        pads=(pad,),
        edges=rectangular_edges(-5.0, -5.0, 25.0, 15.0),
    )
    appendages = [
        item
        for item in detect_ground_antennas(board, _antenna_config())
        if item.rule_id == "antenna.appendage"
    ]
    assert not appendages


def test_nearby_pad_clearance_moat_is_protected_conservatively() -> None:
    """Protect a possible thermal launch even when the zone polygon has a moat."""

    polygon = _tail_polygon()
    # The pad body is outside the simplified zone polygon, but its possible
    # thermal/clearance launch is close enough to the tail that removal cannot
    # be proven safe from the filled polygon alone.
    pad = Pad(
        "pad-gnd",
        "u1",
        "1",
        Point(15.5, 6.35),
        BoundingBox(15.0, 5.85, 16.0, 6.85),
        "GND",
        ("F.Cu",),
    )
    board = snapshot(
        zones=(_zone("zone-gnd", polygon),),
        pads=(pad,),
        edges=rectangular_edges(-2.0, -2.0, 25.0, 12.0),
    )
    findings = detect_ground_antennas(board, _antenna_config())
    for finding in findings:
        raw = finding.metrics.get("safe_keepout_polygon")
        if not isinstance(raw, dict):
            continue
        keepout = Polygon(tuple(Point(float(item["x"]), float(item["y"])) for item in raw["outline"]))
        assert not _polygon_intersects_box(keepout, pad.bounds.inflate(0.30))


def test_rule_area_is_exact_proven_residual_and_never_overlaps_pad() -> None:
    """Select a keepout only after the detector's connectivity proof."""

    polygon = _tail_polygon()
    pad = Pad(
        "pad-gnd",
        "u1",
        "1",
        Point(13.0, 5.0),
        BoundingBox(12.5, 4.6, 13.5, 5.4),
        "GND",
        ("F.Cu",),
    )
    board = snapshot(
        zones=(_zone("zone-gnd", polygon),),
        pads=(pad,),
        edges=rectangular_edges(-2.0, -2.0, 25.0, 12.0),
    )
    findings = detect_ground_antennas(board, _antenna_config())
    plan = plan_antenna_fixes(board, findings, _antenna_config(), FixConfig())
    assert plan.actions
    assert all(action.kind == FixKind.RULE_AREA for action in plan.actions)
    for action in plan.actions:
        assert action.parameters["margin_mm"] == 0.0
        assert action.parameters["safe_keepout"] is True
        assert action.parameters["critical_connectivity_preserved"] is True
        assert action.polygon is not None
        assert not _polygon_intersects_box(action.polygon, pad.bounds)


def test_stale_antenna_finding_is_revalidated_against_new_pad_geometry() -> None:
    """Reject an old keepout after a pad is added inside its former residual."""

    polygon = _tail_polygon()
    anchor = Pad(
        "pad-anchor",
        "u1",
        "1",
        Point(2.0, 2.0),
        BoundingBox(1.5, 1.5, 2.5, 2.5),
        "GND",
        ("F.Cu",),
    )
    original = snapshot(
        zones=(_zone("zone-gnd", polygon),),
        pads=(anchor,),
        edges=rectangular_edges(-2.0, -2.0, 25.0, 12.0),
    )
    config = _antenna_config()
    finding = next(
        item for item in detect_ground_antennas(original, config) if item.rule_id == "antenna.appendage"
    )
    new_pad = Pad(
        "pad-new",
        "j1",
        "1",
        Point(15.8, 5.0),
        BoundingBox(15.3, 4.5, 16.3, 5.5),
        "GND",
        ("F.Cu",),
    )
    edited = snapshot(
        zones=(_zone("zone-gnd", polygon),),
        pads=(anchor, new_pad),
        edges=rectangular_edges(-2.0, -2.0, 25.0, 12.0),
    )
    plan = plan_antenna_fixes(edited, (finding,), config, FixConfig())
    assert not [action for action in plan.actions if action.kind == FixKind.RULE_AREA]
    assert not [
        action for action in plan.alternatives[finding.finding_id] if action.kind == FixKind.RULE_AREA
    ]


def test_unproven_stale_finding_cannot_create_rule_area() -> None:
    """Fail closed when a dashboard finding lacks the current safety proof."""

    polygon = rectangle(0.0, 0.0, 10.0, 10.0)
    finding = Finding(
        "legacy",
        "antenna",
        "legacy",
        "legacy",
        Severity.HIGH,
        0.95,
        10.0,
        Point(5.0, 5.0),
        ("zone",),
        {
            "kind": "appendage",
            "net": "GND",
            "zone_id": "zone",
            "layer": "F.Cu",
            "feature_polygon": rectangle(4.0, 4.0, 6.0, 6.0).to_dict(),
        },
        "remove",
        "antenna.appendage",
    )
    plan = plan_antenna_fixes(
        snapshot(zones=(_zone("zone", polygon),)),
        (finding,),
        _antenna_config(),
        FixConfig(),
    )
    assert not plan.actions
    assert not plan.alternatives["legacy"]


def test_track_fix_is_rejected_when_straight_bridge_leaves_concave_board() -> None:
    """Sample the full track width against Edge.Cuts, not only its endpoints."""

    outline = (
        Point(0.0, 0.0),
        Point(20.0, 0.0),
        Point(20.0, 20.0),
        Point(12.0, 20.0),
        Point(12.0, 8.0),
        Point(8.0, 8.0),
        Point(8.0, 20.0),
        Point(0.0, 20.0),
    )
    edges = tuple(
        BoardEdge(f"e{index}", outline[index], outline[(index + 1) % len(outline)])
        for index in range(len(outline))
    )
    left_pad = Pad(
        "anchor",
        "j1",
        "1",
        Point(4.0, 16.0),
        BoundingBox(3.5, 15.5, 4.5, 16.5),
        "GND",
        ("F.Cu",),
    )
    finding = Finding(
        "outside-bridge",
        "antenna",
        "island",
        "island",
        Severity.HIGH,
        0.95,
        10.0,
        Point(16.0, 16.0),
        (),
        {
            "kind": "island",
            "isolated": True,
            "net": "GND",
            "layer": "F.Cu",
            "layer_id": 0,
            "gate": {"x": 16.0, "y": 16.0},
        },
        "connect",
        "antenna.island",
    )
    board = snapshot(pads=(left_pad,), edges=edges)
    config = FixConfig(require_proven_safe_rule_area=True)
    plan = plan_antenna_fixes(board, (finding,), _antenna_config(), config)
    assert all(candidate.kind != FixKind.TRACK_BRIDGE for candidate in plan.alternatives["outside-bridge"])


def test_return_path_defaults_ignore_short_breakouts_and_common_power_nets() -> None:
    """Require sustained, material reference loss before emitting a finding."""

    gnd = CopperZone(
        "gnd",
        "GND",
        ("B.Cu",),
        (31,),
        rectangle(1.0, 0.0, 20.0, 10.0),
        {"B.Cu": (rectangle(1.0, 0.0, 20.0, 10.0),)},
    )
    short_breakout = TrackSegment("short", Point(0.0, 2.0), Point(4.0, 2.0), 0.2, "F.Cu", 0, "SIG")
    power = TrackSegment("power", Point(0.0, 5.0), Point(18.0, 5.0), 0.4, "F.Cu", 0, "3V3")
    board = snapshot(
        tracks=(short_breakout, power),
        zones=(gnd,),
        edges=rectangular_edges(0.0, 0.0, 20.0, 10.0),
    )
    findings = analyze_noise(board, NoiseConfig(), r"^GND$")
    assert not [item for item in findings if item.rule_id == "noise.reference_gap"]


def test_return_path_still_reports_long_sustained_reference_gap() -> None:
    """Retain useful detection after the false-positive thresholds are relaxed."""

    signal = TrackSegment("sig", Point(1.0, 5.0), Point(19.0, 5.0), 0.2, "F.Cu", 0, "CLK")
    gnd = CopperZone(
        "gnd",
        "GND",
        ("B.Cu",),
        (31,),
        rectangle(0.0, 0.0, 8.0, 10.0),
        {"B.Cu": (rectangle(0.0, 0.0, 8.0, 10.0),)},
    )
    findings = analyze_noise(
        snapshot(
            tracks=(signal,),
            zones=(gnd,),
            edges=rectangular_edges(0.0, 0.0, 20.0, 10.0),
        ),
        NoiseConfig(),
        r"^GND$",
    )
    gaps = [item for item in findings if item.rule_id == "noise.reference_gap"]
    assert gaps
    assert float(gaps[0].metrics["unsupported_fraction"]) >= 0.30


def test_initial_placement_preview_contains_footprint_pads_and_fields() -> None:
    """Show the complete translated component identity instead of one dot."""

    core_pad = Pad("u1-pad", "u1", "1", Point(5.0, 5.0), BoundingBox(4.5, 4.5, 5.5, 5.5), "3V3", ("F.Cu",))
    core = FootprintSnapshot(
        item_id="u1",
        reference="U1",
        value="MCU",
        position=Point(5.0, 5.0),
        layer="F.Cu",
        bounds=BoundingBox(3.0, 3.0, 7.0, 7.0),
        reference_field=text("U1", Point(5.0, 2.4)),
        value_field=text("MCU", Point(5.0, 7.6)),
        pads=(core_pad,),
        sheet_path="/Control/",
    )
    plan = plan_component_placement(
        snapshot(
            pads=(core_pad,),
            footprints=(core,),
            edges=rectangular_edges(0.0, 0.0, 40.0, 30.0),
        ),
        PlacementConfig(),
    )
    placement = plan.placements[0]
    assert placement.destination_bounds.area > 0.0
    assert placement.preview_pads
    assert {item.kind for item in placement.preview_texts} == {"reference", "value"}
    payload = placement.to_dict()
    assert payload["preview_pads"][0]["number"] == "1"
    javascript = (ROOT / "plugin" / "emi_guardian" / "web" / "app.js").read_text(encoding="utf-8")
    assert "placement-footprint-body" in javascript
    assert "placement-identity-label" in javascript
    assert "preview_pads" in javascript
    assert "preview_texts" in javascript


@pytest.mark.parametrize(
    ("platform", "install_name"),
    (("linux", "install-or-update.sh"), ("macos", "install-or-update.command")),
)
def test_posix_update_leaves_no_backup_or_staging_plugin_directory(
    tmp_path: Path,
    platform: str,
    install_name: str,
) -> None:
    """Upgrade in isolation and remove legacy backup folders from plugin scan paths."""

    bash = shutil.which("bash")
    if bash is None:
        pytest.skip("bash is unavailable")
    package = tmp_path / platform
    package.mkdir()
    install = package / install_name
    shutil.copy2(ROOT / "installers" / platform / install_name, install)
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
    else:
        plugins_root = home / "Documents" / "KiCad" / "10.0" / "plugins"
    destination = plugins_root / "emi-guardian"
    destination.mkdir(parents=True)
    (destination / "old-marker.txt").write_text("old", encoding="utf-8")
    legacy = plugins_root / "_emi-guardian-backups" / "old"
    legacy.mkdir(parents=True)
    (legacy / "plugin.json").write_text("{}", encoding="utf-8")

    subprocess.run(
        [bash, str(install), "--force"],
        check=True,
        env=environment,
        input=input_text,
        text=True,
        capture_output=True,
    )
    assert (destination / "plugin.json").is_file()
    assert not (destination / "old-marker.txt").exists()
    assert not (plugins_root / "_emi-guardian-backups").exists()
    assert not tuple(plugins_root.glob("emi-guardian.installing-*"))
    assert [item.name for item in plugins_root.iterdir() if item.is_dir()] == ["emi-guardian"]


def test_release_metadata_and_schema_are_consistent() -> None:
    """Keep package metadata and default configuration synchronized."""

    metadata = json.loads((ROOT / "metadata.json").read_text(encoding="utf-8"))
    default_config = json.loads((ROOT / "plugin" / "default-config.json").read_text(encoding="utf-8"))
    assert metadata["versions"][0]["version"] == project_version()
    assert default_config["schema_version"] == 5
    assert default_config["antenna"]["required_ground_connection_width_mm"] == 1.0
    assert default_config["fixes"]["rule_area_margin_mm"] == 0.0
