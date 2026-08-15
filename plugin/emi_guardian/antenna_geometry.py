"""Connectivity-preserving geometry for ground-pour antenna detection.

The detector in :mod:`emi_guardian.antenna` uses morphological opening to find
narrow copper.  Morphology alone cannot distinguish a useless copper overhang
from a mandatory thermal connection, footprint pad escape, explicit GND trace,
or perimeter ground band.  This module constructs a protected ground backbone
before any removable feature is reported.

The protected backbone is conservative by design:

* footprint pads and vias are protected with configurable margins;
* explicit same-net GND tracks are protected at their real width;
* an existing perimeter GND band near ``Edge.Cuts`` is protected;
* every protected terminal is connected to the broad ground core by a shortest
  occupied-cell path dilated to the required connection width ``t``;
* a candidate is returned only when removing it preserves all proven terminal
  connections to the broad ground core.

This converts the remediation decision into a deterministic planar-geometry
problem and fails closed when the broad core or connectivity proof is absent.
"""

from __future__ import annotations

import math
from collections import deque
from collections.abc import Iterable, Mapping
from dataclasses import dataclass

from .config import AntennaConfig
from .edge_optimizer import current_outline_ring
from .geometry import pairwise_closed, point_segment_distance
from .models import BoardSnapshot, BoundingBox, Pad, Point, Polygon, TrackSegment, Via
from .raster import Cell, RasterFeature, RasterGrid, rasterize_polygon

# Electrical connectivity uses edge-sharing cells only.  Treating diagonal
# corner contact as connected can create a zero-width copper bridge in the
# raster model.  Four-neighbor traversal is deliberately conservative: a very
# thin diagonal conductor may become unproven and therefore ineligible for
# automatic removal, but a required connection is never inferred from one
# mathematical point of contact.
_CONNECTIVITY_NEIGHBORS: tuple[Cell, ...] = (
    (1, 0),
    (-1, 0),
    (0, 1),
    (0, -1),
)


@dataclass(frozen=True)
class ProtectedGroundFeature:
    """One removable residual component with a connectivity proof."""

    feature: RasterFeature
    safe_keepout: bool
    critical_connectivity_preserved: bool
    protected_cell_count: int
    removable_cell_count: int
    required_terminal_count: int
    connected_terminal_count: int
    pad_overlap: bool
    perimeter_overlap: bool
    required_connection_width_mm: float


@dataclass(frozen=True)
class _ProtectionModel:
    """Raster protection state used to validate candidate removal."""

    grid: RasterGrid
    opened: frozenset[Cell]
    root_core: frozenset[Cell]
    residual: frozenset[Cell]
    protected: frozenset[Cell]
    terminal_groups: tuple[frozenset[Cell], ...]
    required_connectivity_groups: tuple[frozenset[Cell], ...]
    perimeter_cells: frozenset[Cell]
    pad_cells: frozenset[Cell]
    connected_terminal_count: int


def detect_protected_ground_features(
    snapshot: BoardSnapshot,
    net: str,
    layer: str,
    polygon: Polygon,
    config: AntennaConfig,
) -> tuple[ProtectedGroundFeature, ...]:
    """Return narrow residuals that are safe to remove from one GND polygon.

    No feature is returned when a broad morphological core cannot be
    established.  That behavior is deliberate: a wholly narrow GND structure
    may be an intentional conductor, and removing it cannot be justified from
    geometry alone.
    """

    model = _build_protection_model(snapshot, net, layer, polygon, config)
    if model is None:
        return ()

    candidate_cells = set(model.residual) - set(model.protected)
    if not candidate_cells:
        return ()

    attachment_reference = set(model.opened) | set(model.protected)
    features: list[ProtectedGroundFeature] = []
    # Keep the candidate topology consistent with the four-neighbor electrical
    # proof.  Eight-neighbor grouping can merge two regions that touch at only
    # one mathematical corner; converting that merged set to one polygon can
    # silently drop a disjoint loop.
    for component in _components_4(candidate_cells):
        if not component:
            continue
        preserved = _removal_preserves_terminals(model, set(component))
        pad_overlap = bool(set(component) & set(model.pad_cells))
        perimeter_overlap = bool(set(component) & set(model.perimeter_cells))
        safe = preserved and not pad_overlap and not perimeter_overlap
        if config.require_safe_removal_connectivity and not safe:
            continue
        raster_feature = model.grid.feature(component, attachment_reference)
        features.append(
            ProtectedGroundFeature(
                feature=raster_feature,
                safe_keepout=safe,
                critical_connectivity_preserved=preserved,
                protected_cell_count=len(model.protected),
                removable_cell_count=len(component),
                required_terminal_count=len(model.terminal_groups),
                connected_terminal_count=model.connected_terminal_count,
                pad_overlap=pad_overlap,
                perimeter_overlap=perimeter_overlap,
                required_connection_width_mm=config.required_ground_connection_width_mm,
            )
        )
    return tuple(features)


