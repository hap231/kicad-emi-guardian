"""Numerically defensive two-dimensional geometry helpers."""

from __future__ import annotations

import math
from collections.abc import Iterable, Sequence

from .models import BoundingBox, Point, Polygon, bounds_from_points

EPSILON = 1.0e-9


def add(a: Point, b: Point) -> Point:
    """Return ``a + b``."""

    return Point(a.x + b.x, a.y + b.y)


def subtract(a: Point, b: Point) -> Point:
    """Return ``a - b``."""

    return Point(a.x - b.x, a.y - b.y)


def scale(point: Point, factor: float) -> Point:
    """Return *point* scaled by *factor*."""

    return Point(point.x * factor, point.y * factor)


def dot(a: Point, b: Point) -> float:
    """Return the dot product."""

    return a.x * b.x + a.y * b.y


def cross(a: Point, b: Point) -> float:
    """Return the two-dimensional cross product scalar."""

    return a.x * b.y - a.y * b.x


def length(vector: Point) -> float:
    """Return vector length."""

    return math.hypot(vector.x, vector.y)


def distance(a: Point, b: Point) -> float:
    """Return Euclidean distance between two points."""

    return length(subtract(a, b))


def normalize(vector: Point) -> Point:
    """Return a unit vector, or zero when the input is degenerate."""

    magnitude = length(vector)
    if magnitude <= EPSILON:
        return Point(0.0, 0.0)
    return Point(vector.x / magnitude, vector.y / magnitude)


def interpolate(a: Point, b: Point, ratio: float) -> Point:
    """Interpolate between *a* and *b*."""

    return Point(a.x + (b.x - a.x) * ratio, a.y + (b.y - a.y) * ratio)


def polygon_signed_area(points: Sequence[Point]) -> float:
    """Return the signed area of a closed polygon."""

    if len(points) < 3:
        return 0.0
    return 0.5 * sum(first.x * second.y - second.x * first.y for first, second in pairwise_closed(points))


def polygon_area(polygon: Polygon) -> float:
    """Return polygon area with holes subtracted."""

    outer = abs(polygon_signed_area(polygon.outline))
    holes = sum(abs(polygon_signed_area(hole)) for hole in polygon.holes)
    return max(0.0, outer - holes)


def polygon_perimeter(points: Sequence[Point]) -> float:
    """Return the perimeter of a closed point sequence."""

    return sum(distance(first, second) for first, second in pairwise_closed(points))


def polygon_centroid(points: Sequence[Point]) -> Point:
    """Return the area centroid, with a bounding-box fallback."""

    signed_area = polygon_signed_area(points)
    if abs(signed_area) <= EPSILON:
        return bounds_from_points(points).center
    factor = 1.0 / (6.0 * signed_area)
    x = 0.0
    y = 0.0
    for first, second in pairwise_closed(points):
        term = first.x * second.y - second.x * first.y
        x += (first.x + second.x) * term
        y += (first.y + second.y) * term
    return Point(x * factor, y * factor)


def pairwise_closed(points: Sequence[Point]) -> Iterable[tuple[Point, Point]]:
    """Yield closed consecutive point pairs."""

    if len(points) < 2:
        return
    for index, point in enumerate(points):
        yield point, points[(index + 1) % len(points)]


def point_on_segment(point: Point, start: Point, end: Point, tolerance: float = 1.0e-6) -> bool:
    """Return whether *point* lies on the segment within *tolerance*."""

    segment = subtract(end, start)
    relative = subtract(point, start)
    if abs(cross(segment, relative)) > tolerance * max(1.0, length(segment)):
        return False
    projection = dot(relative, segment)
    return -tolerance <= projection <= dot(segment, segment) + tolerance


def point_in_ring(point: Point, ring: Sequence[Point]) -> bool:
    """Return whether *point* is inside or on a polygon ring."""

    if len(ring) < 3:
        return False
    inside = False
    previous = ring[-1]
    for current in ring:
        if point_on_segment(point, previous, current):
            return True
        crosses = (current.y > point.y) != (previous.y > point.y)
        if crosses:
            denominator = previous.y - current.y
            if abs(denominator) > EPSILON:
                x_at_y = (previous.x - current.x) * (point.y - current.y) / denominator + current.x
                if point.x < x_at_y:
                    inside = not inside
        previous = current
    return inside


def point_in_polygon(point: Point, polygon: Polygon) -> bool:
    """Return whether *point* lies in *polygon* and outside its holes."""

    return point_in_ring(point, polygon.outline) and not any(
        point_in_ring(point, hole) for hole in polygon.holes
    )


def closest_point_on_segment(point: Point, start: Point, end: Point) -> Point:
    """Return the closest point on a segment."""

    vector = subtract(end, start)
    denominator = dot(vector, vector)
    if denominator <= EPSILON:
        return start
    ratio = max(0.0, min(1.0, dot(subtract(point, start), vector) / denominator))
    return interpolate(start, end, ratio)


def point_segment_distance(point: Point, start: Point, end: Point) -> float:
    """Return point-to-segment distance."""

    return distance(point, closest_point_on_segment(point, start, end))


def orientation(a: Point, b: Point, c: Point) -> float:
    """Return signed orientation of the triangle ``a, b, c``."""

    return cross(subtract(b, a), subtract(c, a))


