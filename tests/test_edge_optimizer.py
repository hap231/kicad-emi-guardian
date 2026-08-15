"""Board-outline generation, filleting, and GND-band verification tests."""

from __future__ import annotations

import math

import pytest

from conftest import footprint, rectangle, rectangular_edges, snapshot
from emi_guardian.config import EdgeConfig
from emi_guardian.edge_optimizer import (
    _box_corners,
    _circle_center,
    _contains_all_points,
    _current_board_area,
    _densify_ring,
    _enforce_allowed_concavities,
    _protected_boxes,
    _reflex_vertices,
    _ring_self_intersects,
    _sample_primitives,
    fillet_ring,
    propose_edge_outline,
)
from emi_guardian.geometry import distance, polygon_signed_area
from emi_guardian.models import BoundingBox, CopperZone, Point


def test_square_fillet_is_tangent_continuous_and_uses_requested_radius() -> None:
    """Generate exact circular arcs rather than fixed 45-degree approximations."""

    ring = (Point(0.0, 0.0), Point(10.0, 0.0), Point(10.0, 10.0), Point(0.0, 10.0))
    primitives = fillet_ring(ring, 1.0)
    assert len([item for item in primitives if item.kind == "arc"]) == 4
    assert len([item for item in primitives if item.kind == "segment"]) == 4
    for index, primitive in enumerate(primitives):
        previous = primitives[index - 1]
        assert distance(previous.end, primitive.start) <= 1.0e-6
        if primitive.kind == "arc":
            assert primitive.mid is not None
            center = _circle_center(primitive.start, primitive.mid, primitive.end)
            assert center is not None
            assert distance(center, primitive.start) == pytest.approx(1.0, abs=1.0e-6)
    sampled = _sample_primitives(primitives, 0.05)
    assert 99.0 < abs(polygon_signed_area(sampled)) < 100.0


def test_concave_corner_is_rounded_without_breaking_loop_continuity() -> None:
    """Support area-saving re-entrant contours while keeping a closed Edge.Cuts path."""

    ring = (
        Point(0.0, 0.0),
        Point(10.0, 0.0),
        Point(10.0, 4.0),
        Point(6.0, 4.0),
        Point(6.0, 10.0),
        Point(0.0, 10.0),
    )
    primitives = fillet_ring(ring, 1.0)
    assert len([item for item in primitives if item.kind == "arc"]) == 6
    for index, primitive in enumerate(primitives):
        assert distance(primitives[index - 1].end, primitive.start) <= 1.0e-6
    sampled = _sample_primitives(primitives, 0.05)
    assert len(sampled) > 100
    assert abs(polygon_signed_area(sampled)) > 70.0


def test_current_area_reconstructs_unordered_and_reversed_edges() -> None:
    """Do not rely on KiCad returning Edge.Cuts in traversal order."""

    board = snapshot(edges=rectangular_edges(0.0, 0.0, 10.0, 10.0, unordered=True))
    assert _current_board_area(board) == pytest.approx(100.0)


def test_orthogonal_mode_stays_orthogonal_even_when_diagonal_capability_is_enabled() -> None:
    """Treat diagonal permission as a guard, not an implicit mode switch."""

    ground = rectangle(-20.0, -20.0, 30.0, 30.0)
    zone = CopperZone("g", "GND", ("F.Cu",), (0,), ground, {"F.Cu": (ground,)})
    board = snapshot(
        zones=(zone,),
        footprints=(footprint(),),
        edges=rectangular_edges(0.0, 0.0, 20.0, 20.0),
    )
    config = EdgeConfig(
        mode="orthogonal",
        allow_diagonal_edges=True,
        maximum_area_reduction_percent=99.0,
        grid_mm=0.5,
    )
    proposal = propose_edge_outline(board, config, r"^GND$")
    points = proposal.polygon.outline
    assert all(
        math.isclose(first.x, second.x, abs_tol=1.0e-9) or math.isclose(first.y, second.y, abs_tol=1.0e-9)
        for first, second in zip(points, points[1:] + points[:1])
    )
    assert proposal.ground_band_verified is True
    assert all(math.isclose(point.x / 0.5, round(point.x / 0.5), abs_tol=1.0e-9) for point in points)