def _build_protection_model(
    snapshot: BoardSnapshot,
    net: str,
    layer: str,
    polygon: Polygon,
    config: AntennaConfig,
) -> _ProtectionModel | None:
    """Build the broad core, mandatory terminals, and width-``t`` corridors."""

    grid = rasterize_polygon(polygon, config.raster_step_mm, config.max_raster_cells)
    if not grid.occupied:
        return None

    # A single KiCad filled polygon should be electrically continuous.  When
    # the selected raster resolution splits it into multiple four-connected
    # components, automatic copper removal cannot be proven safe.  Failing
    # closed is preferable to treating diagonal point contact as a conductor.
    if len(_components_4(grid.occupied)) != 1:
        return None

    # The removable residual must be evaluated relative to both the user's
    # narrow-neck threshold and the mandatory connection width ``t``.  Using a
    # smaller opening than ``t`` could miss copper that lies outside every
    # width-t backbone corridor.
    opening_width_mm = max(
        config.narrow_neck_width_mm,
        config.required_ground_connection_width_mm,
    )
    opened, residual = grid.morphological_opening(opening_width_mm / 2.0)
    if not opened:
        return None

    core_components = _components_4(opened)
    if not core_components:
        return None
    root_core = max(
        core_components,
        key=lambda component: (len(component), tuple(sorted(component))[:1]),
    )
    secondary_core_groups = tuple(component for component in core_components if component is not root_core)

    # Every physical pad is excluded from antenna candidates.  Same-net GND
    # pads additionally become mandatory connectivity terminals, while
    # different-net pads are geometry-only exclusions.  The latter is a
    # deliberate second safety layer for snapshots whose zone polygons do not
    # fully encode pad clearances.
    # Protect a pad and the complete width-t launch region around it.  Using
    # only the literal pad AABB can miss thermal spokes when the filled-zone
    # polygon contains a clearance moat around the pad body.  The wider
    # capture radius is deliberately conservative: a suspected overhang near
    # any pad is left for manual review rather than risking an electrical
    # disconnection.
    pad_capture_margin = (
        config.pad_protection_margin_mm
        + config.required_ground_connection_width_mm / 2.0
        + grid.step_mm * math.sqrt(2.0) / 2.0
    )
    all_pad_groups = tuple(
        cells
        for pad in snapshot.pads
        if _pad_contacts_layer(pad, layer)
        for cells in (_cells_intersecting_box(grid, pad.bounds.inflate(pad_capture_margin)),)
        if cells
    )
    pad_groups = tuple(
        cells
        for pad in snapshot.pads
        if pad.net == net and _pad_contacts_layer(pad, layer)
        for cells in (_cells_intersecting_box(grid, pad.bounds.inflate(pad_capture_margin)),)
        if cells
    )
    # A removable GND overhang is meaningful only when the filled component is
    # electrically anchored to at least one same-net footprint pad.  The outer
    # connectivity analyzer normally enforces this already, but keeping the
    # invariant here prevents synthetic or stale findings from bypassing it.
    if not pad_groups:
        return None
    via_groups = tuple(
        cells
        for via in snapshot.vias
        if via.net == net and _via_contacts_layer(via, layer, snapshot)
        for cells in (
            _cells_near_point(
                grid,
                via.position,
                via.diameter / 2.0 + config.via_protection_margin_mm,
            ),
        )
        if cells
    )
    track_groups: tuple[frozenset[Cell], ...] = ()
    if config.protect_explicit_ground_tracks:
        track_groups = tuple(
            cells
            for track in snapshot.tracks
            if track.net == net and track.layer == layer
            for cells in (
                _cells_near_segment(
                    grid,
                    track,
                    track.width / 2.0 + config.explicit_track_protection_margin_mm,
                ),
            )
            if cells
        )

    perimeter_cells: frozenset[Cell] = frozenset()
    if config.protect_perimeter_ground:
        resolved_perimeter = _perimeter_cells(
            grid,
            snapshot,
            config.perimeter_ground_protection_mm,
        )
        # The user requires existing perimeter GND to be preserved.  Without
        # a valid closed Edge.Cuts loop, that condition cannot be proven, so
        # appendage removal must fail closed instead of guessing.
        if resolved_perimeter is None:
            return None
        perimeter_cells = resolved_perimeter
    perimeter_groups = _components_4(set(perimeter_cells)) if perimeter_cells else ()

    terminal_groups = tuple((*pad_groups, *via_groups, *track_groups, *perimeter_groups))
    # Every broad-core component and every mandatory terminal must remain
    # connected to the same primary GND core.  Seeding the search from all
    # opened components would prove only local reachability and could allow a
    # narrow bridge between two large GND regions to be removed.  A single
    # primary source turns the requirement into one global connectivity proof.
    required_connectivity_groups = tuple((*secondary_core_groups, *terminal_groups))
    distances, predecessor = _multi_source_tree(grid.occupied, root_core)

    # Every required terminal group must already be connected to the broad core
    # through existing copper.  Otherwise a local keepout cannot be proven safe.
    protected: set[Cell] = set()
    path_radius_cells = max(
        1,
        int(math.ceil(config.required_ground_connection_width_mm / (2.0 * grid.step_mm))),
    )
    for group in required_connectivity_groups:
        reachable = [cell for cell in group if cell in distances]
        if not reachable:
            return None
        nearest = min(reachable, key=lambda cell: distances[cell])
        path = _trace_to_source(nearest, predecessor)
        protected.update(_dilate_cells(path, grid.occupied, path_radius_cells))
        protected.update(group)

    # Keep explicit terminal geometry and the existing perimeter band even when
    # a terminal already lies inside the broad core.
    pad_cells = frozenset(cell for group in all_pad_groups for cell in group)
    protected.update(pad_cells)
    protected.update(cell for group in via_groups for cell in group)
    protected.update(cell for group in track_groups for cell in group)
    protected.update(perimeter_cells)

    return _ProtectionModel(
        grid=grid,
        opened=frozenset(opened),
        root_core=frozenset(root_core),
        residual=frozenset(residual),
        protected=frozenset(protected),
        terminal_groups=tuple(frozenset(group) for group in terminal_groups),
        required_connectivity_groups=tuple(frozenset(group) for group in required_connectivity_groups),
        perimeter_cells=perimeter_cells,
        pad_cells=pad_cells,
        connected_terminal_count=len(terminal_groups),
    )


