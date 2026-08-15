"""Connectivity model for filled ground copper across layers and item types.

The model deliberately treats a via as an inter-layer conductor rather than an
independent electrical anchor.  A copper component is considered anchored only
when it reaches at least one same-net footprint pad.  Tracks, vias, pads, and
filled zone polygons are unioned with conservative geometric tolerances.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass

from .geometry import (
    pairwise_closed,
    point_in_polygon,
    point_segment_distance,
    polygon_area,
    polygon_boundary_distance,
    segment_crosses_polygon,
    segment_distance,
    segments_intersect,
)
from .models import (
    BoardSnapshot,
    BoundingBox,
    Pad,
    Point,
    Polygon,
    TrackSegment,
    Via,
    bounds_from_points,
)

RegionKey = tuple[str, str, int]


class _UnionFind:
    """Small deterministic disjoint-set implementation."""

    def __init__(self) -> None:
        self.parent: dict[str, str] = {}
        self.rank: dict[str, int] = {}

    def add(self, value: str) -> None:
        """Add *value* when absent."""

        if value not in self.parent:
            self.parent[value] = value
            self.rank[value] = 0

    def find(self, value: str) -> str:
        """Return the representative for *value*."""

        parent = self.parent[value]
        if parent != value:
            self.parent[value] = self.find(parent)
        return self.parent[value]

    def union(self, first: str, second: str) -> None:
        """Union two existing values."""

        first_root = self.find(first)
        second_root = self.find(second)
        if first_root == second_root:
            return
        first_rank = self.rank[first_root]
        second_rank = self.rank[second_root]
        if first_rank < second_rank:
            first_root, second_root = second_root, first_root
        self.parent[second_root] = first_root
        if first_rank == second_rank:
            self.rank[first_root] += 1


@dataclass(frozen=True)
class GroundRegion:
    """One filled zone polygon on one copper layer."""

    key: RegionKey
    net: str
    layer: str
    polygon: Polygon
    bounds: BoundingBox
    area_mm2: float


@dataclass(frozen=True)
class GroundComponent:
    """One electrically connected same-net ground component."""

    component_id: str
    net: str
    regions: tuple[RegionKey, ...]
    pad_ids: tuple[str, ...]
    via_ids: tuple[str, ...]
    track_ids: tuple[str, ...]
    area_mm2: float

    @property
    def anchored(self) -> bool:
        """Return whether the component reaches at least one footprint pad."""

        return bool(self.pad_ids)


@dataclass(frozen=True)
class GroundConnectivity:
    """Connectivity lookup returned to antenna and return-path analyzers."""

    regions: Mapping[RegionKey, GroundRegion]
    region_components: Mapping[RegionKey, str]
    components: Mapping[str, GroundComponent]
    ground_pad_count: int

    def component_for_region(self, key: RegionKey) -> GroundComponent | None:
        """Return the component containing *key*."""

        component_id = self.region_components.get(key)
        return self.components.get(component_id) if component_id else None

    def region_is_anchored(self, key: RegionKey) -> bool:
        """Return whether *key* reaches a same-net footprint pad."""

        component = self.component_for_region(key)
        return bool(component and component.anchored)


def build_ground_connectivity(
    snapshot: BoardSnapshot,
    ground_net_regex: str,
    tolerance_mm: float = 0.08,
) -> GroundConnectivity:
    """Build a same-net copper connectivity graph for all ground-like nets."""

    pattern = re.compile(ground_net_regex, re.IGNORECASE)
    ground_nets = {
        value
        for value in (
            *(zone.net for zone in snapshot.zones),
            *(track.net for track in snapshot.tracks),
            *(via.net for via in snapshot.vias),
            *(pad.net for pad in snapshot.pads),
        )
        if value and pattern.search(value)
    }
    regions: dict[RegionKey, GroundRegion] = {}
    zones_by_net_layer: dict[tuple[str, str], list[GroundRegion]] = {}
    for zone in snapshot.zones:
        if zone.is_rule_area or zone.net not in ground_nets:
            continue
        emitted = False
        for layer, polygons in zone.filled.items():
            if not polygons:
                continue
            emitted = True
            for index, polygon in enumerate(polygons):
                key = (zone.item_id, layer, index)
                zone_region = GroundRegion(
                    key=key,
                    net=zone.net,
                    layer=layer,
                    polygon=polygon,
                    bounds=bounds_from_points(polygon.outline),
                    area_mm2=polygon_area(polygon),
                )
                regions[key] = zone_region
                zones_by_net_layer.setdefault((zone.net, layer), []).append(zone_region)
        if not emitted:
            for layer in zone.layers:
                key = (zone.item_id, layer, 0)
                zone_region = GroundRegion(
                    key=key,
                    net=zone.net,
                    layer=layer,
                    polygon=zone.outline,
                    bounds=bounds_from_points(zone.outline.outline),
                    area_mm2=polygon_area(zone.outline),
                )
                regions[key] = zone_region
                zones_by_net_layer.setdefault((zone.net, layer), []).append(zone_region)

    ground_tracks = tuple(track for track in snapshot.tracks if track.net in ground_nets)
    ground_vias = tuple(via for via in snapshot.vias if via.net in ground_nets)
    ground_pads = tuple(pad for pad in snapshot.pads if pad.net in ground_nets)

    union = _UnionFind()
    region_nodes = {key: _region_node(key) for key in regions}
    track_nodes = {track.item_id: f"T:{track.item_id}" for track in ground_tracks}
    via_nodes = {via.item_id: f"V:{via.item_id}" for via in ground_vias}
    pad_nodes = {pad.item_id: f"P:{pad.item_id}" for pad in ground_pads}
    for node in (*region_nodes.values(), *track_nodes.values(), *via_nodes.values(), *pad_nodes.values()):
        union.add(node)

    # Filled polygons on the same layer may be emitted as multiple touching
    # contours by KiCad.  Union them before evaluating island status.
    for group in zones_by_net_layer.values():
        for index, first_region in enumerate(group):
            for second_region in group[index + 1 :]:
                if not first_region.bounds.inflate(tolerance_mm).intersects(second_region.bounds):
                    continue
                if _polygons_contact(first_region.polygon, second_region.polygon, tolerance_mm):
                    union.union(region_nodes[first_region.key], region_nodes[second_region.key])

    for track in ground_tracks:
        track_node = track_nodes[track.item_id]
        for zone_region in zones_by_net_layer.get((track.net, track.layer), ()):
            if not _segment_bounds(track.start, track.end, track.width / 2.0 + tolerance_mm).intersects(
                zone_region.bounds
            ):
                continue
            if _segment_contacts_polygon(track, zone_region.polygon, tolerance_mm):
                union.union(track_node, region_nodes[zone_region.key])

    for index, first_track in enumerate(ground_tracks):
        for second_track in ground_tracks[index + 1 :]:
            if first_track.net != second_track.net or first_track.layer != second_track.layer:
                continue
            clearance = first_track.width / 2.0 + second_track.width / 2.0 + tolerance_mm
            if not _segment_bounds(first_track.start, first_track.end, clearance).intersects(
                _segment_bounds(second_track.start, second_track.end, 0.0)
            ):
                continue
            if (
                segment_distance(first_track.start, first_track.end, second_track.start, second_track.end)
                <= clearance
            ):
                union.union(track_nodes[first_track.item_id], track_nodes[second_track.item_id])

    for via in ground_vias:
        via_node = via_nodes[via.item_id]
        for layer in _via_layers(via, snapshot):
            for zone_region in zones_by_net_layer.get((via.net, layer), ()):
                if _point_contacts_polygon(
                    via.position, via.diameter / 2.0 + tolerance_mm, zone_region.polygon
                ):
                    union.union(via_node, region_nodes[zone_region.key])
        for track in ground_tracks:
            if track.net != via.net or track.layer not in _via_layers(via, snapshot):
                continue
            if (
                point_segment_distance(via.position, track.start, track.end)
                <= via.diameter / 2.0 + track.width / 2.0 + tolerance_mm
            ):
                union.union(via_node, track_nodes[track.item_id])

    for pad in ground_pads:
        pad_node = pad_nodes[pad.item_id]
        layers = _pad_copper_layers(pad, snapshot)
        for layer in layers:
            for zone_region in zones_by_net_layer.get((pad.net, layer), ()):
                if pad.bounds.inflate(tolerance_mm).intersects(zone_region.bounds) and _box_contacts_polygon(
                    pad.bounds.inflate(tolerance_mm), zone_region.polygon
                ):
                    union.union(pad_node, region_nodes[zone_region.key])
        for track in ground_tracks:
            if track.net != pad.net or track.layer not in layers:
                continue
            if _segment_intersects_box(
                track.start, track.end, pad.bounds.inflate(track.width / 2.0 + tolerance_mm)
            ):
                union.union(pad_node, track_nodes[track.item_id])
        for via in ground_vias:
            if via.net != pad.net or not set(_via_layers(via, snapshot)).intersection(layers):
                continue
            if _point_in_box(via.position, pad.bounds.inflate(via.diameter / 2.0 + tolerance_mm)):
                union.union(pad_node, via_nodes[via.item_id])

    grouped_regions: dict[str, list[RegionKey]] = {}
    grouped_pads: dict[str, list[str]] = {}
    grouped_vias: dict[str, list[str]] = {}
    grouped_tracks: dict[str, list[str]] = {}
    for key, node in region_nodes.items():
        grouped_regions.setdefault(union.find(node), []).append(key)
    for item_id, node in pad_nodes.items():
        grouped_pads.setdefault(union.find(node), []).append(item_id)
    for item_id, node in via_nodes.items():
        grouped_vias.setdefault(union.find(node), []).append(item_id)
    for item_id, node in track_nodes.items():
        grouped_tracks.setdefault(union.find(node), []).append(item_id)

    component_roots = sorted(
        set(grouped_regions) | set(grouped_pads) | set(grouped_vias) | set(grouped_tracks)
    )
    components: dict[str, GroundComponent] = {}
    root_to_id: dict[str, str] = {}
    for index, root in enumerate(component_roots, start=1):
        component_id = f"GND-COMP-{index:04d}"
        root_to_id[root] = component_id
        component_regions = tuple(sorted(grouped_regions.get(root, ())))
        net = (
            regions[component_regions[0]].net
            if component_regions
            else _net_for_root(
                root,
                union,
                ground_tracks,
                ground_vias,
                ground_pads,
                track_nodes,
                via_nodes,
                pad_nodes,
            )
        )
        components[component_id] = GroundComponent(
            component_id=component_id,
            net=net,
            regions=component_regions,
            pad_ids=tuple(sorted(grouped_pads.get(root, ()))),
            via_ids=tuple(sorted(grouped_vias.get(root, ()))),
            track_ids=tuple(sorted(grouped_tracks.get(root, ()))),
            area_mm2=sum(regions[key].area_mm2 for key in component_regions),
        )

    return GroundConnectivity(
        regions=regions,
        region_components={key: root_to_id[union.find(node)] for key, node in region_nodes.items()},
        components=components,
        ground_pad_count=len(ground_pads),
    )


def _region_node(key: RegionKey) -> str:
    """Return the union-find key for one filled polygon."""

    return f"R:{key[0]}:{key[1]}:{key[2]}"


def _via_layers(via: Via, snapshot: BoardSnapshot) -> tuple[str, ...]:
    """Return copper layers electrically traversed by a via."""

    copper_layers = _all_copper_layers(snapshot)
    if not copper_layers:
        return tuple(dict.fromkeys((via.start_layer, via.end_layer)))
    try:
        start = copper_layers.index(via.start_layer)
        end = copper_layers.index(via.end_layer)
    except ValueError:
        return tuple(dict.fromkeys((via.start_layer, via.end_layer)))
    low, high = sorted((start, end))
    return copper_layers[low : high + 1]


def _all_copper_layers(snapshot: BoardSnapshot) -> tuple[str, ...]:
    """Return known copper layers in physical order when available."""

    records = snapshot.metadata.get("stackup", {}) if isinstance(snapshot.metadata, Mapping) else {}
    layers = records.get("layers", ()) if isinstance(records, Mapping) else ()
    names = tuple(
        str(item.get("name"))
        for item in layers
        if isinstance(item, Mapping) and str(item.get("name", "")).endswith(".Cu")
    )
    if names:
        return names
    observed = {
        *(track.layer for track in snapshot.tracks if track.layer.endswith(".Cu")),
        *(layer for zone in snapshot.zones for layer in zone.layers if layer.endswith(".Cu")),
        *(via.start_layer for via in snapshot.vias),
        *(via.end_layer for via in snapshot.vias),
    }
    ordered: list[str] = [name for name in ("F.Cu", "B.Cu") if name in observed]
    ordered[1:1] = sorted(name for name in observed if name not in {"F.Cu", "B.Cu"})
    return tuple(ordered)


def _pad_copper_layers(pad: Pad, snapshot: BoardSnapshot) -> tuple[str, ...]:
    """Return layers on which a pad can contact copper.

    KiCad may represent through-hole and NPTH padstacks with wildcard layer
    tokens such as ``*.Cu``.  Treat those as all copper layers rather than as a
    literal layer name; otherwise valid through-hole GND anchors are missed and
    connected pours can be reported as floating islands.
    """

    all_layers = _all_copper_layers(snapshot)
    raw_layers = tuple(str(layer) for layer in pad.layers)
    if not raw_layers or any(layer in {"*.Cu", "*.Copper", "All.Cu"} for layer in raw_layers):
        return all_layers
    explicit = tuple(layer for layer in raw_layers if layer.endswith(".Cu") and not layer.startswith("*"))
    return explicit or all_layers


def _polygons_contact(first: Polygon, second: Polygon, tolerance: float) -> bool:
    """Return whether two filled polygons touch or overlap."""

    if any(point_in_polygon(point, second) for point in first.outline):
        return True
    if any(point_in_polygon(point, first) for point in second.outline):
        return True
    for first_start, first_end in pairwise_closed(first.outline):
        for second_start, second_end in pairwise_closed(second.outline):
            if segment_distance(first_start, first_end, second_start, second_end) <= tolerance:
                return True
    return False


def _segment_contacts_polygon(track: TrackSegment, polygon: Polygon, tolerance: float) -> bool:
    """Return whether a finite-width track contacts a filled polygon."""

    if segment_crosses_polygon(track.start, track.end, polygon):
        return True
    radius = track.width / 2.0 + tolerance
    return (
        min(
            polygon_boundary_distance(track.start, polygon),
            polygon_boundary_distance(track.end, polygon),
            *(
                segment_distance(track.start, track.end, first, second)
                for first, second in pairwise_closed(polygon.outline)
            ),
        )
        <= radius
    )


def _point_contacts_polygon(point: Point, radius: float, polygon: Polygon) -> bool:
    """Return whether a circular copper feature contacts a polygon."""

    return point_in_polygon(point, polygon) or polygon_boundary_distance(point, polygon) <= radius


def _box_contacts_polygon(bounds: BoundingBox, polygon: Polygon) -> bool:
    """Return whether an axis-aligned pad box contacts a polygon."""

    corners = (
        Point(bounds.min_x, bounds.min_y),
        Point(bounds.max_x, bounds.min_y),
        Point(bounds.max_x, bounds.max_y),
        Point(bounds.min_x, bounds.max_y),
    )
    if any(point_in_polygon(point, polygon) for point in (*corners, bounds.center)):
        return True
    if any(_point_in_box(point, bounds) for point in polygon.outline):
        return True
    box_edges = tuple(pairwise_closed(corners))
    return any(
        segments_intersect(first_start, first_end, second_start, second_end)
        for first_start, first_end in box_edges
        for second_start, second_end in pairwise_closed(polygon.outline)
    )


def _segment_intersects_box(start: Point, end: Point, bounds: BoundingBox) -> bool:
    """Return whether a segment touches an axis-aligned box."""

    if _point_in_box(start, bounds) or _point_in_box(end, bounds):
        return True
    corners = (
        Point(bounds.min_x, bounds.min_y),
        Point(bounds.max_x, bounds.min_y),
        Point(bounds.max_x, bounds.max_y),
        Point(bounds.min_x, bounds.max_y),
    )
    return any(segments_intersect(start, end, first, second) for first, second in pairwise_closed(corners))


def _point_in_box(point: Point, bounds: BoundingBox) -> bool:
    """Return whether *point* lies in *bounds*."""

    return bounds.min_x <= point.x <= bounds.max_x and bounds.min_y <= point.y <= bounds.max_y


def _segment_bounds(start: Point, end: Point, inflate: float) -> BoundingBox:
    """Return an inflated bounding box for a segment."""

    return BoundingBox(
        min(start.x, end.x) - inflate,
        min(start.y, end.y) - inflate,
        max(start.x, end.x) + inflate,
        max(start.y, end.y) + inflate,
    )


def _net_for_root(
    root: str,
    union: _UnionFind,
    tracks: Iterable[TrackSegment],
    vias: Iterable[Via],
    pads: Iterable[Pad],
    track_nodes: Mapping[str, str],
    via_nodes: Mapping[str, str],
    pad_nodes: Mapping[str, str],
) -> str:
    """Recover the net name for a component without filled polygons."""

    for collection, nodes in ((tracks, track_nodes), (vias, via_nodes), (pads, pad_nodes)):
        for item in collection:
            if union.find(nodes[item.item_id]) == root:
                return item.net
    return ""
