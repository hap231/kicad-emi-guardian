"""Conservative ground-via stitching and perimeter-rebuild planning.

The planner operates on a KiCad-independent board snapshot.  It never assumes
that two differently named ground nets may be shorted.  Candidate through-vias
are accepted only where the same exact ground net is present on both outer
copper layers and where pads, tracks, existing vias, and the board edge leave
sufficient clearance.
"""

from __future__ import annotations

import hashlib
import math
import re
from collections.abc import Iterable, Sequence
from dataclasses import asdict, dataclass

from .config import StitchingConfig
from .edge_optimizer import current_outline_ring
from .geometry import (
    add,
    distance,
    normalize,
    point_in_polygon,
    point_segment_distance,
    polygon_signed_area,
    scale,
    subtract,
)
from .models import BoardSnapshot, BoundingBox, Point, Polygon


@dataclass(frozen=True)
class StitchingViaCandidate:
    """One proposed through-via used to stitch an exact ground net."""

    candidate_id: str
    position: Point
    net: str
    diameter_mm: float
    drill_mm: float
    confidence: float
    critical_vertex: bool
    source: str
    default_selected: bool = True

    def to_dict(self) -> dict[str, object]:
        """Return a JSON-serializable representation."""

        return asdict(self)


@dataclass(frozen=True)
class ViaStitchingPlan:
    """Ground-via additions and optional safe perimeter-via removals."""

    net: str
    candidates: tuple[StitchingViaCandidate, ...]
    removable_via_ids: tuple[str, ...]
    rebuild_perimeter: bool
    outline: Polygon
    warnings: tuple[str, ...]

    def selected(
        self,
        candidate_ids: Iterable[str] | None,
        *,
        rebuild_perimeter: bool | None = None,
    ) -> ViaStitchingPlan:
        """Return a plan limited to explicitly selected candidate identifiers."""

        if candidate_ids is None:
            candidates = self.candidates
        else:
            selected_ids = {str(value) for value in candidate_ids}
            candidates = tuple(item for item in self.candidates if item.candidate_id in selected_ids)
        rebuild = self.rebuild_perimeter if rebuild_perimeter is None else bool(rebuild_perimeter)
        warnings = list(self.warnings)
        if candidate_ids is not None and len(candidates) != len(self.candidates) and rebuild:
            # Removing the complete old perimeter while installing only a subset
            # of the replacement pattern can create large unstitched gaps.  A
            # partial adoption therefore degrades to additions-only.
            rebuild = False
            warnings.append(
                "Perimeter-via removal was disabled because only part of the replacement pattern was selected."
            )
        return ViaStitchingPlan(
            net=self.net,
            candidates=candidates,
            removable_via_ids=self.removable_via_ids if rebuild else (),
            rebuild_perimeter=rebuild,
            outline=self.outline,
            warnings=tuple(dict.fromkeys(warnings)),
        )

    def to_dict(self) -> dict[str, object]:
        """Return a JSON-serializable representation."""

        return {
            "net": self.net,
            "candidates": [candidate.to_dict() for candidate in self.candidates],
            "removable_via_ids": list(self.removable_via_ids),
            "rebuild_perimeter": self.rebuild_perimeter,
            "outline": self.outline.to_dict(),
            "warnings": list(self.warnings),
            "summary": {
                "candidate_count": len(self.candidates),
                "vertex_candidate_count": sum(1 for item in self.candidates if item.critical_vertex),
                "removable_count": len(self.removable_via_ids),
            },
        }


