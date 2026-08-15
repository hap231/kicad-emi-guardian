"""Board-outline proposal generation with mandatory rounded corners."""

from __future__ import annotations

import math
import re
from collections import defaultdict, deque
from collections.abc import Iterable, Sequence
from dataclasses import asdict, dataclass

from .config import EdgeConfig
from .geometry import (
    add,
    convex_hull,
    distance,
    dot,
    normalize,
    point_in_polygon,
    point_in_ring,
    point_segment_distance,
    polygon_signed_area,
    scale,
    simplify_ring,
    snap_point,
    subtract,
)
from .models import BoardEdge, BoardSnapshot, BoundingBox, Point, Polygon, TrackSegment, bounds_from_points

Cell = tuple[int, int]


@dataclass(frozen=True)
class EdgePrimitive:
    """One line or arc forming the rounded Edge.Cuts proposal."""

    kind: str
    start: Point
    end: Point
    mid: Point | None = None

    def to_dict(self) -> dict[str, object]:
        """Return a JSON-serializable representation."""

        return asdict(self)


@dataclass(frozen=True)
class EdgeProposal:
    """Complete board-outline proposal."""

    polygon: Polygon
    primitives: tuple[EdgePrimitive, ...]
    original_area_mm2: float
    proposed_area_mm2: float
    reduction_percent: float
    fillet_radius_mm: float
    grid_mm: float
    mode: str
    operation: str
    outline_strategy: str
    target_vertex_count: int
    actual_vertex_count: int
    preserved_concavity_count: int
    ground_band_verified: bool
    area_guard_applied: bool
    warnings: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        """Return a JSON-serializable representation."""

        return {
            "polygon": self.polygon.to_dict(),
            "primitives": [primitive.to_dict() for primitive in self.primitives],
            "original_area_mm2": self.original_area_mm2,
            "proposed_area_mm2": self.proposed_area_mm2,
            "reduction_percent": self.reduction_percent,
            "fillet_radius_mm": self.fillet_radius_mm,
            "grid_mm": self.grid_mm,
            "mode": self.mode,
            "operation": self.operation,
            "outline_strategy": self.outline_strategy,
            "target_vertex_count": self.target_vertex_count,
            "actual_vertex_count": self.actual_vertex_count,
            "preserved_concavity_count": self.preserved_concavity_count,
            "ground_band_verified": self.ground_band_verified,
            "area_guard_applied": self.area_guard_applied,
            "warnings": list(self.warnings),
        }


def propose_edge_outline(
    snapshot: BoardSnapshot,
    config: EdgeConfig,
    ground_net_regex: str,
    operation: str = "optimize",
) -> EdgeProposal:
    """Generate an optimized, smoothed, or filleted board-outline proposal.

    ``optimize`` is area reducing and refuses to replace a smaller current
    outline with a larger support polygon.  ``smooth`` simplifies the current
    contour before applying fillets, while ``fillet`` preserves the current
    polygon topology and only rounds its corners.  Generated sharp vertices are
    snapped to the configured grid before arc construction.
    """

    normalized_operation = str(operation or "optimize").strip().lower()
    if normalized_operation not in {"optimize", "smooth", "fillet"}:
        raise ValueError(f"Unsupported edge operation: {operation}")

    original_area = _current_board_area(snapshot)
    protected = _protected_boxes(snapshot, config)
    if not protected and normalized_operation == "optimize":
        raise ValueError("No protected board geometry was found.")
    protected_points = _box_corners(protected) if protected else ()
    warnings: list[str] = []
    preserved_concavity_count = 0
    convex_fallback_applied = False

    if normalized_operation == "optimize":
        if config.outline_strategy == "legacy_concave":
            ring = (
                _diagonal_outline(protected, config)
                if config.mode == "diagonal"
                else _orthogonal_outline(protected, config)
            )
        else:
            ring, preserved_concavity_count = _default_convex_outline(snapshot, protected, config)
        ring = _normalize_ring(ring)
        ring, preserved_concavity_count, convex_fallback_applied = _enforce_allowed_concavities(
            ring,
            config,
            preserved_concavity_count,
            protected_points,
        )
    else:
        current = _largest_current_outline_sampled(snapshot, max(0.05, config.grid_mm / 2.0))
        if len(current) < 3:
            raise ValueError("A connected current Edge.Cuts loop is required for this operation.")
        if normalized_operation == "smooth":
            current = tuple(simplify_ring(current, max(config.simplify_tolerance_mm, config.grid_mm / 2.0)))
        else:
            current = tuple(simplify_ring(current, max(1.0e-4, config.grid_mm / 20.0)))
        ring = _snap_ring_safely(current, config.grid_mm)
        ring = _normalize_ring(ring)
        if _ring_self_intersects(ring):
            raise ValueError("Grid snapping made the current outline self-intersecting.")
        preserved_concavity_count = len(_reflex_vertices(ring))

    if len(ring) < 3:
        raise ValueError("The proposed board outline is degenerate.")
    if normalized_operation == "optimize" and len(ring) != config.target_vertex_count:
        warnings.append(
            f"The safety-constrained outline uses {len(ring)} vertices instead of the requested "
            f"{config.target_vertex_count}."
        )
    if preserved_concavity_count:
        warnings.append(
            f"Preserved {preserved_concavity_count} concave vertices from the current Edge.Cuts topology."
        )
    if convex_fallback_applied:
        warnings.append(
            "Grid snapping could not safely preserve the requested concavity; a convex safety fallback was used."
        )

    required_area = (
        original_area * (1.0 - config.maximum_area_reduction_percent / 100.0)
        if normalized_operation == "optimize" and original_area > 0.0
        else 0.0
    )
    area_expansion_applied = False
    fillet_clearance_expansion_applied = False
    primitives: tuple[EdgePrimitive, ...] = ()
    rounded_ring: tuple[Point, ...] = ()
    proposed_area = 0.0
    sampling_step = max(0.05, min(config.grid_mm / 4.0, config.fillet_radius_mm / 5.0))
    for _ in range(64):
        primitives = fillet_ring(ring, config.fillet_radius_mm)
        if not primitives:
            primitives = _ring_segments(ring)
        rounded_ring = _sample_primitives(primitives, sampling_step)
        evaluated_ring = rounded_ring or ring
        proposed_area = abs(polygon_signed_area(evaluated_ring))
        area_is_safe = required_area <= 0.0 or proposed_area + 1.0e-6 >= required_area
        fillets_are_safe = not protected_points or _contains_all_points(evaluated_ring, protected_points)
        if area_is_safe and fillets_are_safe:
            break

        if normalized_operation != "optimize":
            # Smoothing/filleting the current outline must never expand it merely
            # to satisfy optimizer-only content margins.  Return a clear error so
            # the user can reduce the radius instead.
            raise ValueError(
                "The selected fillet radius would cut into protected geometry; reduce the radius or use the optimizer."
            )

        if not area_is_safe:
            raw_area = abs(polygon_signed_area(ring))
            compensated_area = required_area + max(0.0, raw_area - proposed_area)
            expanded = _normalize_ring(_expand_ring_to_area(ring, compensated_area, config.grid_mm))
            if not _contains_all_points(expanded, protected_points):
                expanded = _expand_until_contains(expanded, protected_points, config.grid_mm)
            if expanded != ring:
                ring, preserved_concavity_count, fell_back = _enforce_allowed_concavities(
                    expanded,
                    config,
                    preserved_concavity_count,
                    protected_points,
                )
                convex_fallback_applied = convex_fallback_applied or fell_back
                area_expansion_applied = True
                continue

        expanded = _expand_ring_by_distance(
            ring,
            max(2.0 * config.grid_mm, 0.10 * config.fillet_radius_mm, 0.05),
            config.grid_mm,
        )
        if not _contains_all_points(expanded, protected_points):
            expanded = _expand_until_contains(expanded, protected_points, config.grid_mm)
        if expanded == ring:
            raise ValueError("Unable to preserve protected geometry after applying edge fillets.")
        ring, preserved_concavity_count, fell_back = _enforce_allowed_concavities(
            expanded,
            config,
            preserved_concavity_count,
            protected_points,
        )
        convex_fallback_applied = convex_fallback_applied or fell_back
        fillet_clearance_expansion_applied = True
    else:
        raise ValueError("Unable to generate a rounded outline that contains all protected geometry.")

    if area_expansion_applied:
        warnings.append(
            "The initial proposal exceeded the maximum permitted area reduction; a safety expansion was applied."
        )
    if fillet_clearance_expansion_applied:
        warnings.append(
            "The outline was expanded so the rounded corners remain outside all protected board geometry."
        )

    # The previous optimizer could turn a compact five-sided board into a much
    # larger rectangle because protection margins were interpreted as a reason
    # to enlarge Edge.Cuts.  Area reduction must be monotonic by default.
    maximum_allowed_area = original_area * (1.0 + config.maximum_area_increase_percent / 100.0)
    area_guard_applied = False
    if (
        normalized_operation == "optimize"
        and config.reject_area_increase
        and original_area > 0.0
        and proposed_area > maximum_allowed_area + 1.0e-6
    ):
        current_ring = _largest_current_outline_sampled(snapshot, sampling_step)
        if len(current_ring) >= 3:
            ring = _normalize_ring(current_ring)
            primitives = _existing_edge_primitives(snapshot)
            if not primitives:
                primitives = _ring_segments(ring)
            rounded_ring = _sample_primitives(primitives, sampling_step) or ring
            proposed_area = original_area
            preserved_concavity_count = len(_reflex_vertices(ring))
            area_guard_applied = True
            normalized_operation = "preserve_current"
            warnings.append(
                "The generated outline would increase board area, so the current Edge.Cuts geometry was preserved."
            )
        else:
            raise ValueError(
                "The optimizer would increase board area and the current outline could not be reconstructed."
            )

    reduction = 0.0 if original_area <= 0.0 else (original_area - proposed_area) / original_area * 100.0
    ground_verified = _verify_ground_band(
        snapshot,
        rounded_ring or ring,
        config.minimum_ground_band_mm,
        ground_net_regex,
    )
    if not ground_verified:
        warnings.append(
            "A continuous GND band could not be proven around the entire proposed perimeter; automatic Edge.Cuts replacement is blocked."
        )
    if not config.allow_destructive_edge_replacement:
        warnings.append(
            "Destructive Edge.Cuts replacement is disabled by default; this is a preview-only proposal."
        )

    return EdgeProposal(
        polygon=Polygon(outline=tuple(ring)),
        primitives=primitives,
        original_area_mm2=original_area,
        proposed_area_mm2=proposed_area,
        reduction_percent=reduction,
        fillet_radius_mm=config.fillet_radius_mm,
        grid_mm=config.grid_mm,
        mode=config.mode,
        operation=normalized_operation,
        outline_strategy=config.outline_strategy,
        target_vertex_count=config.target_vertex_count,
        actual_vertex_count=len(ring),
        preserved_concavity_count=preserved_concavity_count,
        ground_band_verified=ground_verified,
        area_guard_applied=area_guard_applied,
        warnings=tuple(warnings),
    )


