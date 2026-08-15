"""Footprint value-field visibility and placement optimization.

The optimizer searches multiple text orientations and keeps values close enough
to their owning footprint that the association remains visually unambiguous.
Mounting-hole and logo footprints are represented by explicit hide operations.
When no collision-free location exists, an on-footprint manual-review fallback
is offered instead of moving the value far away from the component.
"""

from __future__ import annotations

import hashlib
import math
import re
from collections.abc import Iterable, Iterator
from dataclasses import asdict, dataclass

from .config import SilkscreenConfig
from .geometry import distance, point_segment_distance
from .models import BoardSnapshot, BoundingBox, FootprintSnapshot, Point


@dataclass(frozen=True)
class SilkscreenPlacement:
    """One proposed footprint reference/value-field update."""

    placement_id: str
    footprint_id: str
    reference: str
    value: str
    position: Point
    layer: str
    angle_deg: float
    text_width_mm: float
    text_height_mm: float
    text_thickness_mm: float
    hide_reference: bool
    show_value: bool
    reference_layer: str
    estimated_bounds: BoundingBox
    score: float
    distance_from_footprint_mm: float
    manual_review: bool = False
    default_selected: bool = True
    reason: str = "optimized_value_position"

    def to_dict(self) -> dict[str, object]:
        """Return a JSON-serializable representation."""

        return asdict(self)


@dataclass(frozen=True)
class SilkscreenPlan:
    """Complete silkscreen placement proposal."""

    placements: tuple[SilkscreenPlacement, ...]
    skipped: tuple[dict[str, str], ...]

    def selected(self, placement_ids: Iterable[str] | None) -> SilkscreenPlan:
        """Return a plan containing only explicitly selected placements."""

        if placement_ids is None:
            return self
        selected_ids = {str(value) for value in placement_ids}
        return SilkscreenPlan(
            placements=tuple(item for item in self.placements if item.placement_id in selected_ids),
            skipped=self.skipped,
        )

    def to_dict(self) -> dict[str, object]:
        """Return a JSON-serializable representation."""

        return {
            "placements": [placement.to_dict() for placement in self.placements],
            "skipped": list(self.skipped),
            "summary": {
                "placed": sum(1 for placement in self.placements if placement.show_value),
                "hidden": sum(1 for placement in self.placements if not placement.show_value),
                "manual_review": sum(1 for placement in self.placements if placement.manual_review),
                "skipped": len(self.skipped),
            },
        }


class _SpatialBoxIndex:
    """Uniform-grid index for repeated bounding-box collision queries."""

    def __init__(self, cell_size_mm: float = 5.0) -> None:
        self._cell_size = max(0.5, cell_size_mm)
        self._items: dict[tuple[int, int], list[tuple[str, str, BoundingBox]]] = {}

    def add(self, item_id: str, layer: str, bounds: BoundingBox) -> None:
        """Add one box to every intersected grid cell."""

        for cell in self._cells(bounds):
            self._items.setdefault(cell, []).append((item_id, layer, bounds))

    def query(self, bounds: BoundingBox) -> Iterator[tuple[str, str, BoundingBox]]:
        """Yield unique entries from cells touched by *bounds*."""

        seen: set[tuple[str, str, float, float, float, float]] = set()
        for cell in self._cells(bounds):
            for item_id, layer, item_bounds in self._items.get(cell, ()):
                key = (
                    item_id,
                    layer,
                    item_bounds.min_x,
                    item_bounds.min_y,
                    item_bounds.max_x,
                    item_bounds.max_y,
                )
                if key in seen:
                    continue
                seen.add(key)
                yield item_id, layer, item_bounds

    def _cells(self, bounds: BoundingBox) -> Iterator[tuple[int, int]]:
        """Yield grid cells touched by one box."""

        min_x = math.floor(bounds.min_x / self._cell_size)
        max_x = math.floor(bounds.max_x / self._cell_size)
        min_y = math.floor(bounds.min_y / self._cell_size)
        max_y = math.floor(bounds.max_y / self._cell_size)
        for x_index in range(min_x, max_x + 1):
            for y_index in range(min_y, max_y + 1):
                yield x_index, y_index