def plan_via_stitching(
    snapshot: BoardSnapshot,
    config: StitchingConfig,
    *,
    outline: Sequence[Point] | None = None,
    rebuild_perimeter: bool | None = None,
) -> ViaStitchingPlan:
    """Create a moderate-density, clearance-aware ground-via plan.

    The dominant exact ground net is selected by filled-copper area.  Through
    vias are proposed only where that net is filled on both ``F.Cu`` and
    ``B.Cu``.  Vertex-near locations are attempted before regular edge samples.
    Existing perimeter vias are marked removable only when they are unlocked,
    clear of every footprint pad, and not contacted by an explicit same-net
    track.  This intentionally favors false negatives over deleting a
    functional connection.
    """

    if not config.enabled:
        raise ValueError("Ground-via stitching is disabled in the active configuration.")
    ring = tuple(outline or current_outline_ring(snapshot, max(0.05, config.spacing_mm / 20.0)))
    ring = _normalize_ring(ring)
    if len(ring) < 3:
        raise ValueError("A connected board outline is required for via stitching.")

    ground_pattern = re.compile(config.net_regex, re.IGNORECASE)
    net = _dominant_ground_net(snapshot, ground_pattern)
    if not net:
        raise ValueError("No filled ground net was found on the board.")

    outer_layers = _outer_copper_layers(snapshot)
    if config.require_ground_on_both_layers and len(outer_layers) < 2:
        raise ValueError("Two outer copper layers are required for through-via stitching.")
    polygons = _filled_polygons(snapshot, net)
    required_layers = outer_layers if config.require_ground_on_both_layers else tuple(polygons)
    if any(not polygons.get(layer) for layer in required_layers):
        raise ValueError(f"Ground net '{net}' is not filled on every required outer copper layer.")

    requested_rebuild = config.rebuild_perimeter if rebuild_perimeter is None else bool(rebuild_perimeter)
    warnings: list[str] = []
    accepted: list[StitchingViaCandidate] = []
    accepted_positions: list[Point] = []
    rejected_vertices = 0
    maximum = max(1, config.maximum_vias)

    raw_candidates = [
        *(_vertex_candidates(ring, config.vertex_offset_mm)),
        *(_edge_candidates(ring, config.spacing_mm, config.edge_offset_mm)),
    ]
    seen_cells: set[tuple[int, int]] = set()
    dedup = max(0.05, config.minimum_spacing_mm / 3.0)
    for point, source, critical_vertex in raw_candidates:
        if len(accepted) >= maximum:
            warnings.append(f"The stitching plan was limited to {maximum} vias.")
            break
        cell = (round(point.x / dedup), round(point.y / dedup))
        if cell in seen_cells:
            continue
        seen_cells.add(cell)
        if not _candidate_is_safe(
            snapshot,
            point,
            ring,
            net,
            polygons,
            required_layers,
            config,
            accepted_positions,
        ):
            if critical_vertex:
                rejected_vertices += 1
            continue
        candidate = StitchingViaCandidate(
            candidate_id=_candidate_id(net, point, source),
            position=point,
            net=net,
            diameter_mm=config.via_diameter_mm,
            drill_mm=config.via_drill_mm,
            confidence=0.94 if critical_vertex else 0.90,
            critical_vertex=critical_vertex,
            source=source,
        )
        accepted.append(candidate)
        accepted_positions.append(point)

    if rejected_vertices:
        warnings.append(f"{rejected_vertices} board vertices had no clearance-safe ground-via location.")
    if not accepted:
        warnings.append("No clearance-safe ground-via candidate was found.")

    removable = _safe_removable_perimeter_vias(snapshot, ring, net, config) if requested_rebuild else ()
    if requested_rebuild and not removable:
        warnings.append(
            "Perimeter rebuild was requested, but no existing via met the conservative removal criteria."
        )

    return ViaStitchingPlan(
        net=net,
        candidates=tuple(accepted),
        removable_via_ids=tuple(removable),
        rebuild_perimeter=requested_rebuild,
        outline=Polygon(outline=ring),
        warnings=tuple(dict.fromkeys(warnings)),
    )


def _dominant_ground_net(snapshot: BoardSnapshot, pattern: re.Pattern[str]) -> str:
    """Return the exact ground-net name with the largest filled-copper area."""

    areas: dict[str, float] = {}
    for zone in snapshot.zones:
        if zone.is_rule_area or not zone.net or not pattern.search(zone.net):
            continue
        area = 0.0
        for layer_polygons in zone.filled.values():
            for polygon in layer_polygons:
                area += abs(polygon_signed_area(polygon.outline))
                area -= sum(abs(polygon_signed_area(hole)) for hole in polygon.holes)
        areas[zone.net] = areas.get(zone.net, 0.0) + max(0.0, area)
    return max(areas, key=lambda name: (areas[name], name), default="")