def current_outline_ring(
    snapshot: BoardSnapshot,
    maximum_step_mm: float = 0.10,
) -> tuple[Point, ...]:
    """Return the largest current Edge.Cuts contour with arcs sampled safely."""

    return _largest_current_outline_sampled(snapshot, max(0.01, maximum_step_mm))


def current_outline_polygon(
    snapshot: BoardSnapshot,
    maximum_step_mm: float = 0.10,
) -> Polygon | None:
    """Return the current board area as an outer contour with internal cutouts.

    The largest sampled ``Edge.Cuts`` loop is treated as the board perimeter.
    Every smaller loop whose representative point lies inside that perimeter is
    treated as a hole.  This representation is suitable for fail-closed copper
    containment checks used by automatic remediation planners.
    """

    loops = _sampled_current_loops(snapshot, max(0.01, maximum_step_mm))
    if not loops:
        return None
    outer = max(loops, key=lambda ring: abs(polygon_signed_area(ring)))
    holes = tuple(loop for loop in loops if loop is not outer and loop and point_in_ring(loop[0], outer))
    return Polygon(outline=tuple(outer), holes=holes)


def fillet_ring(points: Sequence[Point], radius_mm: float) -> tuple[EdgePrimitive, ...]:
    """Convert a polygon ring to tangent line and circular-arc primitives."""

    ring = _normalize_ring(points)
    if len(ring) < 3 or radius_mm <= 0.0:
        return ()
    orientation_sign = 1.0 if polygon_signed_area(ring) > 0.0 else -1.0
    corners = [
        _fillet_corner(
            ring[index - 1],
            vertex,
            ring[(index + 1) % len(ring)],
            radius_mm,
            orientation_sign,
        )
        for index, vertex in enumerate(ring)
    ]

    primitives: list[EdgePrimitive] = []
    for index, (arc_start, arc_mid, arc_end) in enumerate(corners):
        previous_arc_end = corners[index - 1][2]
        if distance(previous_arc_end, arc_start) > 1.0e-6:
            primitives.append(EdgePrimitive("segment", previous_arc_end, arc_start))
        if arc_mid is not None and distance(arc_start, arc_end) > 1.0e-6:
            primitives.append(EdgePrimitive("arc", arc_start, arc_end, arc_mid))
    return tuple(primitives)


