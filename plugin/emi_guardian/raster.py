"""Raster morphology used to identify narrow copper appendages.

The detector intentionally uses a deterministic grid rather than a native
geometry dependency.  This keeps installation small and makes the resolution
and completeness trade-off explicit through ``raster_step_mm``.
"""

from __future__ import annotations

import math
from collections import deque
from collections.abc import Iterable
from dataclasses import dataclass

from .geometry import distance, point_in_polygon
from .models import BoundingBox, Point, Polygon, bounds_from_points

Cell = tuple[int, int]
_NEIGHBORS_4: tuple[Cell, ...] = ((1, 0), (-1, 0), (0, 1), (0, -1))
_NEIGHBORS_8: tuple[Cell, ...] = (
    (1, 0),
    (-1, 0),
    (0, 1),
    (0, -1),
    (1, 1),
    (1, -1),
    (-1, 1),
    (-1, -1),
)


@dataclass(frozen=True)
class RasterFeature:
    """One residual component produced by morphological opening."""

    cells: frozenset[Cell]
    area_mm2: float
    length_mm: float
    width_mm: float
    tip: Point
    gate: Point
    centroid: Point
    bounds: BoundingBox
    attachment_cells: int
    isolated: bool
    origin: Point
    step_mm: float


@dataclass
class RasterGrid:
    """Rasterized polygon and derived morphology data."""

    origin: Point
    step_mm: float
    occupied: set[Cell]

    def point(self, cell: Cell) -> Point:
        """Return the center point of *cell*."""

        return Point(
            self.origin.x + (cell[0] + 0.5) * self.step_mm,
            self.origin.y + (cell[1] + 0.5) * self.step_mm,
        )

    def boundary_cells(self) -> set[Cell]:
        """Return occupied cells touching an empty four-neighbor."""

        return {
            cell
            for cell in self.occupied
            if any((cell[0] + dx, cell[1] + dy) not in self.occupied for dx, dy in _NEIGHBORS_4)
        }

    def distance_to_boundary(self) -> dict[Cell, int]:
        """Return an eight-neighbor cell-distance transform."""

        boundary = self.boundary_cells()
        distances = {cell: 0 for cell in boundary}
        queue: deque[Cell] = deque(boundary)
        while queue:
            cell = queue.popleft()
            next_distance = distances[cell] + 1
            for dx, dy in _NEIGHBORS_8:
                neighbor = (cell[0] + dx, cell[1] + dy)
                if neighbor in self.occupied and neighbor not in distances:
                    distances[neighbor] = next_distance
                    queue.append(neighbor)
        return distances

    def morphological_opening(self, radius_mm: float) -> tuple[set[Cell], set[Cell]]:
        """Return ``(opened, residual)`` for a disk-like opening."""

        radius_cells = max(1, math.ceil(radius_mm / self.step_mm))
        distances = self.distance_to_boundary()
        core = {cell for cell, value in distances.items() if value >= radius_cells}
        if not core:
            return set(), set(self.occupied)

        opened: set[Cell] = set()
        squared_limit = radius_cells * radius_cells
        for core_x, core_y in core:
            for dx in range(-radius_cells, radius_cells + 1):
                for dy in range(-radius_cells, radius_cells + 1):
                    if dx * dx + dy * dy > squared_limit:
                        continue
                    candidate = (core_x + dx, core_y + dy)
                    if candidate in self.occupied:
                        opened.add(candidate)
        return opened, self.occupied - opened

    def components(self, cells: set[Cell]) -> tuple[frozenset[Cell], ...]:
        """Split *cells* into eight-connected components."""

        remaining = set(cells)
        result: list[frozenset[Cell]] = []
        while remaining:
            seed = remaining.pop()
            component = {seed}
            queue: deque[Cell] = deque([seed])
            while queue:
                current = queue.popleft()
                for dx, dy in _NEIGHBORS_8:
                    neighbor = (current[0] + dx, current[1] + dy)
                    if neighbor in remaining:
                        remaining.remove(neighbor)
                        component.add(neighbor)
                        queue.append(neighbor)
            result.append(frozenset(component))
        return tuple(result)

    def feature(self, component: frozenset[Cell], opened: set[Cell]) -> RasterFeature:
        """Summarize one residual component."""

        attachments = {
            cell
            for cell in component
            if any((cell[0] + dx, cell[1] + dy) in opened for dx, dy in _NEIGHBORS_8)
        }
        isolated = not attachments
        if attachments:
            distance_cells, farthest = _geodesic_distances(component, attachments)
            gate_cell = min(
                attachments,
                key=lambda cell: distance(self.point(cell), self.point(farthest)),
            )
            length_mm = distance_cells.get(farthest, 0) * self.step_mm
        else:
            centroid_cell = _cell_centroid(component)
            gate_cell = min(component, key=lambda cell: _cell_distance(cell, centroid_cell))
            distance_cells, farthest = _geodesic_distances(component, {gate_cell})
            length_mm = max(distance_cells.values(), default=0) * self.step_mm

        area_mm2 = len(component) * self.step_mm * self.step_mm
        effective_length = max(length_mm, self.step_mm)
        width_mm = max(self.step_mm, area_mm2 / effective_length)
        points = [self.point(cell) for cell in component]
        centroid = Point(
            sum(point.x for point in points) / len(points),
            sum(point.y for point in points) / len(points),
        )
        return RasterFeature(
            cells=component,
            area_mm2=area_mm2,
            length_mm=length_mm,
            width_mm=width_mm,
            tip=self.point(farthest),
            gate=self.point(gate_cell),
            centroid=centroid,
            bounds=bounds_from_points(points).inflate(self.step_mm / 2.0),
            attachment_cells=len(attachments),
            isolated=isolated,
            origin=self.origin,
            step_mm=self.step_mm,
        )