def _removal_preserves_terminals(model: _ProtectionModel, removed: set[Cell]) -> bool:
    """Prove that all mandatory terminals still reach the broad ground core."""

    if removed & set(model.protected):
        return False
    remaining = set(model.grid.occupied) - removed
    sources = set(model.root_core) & remaining
    if not sources:
        return False
    reachable = _flood(remaining, sources)
    return all(bool(set(group) & reachable) for group in model.required_connectivity_groups)


def _components_4(cells: Iterable[Cell]) -> tuple[frozenset[Cell], ...]:
    """Split cells into deterministic edge-connected components."""

    remaining = set(cells)
    result: list[frozenset[Cell]] = []
    while remaining:
        seed = min(remaining)
        remaining.remove(seed)
        component = {seed}
        queue: deque[Cell] = deque([seed])
        while queue:
            current = queue.popleft()
            for dx, dy in _CONNECTIVITY_NEIGHBORS:
                neighbor = (current[0] + dx, current[1] + dy)
                if neighbor not in remaining:
                    continue
                remaining.remove(neighbor)
                component.add(neighbor)
                queue.append(neighbor)
        result.append(frozenset(component))
    result.sort(key=lambda component: (min(component), len(component)))
    return tuple(result)


def _multi_source_tree(
    occupied: set[Cell],
    sources: Iterable[Cell],
) -> tuple[dict[Cell, int], dict[Cell, Cell]]:
    """Return grid distances and predecessors toward the nearest source."""

    initial = sorted(set(sources) & occupied)
    distances = {cell: 0 for cell in initial}
    predecessor: dict[Cell, Cell] = {}
    queue: deque[Cell] = deque(initial)
    while queue:
        current = queue.popleft()
        next_distance = distances[current] + 1
        for dx, dy in _CONNECTIVITY_NEIGHBORS:
            neighbor = (current[0] + dx, current[1] + dy)
            if neighbor not in occupied or neighbor in distances:
                continue
            distances[neighbor] = next_distance
            predecessor[neighbor] = current
            queue.append(neighbor)
    return distances, predecessor