def test_ground_band_requires_filled_copper_on_one_continuous_layer() -> None:
    """Reject outline-only zones and cross-layer mosaics as unproven perimeter ground."""

    ground = rectangle(-20.0, -20.0, 30.0, 30.0)
    outline_only = CopperZone("g", "GND", ("F.Cu",), (0,), ground, {})
    board = snapshot(
        zones=(outline_only,),
        footprints=(footprint(),),
        edges=rectangular_edges(0.0, 0.0, 20.0, 20.0),
    )
    proposal = propose_edge_outline(
        board,
        EdgeConfig(maximum_area_reduction_percent=99.0),
        r"^GND$",
    )
    assert proposal.ground_band_verified is False
    assert any("blocked" in warning for warning in proposal.warnings)


def test_grid_densification_never_moves_a_safe_edge_inward() -> None:
    """Keep protected geometry inside when a diagonal edge lacks a lattice midpoint."""

    ring = (
        Point(51.0, 20.0),
        Point(47.0, 23.0),
        Point(1.0, 22.0),
        Point(0.0, 21.0),
        Point(-3.0, 14.0),
        Point(-1.0, 2.0),
        Point(27.0, -7.0),
        Point(47.0, 0.0),
        Point(49.0, 2.0),
        Point(51.0, 19.0),
    )
    protected = (Point(18.51, 22.03), Point(5.78, 22.03))
    assert _contains_all_points(ring, protected)

    densified = _densify_ring(ring, 11, 1.0, protected)

    assert not _ring_self_intersects(densified)
    assert _contains_all_points(densified, protected)
    assert len(densified) <= 11
    assert all(
        math.isclose(point.x, round(point.x), abs_tol=1.0e-9)
        and math.isclose(point.y, round(point.y), abs_tol=1.0e-9)
        for point in densified
    )


def test_rounded_outline_keeps_protected_geometry_outside_fillets() -> None:
    """Validate the actual sampled arc contour, not only its sharp-corner polygon."""

    board = snapshot(
        footprints=(footprint(bounds=BoundingBox(0.0, 0.0, 70.0, 30.0)),),
        edges=rectangular_edges(-2.0, -2.0, 72.0, 32.0),
    )
    config = EdgeConfig(
        target_vertex_count=6,
        grid_mm=0.1,
        fillet_radius_mm=3.0,
        minimum_ground_band_mm=0.2,
        maximum_area_reduction_percent=99.0,
    )

    proposal = propose_edge_outline(board, config, r"^GND$")
    sampled = _sample_primitives(
        proposal.primitives,
        max(0.05, min(config.grid_mm / 4.0, config.fillet_radius_mm / 5.0)),
    )
    protected = _box_corners(_protected_boxes(board, config))

    assert _contains_all_points(sampled, protected)
    assert any("rounded corners" in warning for warning in proposal.warnings)


def test_convex_strategy_removes_grid_induced_reflex_vertex() -> None:
    """Never invent a recess when the source outline has no concavity."""

    ring = (
        Point(0.0, 0.0),
        Point(10.0, 0.0),
        Point(10.0, 10.0),
        Point(5.0, 9.9),
        Point(0.0, 10.0),
    )
    protected = (Point(1.0, 1.0), Point(9.0, 9.0))
    config = EdgeConfig(target_vertex_count=5, grid_mm=0.1)

    corrected, preserved, fell_back = _enforce_allowed_concavities(
        ring,
        config,
        0,
        protected,
    )

    assert fell_back is True
    assert preserved == 0
    assert _reflex_vertices(corrected) == ()
    assert _contains_all_points(corrected, protected)
