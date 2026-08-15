"""Schematic-block-aware initial footprint placement proposals.

The planner uses KiCad sheet paths when available and falls back to stable
reference-prefix groups.  It is intentionally a proposal generator: locked
footprints are preserved, connectors are kept on group perimeters, larger core
parts establish each block, and capacitors are placed close to matching power
pads when pad-net evidence is available.
"""

from __future__ import annotations

import hashlib
import math
import re
from collections.abc import Iterable, Sequence
from dataclasses import asdict, dataclass

from .config import PlacementConfig
from .models import BoardSnapshot, BoundingBox, FootprintSnapshot, Pad, Point, bounds_from_points


@dataclass(frozen=True)
class PlacementPadPreview:
    """Translated pad geometry shown at a proposed footprint destination."""

    item_id: str
    number: str
    net: str
    position: Point
    bounds: BoundingBox


@dataclass(frozen=True)
class PlacementTextPreview:
    """Translated footprint field shown with an initial-placement proposal."""

    kind: str
    text: str
    position: Point
    layer: str
    visible: bool
    width: float
    height: float
    thickness: float
    angle_deg: float


@dataclass(frozen=True)
class FootprintPlacement:
    """One proposed footprint position within a schematic block."""

    placement_id: str
    footprint_id: str
    reference: str
    value: str
    group_id: str
    old_position: Point
    position: Point
    layer: str
    reason: str
    associated_footprint_id: str = ""
    associated_pad_id: str = ""
    confidence: float = 0.80
    default_selected: bool = True
    locked: bool = False
    old_bounds: BoundingBox = BoundingBox(0.0, 0.0, 0.0, 0.0)
    destination_bounds: BoundingBox = BoundingBox(0.0, 0.0, 0.0, 0.0)
    preview_pads: tuple[PlacementPadPreview, ...] = ()
    preview_texts: tuple[PlacementTextPreview, ...] = ()

    def to_dict(self) -> dict[str, object]:
        """Return a JSON-serializable representation."""

        return asdict(self)


@dataclass(frozen=True)
class PlacementGroup:
    """One schematic block and its planned bounding box."""

    group_id: str
    title: str
    footprint_ids: tuple[str, ...]
    bounds: BoundingBox

    def to_dict(self) -> dict[str, object]:
        """Return a JSON-serializable representation."""

        return asdict(self)


@dataclass(frozen=True)
class ComponentPlacementPlan:
    """Complete initial-placement proposal grouped by schematic block."""

    placements: tuple[FootprintPlacement, ...]
    groups: tuple[PlacementGroup, ...]
    warnings: tuple[str, ...]

    def selected(self, placement_ids: Iterable[str] | None) -> ComponentPlacementPlan:
        """Return a plan limited to explicitly selected placements."""

        if placement_ids is None:
            return self
        selected_ids = {str(value) for value in placement_ids}
        return ComponentPlacementPlan(
            placements=tuple(item for item in self.placements if item.placement_id in selected_ids),
            groups=self.groups,
            warnings=self.warnings,
        )

    def to_dict(self) -> dict[str, object]:
        """Return a JSON-serializable representation."""

        return {
            "placements": [item.to_dict() for item in self.placements],
            "groups": [group.to_dict() for group in self.groups],
            "warnings": list(self.warnings),
            "summary": {
                "placement_count": len(self.placements),
                "group_count": len(self.groups),
                "locked_count": sum(1 for item in self.placements if item.locked),
                "capacitor_count": sum(1 for item in self.placements if item.reason.startswith("capacitor")),
            },
        }