def _fillet_corner(
    previous: Point,
    vertex: Point,
    following: Point,
    requested_radius: float,
    orientation_sign: float,
) -> tuple[Point, Point | None, Point]:
    """Return tangent points and an exact circular midpoint for one corner."""

    incoming = normalize(subtract(vertex, previous))
    outgoing = normalize(subtract(following, vertex))
    incoming_length = distance(previous, vertex)
    outgoing_length = distance(vertex, following)
    turn = (incoming.x * outgoing.y - incoming.y * outgoing.x) * orientation_sign
    if incoming_length <= 1.0e-9 or outgoing_length <= 1.0e-9 or abs(turn) <= 1.0e-8:
        return vertex, None, vertex

    unit = _offset_corner_geometry(
        vertex,
        incoming,
        outgoing,
        1.0,
        orientation_sign,
        turn,
    )
    if unit is None:
        return vertex, None, vertex
    unit_start, _, unit_end = unit
    incoming_per_radius = distance(vertex, unit_start)
    outgoing_per_radius = distance(vertex, unit_end)
    if incoming_per_radius <= 1.0e-9 or outgoing_per_radius <= 1.0e-9:
        return vertex, None, vertex

    radius = min(
        requested_radius,
        incoming_length * 0.45 / incoming_per_radius,
        outgoing_length * 0.45 / outgoing_per_radius,
    )
    if radius <= 1.0e-6:
        return vertex, None, vertex
    geometry = _offset_corner_geometry(
        vertex,
        incoming,
        outgoing,
        radius,
        orientation_sign,
        turn,
    )
    if geometry is None:
        return vertex, None, vertex
    start, center, end = geometry
    mid = _arc_midpoint_near_vertex(center, start, end, vertex)
    return start, mid, end


def _offset_corner_geometry(
    vertex: Point,
    incoming: Point,
    outgoing: Point,
    radius: float,
    orientation_sign: float,
    normalized_turn: float,
) -> tuple[Point, Point, Point] | None:
    """Construct a tangent circle from offset-line intersections."""

    side = 1.0 if normalized_turn > 0.0 else -1.0
    incoming_normal = Point(
        -incoming.y * orientation_sign * side,
        incoming.x * orientation_sign * side,
    )
    outgoing_normal = Point(
        -outgoing.y * orientation_sign * side,
        outgoing.x * orientation_sign * side,
    )
    first_origin = add(vertex, scale(incoming_normal, radius))
    second_origin = add(vertex, scale(outgoing_normal, radius))
    denominator = incoming.x * outgoing.y - incoming.y * outgoing.x
    if abs(denominator) <= 1.0e-10:
        return None
    offset = subtract(second_origin, first_origin)
    parameter = (offset.x * outgoing.y - offset.y * outgoing.x) / denominator
    center = add(first_origin, scale(incoming, parameter))
    relative = subtract(center, vertex)
    incoming_projection = dot(relative, incoming)
    outgoing_projection = dot(relative, outgoing)
    if incoming_projection >= -1.0e-9 or outgoing_projection <= 1.0e-9:
        return None
    start = add(vertex, scale(incoming, incoming_projection))
    end = add(vertex, scale(outgoing, outgoing_projection))
    return start, center, end


def _arc_midpoint_near_vertex(center: Point, start: Point, end: Point, vertex: Point) -> Point:
    """Return the midpoint of the circular sweep that replaces a vertex."""

    radius = distance(center, start)
    if radius <= 1.0e-9:
        return vertex
    start_angle = math.atan2(start.y - center.y, start.x - center.x)
    end_angle = math.atan2(end.y - center.y, end.x - center.x)
    short_sweep = (end_angle - start_angle + math.pi) % (2.0 * math.pi) - math.pi
    if abs(short_sweep) <= 1.0e-10:
        return vertex
    long_sweep = short_sweep - math.copysign(2.0 * math.pi, short_sweep)

    def candidate(sweep: float) -> Point:
        angle = start_angle + sweep / 2.0
        return Point(center.x + radius * math.cos(angle), center.y + radius * math.sin(angle))

    short_mid = candidate(short_sweep)
    long_mid = candidate(long_sweep)
    return short_mid if distance(short_mid, vertex) <= distance(long_mid, vertex) else long_mid


def _protected_boxes(snapshot: BoardSnapshot, config: EdgeConfig) -> list[BoundingBox]:
    """Return content boxes inflated by safety and GND-band margins."""

    base_margin = max(
        config.component_margin_mm,
        config.copper_margin_mm + config.minimum_ground_band_mm,
    )
    boxes: list[BoundingBox] = []
    boxes.extend(footprint.bounds.inflate(base_margin) for footprint in snapshot.footprints)
    boxes.extend(
        pad.bounds.inflate(config.copper_margin_mm + config.minimum_ground_band_mm) for pad in snapshot.pads
    )
    for via in snapshot.vias:
        radius = via.diameter / 2.0 + config.copper_margin_mm + config.minimum_ground_band_mm
        boxes.append(
            BoundingBox(
                via.position.x - radius,
                via.position.y - radius,
                via.position.x + radius,
                via.position.y + radius,
            )
        )
    for track in snapshot.tracks:
        margin = track.width / 2.0 + config.copper_margin_mm + config.minimum_ground_band_mm
        boxes.append(
            BoundingBox(
                min(track.start.x, track.end.x) - margin,
                min(track.start.y, track.end.y) - margin,
                max(track.start.x, track.end.x) + margin,
                max(track.start.y, track.end.y) + margin,
            )
        )
    return boxes


def _default_convex_outline(
    snapshot: BoardSnapshot,
    boxes: Sequence[BoundingBox],
    config: EdgeConfig,
) -> tuple[tuple[Point, ...], int]:
    """Return a convex default outline with only pre-existing concavities.

    Diagonal mode creates an exact-sided circumscribed support polygon.  When
    requested, existing reflex vertices may be reinserted only if the resulting
    contour remains simple and still contains every protected point.  No new
    concavity can therefore be invented by the optimizer.
    """

    protected_points = _box_corners(boxes)
    original = _largest_current_outline(snapshot)
    reflex_vertices = _reflex_vertices(original) if config.preserve_existing_concavities else ()
    target = max(4, config.target_vertex_count)
    reserved = min(len(reflex_vertices), max(0, target - 4))
    base_target = max(4, target - reserved)

    if config.mode == "orthogonal":
        ring = _orthogonal_bounding_outline(boxes, config.grid_mm)
    else:
        ring = _support_polygon(protected_points, base_target, config.grid_mm)

    preserved = 0
    if config.outline_strategy == "convex_preserve_existing_concavities" and reflex_vertices:
        candidates = sorted(
            reflex_vertices,
            key=lambda point: _distance_to_ring(point, ring),
            reverse=True,
        )
        for point in candidates:
            if len(ring) >= target:
                break
            candidate = _insert_point_on_nearest_edge(ring, snap_point(point, config.grid_mm))
            candidate = _normalize_ring(candidate)
            if (
                len(candidate) == len(ring) + 1
                and not _ring_self_intersects(candidate)
                and _contains_all_points(candidate, protected_points)
            ):
                ring = candidate
                preserved += 1

    ring = _densify_ring(ring, target, config.grid_mm, protected_points)
    ring = _normalize_ring(ring)
    if not _contains_all_points(ring, protected_points):
        raise ValueError("The generated outline does not contain all protected board geometry.")
    return ring, preserved