def segments_intersect(
    a_start: Point,
    a_end: Point,
    b_start: Point,
    b_end: Point,
    tolerance: float = 1.0e-9,
) -> bool:
    """Return whether two closed segments intersect."""

    o1 = orientation(a_start, a_end, b_start)
    o2 = orientation(a_start, a_end, b_end)
    o3 = orientation(b_start, b_end, a_start)
    o4 = orientation(b_start, b_end, a_end)
    if ((o1 > tolerance and o2 < -tolerance) or (o1 < -tolerance and o2 > tolerance)) and (
        (o3 > tolerance and o4 < -tolerance) or (o3 < -tolerance and o4 > tolerance)
    ):
        return True
    return any(
        (abs(value) <= tolerance and point_on_segment(point, start, end, tolerance=max(tolerance, 1.0e-6)))
        for value, point, start, end in (
            (o1, b_start, a_start, a_end),
            (o2, b_end, a_start, a_end),
            (o3, a_start, b_start, b_end),
            (o4, a_end, b_start, b_end),
        )
    )


def segment_distance(a_start: Point, a_end: Point, b_start: Point, b_end: Point) -> float:
    """Return minimum distance between two segments."""

    if segments_intersect(a_start, a_end, b_start, b_end):
        return 0.0
    return min(
        point_segment_distance(a_start, b_start, b_end),
        point_segment_distance(a_end, b_start, b_end),
        point_segment_distance(b_start, a_start, a_end),
        point_segment_distance(b_end, a_start, a_end),
    )


def angle_between(a: Point, b: Point) -> float:
    """Return the unsigned angle between vectors in degrees."""

    denominator = length(a) * length(b)
    if denominator <= EPSILON:
        return 180.0
    cosine = max(-1.0, min(1.0, dot(a, b) / denominator))
    return math.degrees(math.acos(cosine))


def direction_angle(start: Point, end: Point) -> float:
    """Return segment direction in degrees in the range ``[0, 180)``."""

    return math.degrees(math.atan2(end.y - start.y, end.x - start.x)) % 180.0


def acute_direction_difference(first_deg: float, second_deg: float) -> float:
    """Return the acute difference between two undirected angles."""

    difference = abs(first_deg - second_deg) % 180.0
    return min(difference, 180.0 - difference)


def parallel_overlap_length(
    first_start: Point,
    first_end: Point,
    second_start: Point,
    second_end: Point,
) -> float:
    """Return projected overlap along the first segment direction."""

    axis = normalize(subtract(first_end, first_start))
    if length(axis) <= EPSILON:
        return 0.0
    first_values = sorted((dot(first_start, axis), dot(first_end, axis)))
    second_values = sorted((dot(second_start, axis), dot(second_end, axis)))
    return max(0.0, min(first_values[1], second_values[1]) - max(first_values[0], second_values[0]))


def segment_crosses_polygon(start: Point, end: Point, polygon: Polygon) -> bool:
    """Return whether a segment enters or crosses a polygon."""

    if point_in_polygon(start, polygon) or point_in_polygon(end, polygon):
        return True
    return any(
        segments_intersect(start, end, first, second) for first, second in pairwise_closed(polygon.outline)
    )


def ring_distance(point: Point, ring: Sequence[Point]) -> float:
    """Return minimum distance from a point to a ring."""

    if len(ring) < 2:
        return math.inf
    return min(point_segment_distance(point, start, end) for start, end in pairwise_closed(ring))


def polygon_boundary_distance(point: Point, polygon: Polygon) -> float:
    """Return minimum distance from a point to any polygon boundary."""

    return min(
        [ring_distance(point, polygon.outline), *(ring_distance(point, hole) for hole in polygon.holes)]
    )


def nearest_point_on_polygon(point: Point, polygon: Polygon) -> Point:
    """Return the closest point on a polygon boundary."""

    candidates = [
        closest_point_on_segment(point, start, end)
        for ring in (polygon.outline, *polygon.holes)
        for start, end in pairwise_closed(ring)
    ]
    return min(candidates, key=lambda candidate: distance(point, candidate), default=point)


def convex_hull(points: Sequence[Point]) -> tuple[Point, ...]:
    """Return the monotonic-chain convex hull."""

    unique = sorted(set(points), key=lambda point: (point.x, point.y))
    if len(unique) <= 1:
        return tuple(unique)

    def build(sequence: Sequence[Point]) -> list[Point]:
        half: list[Point] = []
        for point in sequence:
            while len(half) >= 2 and orientation(half[-2], half[-1], point) <= 0.0:
                half.pop()
            half.append(point)
        return half

    lower = build(unique)
    upper = build(tuple(reversed(unique)))
    return tuple(lower[:-1] + upper[:-1])


def simplify_ring(points: Sequence[Point], tolerance: float) -> tuple[Point, ...]:
    """Remove nearly collinear vertices from a closed ring."""

    if len(points) <= 3:
        return tuple(points)
    result: list[Point] = []
    for index, point in enumerate(points):
        previous = points[index - 1]
        following = points[(index + 1) % len(points)]
        if point_segment_distance(point, previous, following) > tolerance:
            result.append(point)
    return tuple(result if len(result) >= 3 else points)


def snap_point(point: Point, grid: float) -> Point:
    """Snap a point to a positive grid."""

    return Point(round(point.x / grid) * grid, round(point.y / grid) * grid)


def bbox_distance(first: BoundingBox, second: BoundingBox) -> float:
    """Return minimum distance between two axis-aligned boxes."""

    dx = max(first.min_x - second.max_x, second.min_x - first.max_x, 0.0)
    dy = max(first.min_y - second.max_y, second.min_y - first.max_y, 0.0)
    return math.hypot(dx, dy)