def plan_silkscreen(snapshot: BoardSnapshot, config: SilkscreenConfig) -> SilkscreenPlan:
    """Place footprint values while avoiding known pads, vias, edges, and text."""

    hidden_patterns = tuple(re.compile(pattern) for pattern in config.hide_value_patterns)
    text_index = _SpatialBoxIndex()
    footprint_index = _SpatialBoxIndex()
    pad_index = _SpatialBoxIndex()
    via_index = _SpatialBoxIndex()

    for footprint in snapshot.footprints:
        footprint_index.add(footprint.item_id, footprint.layer, footprint.bounds)
        for text in (footprint.reference_field, footprint.value_field):
            if text.visible and text.value:
                text_index.add(
                    footprint.item_id,
                    text.layer,
                    _text_bounds(text.value, text.position, text.width, text.height, text.angle_deg),
                )
    for pad in snapshot.pads:
        for layer in pad.layers or ("*",):
            pad_index.add(pad.item_id, layer, pad.bounds)
    for via in snapshot.vias:
        box = BoundingBox(
            via.position.x - via.diameter / 2.0,
            via.position.y - via.diameter / 2.0,
            via.position.x + via.diameter / 2.0,
            via.position.y + via.diameter / 2.0,
        )
        via_index.add(via.item_id, "*", box)

    placements: list[SilkscreenPlacement] = []
    skipped: list[dict[str, str]] = []
    for footprint in sorted(snapshot.footprints, key=lambda item: item.bounds.area, reverse=True):
        if footprint.locked and config.skip_locked_footprints:
            skipped.append(
                {
                    "footprint_id": footprint.item_id,
                    "reference": footprint.reference,
                    "reason": "locked footprint",
                }
            )
            continue

        layer = "B.SilkS" if footprint.layer.startswith("B.") else "F.SilkS"
        reference_layer = "B.Fab" if footprint.layer.startswith("B.") else "F.Fab"
        should_hide_value = _matches_hidden_footprint(footprint, hidden_patterns)
        if should_hide_value:
            placements.append(
                SilkscreenPlacement(
                    placement_id=_placement_id(footprint.item_id, "hide"),
                    footprint_id=footprint.item_id,
                    reference=footprint.reference,
                    value=footprint.value,
                    position=footprint.value_field.position,
                    layer=layer,
                    angle_deg=footprint.value_field.angle_deg,
                    text_width_mm=config.text_width_mm,
                    text_height_mm=config.text_height_mm,
                    text_thickness_mm=config.text_thickness_mm,
                    hide_reference=True,
                    show_value=False,
                    reference_layer=reference_layer,
                    estimated_bounds=footprint.bounds,
                    score=0.0,
                    distance_from_footprint_mm=0.0,
                    reason="hidden_mounting_hole_or_logo",
                )
            )
            continue

        if not footprint.value or footprint.value in {"~", "DNP", "DNF"}:
            skipped.append(
                {
                    "footprint_id": footprint.item_id,
                    "reference": footprint.reference,
                    "reason": "empty or excluded value",
                }
            )
            continue

        angles = _candidate_angles(footprint, config)
        valid: list[tuple[float, Point, BoundingBox, float, float]] = []
        for angle in angles:
            for position, bounds in _candidate_positions(footprint, footprint.value, config, angle):
                edge_distance = _box_distance(bounds, footprint.bounds)
                if edge_distance > config.maximum_distance_from_footprint_mm + 1.0e-9:
                    continue
                collision_cost = _collision_cost(
                    snapshot,
                    footprint,
                    layer,
                    bounds,
                    text_index,
                    footprint_index,
                    pad_index,
                    via_index,
                    config,
                )
                if collision_cost > 0.0:
                    continue
                displacement = distance(position, footprint.value_field.position)
                angle_change = _angle_difference(angle, footprint.value_field.angle_deg)
                score = edge_distance * 1.35 + displacement * 0.20 + angle_change / 180.0 * 0.18
                valid.append((score, position, bounds, angle, edge_distance))

        manual_review = False
        default_selected = True
        reason = "optimized_value_position"
        if valid:
            score, position, bounds, angle, edge_distance = min(valid, key=lambda item: item[0])
        elif config.allow_on_footprint_fallback:
            angle = angles[0] if angles else 0.0
            position = footprint.bounds.center
            bounds = _text_bounds(
                footprint.value,
                position,
                config.text_width_mm,
                config.text_height_mm,
                angle,
            )
            edge_distance = 0.0
            score = 100.0 + _collision_cost(
                snapshot,
                footprint,
                layer,
                bounds,
                text_index,
                footprint_index,
                pad_index,
                via_index,
                config,
                allow_owner_overlap=True,
            )
            manual_review = True
            default_selected = False
            reason = "on_footprint_manual_fallback"
        else:
            skipped.append(
                {
                    "footprint_id": footprint.item_id,
                    "reference": footprint.reference,
                    "reason": "no collision-free value position within maximum footprint distance",
                }
            )
            continue

        placement = SilkscreenPlacement(
            placement_id=_placement_id(footprint.item_id, f"{position.x:.4f}:{position.y:.4f}:{angle:.2f}"),
            footprint_id=footprint.item_id,
            reference=footprint.reference,
            value=footprint.value,
            position=position,
            layer=layer,
            angle_deg=angle,
            text_width_mm=config.text_width_mm,
            text_height_mm=config.text_height_mm,
            text_thickness_mm=config.text_thickness_mm,
            hide_reference=config.hide_reference,
            show_value=config.show_value,
            reference_layer=reference_layer,
            estimated_bounds=bounds,
            score=score,
            distance_from_footprint_mm=edge_distance,
            manual_review=manual_review,
            default_selected=default_selected,
            reason=reason,
        )
        placements.append(placement)
        if placement.show_value:
            text_index.add(footprint.item_id, layer, bounds)

    return SilkscreenPlan(placements=tuple(placements), skipped=tuple(skipped))


