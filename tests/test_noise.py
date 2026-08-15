"""Qualitative noise-analysis heuristic tests."""

from __future__ import annotations

from conftest import rectangular_edges, snapshot
from emi_guardian.config import NoiseConfig
from emi_guardian.models import BoundingBox, Pad, Point, TrackSegment, Via
from emi_guardian.noise import analyze_noise


def test_noise_suite_detects_major_geometry_risks() -> None:
    """Exercise stubs, parallelism, corners, length, return paths, edges, and pairs."""

    tracks = (
        TrackSegment("stub", Point(2.0, 2.0), Point(12.0, 2.0), 0.2, "F.Cu", 0, "STUB"),
        TrackSegment("parallel-a", Point(2.0, 6.0), Point(12.0, 6.0), 0.2, "F.Cu", 0, "CLK"),
        TrackSegment("parallel-b", Point(2.0, 6.3), Point(12.0, 6.3), 0.2, "F.Cu", 0, "DATA"),
        TrackSegment("corner-a", Point(15.0, 5.0), Point(20.0, 5.0), 0.2, "F.Cu", 0, "CORNER"),
        TrackSegment("corner-b", Point(20.0, 5.0), Point(16.0, 9.0), 0.2, "F.Cu", 0, "CORNER"),
        TrackSegment("long", Point(2.0, 20.0), Point(72.0, 20.0), 0.2, "F.Cu", 0, "LONG"),
        TrackSegment("edge", Point(0.3, 12.0), Point(10.0, 12.0), 0.2, "F.Cu", 0, "EDGE"),
        TrackSegment("usb-p", Point(30.0, 30.0), Point(40.0, 30.0), 0.2, "F.Cu", 0, "USB_P"),
        TrackSegment("usb-n", Point(30.0, 31.0), Point(46.0, 31.0), 0.2, "F.Cu", 0, "USB_N"),
    )
    pads = (
        Pad("stub-pad", "fp", "1", Point(2.0, 2.0), BoundingBox(1.5, 1.5, 2.5, 2.5), "STUB", ("F.Cu",)),
        Pad(
            "wrong-net-pad",
            "fp2",
            "1",
            Point(12.0, 2.0),
            BoundingBox(11.5, 1.5, 12.5, 2.5),
            "OTHER",
            ("F.Cu",),
        ),
    )
    vias = (Via("signal-via", Point(25.0, 15.0), 0.6, 0.3, "SIG"),)
    board = snapshot(
        tracks=tracks,
        pads=pads,
        vias=vias,
        edges=rectangular_edges(0.0, 0.0, 80.0, 40.0),
    )
    findings = analyze_noise(board, NoiseConfig(), r"^GND$")
    titles = {finding.title for finding in findings}
    assert "Possible dangling trace stub" in titles
    assert "Close parallel routing on different nets" in titles
    assert "Sharp trace corner" in titles
    assert any("long routed net" in title.lower() for title in titles)
    assert "Layer transition lacks a nearby GND return via" not in titles
    assert "Signal trace close to board edge" in titles
    assert "Differential-pair routed-length mismatch" in titles
    stub_findings = [
        finding
        for finding in findings
        if finding.title == "Possible dangling trace stub" and "stub" in finding.item_ids
    ]
    assert len(stub_findings) == 1


def test_parallel_search_covers_bucket_boundaries() -> None:
    """Do not miss close traces that fall on opposite spatial-index boundaries."""

    config = NoiseConfig(parallel_overlap_warning_mm=5.0, parallel_spacing_warning_mm=0.5)
    tracks = (
        TrackSegment("a", Point(0.0, 4.99), Point(10.0, 4.99), 0.2, "F.Cu", 0, "A"),
        TrackSegment("b", Point(0.0, 5.01), Point(10.0, 5.01), 0.2, "F.Cu", 0, "B"),
    )
    findings = analyze_noise(snapshot(tracks=tracks), config, r"^GND$")
    assert any(finding.category == "parallel" for finding in findings)


def test_right_angle_is_not_reported_as_sharp_by_default() -> None:
    """Treat an ordinary 90-degree bend as acceptable unless the user raises the threshold."""

    tracks = (
        TrackSegment("a", Point(0.0, 0.0), Point(5.0, 0.0), 0.2, "F.Cu", 0, "SIG"),
        TrackSegment("b", Point(5.0, 0.0), Point(5.0, 5.0), 0.2, "F.Cu", 0, "SIG"),
    )
    findings = analyze_noise(snapshot(tracks=tracks), NoiseConfig(), r"^GND$")
    assert not any(finding.rule_id == "noise.corner" for finding in findings)