def _enforce_allowed_concavities(
    ring: Sequence[Point],
    config: EdgeConfig,
    preserved_concavity_count: int,
    protected_points: Sequence[Point],
) -> tuple[tuple[Point, ...], int, bool]:
    """Remove any concavity that was not explicitly preserved from Edge.Cuts."""

    normalized = _normalize_ring(ring)
    if config.outline_strategy == "legacy_concave":
        return normalized, preserved_concavity_count, False
    reflex_count = len(_reflex_vertices(normalized))
    if reflex_count <= preserved_concavity_count:
        return normalized, preserved_concavity_count, False

    # Grid rounding and radial expansion can turn a nearly collinear vertex into
    # a tiny reflex corner.  Falling back to the convex hull is safer than
    # inventing a new recess that did not exist in the source Edge.Cuts.
    convex = tuple(convex_hull(normalized))
    if not _contains_all_points(convex, protected_points):
        convex = _expand_until_contains(convex, protected_points, config.grid_mm)
    convex = _densify_ring(convex, config.target_vertex_count, config.grid_mm, protected_points)
    if not _contains_all_points(convex, protected_points) or _ring_self_intersects(convex):
        raise ValueError("Unable to restore a safe convex board outline after grid snapping.")
    return _normalize_ring(convex), 0, True


def _box_corners(boxes: Sequence[BoundingBox]) -> tuple[Point, ...]:
    """Return every protected box corner."""

    return tuple(
        point
        for box in boxes
        for point in (
            Point(box.min_x, box.min_y),
            Point(box.max_x, box.min_y),
            Point(box.max_x, box.max_y),
            Point(box.min_x, box.max_y),
        )
    )


def _support_polygon(points: Sequence[Point], side_count: int, grid: float) -> tuple[Point, ...]:
    """Build a minimum-area sampled circumscribed polygon with fixed normals."""

    if side_count <= 4:
        hull = convex_hull(points)
        if len(hull) <= side_count:
            snapped_hull = tuple(snap_point(point, grid) for point in hull)
            return _densify_ring(snapped_hull, side_count, grid, points)
    best: tuple[Point, ...] | None = None
    best_area = math.inf
    # Rotate the normal fan to avoid needless area for strongly oriented boards.
    for sample in range(max(8, side_count * 2)):
        rotation = (math.pi / side_count) * sample / max(1, side_count)
        normals = tuple(
            Point(
                math.cos(rotation + 2.0 * math.pi * index / side_count),
                math.sin(rotation + 2.0 * math.pi * index / side_count),
            )
            for index in range(side_count)
        )
        supports = tuple(max(dot(point, normal) for point in points) for normal in normals)
        vertices: list[Point] = []
        valid = True
        for index, first_normal in enumerate(normals):
            second_normal = normals[(index + 1) % side_count]
            determinant = first_normal.x * second_normal.y - first_normal.y * second_normal.x
            if abs(determinant) <= 1.0e-10:
                valid = False
                break
            first_support = supports[index]
            second_support = supports[(index + 1) % side_count]
            vertices.append(
                Point(
                    (first_support * second_normal.y - first_normal.y * second_support) / determinant,
                    (first_normal.x * second_support - first_support * second_normal.x) / determinant,
                )
            )
        if not valid:
            continue
        ring = _normalize_ring(vertices)
        if not _contains_all_points(ring, points):
            continue
        area = abs(polygon_signed_area(ring))
        if area < best_area:
            best = ring
            best_area = area
    if best is None:
        best = tuple(convex_hull(points))

    snapped = tuple(snap_point(point, grid) for point in best)
    snapped = tuple(convex_hull(_normalize_ring(snapped)))
    if not _contains_all_points(snapped, points):
        snapped = _expand_until_contains(snapped, points, grid)
    snapped = tuple(convex_hull(snapped))
    result = _densify_ring(snapped, side_count, grid, points)
    if not _contains_all_points(result, points):
        raise ValueError("The fixed-sided support polygon does not contain all protected points.")
    return result


def _expand_until_contains(
    ring: Sequence[Point],
    points: Sequence[Point],
    grid: float,
) -> tuple[Point, ...]:
    """Expand a snapped convex ring until it contains all protected points.

    Grid rounding can move a mathematically circumscribed support polygon
    slightly inward.  The previous fixed 24-step loop could return the unsafe
    original contour.  This routine now uses monotonic exponential expansion
    and fails closed instead of returning a contour that violates containment.
    """

    normalized = _normalize_ring(ring)
    if _contains_all_points(normalized, points):
        return normalized
    if len(normalized) < 3:
        raise ValueError("Cannot expand a degenerate board outline.")

    center = Point(
        sum(point.x for point in normalized) / len(normalized),
        sum(point.y for point in normalized) / len(normalized),
    )
    radius = max(distance(center, point) for point in normalized)
    if radius <= 1.0e-9:
        raise ValueError("Cannot expand a zero-radius board outline.")

    # At least one grid unit of radial growth is attempted early, while the
    # multiplicative term guarantees progress on large boards.
    growth = max(1.01, 1.0 + grid / radius)
    factor = 1.0
    for _ in range(128):
        factor *= growth
        candidate = tuple(
            snap_point(
                Point(
                    center.x + (point.x - center.x) * factor,
                    center.y + (point.y - center.y) * factor,
                ),
                grid,
            )
            for point in normalized
        )
        candidate = _normalize_ring(candidate)
        if (
            len(candidate) >= 3
            and not _ring_self_intersects(candidate)
            and _contains_all_points(candidate, points)
        ):
            return candidate
    raise ValueError("Unable to expand the board outline around all protected geometry.")


def _ring_segments(ring: Sequence[Point]) -> tuple[EdgePrimitive, ...]:
    """Return closed line primitives for a polygon ring."""

    normalized = _normalize_ring(ring)
    if len(normalized) < 3:
        return ()
    return tuple(
        EdgePrimitive("segment", normalized[index], normalized[(index + 1) % len(normalized)])
        for index in range(len(normalized))
        if distance(normalized[index], normalized[(index + 1) % len(normalized)]) > 1.0e-9
    )


def _reverse_primitive(primitive: EdgePrimitive) -> EdgePrimitive:
    """Return one outline primitive with reversed traversal direction."""

    return EdgePrimitive(primitive.kind, primitive.end, primitive.start, primitive.mid)