def _matches_hidden_footprint(
    footprint: FootprintSnapshot,
    patterns: Iterable[re.Pattern[str]],
) -> bool:
    """Return whether footprint metadata identifies a mounting hole or logo."""

    candidates = (
        footprint.value,
        footprint.reference,
        footprint.library_id,
        footprint.description,
    )
    return any(pattern.search(value or "") for pattern in patterns for value in candidates)


def _candidate_angles(footprint: FootprintSnapshot, config: SilkscreenConfig) -> tuple[float, ...]:
    """Return normalized candidate text angles in stable preference order."""

    if config.preserve_existing_angle:
        return (_normalize_text_angle(footprint.value_field.angle_deg, config.keep_upright),)
    values = [_normalize_text_angle(float(angle), config.keep_upright) for angle in config.allowed_angles_deg]
    existing = _normalize_text_angle(footprint.value_field.angle_deg, config.keep_upright)
    values.insert(0, existing)
    return tuple(dict.fromkeys(values))


def _candidate_positions(
    footprint: FootprintSnapshot,
    value: str,
    config: SilkscreenConfig,
    angle_deg: float,
) -> list[tuple[Point, BoundingBox]]:
    """Generate nearby candidate locations in concentric rings."""

    text_width = _rendered_text_width(value, config.text_width_mm)
    text_height = config.text_height_mm
    result: list[tuple[Point, BoundingBox]] = []
    center = footprint.bounds.center
    current = footprint.value_field.position
    result.append((current, _text_bounds(value, current, config.text_width_mm, text_height, angle_deg)))
    for ring in range(config.candidate_rings):
        offset = config.candidate_offset_mm + ring * config.candidate_ring_step_mm
        if offset > config.maximum_distance_from_footprint_mm:
            break
        x_left = footprint.bounds.min_x - offset - text_width / 2.0
        x_right = footprint.bounds.max_x + offset + text_width / 2.0
        y_top = footprint.bounds.min_y - offset - text_height / 2.0
        y_bottom = footprint.bounds.max_y + offset + text_height / 2.0
        positions = (
            Point(center.x, y_top),
            Point(center.x, y_bottom),
            Point(x_left, center.y),
            Point(x_right, center.y),
            Point(x_left, y_top),
            Point(x_right, y_top),
            Point(x_left, y_bottom),
            Point(x_right, y_bottom),
        )
        for position in positions:
            result.append(
                (position, _text_bounds(value, position, config.text_width_mm, text_height, angle_deg))
            )
    return result


def _collision_cost(
    snapshot: BoardSnapshot,
    footprint: FootprintSnapshot,
    layer: str,
    bounds: BoundingBox,
    text_index: _SpatialBoxIndex,
    footprint_index: _SpatialBoxIndex,
    pad_index: _SpatialBoxIndex,
    via_index: _SpatialBoxIndex,
    config: SilkscreenConfig,
    allow_owner_overlap: bool = False,
) -> float:
    """Return zero for a clear location and a positive collision cost otherwise."""

    cost = 0.0
    copper_layer = "B.Cu" if layer.startswith("B.") else "F.Cu"
    query = bounds.inflate(max(config.minimum_pad_clearance_mm, config.minimum_via_clearance_mm))
    for _item_id, item_layer, pad_bounds in pad_index.query(query):
        if item_layer not in {"*", copper_layer}:
            continue
        if pad_bounds.inflate(config.minimum_pad_clearance_mm).intersects(bounds):
            cost += 10.0
    for _item_id, _item_layer, via_bounds in via_index.query(query):
        if via_bounds.inflate(config.minimum_via_clearance_mm).intersects(bounds):
            cost += 8.0
    for owner_id, text_layer, text_bounds in text_index.query(
        bounds.inflate(config.minimum_text_clearance_mm)
    ):
        if owner_id == footprint.item_id:
            continue
        if text_layer == layer and text_bounds.inflate(config.minimum_text_clearance_mm).intersects(bounds):
            cost += 6.0
    for edge in snapshot.edges:
        if _box_edge_distance(bounds, edge.start, edge.end) < config.minimum_edge_clearance_mm:
            cost += 12.0
    for other_id, other_layer, other_bounds in footprint_index.query(bounds):
        if other_id == footprint.item_id:
            if not allow_owner_overlap:
                # Text is allowed over courtyard/body geometry of its owner; pads
                # and vias remain independently protected above.
                continue
            continue
        if other_layer.startswith(layer[0]) and other_bounds.intersects(bounds):
            cost += 4.0
    return cost