def test_acute_corner_is_excluded_inside_same_net_pad() -> None:
    """Suppress pad-entry geometry while retaining genuine routed acute corners."""

    tracks = (
        TrackSegment("a", Point(0.0, 0.0), Point(5.0, 0.0), 0.2, "F.Cu", 0, "SIG"),
        TrackSegment("b", Point(5.0, 0.0), Point(8.0, 3.0), 0.2, "F.Cu", 0, "SIG"),
    )
    pad = Pad("p", "fp", "1", Point(5.0, 0.0), BoundingBox(4.4, -0.6, 5.6, 0.6), "SIG", ("F.Cu",))
    findings = analyze_noise(snapshot(tracks=tracks, pads=(pad,)), NoiseConfig(), r"^GND$")
    assert not any(finding.rule_id == "noise.corner" for finding in findings)


def test_arc_chord_split_is_not_reported_as_corner() -> None:
    """Do not treat the internal chord joint of one KiCad arc as a trace corner."""

    tracks = (
        TrackSegment(
            "arc:0",
            Point(0.0, 0.0),
            Point(3.0, 0.0),
            0.2,
            "F.Cu",
            0,
            "SIG",
            source_item_id="arc",
            is_curve_approximation=True,
        ),
        TrackSegment(
            "arc:1",
            Point(3.0, 0.0),
            Point(5.0, 2.0),
            0.2,
            "F.Cu",
            0,
            "SIG",
            source_item_id="arc",
            is_curve_approximation=True,
        ),
    )
    findings = analyze_noise(snapshot(tracks=tracks), NoiseConfig(), r"^GND$")
    assert not any(finding.rule_id == "noise.corner" for finding in findings)


def test_long_net_uses_endpoint_path_instead_of_branch_sum() -> None:
    """Avoid a false positive when many short branches inflate total copper."""

    tracks = [TrackSegment("trunk", Point(0.0, 0.0), Point(20.0, 0.0), 0.2, "F.Cu", 0, "BUS")]
    for index in range(1, 7):
        x = float(index * 3)
        tracks.append(TrackSegment(f"branch-{index}", Point(x, 0.0), Point(x, 4.0), 0.2, "F.Cu", 0, "BUS"))
    config = NoiseConfig(trace_length_warning_mm=30.0, signal_rise_time_ns=3.0)
    findings = analyze_noise(snapshot(tracks=tuple(tracks)), config, r"^GND$")
    assert not any(finding.rule_id == "noise.long_net" for finding in findings)


def test_genuinely_long_endpoint_path_is_reported() -> None:
    """Retain coverage for a real long source-to-load route."""

    tracks = (TrackSegment("long", Point(0.0, 0.0), Point(90.0, 0.0), 0.2, "F.Cu", 0, "SIG"),)
    findings = analyze_noise(snapshot(tracks=tracks), NoiseConfig(), r"^GND$")
    finding = next(item for item in findings if item.rule_id == "noise.long_net")
    assert finding.metrics["estimated_path_length_mm"] == 90.0


def test_long_net_small_cycle_uses_exact_all_node_diameter_scan() -> None:
    """Avoid endpoint-only misses in a small cyclic route component."""

    tracks = (
        TrackSegment("a", Point(0.0, 0.0), Point(10.0, 0.0), 0.2, "F.Cu", 0, "LOOP"),
        TrackSegment("b", Point(10.0, 0.0), Point(10.0, 10.0), 0.2, "F.Cu", 0, "LOOP"),
        TrackSegment("c", Point(10.0, 10.0), Point(0.0, 10.0), 0.2, "F.Cu", 0, "LOOP"),
        TrackSegment("d", Point(0.0, 10.0), Point(0.0, 0.0), 0.2, "F.Cu", 0, "LOOP"),
    )
    config = NoiseConfig(
        trace_length_warning_mm=18.0,
        long_net_trigger_mode="either",
        long_net_diameter_scan_limit=32,
    )
    findings = analyze_noise(snapshot(tracks=tracks), config, r"^GND$")
    finding = next(item for item in findings if item.rule_id == "noise.long_net")
    assert finding.metrics["estimated_path_length_mm"] == 20.0
    assert finding.metrics["diameter_method"] == "exact_all_nodes"
    assert finding.metrics["diameter_source_count"] == 4


def test_long_net_findings_are_deterministic_across_repeated_runs() -> None:
    """Keep component ordering, path evidence, and identifiers stable."""

    tracks = (
        TrackSegment("z", Point(0.0, 0.0), Point(40.0, 0.0), 0.2, "F.Cu", 0, "SIG"),
        TrackSegment("a", Point(40.0, 0.0), Point(70.0, 20.0), 0.2, "F.Cu", 0, "SIG"),
        TrackSegment("b", Point(40.0, 0.0), Point(55.0, -8.0), 0.2, "F.Cu", 0, "SIG"),
    )
    config = NoiseConfig(trace_length_warning_mm=30.0, long_net_trigger_mode="either")
    first = [
        item.to_dict()
        for item in analyze_noise(snapshot(tracks=tracks), config, r"^GND$")
        if item.rule_id == "noise.long_net"
    ]
    second = [
        item.to_dict()
        for item in analyze_noise(snapshot(tracks=tracks), config, r"^GND$")
        if item.rule_id == "noise.long_net"
    ]
    assert first == second