def plan_component_placement(
    snapshot: BoardSnapshot,
    config: PlacementConfig,
) -> ComponentPlacementPlan:
    """Generate a grouped initial placement with pad-aware capacitor proximity."""

    capacitor_reference = re.compile(config.capacitor_reference_regex, re.IGNORECASE)
    capacitor_value = re.compile(config.capacitor_value_regex, re.IGNORECASE)
    connector_reference = re.compile(config.connector_reference_regex, re.IGNORECASE)
    groups = _group_footprints(snapshot.footprints, config)
    board_bounds = _planning_bounds(snapshot)
    warnings: list[str] = []
    placements: list[FootprintPlacement] = []
    group_records: list[PlacementGroup] = []

    cursor_x = board_bounds.min_x + config.group_spacing_mm
    cursor_y = board_bounds.min_y + config.group_spacing_mm
    row_height = 0.0
    available_width = max(config.block_max_width_mm, board_bounds.width - 2.0 * config.group_spacing_mm)

    for group_id, footprints in sorted(groups.items(), key=lambda item: item[0]):
        local, local_bounds = _layout_group(
            snapshot,
            group_id,
            footprints,
            config,
            capacitor_reference,
            capacitor_value,
            connector_reference,
        )
        block_width = max(8.0, local_bounds.width)
        block_height = max(8.0, local_bounds.height)
        if (
            cursor_x + block_width > board_bounds.min_x + available_width
            and cursor_x > board_bounds.min_x + config.group_spacing_mm
        ):
            cursor_x = board_bounds.min_x + config.group_spacing_mm
            cursor_y += row_height + config.group_spacing_mm
            row_height = 0.0
        offset = Point(cursor_x - local_bounds.min_x, cursor_y - local_bounds.min_y)
        translated_ids: list[str] = []
        translated_points: list[Point] = []
        for item in local:
            position = (
                item.old_position
                if item.locked
                else Point(item.position.x + offset.x, item.position.y + offset.y)
            )
            source_footprint = _footprint_by_id(footprints, item.footprint_id)
            translated = _placement(
                source_footprint,
                item.group_id,
                position,
                item.reason,
                associated_footprint_id=item.associated_footprint_id,
                associated_pad_id=item.associated_pad_id,
                confidence=item.confidence,
                locked=item.locked,
            )
            placements.append(translated)
            translated_ids.append(item.footprint_id)
            translated_points.append(position)
        translated_bounds = BoundingBox(
            cursor_x,
            cursor_y,
            cursor_x + block_width,
            cursor_y + block_height,
        )
        group_records.append(
            PlacementGroup(
                group_id=group_id,
                title=_group_title(group_id),
                footprint_ids=tuple(translated_ids),
                bounds=translated_bounds,
            )
        )
        cursor_x += block_width + config.group_spacing_mm
        row_height = max(row_height, block_height)

    if any(item.locked for item in placements):
        warnings.append(
            "Locked footprints were left at their current positions and may overlap the proposed block layout."
        )
    if not any(footprint.sheet_path for footprint in snapshot.footprints):
        warnings.append(
            "No schematic sheet paths were available; reference-prefix groups were used as a fallback."
        )
    warnings.append(
        "This is an initial placement proposal. Review mechanical constraints, signal flow, thermal paths, and routing before applying it."
    )
    return ComponentPlacementPlan(
        placements=tuple(placements),
        groups=tuple(group_records),
        warnings=tuple(warnings),
    )


def _group_footprints(
    footprints: Sequence[FootprintSnapshot],
    config: PlacementConfig,
) -> dict[str, tuple[FootprintSnapshot, ...]]:
    """Group footprints by schematic sheet path or stable reference prefix."""

    grouped: dict[str, list[FootprintSnapshot]] = {}
    for footprint in footprints:
        if config.use_sheet_path and footprint.sheet_path.strip():
            group = footprint.sheet_path.strip()
        else:
            match = re.match(r"([A-Za-z]+)", footprint.reference)
            prefix = match.group(1).upper() if match else "MISC"
            group = f"reference:{prefix}"
        grouped.setdefault(group, []).append(footprint)
    return {
        key: tuple(sorted(values, key=lambda item: (_natural_reference(item.reference), item.item_id)))
        for key, values in grouped.items()
    }