def _outer_copper_layers(snapshot: BoardSnapshot) -> tuple[str, ...]:
    """Return available outer copper layers in deterministic order."""

    available = {track.layer for track in snapshot.tracks if track.layer.endswith(".Cu")}
    available.update(layer for zone in snapshot.zones for layer in zone.layers if layer.endswith(".Cu"))
    available.update(layer for pad in snapshot.pads for layer in pad.layers if layer.endswith(".Cu"))
    result = tuple(layer for layer in ("F.Cu", "B.Cu") if layer in available)
    return result or ("F.Cu", "B.Cu")


def _filled_polygons(snapshot: BoardSnapshot, net: str) -> dict[str, tuple[Polygon, ...]]:
    """Group filled polygons for one exact net by copper layer."""

    grouped: dict[str, list[Polygon]] = {}
    for zone in snapshot.zones:
        if zone.is_rule_area or zone.net != net:
            continue
        for layer, polygons in zone.filled.items():
            grouped.setdefault(layer, []).extend(polygons)
    return {layer: tuple(polygons) for layer, polygons in grouped.items()}


def _vertex_candidates(
    ring: Sequence[Point],
    offset_mm: float,
) -> Iterable[tuple[Point, str, bool]]:
    """Yield one inward candidate close to every sharp outline vertex."""

    orientation = 1.0 if polygon_signed_area(ring) > 0.0 else -1.0
    centroid = Point(
        sum(point.x for point in ring) / len(ring),
        sum(point.y for point in ring) / len(ring),
    )
    for index, vertex in enumerate(ring):
        previous = ring[index - 1]
        following = ring[(index + 1) % len(ring)]
        incoming = normalize(subtract(vertex, previous))
        outgoing = normalize(subtract(following, vertex))
        inward_first = Point(-incoming.y * orientation, incoming.x * orientation)
        inward_second = Point(-outgoing.y * orientation, outgoing.x * orientation)
        direction = normalize(add(inward_first, inward_second))
        if abs(direction.x) + abs(direction.y) <= 1.0e-9:
            direction = normalize(subtract(centroid, vertex))
        candidate = add(vertex, scale(direction, max(0.05, offset_mm)))
        if not point_in_polygon(candidate, Polygon(outline=tuple(ring))):
            candidate = add(vertex, scale(normalize(subtract(centroid, vertex)), max(0.05, offset_mm)))
        yield candidate, "vertex", True


def _edge_candidates(
    ring: Sequence[Point],
    spacing_mm: float,
    offset_mm: float,
) -> Iterable[tuple[Point, str, bool]]:
    """Yield evenly spaced inward candidates along every outline segment."""

    orientation = 1.0 if polygon_signed_area(ring) > 0.0 else -1.0
    spacing = max(0.25, spacing_mm)
    offset = max(0.05, offset_mm)
    for index, start in enumerate(ring):
        end = ring[(index + 1) % len(ring)]
        length = distance(start, end)
        if length <= spacing * 0.75:
            continue
        tangent = normalize(subtract(end, start))
        inward = Point(-tangent.y * orientation, tangent.x * orientation)
        count = max(1, int(math.floor(length / spacing)))
        for sample in range(1, count + 1):
            along = min(length - spacing * 0.35, sample * length / (count + 1))
            boundary = add(start, scale(tangent, along))
            yield add(boundary, scale(inward, offset)), "perimeter", False