def _ordered_edge_primitive_loops(
    edges: Sequence[BoardEdge],
    tolerance_mm: float = 1.0e-4,
) -> list[tuple[EdgePrimitive, ...]]:
    """Reconstruct closed primitive loops while preserving circular arcs."""

    def key(point: Point) -> tuple[int, int]:
        return (round(point.x / tolerance_mm), round(point.y / tolerance_mm))

    adjacency: dict[tuple[int, int], list[int]] = defaultdict(list)
    for index, edge in enumerate(edges):
        adjacency[key(edge.start)].append(index)
        adjacency[key(edge.end)].append(index)

    unused = set(range(len(edges)))
    loops: list[tuple[EdgePrimitive, ...]] = []
    while unused:
        first_index = min(unused)
        first_edge = edges[first_index]
        unused.remove(first_index)
        first = EdgePrimitive(first_edge.kind, first_edge.start, first_edge.end, first_edge.mid)
        chain = [first]
        start_key = key(first.start)
        current_key = key(first.end)
        guard = len(edges) + 1
        while current_key != start_key and guard > 0:
            guard -= 1
            candidates = [index for index in adjacency.get(current_key, ()) if index in unused]
            if not candidates:
                break
            current = chain[-1].end
            previous = chain[-1].start
            incoming = normalize(subtract(current, previous))

            def continuation_score(
                index: int,
                current_key: tuple[int, int] = current_key,
                current: Point = current,
                incoming: Point = incoming,
            ) -> tuple[float, int]:
                edge = edges[index]
                other = edge.end if key(edge.start) == current_key else edge.start
                direction = normalize(subtract(other, current))
                return (dot(incoming, direction), -index)

            next_index = max(candidates, key=continuation_score)
            raw = edges[next_index]
            primitive = EdgePrimitive(raw.kind, raw.start, raw.end, raw.mid)
            if key(primitive.start) != current_key:
                primitive = _reverse_primitive(primitive)
            unused.remove(next_index)
            chain.append(primitive)
            current_key = key(primitive.end)
        if current_key == start_key and len(chain) >= 2:
            loops.append(tuple(chain))
    return loops


def _sampled_current_loops(
    snapshot: BoardSnapshot,
    maximum_step_mm: float,
) -> list[tuple[Point, ...]]:
    """Return all current Edge.Cuts loops sampled with circular arcs intact."""

    loops: list[tuple[Point, ...]] = []
    for primitives in _ordered_edge_primitive_loops(snapshot.edges):
        sampled = _normalize_ring(_sample_primitives(primitives, maximum_step_mm))
        if len(sampled) >= 3 and not _ring_self_intersects(sampled):
            loops.append(sampled)
    if loops:
        return loops
    return [_normalize_ring(loop) for loop in _edge_loops(snapshot.edges) if len(loop) >= 3]


def _largest_current_outline_sampled(
    snapshot: BoardSnapshot,
    maximum_step_mm: float,
) -> tuple[Point, ...]:
    """Return the largest sampled current Edge.Cuts contour."""

    loops = _sampled_current_loops(snapshot, maximum_step_mm)
    if not loops:
        return ()
    return _normalize_ring(max(loops, key=lambda ring: abs(polygon_signed_area(ring))))


def _existing_edge_primitives(snapshot: BoardSnapshot) -> tuple[EdgePrimitive, ...]:
    """Return the largest current Edge.Cuts loop as ordered exact primitives."""

    candidates: list[tuple[float, tuple[EdgePrimitive, ...]]] = []
    for primitives in _ordered_edge_primitive_loops(snapshot.edges):
        sampled = _sample_primitives(primitives, 0.05)
        if len(sampled) >= 3:
            candidates.append((abs(polygon_signed_area(sampled)), primitives))
    if not candidates:
        return ()
    return max(candidates, key=lambda item: item[0])[1]


def _snap_ring_safely(ring: Sequence[Point], grid_mm: float) -> tuple[Point, ...]:
    """Snap every sharp vertex to the configured grid and fail closed."""

    if grid_mm <= 0.0:
        raise ValueError("The edge vertex grid must be positive.")
    snapped = _normalize_ring(tuple(snap_point(point, grid_mm) for point in ring))
    if len(snapped) < 3 or abs(polygon_signed_area(snapped)) <= 1.0e-9:
        raise ValueError("Grid snapping collapsed the current board outline.")
    if _ring_self_intersects(snapped):
        raise ValueError("Grid snapping made the current board outline self-intersecting.")
    return snapped


def _largest_current_outline(snapshot: BoardSnapshot) -> tuple[Point, ...]:
    """Return the largest reconstructed current Edge.Cuts loop."""

    return _largest_current_outline_sampled(snapshot, 0.05)


def _reflex_vertices(ring: Sequence[Point]) -> tuple[Point, ...]:
    """Return concave vertices from a normalized counter-clockwise ring."""

    normalized = _normalize_ring(ring)
    result: list[Point] = []
    for index, vertex in enumerate(normalized):
        previous = normalized[index - 1]
        following = normalized[(index + 1) % len(normalized)]
        first = subtract(vertex, previous)
        second = subtract(following, vertex)
        cross = first.x * second.y - first.y * second.x
        if cross < -1.0e-9:
            result.append(vertex)
    return tuple(result)


def _insert_point_on_nearest_edge(ring: Sequence[Point], point: Point) -> tuple[Point, ...]:
    """Insert a point between the endpoints of its nearest ring edge."""

    if any(distance(point, existing) <= 1.0e-9 for existing in ring):
        return tuple(ring)
    index = min(
        range(len(ring)),
        key=lambda value: point_segment_distance(point, ring[value], ring[(value + 1) % len(ring)]),
    )
    return tuple((*ring[: index + 1], point, *ring[index + 1 :]))


def _distance_to_ring(point: Point, ring: Sequence[Point]) -> float:
    """Return the shortest distance from a point to a polygon boundary."""

    return min(
        point_segment_distance(point, ring[index], ring[(index + 1) % len(ring)])
        for index in range(len(ring))
    )


def _contains_all_points(ring: Sequence[Point], points: Sequence[Point]) -> bool:
    """Return whether all protected points are inside or on the boundary.

    Rounded convex contours can contain thousands of sampled arc points.  A
    binary-search convex-polygon test avoids the previous ``O(P * E)`` scan for
    every protected point while retaining the general fallback for preserved
    concavities.
    """

    normalized = _normalize_ring(ring)
    if len(normalized) < 3:
        return False
    bounds = bounds_from_points(normalized)
    convex = _ring_is_convex(normalized)
    for point in points:
        if (
            point.x < bounds.min_x - 1.0e-6
            or point.x > bounds.max_x + 1.0e-6
            or point.y < bounds.min_y - 1.0e-6
            or point.y > bounds.max_y + 1.0e-6
        ):
            return False
        if convex:
            if not _point_in_convex_ring(point, normalized, 1.0e-6):
                return False
            continue
        if point_in_ring(point, normalized):
            continue
        if (
            min(
                point_segment_distance(point, normalized[index], normalized[(index + 1) % len(normalized)])
                for index in range(len(normalized))
            )
            > 1.0e-6
        ):
            return False
    return True


def _ring_is_convex(ring: Sequence[Point]) -> bool:
    """Return whether a counter-clockwise ring has no reflex turn."""

    orientation = 0
    count = len(ring)
    for index in range(count):
        first = ring[index]
        second = ring[(index + 1) % count]
        third = ring[(index + 2) % count]
        cross = (second.x - first.x) * (third.y - second.y) - (second.y - first.y) * (third.x - second.x)
        scale_value = max(1.0, distance(first, second) * distance(second, third))
        if abs(cross) <= 1.0e-10 * scale_value:
            continue
        sign = 1 if cross > 0.0 else -1
        if orientation == 0:
            orientation = sign
        elif sign != orientation:
            return False
    return orientation >= 0


