"""Deterministic randomized safety regressions for EMI Guardian."""

from __future__ import annotations

import math
import random

from conftest import rectangular_edges, snapshot
from emi_guardian.antenna import detect_ground_antennas
from emi_guardian.config import AntennaConfig, FixConfig
from emi_guardian.fixes import _polygon_intersects_box, _track_inside_board, plan_antenna_fixes
from emi_guardian.geometry import point_in_polygon
from emi_guardian.models import BoardEdge, BoundingBox, CopperZone, FixKind, Pad, Point, Polygon

RANDOM_SEED = 0xE1A002


def _zone(item_id: str, polygon: Polygon) -> CopperZone:
    """Return one filled F.Cu GND zone."""

    return CopperZone(
        item_id,
        "GND",
        ("F.Cu",),
        (0,),
        polygon,
        {"F.Cu": (polygon,)},
    )


def _antenna_config() -> AntennaConfig:
    """Return a deterministic high-resolution safety configuration."""

    return AntennaConfig(
        raster_step_mm=0.20,
        narrow_neck_width_mm=1.60,
        minimum_appendage_area_mm2=0.20,
        minimum_appendage_length_mm=0.50,
        required_ground_connection_width_mm=1.00,
        pad_protection_margin_mm=0.30,
        perimeter_ground_protection_mm=1.00,
    )


def test_randomized_rule_areas_never_intersect_any_pad_or_leave_board() -> None:
    """Stress shape-matched keepouts against random tail and pad geometry."""

    rng = random.Random(RANDOM_SEED)
    config = _antenna_config()
    for case_index in range(48):
        body_width = rng.uniform(8.0, 14.0)
        body_height = rng.uniform(8.0, 14.0)
        tail_length = rng.uniform(3.0, 10.0)
        tail_width = rng.uniform(0.65, 1.35)
        center_y = body_height * rng.uniform(0.35, 0.65)
        half_tail = tail_width / 2.0
        polygon = Polygon(
            (
                Point(0.0, 0.0),
                Point(body_width, 0.0),
                Point(body_width, center_y - half_tail),
                Point(body_width + tail_length, center_y - half_tail),
                Point(body_width + tail_length, center_y + half_tail),
                Point(body_width, center_y + half_tail),
                Point(body_width, body_height),
                Point(0.0, body_height),
            )
        )
        anchor = Pad(
            f"anchor-{case_index}",
            "u1",
            "1",
            Point(2.0, 2.0),
            BoundingBox(1.4, 1.4, 2.6, 2.6),
            "GND",
            ("F.Cu",),
        )
        pads = [anchor]
        # Half of the cases place an arbitrary physical pad near or inside the
        # overhang.  The detector may then suppress the finding, but it must
        # never emit a keepout that overlaps the protected pad geometry.
        if case_index % 2:
            pad_x = body_width + tail_length * rng.uniform(0.35, 0.90)
            pad_y = center_y + rng.uniform(-0.25, 0.25)
            pad_half = rng.uniform(0.35, 0.70)
            pads.append(
                Pad(
                    f"signal-{case_index}",
                    "j1",
                    "2",
                    Point(pad_x, pad_y),
                    BoundingBox(
                        pad_x - pad_half,
                        pad_y - pad_half,
                        pad_x + pad_half,
                        pad_y + pad_half,
                    ),
                    "SIG",
                    ("F.Cu",),
                )
            )
        edge_margin = 3.0
        board_outline = Polygon(
            (
                Point(-edge_margin, -edge_margin),
                Point(body_width + tail_length + edge_margin, -edge_margin),
                Point(body_width + tail_length + edge_margin, body_height + edge_margin),
                Point(-edge_margin, body_height + edge_margin),
            )
        )
        board = snapshot(
            zones=(_zone(f"zone-{case_index}", polygon),),
            pads=tuple(pads),
            edges=rectangular_edges(
                -edge_margin,
                -edge_margin,
                body_width + tail_length + edge_margin,
                body_height + edge_margin,
            ),
        )
        findings = detect_ground_antennas(board, config)
        plan = plan_antenna_fixes(board, findings, config, FixConfig())
        for action in plan.actions:
            if action.kind != FixKind.RULE_AREA:
                continue
            assert action.polygon is not None
            assert all(not _polygon_intersects_box(action.polygon, pad.bounds) for pad in pads)
            assert all(point_in_polygon(point, board_outline) for point in action.polygon.outline)