def rasterize_polygon(polygon: Polygon, requested_step_mm: float, max_cells: int) -> RasterGrid:
    """Rasterize a polygon, increasing the step when required by *max_cells*."""

    bounds = bounds_from_points(polygon.outline)
    step = requested_step_mm
    estimated = max(1.0, bounds.width / step) * max(1.0, bounds.height / step)
    if estimated > max_cells:
        step *= math.sqrt(estimated / max_cells)

    padding = step
    origin = Point(bounds.min_x - padding, bounds.min_y - padding)
    columns = max(1, math.ceil((bounds.width + 2.0 * padding) / step))
    rows = max(1, math.ceil((bounds.height + 2.0 * padding) / step))
    occupied: set[Cell] = set()
    for x_index in range(columns):
        x = origin.x + (x_index + 0.5) * step
        for y_index in range(rows):
            point = Point(x, origin.y + (y_index + 0.5) * step)
            if point_in_polygon(point, polygon):
                occupied.add((x_index, y_index))
    return RasterGrid(origin=origin, step_mm=step, occupied=occupied)


def detect_narrow_features(
    polygon: Polygon,
    raster_step_mm: float,
    neck_width_mm: float,
    max_cells: int,
) -> tuple[RasterFeature, ...]:
    """Detect narrow appendages using opening by half the neck width."""

    grid = rasterize_polygon(polygon, raster_step_mm, max_cells)
    if not grid.occupied:
        return ()
    opened, residual = grid.morphological_opening(neck_width_mm / 2.0)
    return tuple(grid.feature(component, opened) for component in grid.components(residual))