def _candidate_is_safe(
    snapshot: BoardSnapshot,
    point: Point,
    ring: Sequence[Point],
    net: str,
    polygons: dict[str, tuple[Polygon, ...]],
    required_layers: Sequence[str],
    config: StitchingConfig,
    accepted_positions: Sequence[Point],
) -> bool:
    """Return whether one proposed via satisfies copper and clearance checks."""

    radius = config.via_diameter_mm / 2.0
    clearance = max(0.0, config.clearance_mm)
    outline = Polygon(outline=tuple(ring))
    if not point_in_polygon(point, outline):
        return False
    edge_distance = min(
        point_segment_distance(point, ring[index], ring[(index + 1) % len(ring)])
        for index in range(len(ring))
    )
    if edge_distance + 1.0e-9 < radius + clearance:
        return False
    if any(
        not _via_disk_inside_polygons(point, radius, polygons.get(layer, ())) for layer in required_layers
    ):
        return False
    for pad in snapshot.pads:
        if _point_box_distance(point, pad.bounds) < radius + clearance:
            return False
    for track in snapshot.tracks:
        if point_segment_distance(point, track.start, track.end) < radius + track.width / 2.0 + clearance:
            return False
    for via in snapshot.vias:
        if distance(point, via.position) < max(
            config.minimum_spacing_mm,
            radius + via.diameter / 2.0 + clearance,
        ):
            return False
    return not any(distance(point, existing) < config.minimum_spacing_mm for existing in accepted_positions)


def _via_disk_inside_polygons(
    center: Point,
    radius: float,
    polygons: Sequence[Polygon],
    sample_count: int = 16,
) -> bool:
    """Return whether a via annulus footprint remains inside filled copper.

    Testing only the center can accept a via whose annular ring hangs beyond a
    narrow pour edge or falls into a polygon hole.  The center and a sampled
    circle at the copper radius are checked on every required layer.  This is a
    conservative geometric screen; KiCad DRC remains the final authority.
    """

    if not polygons or not any(point_in_polygon(center, polygon) for polygon in polygons):
        return False
    probe_radius = max(0.0, radius) * 1.001
    for index in range(max(8, sample_count)):
        angle = 2.0 * math.pi * index / max(8, sample_count)
        point = Point(
            center.x + probe_radius * math.cos(angle),
            center.y + probe_radius * math.sin(angle),
        )
        if not any(point_in_polygon(point, polygon) for polygon in polygons):
            return False
    return True


def _safe_removable_perimeter_vias(
    snapshot: BoardSnapshot,
    ring: Sequence[Point],
    net: str,
    config: StitchingConfig,
) -> tuple[str, ...]:
    """Return existing vias that conservatively look like perimeter stitching."""

    removable: list[str] = []
    for via in snapshot.vias:
        if via.net != net or via.locked:
            continue
        edge_distance = min(
            point_segment_distance(via.position, ring[index], ring[(index + 1) % len(ring)])
            for index in range(len(ring))
        )
        if edge_distance > config.removable_band_mm:
            continue
        keep = False
        safety_radius = via.diameter / 2.0 + config.clearance_mm
        for pad in snapshot.pads:
            if _point_box_distance(via.position, pad.bounds) <= safety_radius:
                keep = True
                break
        if keep:
            continue
        for track in snapshot.tracks:
            if track.net != net:
                continue
            if (
                point_segment_distance(via.position, track.start, track.end)
                <= via.diameter / 2.0 + track.width / 2.0 + 1.0e-6
            ):
                keep = True
                break
        if not keep:
            removable.append(via.item_id)
    return tuple(sorted(removable))


def _point_box_distance(point: Point, bounds: BoundingBox) -> float:
    """Return Euclidean distance from a point to an axis-aligned box."""

    dx = max(bounds.min_x - point.x, 0.0, point.x - bounds.max_x)
    dy = max(bounds.min_y - point.y, 0.0, point.y - bounds.max_y)
    return math.hypot(dx, dy)


def _normalize_ring(points: Sequence[Point]) -> tuple[Point, ...]:
    """Remove duplicate closure points and normalize orientation."""

    cleaned: list[Point] = []
    for point in points:
        if not cleaned or distance(cleaned[-1], point) > 1.0e-8:
            cleaned.append(point)
    if len(cleaned) > 1 and distance(cleaned[0], cleaned[-1]) <= 1.0e-8:
        cleaned.pop()
    if len(cleaned) >= 3 and polygon_signed_area(cleaned) < 0.0:
        cleaned.reverse()
    return tuple(cleaned)


def _candidate_id(net: str, point: Point, source: str) -> str:
    """Return a stable candidate identifier."""

    digest = hashlib.sha1(
        f"{net}|{point.x:.5f}|{point.y:.5f}|{source}".encode(), usedforsecurity=False
    ).hexdigest()[:14]
    return f"stitch-{digest}"