def _trace_to_source(cell: Cell, predecessor: Mapping[Cell, Cell]) -> set[Cell]:
    """Return the predecessor chain from one terminal cell to a source."""

    path = {cell}
    current = cell
    while current in predecessor:
        current = predecessor[current]
        if current in path:
            break
        path.add(current)
    return path


def _dilate_cells(cells: Iterable[Cell], occupied: set[Cell], radius_cells: int) -> set[Cell]:
    """Dilate a centerline while retaining only existing occupied copper."""

    result: set[Cell] = set()
    squared = radius_cells * radius_cells
    for x, y in cells:
        for dx in range(-radius_cells, radius_cells + 1):
            for dy in range(-radius_cells, radius_cells + 1):
                if dx * dx + dy * dy > squared:
                    continue
                candidate = (x + dx, y + dy)
                if candidate in occupied:
                    result.add(candidate)
    return result


def _flood(occupied: set[Cell], sources: Iterable[Cell]) -> set[Cell]:
    """Return all occupied cells reachable from *sources*."""

    reachable = set(sources) & occupied
    queue: deque[Cell] = deque(reachable)
    while queue:
        current = queue.popleft()
        for dx, dy in _CONNECTIVITY_NEIGHBORS:
            neighbor = (current[0] + dx, current[1] + dy)
            if neighbor in occupied and neighbor not in reachable:
                reachable.add(neighbor)
                queue.append(neighbor)
    return reachable


def _cells_intersecting_box(grid: RasterGrid, bounds: BoundingBox) -> frozenset[Cell]:
    """Return occupied raster cells whose square intersects an AABB."""

    half = grid.step_mm / 2.0
    return frozenset(
        cell
        for cell in _occupied_cells_in_bounds(grid, bounds.inflate(half))
        if _cell_bounds(grid, cell, half).intersects(bounds)
    )


def _cells_near_point(grid: RasterGrid, point: Point, radius: float) -> frozenset[Cell]:
    """Return occupied cells whose square can intersect a circular feature."""

    padding = grid.step_mm * math.sqrt(2.0) / 2.0
    limit = radius + padding
    return frozenset(
        cell
        for cell in _occupied_cells_in_bounds(
            grid,
            BoundingBox(
                point.x - limit,
                point.y - limit,
                point.x + limit,
                point.y + limit,
            ),
        )
        if math.hypot(grid.point(cell).x - point.x, grid.point(cell).y - point.y) <= limit
    )