def _point_in_convex_ring(point: Point, ring: Sequence[Point], tolerance: float) -> bool:
    """Test a point against a normalized convex ring in logarithmic time."""

    origin = ring[0]

    def cross(first: Point, second: Point, third: Point) -> float:
        return (second.x - first.x) * (third.y - first.y) - (second.y - first.y) * (third.x - first.x)

    first_cross = cross(origin, ring[1], point)
    last_cross = cross(origin, ring[-1], point)
    first_tolerance = tolerance * max(1.0, distance(origin, ring[1]))
    last_tolerance = tolerance * max(1.0, distance(origin, ring[-1]))
    if first_cross < -first_tolerance or last_cross > last_tolerance:
        return False
    if abs(first_cross) <= first_tolerance:
        return point_segment_distance(point, origin, ring[1]) <= tolerance
    if abs(last_cross) <= last_tolerance:
        return point_segment_distance(point, origin, ring[-1]) <= tolerance

    low = 1
    high = len(ring) - 1
    while high - low > 1:
        middle = (low + high) // 2
        if cross(origin, ring[middle], point) >= 0.0:
            low = middle
        else:
            high = middle

    edge_tolerance = tolerance * max(1.0, distance(ring[low], ring[high]))
    return cross(ring[low], ring[high], point) >= -edge_tolerance


def _ring_self_intersects(ring: Sequence[Point]) -> bool:
    """Return whether non-adjacent polygon edges intersect."""

    count = len(ring)
    for first in range(count):
        a = ring[first]
        b = ring[(first + 1) % count]
        for second in range(first + 1, count):
            if second in {first, (first + 1) % count} or (second + 1) % count in {first, (first + 1) % count}:
                continue
            c = ring[second]
            d = ring[(second + 1) % count]
            if _segments_intersect(a, b, c, d):
                return True
    return False


def _segments_intersect(a: Point, b: Point, c: Point, d: Point) -> bool:
    """Return whether two closed segments cross away from shared endpoints."""

    def orientation(first: Point, second: Point, third: Point) -> float:
        return (second.x - first.x) * (third.y - first.y) - (second.y - first.y) * (third.x - first.x)

    first = orientation(a, b, c)
    second = orientation(a, b, d)
    third = orientation(c, d, a)
    fourth = orientation(c, d, b)
    return first * second < -1.0e-12 and third * fourth < -1.0e-12


def _densify_ring(
    ring: Sequence[Point],
    target: int,
    grid: float,
    protected_points: Sequence[Point] = (),
) -> tuple[Point, ...]:
    """Add only exactly collinear grid vertices up to the requested count.

    Snapping an arbitrary midpoint of a diagonal edge can move that midpoint
    inside the polygon and invalidate a previously safe circumscribed outline.
    A new vertex is therefore inserted only when an interior lattice point lies
    exactly on the edge.  If the requested count is impossible on the selected
    grid, the function safely returns fewer vertices and the caller reports the
    resulting count to the user.
    """

    result = list(_normalize_ring(ring))
    if grid <= 0.0:
        return tuple(result)

    while len(result) < target:
        candidates: list[tuple[float, int, Point]] = []
        for index, first in enumerate(result):
            second = result[(index + 1) % len(result)]
            first_x = round(first.x / grid)
            first_y = round(first.y / grid)
            second_x = round(second.x / grid)
            second_y = round(second.y / grid)
            delta_x = second_x - first_x
            delta_y = second_y - first_y
            divisor = math.gcd(abs(delta_x), abs(delta_y))
            if divisor <= 1:
                continue
            step_index = divisor // 2
            if step_index <= 0 or step_index >= divisor:
                continue
            point = Point(
                (first_x + delta_x * step_index / divisor) * grid,
                (first_y + delta_y * step_index / divisor) * grid,
            )
            if distance(point, first) <= 1.0e-9 or distance(point, second) <= 1.0e-9:
                continue
            candidates.append((distance(first, second), index, point))

        inserted = False
        for _, index, point in sorted(candidates, key=lambda item: (-item[0], item[1])):
            candidate = tuple((*result[: index + 1], point, *result[index + 1 :]))
            candidate = _normalize_ring(candidate)
            if len(candidate) != len(result) + 1 or _ring_self_intersects(candidate):
                continue
            if protected_points and not _contains_all_points(candidate, protected_points):
                continue
            result = list(candidate)
            inserted = True
            break
        if not inserted:
            break
    return tuple(result)


def _orthogonal_outline(boxes: Sequence[BoundingBox], config: EdgeConfig) -> tuple[Point, ...]:
    """Create a connected rectilinear contour from occupied grid cells."""

    grid = config.grid_mm
    occupied: set[Cell] = set()
    for box in boxes:
        x_start = math.floor(box.min_x / grid)
        x_end = math.ceil(box.max_x / grid)
        y_start = math.floor(box.min_y / grid)
        y_end = math.ceil(box.max_y / grid)
        for x_index in range(x_start, x_end):
            for y_index in range(y_start, y_end):
                occupied.add((x_index, y_index))
    _connect_components(occupied)
    loops = _trace_cell_boundaries(occupied, grid)
    if not loops:
        bounds = _union_bounds(boxes)
        return (
            snap_point(Point(bounds.min_x, bounds.min_y), grid),
            snap_point(Point(bounds.max_x, bounds.min_y), grid),
            snap_point(Point(bounds.max_x, bounds.max_y), grid),
            snap_point(Point(bounds.min_x, bounds.max_y), grid),
        )
    largest = max(loops, key=lambda ring: abs(polygon_signed_area(ring)))
    return simplify_ring(largest, grid * 0.01)


def _orthogonal_bounding_outline(
    boxes: Sequence[BoundingBox],
    grid: float,
) -> tuple[Point, ...]:
    """Create a non-concave snapped rectangle around protected content."""

    bounds = _union_bounds(boxes)
    minimum = snap_point(
        Point(math.floor(bounds.min_x / grid) * grid, math.floor(bounds.min_y / grid) * grid), grid
    )
    maximum = snap_point(
        Point(math.ceil(bounds.max_x / grid) * grid, math.ceil(bounds.max_y / grid) * grid), grid
    )
    return (
        Point(minimum.x, minimum.y),
        Point(maximum.x, minimum.y),
        Point(maximum.x, maximum.y),
        Point(minimum.x, maximum.y),
    )


def _diagonal_outline(boxes: Sequence[BoundingBox], config: EdgeConfig) -> tuple[Point, ...]:
    """Create a snapped diagonal-capable convex contour."""

    points = [
        point
        for box in boxes
        for point in (
            Point(box.min_x, box.min_y),
            Point(box.max_x, box.min_y),
            Point(box.max_x, box.max_y),
            Point(box.min_x, box.max_y),
        )
    ]
    hull = convex_hull(points)
    snapped = tuple(snap_point(point, config.grid_mm) for point in hull)
    return simplify_ring(snapped, config.simplify_tolerance_mm)