def test_randomized_mandatory_bridges_between_broad_ground_regions_are_preserved() -> None:
    """Do not classify the only bridge between two random broad GND lobes."""

    rng = random.Random(RANDOM_SEED + 1)
    config = _antenna_config()
    for case_index in range(32):
        left_width = rng.uniform(6.0, 12.0)
        right_width = rng.uniform(6.0, 12.0)
        height = rng.uniform(8.0, 14.0)
        bridge_length = rng.uniform(2.0, 7.0)
        bridge_width = rng.uniform(0.65, 1.35)
        center_y = height * rng.uniform(0.35, 0.65)
        half_bridge = bridge_width / 2.0
        right_start = left_width + bridge_length
        polygon = Polygon(
            (
                Point(0.0, 0.0),
                Point(left_width, 0.0),
                Point(left_width, center_y - half_bridge),
                Point(right_start, center_y - half_bridge),
                Point(right_start, 0.0),
                Point(right_start + right_width, 0.0),
                Point(right_start + right_width, height),
                Point(right_start, height),
                Point(right_start, center_y + half_bridge),
                Point(left_width, center_y + half_bridge),
                Point(left_width, height),
                Point(0.0, height),
            )
        )
        pad = Pad(
            f"anchor-{case_index}",
            "u1",
            "1",
            Point(2.0, 2.0),
            BoundingBox(1.4, 1.4, 2.6, 2.6),
            "GND",
            ("F.Cu",),
        )
        board = snapshot(
            zones=(_zone(f"dumbbell-{case_index}", polygon),),
            pads=(pad,),
            edges=rectangular_edges(
                -4.0,
                -4.0,
                right_start + right_width + 4.0,
                height + 4.0,
            ),
        )
        appendages = [
            finding
            for finding in detect_ground_antennas(board, config)
            if finding.rule_id == "antenna.appendage"
        ]
        assert not appendages


def test_randomized_accepted_tracks_keep_full_width_inside_concave_edge_cuts() -> None:
    """Dense-sample every accepted random bridge against a concave outline."""

    rng = random.Random(RANDOM_SEED + 2)
    config = FixConfig(board_edge_clearance_mm=0.10)
    for case_index in range(24):
        notch_center = rng.uniform(10.0, 20.0)
        notch_width = rng.uniform(0.25, 4.0)
        notch_depth = rng.uniform(3.0, 14.0)
        left = notch_center - notch_width / 2.0
        right = notch_center + notch_width / 2.0
        outline = (
            Point(0.0, 0.0),
            Point(30.0, 0.0),
            Point(30.0, 24.0),
            Point(right, 24.0),
            Point(right, 24.0 - notch_depth),
            Point(left, 24.0 - notch_depth),
            Point(left, 24.0),
            Point(0.0, 24.0),
        )
        edges = tuple(
            BoardEdge(
                f"e-{case_index}-{index}",
                outline[index],
                outline[(index + 1) % len(outline)],
            )
            for index in range(len(outline))
        )
        board = snapshot(edges=edges)
        polygon = Polygon(outline)
        for _ in range(40):
            start = Point(rng.uniform(0.5, 29.5), rng.uniform(0.5, 23.5))
            end = Point(rng.uniform(0.5, 29.5), rng.uniform(0.5, 23.5))
            width = rng.uniform(0.10, 1.20)
            if not _track_inside_board(board, start, end, width, config):
                continue
            radius = width / 2.0 + config.board_edge_clearance_mm
            length = math.hypot(end.x - start.x, end.y - start.y)
            if length <= 1.0e-12:
                directions = ((1.0, 0.0),)
            else:
                tangent = ((end.x - start.x) / length, (end.y - start.y) / length)
                directions = (
                    tangent,
                    (-tangent[0], -tangent[1]),
                    (-tangent[1], tangent[0]),
                    (tangent[1], -tangent[0]),
                )
            for step in range(101):
                ratio = step / 100.0
                center = Point(
                    start.x + (end.x - start.x) * ratio,
                    start.y + (end.y - start.y) * ratio,
                )
                assert point_in_polygon(center, polygon)
                for dx, dy in directions:
                    probe = Point(center.x + dx * radius, center.y + dy * radius)
                    assert point_in_polygon(probe, polygon)