def cells_to_outline(feature: RasterFeature, simplify: bool = True) -> Polygon:
    """Return an orthogonal boundary polygon for the exact residual cell union.

    Shared cell edges cancel.  The largest remaining loop is used as the rule
    area outline; smaller loops become holes when they are enclosed.  This is
    substantially less destructive than the previous bounding rectangle.
    """

    edges: set[tuple[tuple[int, int], tuple[int, int]]] = set()
    for x, y in feature.cells:
        corners = ((x, y), (x + 1, y), (x + 1, y + 1), (x, y + 1))
        for index, first in enumerate(corners):
            second = corners[(index + 1) % 4]
            reverse = (second, first)
            if reverse in edges:
                edges.remove(reverse)
            else:
                edges.add((first, second))
    outgoing: dict[tuple[int, int], list[tuple[int, int]]] = {}
    for first, second in edges:
        outgoing.setdefault(first, []).append(second)
    loops: list[list[tuple[int, int]]] = []
    remaining = set(edges)
    while remaining:
        first_edge = min(remaining)
        start, current = first_edge
        loop = [start]
        remaining.remove(first_edge)
        while current != start:
            loop.append(current)
            candidates = sorted(
                next_point for next_point in outgoing.get(current, ()) if (current, next_point) in remaining
            )
            if not candidates:
                break
            next_point = candidates[0]
            remaining.remove((current, next_point))
            current = next_point
        if current == start and len(loop) >= 4:
            loops.append(loop)
    if not loops:
        bounds = feature.bounds
        return Polygon(
            outline=(
                Point(bounds.min_x, bounds.min_y),
                Point(bounds.max_x, bounds.min_y),
                Point(bounds.max_x, bounds.max_y),
                Point(bounds.min_x, bounds.max_y),
            )
        )

    def to_points(loop: list[tuple[int, int]]) -> tuple[Point, ...]:
        points = tuple(
            Point(
                feature.origin.x + x * feature.step_mm,
                feature.origin.y + y * feature.step_mm,
            )
            for x, y in loop
        )
        if not simplify or len(points) <= 4:
            return points
        result: list[Point] = []
        for index, point in enumerate(points):
            previous = points[index - 1]
            following = points[(index + 1) % len(points)]
            if (previous.x == point.x == following.x) or (previous.y == point.y == following.y):
                continue
            result.append(point)
        return tuple(result) if len(result) >= 4 else points

    point_loops = [to_points(loop) for loop in loops]
    point_loops.sort(key=lambda ring: abs(_signed_area(ring)), reverse=True)
    outline = point_loops[0]
    holes = tuple(ring for ring in point_loops[1:] if _point_in_ring_average(ring, outline))
    if _signed_area(outline) < 0.0:
        outline = tuple(reversed(outline))
    normalized_holes = tuple(tuple(reversed(hole)) if _signed_area(hole) > 0.0 else hole for hole in holes)
    return Polygon(outline=outline, holes=normalized_holes)


def _signed_area(points: tuple[Point, ...]) -> float:
    """Return the signed area of a closed point tuple."""

    return 0.5 * sum(
        first.x * second.y - second.x * first.y for first, second in zip(points, points[1:] + points[:1])
    )


def _point_in_ring_average(points: tuple[Point, ...], outline: tuple[Point, ...]) -> bool:
    """Return whether a loop centroid lies inside another ring."""

    if not points:
        return False
    centroid = Point(
        sum(point.x for point in points) / len(points),
        sum(point.y for point in points) / len(points),
    )
    return point_in_polygon(centroid, Polygon(outline=outline))


def _geodesic_distances(component: Iterable[Cell], seeds: set[Cell]) -> tuple[dict[Cell, int], Cell]:
    """Return unweighted geodesic distances and the farthest cell."""

    allowed = set(component)
    distances = {seed: 0 for seed in seeds if seed in allowed}
    queue: deque[Cell] = deque(distances)
    while queue:
        current = queue.popleft()
        next_distance = distances[current] + 1
        for dx, dy in _NEIGHBORS_8:
            neighbor = (current[0] + dx, current[1] + dy)
            if neighbor in allowed and neighbor not in distances:
                distances[neighbor] = next_distance
                queue.append(neighbor)
    farthest = max(distances, key=distances.__getitem__) if distances else next(iter(allowed))
    return distances, farthest


def _cell_centroid(cells: Iterable[Cell]) -> tuple[float, float]:
    """Return the arithmetic centroid in cell coordinates."""

    collected = tuple(cells)
    return (
        sum(cell[0] for cell in collected) / len(collected),
        sum(cell[1] for cell in collected) / len(collected),
    )


def _cell_distance(cell: Cell, centroid: tuple[float, float]) -> float:
    """Return distance from a cell to a floating cell centroid."""

    return math.hypot(cell[0] - centroid[0], cell[1] - centroid[1])