def _connect_components(occupied: set[Cell]) -> None:
    """Connect disjoint occupied components with shortest Manhattan corridors."""

    components = _cell_components(occupied)
    while len(components) > 1:
        first = components[0]
        best: tuple[int, Cell, Cell, int] | None = None
        for component_index, component in enumerate(components[1:], start=1):
            for a in first:
                for b in component:
                    metric = abs(a[0] - b[0]) + abs(a[1] - b[1])
                    if best is None or metric < best[0]:
                        best = (metric, a, b, component_index)
        if best is None:
            return
        _, start, end, _ = best
        x, y = start
        while x != end[0]:
            x += 1 if end[0] > x else -1
            occupied.add((x, y))
        while y != end[1]:
            y += 1 if end[1] > y else -1
            occupied.add((x, y))
        components = _cell_components(occupied)


def _cell_components(occupied: set[Cell]) -> list[set[Cell]]:
    """Return four-connected occupied components."""

    remaining = set(occupied)
    components: list[set[Cell]] = []
    while remaining:
        seed = remaining.pop()
        component = {seed}
        queue: deque[Cell] = deque([seed])
        while queue:
            x, y = queue.popleft()
            for neighbor in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
                if neighbor in remaining:
                    remaining.remove(neighbor)
                    component.add(neighbor)
                    queue.append(neighbor)
        components.append(component)
    return components


def _trace_cell_boundaries(occupied: set[Cell], grid: float) -> list[tuple[Point, ...]]:
    """Extract directed boundary loops from a union of grid cells."""

    edges: set[tuple[tuple[int, int], tuple[int, int]]] = set()
    for x, y in occupied:
        candidates = (
            (((x, y), (x + 1, y)), (x, y - 1)),
            (((x + 1, y), (x + 1, y + 1)), (x + 1, y)),
            (((x + 1, y + 1), (x, y + 1)), (x, y + 1)),
            (((x, y + 1), (x, y)), (x - 1, y)),
        )
        for edge, neighbor in candidates:
            if neighbor not in occupied:
                edges.add(edge)

    outgoing: dict[tuple[int, int], list[tuple[int, int]]] = defaultdict(list)
    for start, end in edges:
        outgoing[start].append(end)
    loops: list[tuple[Point, ...]] = []
    unused = set(edges)
    while unused:
        start_edge = next(iter(unused))
        start, current = start_edge
        unused.remove(start_edge)
        vertices = [start, current]
        while current != start:
            options = [end for end in outgoing.get(current, []) if (current, end) in unused]
            if not options:
                break
            next_vertex = _choose_boundary_turn(vertices[-2], current, options)
            unused.remove((current, next_vertex))
            current = next_vertex
            vertices.append(current)
        if len(vertices) >= 4 and vertices[-1] == start:
            loops.append(tuple(Point(x * grid, y * grid) for x, y in vertices[:-1]))
    return loops


def _choose_boundary_turn(
    previous: tuple[int, int],
    current: tuple[int, int],
    options: Sequence[tuple[int, int]],
) -> tuple[int, int]:
    """Choose the rightmost available turn to keep a boundary loop coherent."""

    incoming = (current[0] - previous[0], current[1] - previous[1])
    ranking: list[tuple[int, tuple[int, int]]] = []
    directions = ((1, 0), (0, 1), (-1, 0), (0, -1))
    incoming_index = directions.index(incoming)
    for option in options:
        outgoing = (option[0] - current[0], option[1] - current[1])
        outgoing_index = directions.index(outgoing)
        turn = (outgoing_index - incoming_index) % 4
        priority = {3: 0, 0: 1, 1: 2, 2: 3}[turn]
        ranking.append((priority, option))
    return min(ranking, key=lambda item: item[0])[1]


def _verify_ground_band(
    snapshot: BoardSnapshot,
    ring: Sequence[Point],
    band_mm: float,
    ground_net_regex: str,
) -> bool:
    """Verify one continuous layer of GND copper across the perimeter band."""

    if len(ring) < 3 or band_mm <= 0.0:
        return False
    ground_pattern = re.compile(ground_net_regex, re.IGNORECASE)
    polygons_by_layer: dict[str, list[Polygon]] = defaultdict(list)
    tracks_by_layer: dict[str, list[TrackSegment]] = defaultdict(list)
    for zone in snapshot.zones:
        if zone.is_rule_area or not ground_pattern.search(zone.net or ""):
            continue
        for layer, layer_polygons in zone.filled.items():
            polygons_by_layer[layer].extend(layer_polygons)
    for track in snapshot.tracks:
        if ground_pattern.search(track.net or ""):
            tracks_by_layer[track.layer].append(track)
    candidate_layers = set(polygons_by_layer) | set(tracks_by_layer)
    if not candidate_layers:
        return False

    orientation = 1.0 if polygon_signed_area(ring) > 0.0 else -1.0
    sample_spacing = max(0.10, min(0.50, band_mm * 0.40))
    depth_ratios = (0.15, 0.50, 0.90)
    probes: list[Point] = []
    for index, start in enumerate(ring):
        end = ring[(index + 1) % len(ring)]
        segment_length = distance(start, end)
        if segment_length <= 1.0e-9:
            continue
        samples = max(1, math.ceil(segment_length / sample_spacing))
        tangent = normalize(subtract(end, start))
        inward = Point(-tangent.y * orientation, tangent.x * orientation)
        for sample in range(samples):
            ratio = (sample + 0.5) / samples
            boundary = Point(start.x + (end.x - start.x) * ratio, start.y + (end.y - start.y) * ratio)
            probes.extend(add(boundary, scale(inward, band_mm * depth)) for depth in depth_ratios)

    for layer in candidate_layers:
        polygons = polygons_by_layer.get(layer, ())
        tracks = tracks_by_layer.get(layer, ())
        if all(
            any(point_in_polygon(probe, polygon) for polygon in polygons)
            or any(
                point_segment_distance(probe, track.start, track.end) <= track.width / 2.0 + 1.0e-6
                for track in tracks
            )
            for probe in probes
        ):
            return True
    return False


def _current_board_area(snapshot: BoardSnapshot) -> float:
    """Estimate current board area from closed line and arc Edge.Cuts loops."""

    if not snapshot.edges:
        return 0.0
    loops = _sampled_current_loops(snapshot, 0.025)
    if loops:
        ordered = sorted(loops, key=lambda item: abs(polygon_signed_area(item)), reverse=True)
        total = 0.0
        for index, loop in enumerate(ordered):
            area = abs(polygon_signed_area(loop))
            sample = loop[0]
            nesting_depth = sum(point_in_ring(sample, outer) for outer in ordered[:index])
            total += -area if nesting_depth % 2 else area
        if total > 0.0:
            return total
    bounds = bounds_from_points([point for edge in snapshot.edges for point in (edge.start, edge.end)])
    return bounds.area