def _cells_near_segment(
    grid: RasterGrid,
    track: TrackSegment,
    radius: float,
) -> frozenset[Cell]:
    """Return occupied cells intersecting a finite-width track corridor."""

    return _cells_near_line(grid, track.start, track.end, radius)


def _cells_near_line(
    grid: RasterGrid,
    start: Point,
    end: Point,
    radius: float,
) -> frozenset[Cell]:
    """Return occupied cells intersecting a finite-width line corridor."""

    padding = grid.step_mm * math.sqrt(2.0) / 2.0
    limit = radius + padding
    return frozenset(
        cell
        for cell in _occupied_cells_in_bounds(
            grid,
            BoundingBox(
                min(start.x, end.x) - limit,
                min(start.y, end.y) - limit,
                max(start.x, end.x) + limit,
                max(start.y, end.y) + limit,
            ),
        )
        if point_segment_distance(grid.point(cell), start, end) <= limit
    )


def _perimeter_cells(
    grid: RasterGrid,
    snapshot: BoardSnapshot,
    band_mm: float,
) -> frozenset[Cell] | None:
    """Return occupied cells within the protected band of current Edge.Cuts."""

    try:
        ring = current_outline_ring(snapshot, maximum_step_mm=max(0.05, grid.step_mm / 2.0))
    except (RuntimeError, ValueError):
        return None
    if len(ring) < 3:
        return None
    edges = tuple(pairwise_closed(ring))
    result: set[Cell] = set()
    for start, end in edges:
        result.update(_cells_near_line(grid, start, end, max(0.0, band_mm)))
    return frozenset(result)


def _occupied_cells_in_bounds(grid: RasterGrid, bounds: BoundingBox) -> Iterable[Cell]:
    """Yield occupied cells whose grid squares can intersect *bounds*.

    Feature protection used to scan the complete raster once per pad, via, and
    trace.  Limiting enumeration to the item's grid-aligned AABB changes that
    cost from ``O(items * board_cells)`` to approximately the number of cells
    covered by each item, which is critical on dense boards.
    """

    step = grid.step_mm
    min_x = math.floor((bounds.min_x - grid.origin.x) / step) - 1
    max_x = math.floor((bounds.max_x - grid.origin.x) / step) + 1
    min_y = math.floor((bounds.min_y - grid.origin.y) / step) - 1
    max_y = math.floor((bounds.max_y - grid.origin.y) / step) + 1
    for x_index in range(min_x, max_x + 1):
        for y_index in range(min_y, max_y + 1):
            cell = (x_index, y_index)
            if cell in grid.occupied:
                yield cell


def _cell_bounds(grid: RasterGrid, cell: Cell, half: float) -> BoundingBox:
    """Return the world-space square occupied by one raster cell."""

    point = grid.point(cell)
    return BoundingBox(point.x - half, point.y - half, point.x + half, point.y + half)


def _pad_contacts_layer(pad: Pad, layer: str) -> bool:
    """Return whether a footprint pad can contact one copper layer."""

    if not pad.layers:
        return True
    layers = {str(value) for value in pad.layers}
    return layer in layers or bool(layers & {"*.Cu", "*.Copper", "All.Cu"})


def _via_contacts_layer(via: Via, layer: str, snapshot: BoardSnapshot) -> bool:
    """Return whether a via traverses the requested copper layer."""

    if layer in {via.start_layer, via.end_layer}:
        return True
    stackup = snapshot.metadata.get("stackup", {}) if isinstance(snapshot.metadata, Mapping) else {}
    raw_layers = stackup.get("layers", ()) if isinstance(stackup, Mapping) else ()
    copper_layers = tuple(
        str(item.get("name"))
        for item in raw_layers
        if isinstance(item, Mapping) and str(item.get("name", "")).endswith(".Cu")
    )
    if not copper_layers:
        return layer.endswith(".Cu")
    try:
        first = copper_layers.index(via.start_layer)
        last = copper_layers.index(via.end_layer)
        target = copper_layers.index(layer)
    except ValueError:
        return False
    low, high = sorted((first, last))
    return low <= target <= high