def _text_bounds(
    value: str,
    position: Point,
    character_width_mm: float,
    text_height_mm: float,
    angle_deg: float,
) -> BoundingBox:
    """Return a conservative axis-aligned text bounding box."""

    width = _rendered_text_width(value, character_width_mm)
    height = text_height_mm
    angle = math.radians(angle_deg % 180.0)
    projected_width = abs(width * math.cos(angle)) + abs(height * math.sin(angle))
    projected_height = abs(width * math.sin(angle)) + abs(height * math.cos(angle))
    return BoundingBox(
        position.x - projected_width / 2.0,
        position.y - projected_height / 2.0,
        position.x + projected_width / 2.0,
        position.y + projected_height / 2.0,
    )


def _rendered_text_width(value: str, character_width_mm: float) -> float:
    """Return a conservative rendered text width."""

    return max(character_width_mm, len(value) * character_width_mm * 0.62)


def _box_edge_distance(bounds: BoundingBox, start: Point, end: Point) -> float:
    """Return the minimum distance from a box to a segment."""

    if _segment_intersects_box(start, end, bounds):
        return 0.0
    corners = (
        Point(bounds.min_x, bounds.min_y),
        Point(bounds.max_x, bounds.min_y),
        Point(bounds.max_x, bounds.max_y),
        Point(bounds.min_x, bounds.max_y),
    )
    return min(point_segment_distance(point, start, end) for point in corners)


def _segment_intersects_box(start: Point, end: Point, bounds: BoundingBox) -> bool:
    """Return whether a segment intersects a box."""

    if (bounds.min_x <= start.x <= bounds.max_x and bounds.min_y <= start.y <= bounds.max_y) or (
        bounds.min_x <= end.x <= bounds.max_x and bounds.min_y <= end.y <= bounds.max_y
    ):
        return True
    corners = (
        Point(bounds.min_x, bounds.min_y),
        Point(bounds.max_x, bounds.min_y),
        Point(bounds.max_x, bounds.max_y),
        Point(bounds.min_x, bounds.max_y),
    )
    return any(
        _segments_intersect(start, end, corners[index], corners[(index + 1) % 4]) for index in range(4)
    )


def _segments_intersect(first_start: Point, first_end: Point, second_start: Point, second_end: Point) -> bool:
    """Return whether two finite segments intersect."""

    def orientation(first: Point, second: Point, third: Point) -> float:
        return (second.x - first.x) * (third.y - first.y) - (second.y - first.y) * (third.x - first.x)

    a = orientation(first_start, first_end, second_start)
    b = orientation(first_start, first_end, second_end)
    c = orientation(second_start, second_end, first_start)
    d = orientation(second_start, second_end, first_end)
    return a * b <= 0.0 and c * d <= 0.0


def _box_distance(first: BoundingBox, second: BoundingBox) -> float:
    """Return the Euclidean separation between two axis-aligned boxes."""

    dx = max(second.min_x - first.max_x, first.min_x - second.max_x, 0.0)
    dy = max(second.min_y - first.max_y, first.min_y - second.max_y, 0.0)
    return math.hypot(dx, dy)


def _normalize_text_angle(angle: float, keep_upright: bool) -> float:
    """Normalize text angle and optionally keep glyphs upright."""

    normalized = ((angle + 180.0) % 360.0) - 180.0
    if keep_upright:
        if normalized > 90.0:
            normalized -= 180.0
        elif normalized < -90.0:
            normalized += 180.0
    return round(normalized, 6)


def _angle_difference(first: float, second: float) -> float:
    """Return the smallest absolute angular difference in degrees."""

    return abs(((first - second + 180.0) % 360.0) - 180.0)


def _placement_id(footprint_id: str, suffix: str) -> str:
    """Return a stable placement identifier for partial adoption."""

    payload = f"{footprint_id}|{suffix}".encode()
    return "SILK-" + hashlib.sha1(payload, usedforsecurity=False).hexdigest()[:12].upper()