def _sample_primitives(
    primitives: Sequence[EdgePrimitive],
    maximum_step_mm: float,
) -> tuple[Point, ...]:
    """Sample line and arc primitives into a closed polygonal boundary."""

    if not primitives:
        return ()
    step = max(maximum_step_mm, 1.0e-3)
    points: list[Point] = []
    for primitive in primitives:
        if not points or distance(points[-1], primitive.start) > 1.0e-6:
            points.append(primitive.start)
        if primitive.kind != "arc" or primitive.mid is None:
            # Straight segments are represented exactly by their endpoints.
            # Subdividing long lines at the arc sampling step produced thousands
            # of collinear vertices and made self-intersection checks quadratic
            # without improving area or containment accuracy.
            points.append(primitive.end)
            continue

        center = _circle_center(primitive.start, primitive.mid, primitive.end)
        if center is None:
            points.append(primitive.end)
            continue
        radius = distance(center, primitive.start)
        start_angle = math.atan2(primitive.start.y - center.y, primitive.start.x - center.x)
        mid_angle = math.atan2(primitive.mid.y - center.y, primitive.mid.x - center.x)
        end_angle = math.atan2(primitive.end.y - center.y, primitive.end.x - center.x)
        ccw_sweep = (end_angle - start_angle) % (2.0 * math.pi)
        ccw_to_mid = (mid_angle - start_angle) % (2.0 * math.pi)
        sweep = ccw_sweep if ccw_to_mid <= ccw_sweep + 1.0e-8 else ccw_sweep - 2.0 * math.pi
        count = max(2, math.ceil(abs(sweep) * radius / step))
        points.extend(
            Point(
                center.x + radius * math.cos(start_angle + sweep * index / count),
                center.y + radius * math.sin(start_angle + sweep * index / count),
            )
            for index in range(1, count + 1)
        )
    if len(points) > 1 and distance(points[0], points[-1]) <= 1.0e-6:
        points.pop()
    return tuple(points)


def _circle_center(first: Point, second: Point, third: Point) -> Point | None:
    """Return the circumcenter of three points, or ``None`` when collinear."""

    denominator = 2.0 * (
        first.x * (second.y - third.y) + second.x * (third.y - first.y) + third.x * (first.y - second.y)
    )
    if abs(denominator) <= 1.0e-10:
        return None
    first_norm = first.x * first.x + first.y * first.y
    second_norm = second.x * second.x + second.y * second.y
    third_norm = third.x * third.x + third.y * third.y
    return Point(
        (
            first_norm * (second.y - third.y)
            + second_norm * (third.y - first.y)
            + third_norm * (first.y - second.y)
        )
        / denominator,
        (
            first_norm * (third.x - second.x)
            + second_norm * (first.x - third.x)
            + third_norm * (second.x - first.x)
        )
        / denominator,
    )


def _edge_loops(
    edges: Sequence[BoardEdge],
    tolerance_mm: float = 1.0e-4,
) -> list[tuple[Point, ...]]:
    """Reconstruct closed loops from unordered and inconsistently directed edges."""

    def key(point: Point) -> tuple[int, int]:
        return (round(point.x / tolerance_mm), round(point.y / tolerance_mm))

    adjacency: dict[tuple[int, int], list[int]] = defaultdict(list)
    for index, edge in enumerate(edges):
        adjacency[key(edge.start)].append(index)
        adjacency[key(edge.end)].append(index)

    unused = set(range(len(edges)))
    loops: list[tuple[Point, ...]] = []
    while unused:
        first_index = min(unused)
        first_edge = edges[first_index]
        unused.remove(first_index)
        ring = [first_edge.start, first_edge.end]
        start_key = key(first_edge.start)
        current_key = key(first_edge.end)
        guard = len(edges) + 1
        while current_key != start_key and guard > 0:
            guard -= 1
            candidates = [index for index in adjacency.get(current_key, ()) if index in unused]
            if not candidates:
                break
            current = ring[-1]
            previous = ring[-2]
            incoming = normalize(subtract(current, previous))

            def continuation_score(
                index: int,
                current_key: tuple[int, int] = current_key,
                current: Point = current,
                incoming: Point = incoming,
            ) -> float:
                edge = edges[index]
                other = edge.end if key(edge.start) == current_key else edge.start
                return dot(incoming, normalize(subtract(other, current)))

            next_index = max(candidates, key=continuation_score)
            next_edge = edges[next_index]
            unused.remove(next_index)
            other = next_edge.end if key(next_edge.start) == current_key else next_edge.start
            ring.append(other)
            current_key = key(other)
        if current_key == start_key and len(ring) >= 4:
            if distance(ring[0], ring[-1]) <= tolerance_mm * 1.5:
                ring.pop()
            if len(ring) >= 3:
                loops.append(tuple(ring))
    return loops


def _expand_ring_by_distance(
    ring: Sequence[Point],
    outward_distance: float,
    grid: float,
) -> tuple[Point, ...]:
    """Scale a ring radially by at least an approximate outward distance."""

    normalized = _normalize_ring(ring)
    center = Point(
        sum(point.x for point in normalized) / len(normalized),
        sum(point.y for point in normalized) / len(normalized),
    )
    radius = max(distance(center, point) for point in normalized)
    if radius <= 1.0e-9:
        return normalized
    factor = 1.0 + max(outward_distance, grid) / radius
    candidate = tuple(
        snap_point(
            Point(
                center.x + (point.x - center.x) * factor,
                center.y + (point.y - center.y) * factor,
            ),
            grid,
        )
        for point in normalized
    )
    candidate = _normalize_ring(candidate)
    if len(candidate) < 3 or _ring_self_intersects(candidate):
        raise ValueError("Rounded-corner safety expansion produced an invalid outline.")
    return candidate


def _expand_ring_to_area(ring: Sequence[Point], required_area: float, grid: float) -> tuple[Point, ...]:
    """Scale a ring about its centroid until it reaches a minimum area."""

    current_area = abs(polygon_signed_area(ring))
    if current_area <= 0.0 or current_area >= required_area:
        return tuple(ring)
    center = Point(
        sum(point.x for point in ring) / len(ring),
        sum(point.y for point in ring) / len(ring),
    )
    factor = math.sqrt(required_area / current_area)
    return tuple(
        snap_point(
            Point(center.x + (point.x - center.x) * factor, center.y + (point.y - center.y) * factor),
            grid,
        )
        for point in ring
    )


def _normalize_ring(ring: Sequence[Point]) -> tuple[Point, ...]:
    """Remove duplicate vertices and enforce counter-clockwise winding."""

    deduplicated: list[Point] = []
    for point in ring:
        if not deduplicated or distance(point, deduplicated[-1]) > 1.0e-9:
            deduplicated.append(point)
    if len(deduplicated) > 1 and distance(deduplicated[0], deduplicated[-1]) <= 1.0e-9:
        deduplicated.pop()
    if polygon_signed_area(deduplicated) < 0.0:
        deduplicated.reverse()
    return tuple(deduplicated)


def _union_bounds(boxes: Iterable[BoundingBox]) -> BoundingBox:
    """Return the union of bounding boxes."""

    collected = tuple(boxes)
    return BoundingBox(
        min(box.min_x for box in collected),
        min(box.min_y for box in collected),
        max(box.max_x for box in collected),
        max(box.max_y for box in collected),
    )