def _layout_group(
    snapshot: BoardSnapshot,
    group_id: str,
    footprints: Sequence[FootprintSnapshot],
    config: PlacementConfig,
    capacitor_reference: re.Pattern[str],
    capacitor_value: re.Pattern[str],
    connector_reference: re.Pattern[str],
) -> tuple[tuple[FootprintPlacement, ...], BoundingBox]:
    """Lay out one block locally around its largest core component."""

    capacitors = [
        item
        for item in footprints
        if capacitor_reference.search(item.reference) or capacitor_value.search(item.value or "")
    ]
    connectors = [item for item in footprints if connector_reference.search(item.reference)]
    capacitor_ids = {item.item_id for item in capacitors}
    connector_ids = {item.item_id for item in connectors}
    cores = [item for item in footprints if item.item_id not in capacitor_ids | connector_ids]
    cores.sort(key=lambda item: (-item.bounds.area, _natural_reference(item.reference)))
    capacitors.sort(key=lambda item: (-item.bounds.area, _natural_reference(item.reference)))
    connectors.sort(key=lambda item: (-item.bounds.area, _natural_reference(item.reference)))

    placements: dict[str, FootprintPlacement] = {}
    occupied: list[tuple[str, BoundingBox]] = []
    spacing = max(0.25, config.component_spacing_mm)
    max_width = max(12.0, config.block_max_width_mm)

    cursor_x = 0.0
    cursor_y = 0.0
    row_height = 0.0
    for footprint in cores:
        width = max(0.5, footprint.bounds.width)
        height = max(0.5, footprint.bounds.height)
        if cursor_x + width > max_width and cursor_x > 0.0:
            cursor_x = 0.0
            cursor_y += row_height + spacing
            row_height = 0.0
        position = Point(cursor_x + width / 2.0, cursor_y + height / 2.0)
        bounds = _bounds_at(footprint, position)
        placements[footprint.item_id] = _placement(
            footprint,
            group_id,
            position,
            "core_component",
            confidence=0.82,
        )
        occupied.append((footprint.item_id, bounds))
        cursor_x += width + spacing
        row_height = max(row_height, height)

    core_height = cursor_y + row_height
    connector_y = 0.0
    connector_x = max_width + spacing
    for footprint in connectors:
        position = Point(
            connector_x + max(0.5, footprint.bounds.width) / 2.0,
            connector_y + max(0.5, footprint.bounds.height) / 2.0,
        )
        bounds = _bounds_at(footprint, position)
        placements[footprint.item_id] = _placement(
            footprint,
            group_id,
            position,
            "connector_at_block_perimeter",
            confidence=0.78,
        )
        occupied.append((footprint.item_id, bounds))
        connector_y += max(0.5, footprint.bounds.height) + spacing

    targets = cores or connectors
    pads_by_footprint: dict[str, tuple[Pad, ...]] = {
        item.item_id: tuple(pad for pad in snapshot.pads if pad.footprint_id == item.item_id)
        for item in targets
    }
    fallback_y = max(core_height, connector_y) + spacing
    for index, capacitor in enumerate(capacitors):
        target, pad = _capacitor_target(capacitor, targets, pads_by_footprint)
        associated_id = target.item_id if target else ""
        pad_id = pad.item_id if pad else ""
        if target and target.item_id in placements:
            target_position = placements[target.item_id].position
            target_pad_position = (
                _translated_pad_position(target, target_position, pad) if pad else target_position
            )
            position = _nearby_free_position(capacitor, target_pad_position, occupied, spacing)
            reason = "capacitor_near_matching_pad" if pad else "capacitor_near_block_core"
            confidence = 0.88 if pad else 0.72
        else:
            position = Point(
                (index % 6) * (max(0.5, capacitor.bounds.width) + spacing),
                fallback_y + (index // 6) * (max(0.5, capacitor.bounds.height) + spacing),
            )
            reason = "capacitor_fallback_row"
            confidence = 0.62
        occupied.append((capacitor.item_id, _bounds_at(capacitor, position)))
        placements[capacitor.item_id] = _placement(
            capacitor,
            group_id,
            position,
            reason,
            associated_footprint_id=associated_id,
            associated_pad_id=pad_id,
            confidence=confidence,
        )

    for footprint in footprints:
        if footprint.item_id in placements:
            continue
        placements[footprint.item_id] = _placement(
            footprint,
            group_id,
            footprint.position,
            "locked_preserved" if footprint.locked else "unclassified_preserved",
            confidence=1.0 if footprint.locked else 0.50,
            locked=footprint.locked,
        )

    all_boxes = [
        _bounds_at(_footprint_by_id(footprints, item.footprint_id), item.position)
        for item in placements.values()
    ]
    points = [
        point for box in all_boxes for point in (Point(box.min_x, box.min_y), Point(box.max_x, box.max_y))
    ]
    bounds = bounds_from_points(points) if points else BoundingBox(0.0, 0.0, 10.0, 10.0)
    return tuple(placements[item.item_id] for item in footprints), bounds


def _capacitor_target(
    capacitor: FootprintSnapshot,
    targets: Sequence[FootprintSnapshot],
    pads_by_footprint: dict[str, tuple[Pad, ...]],
) -> tuple[FootprintSnapshot | None, Pad | None]:
    """Choose the target component and power pad sharing a capacitor net."""

    capacitor_nets = {pad.net for pad in capacitor.pads if pad.net}
    best: tuple[int, float, FootprintSnapshot, Pad | None] | None = None
    for target in targets:
        target_pads = pads_by_footprint.get(target.item_id, target.pads)
        matching = [pad for pad in target_pads if pad.net and pad.net in capacitor_nets]
        non_ground = [pad for pad in matching if not _looks_like_ground(pad.net)]
        pad = next(iter(non_ground or matching), None)
        shared = len({item.net for item in matching})
        score = (shared, target.bounds.area)
        candidate = (score[0], score[1], target, pad)
        if best is None or candidate[:2] > best[:2]:
            best = candidate
    if best is None or best[0] <= 0:
        return (targets[0], None) if targets else (None, None)
    return best[2], best[3]


def _translated_pad_position(
    footprint: FootprintSnapshot,
    new_footprint_position: Point,
    pad: Pad | None,
) -> Point:
    """Translate one pad position with its owning footprint proposal."""

    if pad is None:
        return new_footprint_position
    return Point(
        new_footprint_position.x + pad.position.x - footprint.position.x,
        new_footprint_position.y + pad.position.y - footprint.position.y,
    )


def _nearby_free_position(
    footprint: FootprintSnapshot,
    target: Point,
    occupied: Sequence[tuple[str, BoundingBox]],
    spacing: float,
) -> Point:
    """Choose the nearest non-overlapping position around an associated pad."""

    radial_step = max(
        spacing,
        max(footprint.bounds.width, footprint.bounds.height) / 2.0 + spacing,
    )
    for ring in range(1, 7):
        radius = radial_step * ring
        sample_count = 8 + 4 * ring
        for sample in range(sample_count):
            angle = 2.0 * math.pi * sample / sample_count
            point = Point(target.x + radius * math.cos(angle), target.y + radius * math.sin(angle))
            bounds = _bounds_at(footprint, point).inflate(spacing / 2.0)
            if all(not bounds.intersects(other) for _, other in occupied):
                return point
    return Point(target.x + radial_step * 7.0, target.y)


def _placement(
    footprint: FootprintSnapshot,
    group_id: str,
    position: Point,
    reason: str,
    *,
    associated_footprint_id: str = "",
    associated_pad_id: str = "",
    confidence: float,
    locked: bool | None = None,
) -> FootprintPlacement:
    """Build a stable placement record."""

    is_locked = footprint.locked if locked is None else locked
    digest = hashlib.sha1(
        f"{footprint.item_id}|{group_id}|{reason}".encode(), usedforsecurity=False
    ).hexdigest()[:14]
    return FootprintPlacement(
        placement_id=f"place-{digest}",
        footprint_id=footprint.item_id,
        reference=footprint.reference,
        value=footprint.value,
        group_id=group_id,
        old_position=footprint.position,
        position=footprint.position if is_locked else position,
        layer=footprint.layer,
        reason=reason,
        associated_footprint_id=associated_footprint_id,
        associated_pad_id=associated_pad_id,
        confidence=confidence,
        default_selected=not is_locked,
        locked=is_locked,
        old_bounds=footprint.bounds,
        destination_bounds=_bounds_at(footprint, footprint.position if is_locked else position),
        preview_pads=_preview_pads(footprint, footprint.position if is_locked else position),
        preview_texts=_preview_texts(footprint, footprint.position if is_locked else position),
    )


def _preview_pads(
    footprint: FootprintSnapshot,
    position: Point,
) -> tuple[PlacementPadPreview, ...]:
    """Translate every footprint pad to the proposed destination."""

    dx = position.x - footprint.position.x
    dy = position.y - footprint.position.y
    return tuple(
        PlacementPadPreview(
            item_id=pad.item_id,
            number=pad.number,
            net=pad.net,
            position=Point(pad.position.x + dx, pad.position.y + dy),
            bounds=BoundingBox(
                pad.bounds.min_x + dx,
                pad.bounds.min_y + dy,
                pad.bounds.max_x + dx,
                pad.bounds.max_y + dy,
            ),
        )
        for pad in footprint.pads
    )


def _preview_texts(
    footprint: FootprintSnapshot,
    position: Point,
) -> tuple[PlacementTextPreview, ...]:
    """Translate reference and value fields with their owning footprint."""

    dx = position.x - footprint.position.x
    dy = position.y - footprint.position.y
    result: list[PlacementTextPreview] = []
    for kind, field, fallback in (
        ("reference", footprint.reference_field, footprint.reference),
        ("value", footprint.value_field, footprint.value),
    ):
        result.append(
            PlacementTextPreview(
                kind=kind,
                text=field.value or fallback,
                position=Point(field.position.x + dx, field.position.y + dy),
                layer=field.layer,
                visible=field.visible,
                width=field.width,
                height=field.height,
                thickness=field.thickness,
                angle_deg=field.angle_deg,
            )
        )
    return tuple(result)


def _planning_bounds(snapshot: BoardSnapshot) -> BoundingBox:
    """Return a reasonable initial placement canvas from Edge.Cuts or footprints."""

    edge_points = [point for edge in snapshot.edges for point in (edge.start, edge.end)]
    if edge_points:
        bounds = bounds_from_points(edge_points)
        if bounds.area > 0.0:
            return bounds
    footprint_points = [
        point
        for footprint in snapshot.footprints
        for point in (
            Point(footprint.bounds.min_x, footprint.bounds.min_y),
            Point(footprint.bounds.max_x, footprint.bounds.max_y),
        )
    ]
    if footprint_points:
        return bounds_from_points(footprint_points).inflate(10.0)
    return BoundingBox(0.0, 0.0, 100.0, 80.0)


def _bounds_at(footprint: FootprintSnapshot, position: Point) -> BoundingBox:
    """Translate a footprint's conservative bounding box to a new position."""

    dx = position.x - footprint.position.x
    dy = position.y - footprint.position.y
    return BoundingBox(
        footprint.bounds.min_x + dx,
        footprint.bounds.min_y + dy,
        footprint.bounds.max_x + dx,
        footprint.bounds.max_y + dy,
    )


def _footprint_by_id(
    footprints: Sequence[FootprintSnapshot],
    item_id: str,
) -> FootprintSnapshot:
    """Return a footprint by identifier."""

    return next(item for item in footprints if item.item_id == item_id)


def _group_title(group_id: str) -> str:
    """Return a readable schematic-block title."""

    if group_id.startswith("reference:"):
        return group_id.split(":", 1)[1]
    stripped = group_id.rstrip("/")
    return stripped.rsplit("/", 1)[-1] or group_id


def _natural_reference(value: str) -> tuple[str, int, str]:
    """Return a stable natural-sort key for component references."""

    match = re.match(r"([A-Za-z]+)([0-9]+)(.*)", value or "")
    if not match:
        return value.upper(), 0, value
    return match.group(1).upper(), int(match.group(2)), match.group(3)


def _looks_like_ground(net: str) -> bool:
    """Return whether a net name is a common ground designation."""

    return bool(re.match(r"(?i)^(?:GND|AGND|DGND|PGND|VSS)(?:[_-].*)?$", net or ""))
