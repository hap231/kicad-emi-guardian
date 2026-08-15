"""Qualitative PCB noise and signal-integrity heuristics.

The checks intentionally favor traceable geometric evidence over opaque global
rules.  Expensive searches use uniform-grid or graph indexes so runtime grows
close to linearly for typical boards.
"""

from __future__ import annotations

import hashlib
import heapq
import math
import re
from collections import defaultdict
from collections.abc import Iterable, Iterator, Mapping, Sequence
from dataclasses import dataclass

from .config import NoiseConfig
from .geometry import (
    acute_direction_difference,
    angle_between,
    direction_angle,
    distance,
    parallel_overlap_length,
    point_in_polygon,
    point_segment_distance,
    segment_distance,
    subtract,
)
from .models import BoardSnapshot, Finding, Pad, Point, Polygon, Severity, TrackSegment, Via
from .quantitative import critical_length_mm, crosstalk_proxy, effective_permittivity_microstrip
from .raster import cells_to_outline, detect_narrow_features

NodeKey = tuple[str, int, int]


@dataclass(frozen=True)
class _GraphEdge:
    """One weighted route-graph edge."""

    other: NodeKey
    length_mm: float
    track: TrackSegment


@dataclass(frozen=True)
class _RouteComponent:
    """Connected route component and its approximate electrical diameter."""

    nodes: tuple[NodeKey, ...]
    tracks: tuple[TrackSegment, ...]
    total_length_mm: float
    path_length_mm: float
    path_track_ids: tuple[str, ...]
    path_start: Point
    path_end: Point
    diameter_method: str
    diameter_source_count: int


class _AnchorIndex:
    """Uniform-grid index for same-net pads and vias near route vertices."""

    def __init__(self, snapshot: BoardSnapshot, cell_size_mm: float) -> None:
        self._cell_size = max(0.25, cell_size_mm)
        self._vias: dict[tuple[str, int, int], list[Via]] = defaultdict(list)
        self._pads: dict[tuple[str, int, int], list[Pad]] = defaultdict(list)
        for via in snapshot.vias:
            radius = max(0.0, via.diameter / 2.0)
            for cell in self._cells_for_bounds(
                via.position.x - radius,
                via.position.y - radius,
                via.position.x + radius,
                via.position.y + radius,
            ):
                self._vias[(via.net, *cell)].append(via)
        for pad in snapshot.pads:
            for cell in self._cells_for_bounds(
                pad.bounds.min_x,
                pad.bounds.min_y,
                pad.bounds.max_x,
                pad.bounds.max_y,
            ):
                self._pads[(pad.net, *cell)].append(pad)

    def has_same_net_anchor(
        self,
        track: TrackSegment,
        point: Point,
        tolerance_mm: float,
    ) -> bool:
        """Return whether same-net copper anchors a route vertex."""

        cells = self._query_cells(point, tolerance_mm)
        seen_vias: set[str] = set()
        for cell_x, cell_y in cells:
            for via in self._vias.get((track.net, cell_x, cell_y), ()):
                if via.item_id in seen_vias:
                    continue
                seen_vias.add(via.item_id)
                if distance(point, via.position) <= tolerance_mm + via.diameter / 2.0:
                    return True
        seen_pads: set[str] = set()
        for cell_x, cell_y in cells:
            for pad in self._pads.get((track.net, cell_x, cell_y), ()):
                if pad.item_id in seen_pads:
                    continue
                seen_pads.add(pad.item_id)
                if pad.layers and track.layer not in pad.layers:
                    continue
                bounds = pad.bounds.inflate(tolerance_mm)
                if bounds.min_x <= point.x <= bounds.max_x and bounds.min_y <= point.y <= bounds.max_y:
                    return True
        return False

    def collapses_route_layer(
        self,
        track: TrackSegment,
        point: Point,
        tolerance_mm: float,
    ) -> bool:
        """Return whether a via or multilayer pad joins route graph layers."""

        cells = self._query_cells(point, tolerance_mm)
        seen_vias: set[str] = set()
        for cell_x, cell_y in cells:
            for via in self._vias.get((track.net, cell_x, cell_y), ()):
                if via.item_id in seen_vias:
                    continue
                seen_vias.add(via.item_id)
                if distance(point, via.position) <= tolerance_mm + via.diameter / 2.0:
                    return True
        seen_pads: set[str] = set()
        for cell_x, cell_y in cells:
            for pad in self._pads.get((track.net, cell_x, cell_y), ()):
                if pad.item_id in seen_pads:
                    continue
                seen_pads.add(pad.item_id)
                bounds = pad.bounds.inflate(tolerance_mm)
                if not (bounds.min_x <= point.x <= bounds.max_x and bounds.min_y <= point.y <= bounds.max_y):
                    continue
                copper_layers = {layer for layer in pad.layers if layer.endswith(".Cu")}
                if len(copper_layers) > 1:
                    return True
        return False

    def _query_cells(self, point: Point, tolerance_mm: float) -> tuple[tuple[int, int], ...]:
        """Return grid cells touched by a point-centered tolerance box."""

        return tuple(
            self._cells_for_bounds(
                point.x - tolerance_mm,
                point.y - tolerance_mm,
                point.x + tolerance_mm,
                point.y + tolerance_mm,
            )
        )

    def _cells_for_bounds(
        self,
        min_x: float,
        min_y: float,
        max_x: float,
        max_y: float,
    ) -> Iterator[tuple[int, int]]:
        """Yield every grid cell intersected by a bounding box."""

        x_start = math.floor(min_x / self._cell_size)
        x_end = math.floor(max_x / self._cell_size)
        y_start = math.floor(min_y / self._cell_size)
        y_end = math.floor(max_y / self._cell_size)
        for cell_x in range(x_start, x_end + 1):
            for cell_y in range(y_start, y_end + 1):
                yield cell_x, cell_y


def analyze_noise(
    snapshot: BoardSnapshot,
    config: NoiseConfig,
    ground_net_regex: str,
) -> tuple[Finding, ...]:
    """Run all qualitative noise checks and return evidence-backed findings."""

    ground_pattern = re.compile(ground_net_regex, re.IGNORECASE)
    anchor_index = _AnchorIndex(
        snapshot,
        max(0.50, config.endpoint_snap_mm * 4.0, config.corner_pad_clearance_mm * 2.0),
    )
    findings: list[Finding] = []
    findings.extend(_detect_dangling_stubs(snapshot, config, anchor_index))
    findings.extend(_detect_parallel_coupling(snapshot, config))
    findings.extend(_detect_corners(snapshot, config, anchor_index))
    findings.extend(_detect_long_nets(snapshot, config, ground_pattern, anchor_index))
    layer_count = _copper_layer_count(snapshot)
    if not (layer_count <= 2 and config.skip_return_via_check_on_two_layer):
        findings.extend(_detect_return_via_gaps(snapshot, config, ground_pattern))
    findings.extend(_detect_reference_plane_gaps(snapshot, config, ground_pattern, layer_count))
    findings.extend(_detect_ground_return_detours(snapshot, config, ground_pattern, anchor_index))
    findings.extend(_detect_ground_bottlenecks(snapshot, config, ground_pattern))
    findings.extend(_detect_edge_proximity(snapshot, config, ground_pattern))
    findings.extend(_detect_differential_mismatch(snapshot, config))
    return tuple(findings)


def _detect_dangling_stubs(
    snapshot: BoardSnapshot,
    config: NoiseConfig,
    anchor_index: _AnchorIndex,
) -> list[Finding]:
    """Detect degree-one routed endpoints that do not terminate at a pad or via."""

    endpoints: dict[tuple[str, str, int, int], list[tuple[TrackSegment, Point]]] = defaultdict(list)
    for track in snapshot.tracks:
        endpoints[_endpoint_key(track.net, track.layer, track.start, config.endpoint_snap_mm)].append(
            (track, track.start)
        )
        endpoints[_endpoint_key(track.net, track.layer, track.end, config.endpoint_snap_mm)].append(
            (track, track.end)
        )

    findings: list[Finding] = []
    emitted_tracks: set[str] = set()
    for key, attached in endpoints.items():
        if len(attached) != 1:
            continue
        track, point = attached[0]
        source_id = _source_item_id(track)
        if source_id in emitted_tracks:
            continue
        segment_length = distance(track.start, track.end)
        if segment_length < config.dangling_stub_min_length_mm:
            continue
        if anchor_index.has_same_net_anchor(track, point, config.endpoint_snap_mm * 2.0):
            continue
        emitted_tracks.add(source_id)
        severity_score = _clamp(segment_length / max(config.trace_length_warning_mm / 2.0, 1.0))
        findings.append(
            Finding(
                finding_id=_finding_id("stub", source_id, key),
                category="other",
                title="Possible dangling trace stub",
                description=(
                    "A routed endpoint has graph degree one and does not coincide with a detected pad or via. "
                    "Unused stubs can resonate and add capacitive loading."
                ),
                severity=_severity(0.25 + 0.55 * severity_score),
                confidence=0.84,
                score_penalty=2.0 + 7.0 * severity_score,
                location=point,
                item_ids=(source_id,),
                metrics={
                    "net": track.net,
                    "layer": track.layer,
                    "segment_length_mm": round(segment_length, 4),
                },
                recommendation="Remove the stub, terminate it intentionally, or document it as a required test point.",
                rule_id="noise.stub",
            )
        )
    return findings


def _detect_parallel_coupling(snapshot: BoardSnapshot, config: NoiseConfig) -> list[Finding]:
    """Detect close, long, parallel traces on different nets."""

    findings: list[Finding] = []
    for first, second in _nearby_track_pairs(snapshot.tracks, config.parallel_overlap_warning_mm):
        first_id = _source_item_id(first)
        second_id = _source_item_id(second)
        if first_id == second_id or first.layer != second.layer or first.net == second.net:
            continue
        angle_difference = acute_direction_difference(
            direction_angle(first.start, first.end),
            direction_angle(second.start, second.end),
        )
        if angle_difference > config.parallel_angle_tolerance_deg:
            continue
        overlap = parallel_overlap_length(first.start, first.end, second.start, second.end)
        if overlap < config.parallel_overlap_warning_mm:
            continue
        spacing = segment_distance(first.start, first.end, second.start, second.end)
        if spacing > config.parallel_spacing_warning_mm:
            continue

        stackup = snapshot.stackup
        effective_er = effective_permittivity_microstrip(
            (first.width + second.width) / 2.0,
            stackup.signal_to_reference_height,
            stackup.dielectric_constant,
        )
        coupling = crosstalk_proxy(
            overlap,
            spacing,
            stackup.signal_to_reference_height,
            config.signal_rise_time_ns,
            effective_er,
        )
        severity_score = _clamp(
            0.45 * overlap / max(config.parallel_overlap_warning_mm * 3.0, 0.1)
            + 0.35
            * (config.parallel_spacing_warning_mm - spacing)
            / max(config.parallel_spacing_warning_mm, 1.0e-9)
            + 0.20 * coupling
        )
        location = Point(
            (first.start.x + first.end.x + second.start.x + second.end.x) / 4.0,
            (first.start.y + first.end.y + second.start.y + second.end.y) / 4.0,
        )
        pair = tuple(sorted((first_id, second_id)))
        findings.append(
            Finding(
                finding_id=_finding_id("parallel", *pair),
                category="parallel",
                title="Close parallel routing on different nets",
                description=(
                    "Two traces share a long parallel run at small spacing. The geometry increases capacitive "
                    "and inductive coupling, especially for fast edges."
                ),
                severity=_severity(0.25 + 0.70 * severity_score),
                confidence=0.90,
                score_penalty=3.0 + 12.0 * severity_score,
                location=location,
                item_ids=pair,
                metrics={
                    "first_net": first.net,
                    "second_net": second.net,
                    "layer": first.layer,
                    "overlap_mm": round(overlap, 4),
                    "spacing_mm": round(spacing, 4),
                    "angle_difference_deg": round(angle_difference, 3),
                    "normalized_crosstalk_proxy": round(coupling, 4),
                },
                recommendation=(
                    "Increase spacing, shorten the parallel section, route on an orthogonal adjacent layer, "
                    "or add a continuous reference plane between routing layers."
                ),
                rule_id="noise.parallel",
            )
        )
    return findings


def _detect_corners(
    snapshot: BoardSnapshot,
    config: NoiseConfig,
    anchor_index: _AnchorIndex,
) -> list[Finding]:
    """Detect genuinely acute routed corners while suppressing pad and arc artifacts."""

    nodes: dict[tuple[str, str, int, int], list[tuple[TrackSegment, Point, Point]]] = defaultdict(list)
    for track in snapshot.tracks:
        if distance(track.start, track.end) + 1.0e-9 < config.corner_min_segment_length_mm:
            continue
        nodes[_endpoint_key(track.net, track.layer, track.start, config.endpoint_snap_mm)].append(
            (track, track.start, track.end)
        )
        nodes[_endpoint_key(track.net, track.layer, track.end, config.endpoint_snap_mm)].append(
            (track, track.end, track.start)
        )

    findings: list[Finding] = []
    emitted: set[tuple[str, str, int, int]] = set()
    for attached in nodes.values():
        if len(attached) < 2:
            continue
        vertex = attached[0][1]
        if config.corner_skip_complex_junctions and len(attached) > 2:
            continue
        if config.corner_pad_exclusion and anchor_index.has_same_net_anchor(
            attached[0][0],
            vertex,
            config.corner_pad_clearance_mm,
        ):
            continue
        for index, first in enumerate(attached):
            for second in attached[index + 1 :]:
                first_track, _, first_other = first
                second_track, _, second_other = second
                first_source = _source_item_id(first_track)
                second_source = _source_item_id(second_track)
                if first_source == second_source:
                    # KiCad arcs are represented by two chords in the snapshot.
                    continue
                quantized_vertex = (
                    round(vertex.x / config.endpoint_snap_mm),
                    round(vertex.y / config.endpoint_snap_mm),
                )
                first_id, second_id = sorted((first_source, second_source))
                pair_key = (first_id, second_id, quantized_vertex[0], quantized_vertex[1])
                if pair_key in emitted:
                    continue
                emitted.add(pair_key)
                included_angle = angle_between(
                    subtract(first_other, vertex),
                    subtract(second_other, vertex),
                )
                if included_angle + 1.0e-6 >= config.acute_corner_warning_deg:
                    continue
                sharpness = _clamp(
                    (config.acute_corner_warning_deg - included_angle)
                    / max(config.acute_corner_warning_deg, 1.0)
                )
                severity_score = _clamp(0.10 + 0.90 * sharpness)
                findings.append(
                    Finding(
                        finding_id=_finding_id("corner", *pair_key),
                        category="corner",
                        title="Sharp trace corner",
                        description=(
                            "The included routing angle is below the configured threshold after excluding pad, "
                            "via, complex-junction, and arc-approximation artifacts. Sharp corners are usually a "
                            "lower-order issue than return-path discontinuities, but they can create local "
                            "impedance changes and manufacturing traps."
                        ),
                        severity=_severity(0.12 + 0.58 * severity_score),
                        confidence=0.93,
                        score_penalty=0.75 + 3.25 * severity_score,
                        location=vertex,
                        item_ids=tuple(sorted((first_source, second_source))),
                        metrics={
                            "net": first_track.net,
                            "layer": first_track.layer,
                            "included_angle_deg": round(included_angle, 3),
                            "corner_threshold_deg": config.acute_corner_warning_deg,
                            "pad_exclusion_applied": config.corner_pad_exclusion,
                        },
                        recommendation="Use two 45-degree bends or a smooth arc where routing and clearance permit.",
                        rule_id="noise.corner",
                    )
                )
    return findings


def _detect_long_nets(
    snapshot: BoardSnapshot,
    config: NoiseConfig,
    ground_pattern: re.Pattern[str],
    anchor_index: _AnchorIndex,
) -> list[Finding]:
    """Detect long signal routes using connected-component graph diameter.

    Summing every branch of a net can make a short multi-drop bus look longer
    than any actual source-to-load route.  The graph-diameter estimate avoids
    that false positive while still retaining total copper length as evidence.
    """

    ignore_pattern = re.compile(config.long_net_ignore_regex, re.IGNORECASE)
    stackup = snapshot.stackup
    signal_tracks = tuple(
        track
        for track in snapshot.tracks
        if track.net and not ground_pattern.search(track.net) and not ignore_pattern.search(track.net)
    )
    tracks_by_net: dict[str, list[TrackSegment]] = defaultdict(list)
    for track in signal_tracks:
        tracks_by_net[track.net].append(track)

    findings: list[Finding] = []
    for net, tracks in tracks_by_net.items():
        components = _route_components(
            tracks,
            config.endpoint_snap_mm,
            anchor_index,
            config.long_net_diameter_scan_limit,
        )
        for component_index, component in enumerate(components):
            path_length = component.path_length_mm
            effective_er = effective_permittivity_microstrip(
                _median(track.width for track in component.tracks) or 0.20,
                stackup.signal_to_reference_height,
                stackup.dielectric_constant,
            )
            electrical_threshold = critical_length_mm(
                config.signal_rise_time_ns,
                effective_er,
                config.critical_length_fraction,
            )
            geometric_excess = path_length > config.trace_length_warning_mm
            electrical_excess = path_length > electrical_threshold
            severe_threshold = (
                min(config.trace_length_warning_mm, electrical_threshold) * config.long_net_severe_multiplier
            )
            if config.long_net_trigger_mode == "both":
                triggered = geometric_excess and electrical_excess
            elif config.long_net_trigger_mode == "either":
                triggered = geometric_excess or electrical_excess
            else:
                triggered = (geometric_excess and electrical_excess) or path_length > severe_threshold
            if not triggered:
                continue

            relevant_threshold = max(
                1.0,
                min(config.trace_length_warning_mm, electrical_threshold),
            )
            excess_ratio = path_length / relevant_threshold
            severity_score = _clamp((excess_ratio - 1.0) / 3.0 + 0.20)
            branch_ratio = max(0.0, component.total_length_mm / max(path_length, 1.0e-9) - 1.0)
            tracks_by_id = {track.item_id: track for track in component.tracks}
            path_sources = tuple(
                dict.fromkeys(
                    _source_item_id(tracks_by_id[item_id])
                    for item_id in component.path_track_ids
                    if item_id in tracks_by_id
                )
            )
            source_ids = path_sources or tuple(
                dict.fromkeys(_source_item_id(track) for track in component.tracks)
            )
            location = Point(
                (component.path_start.x + component.path_end.x) / 2.0,
                (component.path_start.y + component.path_end.y) / 2.0,
            )
            findings.append(
                Finding(
                    finding_id=_finding_id("length", net, component_index, round(path_length, 3)),
                    category="length",
                    title="Electrically long routed net",
                    description=(
                        "The estimated longest point-to-point route in one connected net component exceeds the "
                        "configured geometric and/or rise-time-based distributed-line threshold. Branch copper "
                        "is not blindly added to the electrical path estimate."
                    ),
                    severity=_severity(0.20 + 0.65 * severity_score),
                    confidence=0.82,
                    score_penalty=1.75 + 8.25 * severity_score,
                    location=location,
                    item_ids=source_ids,
                    metrics={
                        "net": net,
                        "component_index": component_index,
                        "diameter_method": component.diameter_method,
                        "diameter_source_count": component.diameter_source_count,
                        "total_length_mm": round(component.total_length_mm, 4),
                        "estimated_path_length_mm": round(path_length, 4),
                        "critical_length_mm": round(electrical_threshold, 4),
                        "configured_length_warning_mm": config.trace_length_warning_mm,
                        "assumed_rise_time_ns": config.signal_rise_time_ns,
                        "branch_ratio": round(branch_ratio, 4),
                    },
                    recommendation=(
                        "Review source termination, receiver loading, reference continuity, and timing. Shorten "
                        "the route where practical or enter the actual driver rise time for a more relevant threshold."
                    ),
                    rule_id="noise.long_net",
                )
            )
    return findings


def _route_components(
    tracks: Sequence[TrackSegment],
    snap: float,
    anchor_index: _AnchorIndex,
    scan_limit: int,
) -> tuple[_RouteComponent, ...]:
    """Build connected route components and estimate their weighted diameter."""

    adjacency: dict[NodeKey, list[_GraphEdge]] = defaultdict(list)
    node_points: dict[NodeKey, Point] = {}
    for track in tracks:
        first = _route_node_key(anchor_index, track, track.start, snap)
        second = _route_node_key(anchor_index, track, track.end, snap)
        node_points.setdefault(first, track.start)
        node_points.setdefault(second, track.end)
        length_mm = distance(track.start, track.end)
        adjacency[first].append(_GraphEdge(second, length_mm, track))
        adjacency[second].append(_GraphEdge(first, length_mm, track))

    unvisited = set(adjacency)
    result: list[_RouteComponent] = []
    while unvisited:
        root = min(unvisited)
        stack = [root]
        nodes: list[NodeKey] = []
        track_map: dict[str, TrackSegment] = {}
        while stack:
            node = stack.pop()
            if node not in unvisited:
                continue
            unvisited.remove(node)
            nodes.append(node)
            for edge in adjacency[node]:
                track_map[edge.track.item_id] = edge.track
                if edge.other in unvisited:
                    stack.append(edge.other)
        if not track_map:
            continue
        ordered_nodes = tuple(sorted(nodes))
        first_far, second_far, path_length, predecessor, method, source_count = _route_diameter(
            ordered_nodes,
            adjacency,
            scan_limit,
        )
        path_ids = _reconstruct_path_track_ids(first_far, second_far, predecessor)
        ordered_tracks = tuple(track_map[key] for key in sorted(track_map))
        result.append(
            _RouteComponent(
                nodes=ordered_nodes,
                tracks=ordered_tracks,
                total_length_mm=sum(distance(item.start, item.end) for item in ordered_tracks),
                path_length_mm=path_length,
                path_track_ids=path_ids,
                path_start=node_points.get(first_far, Point(0.0, 0.0)),
                path_end=node_points.get(second_far, Point(0.0, 0.0)),
                diameter_method=method,
                diameter_source_count=source_count,
            )
        )
    return tuple(result)


def _route_diameter(
    nodes: Sequence[NodeKey],
    adjacency: Mapping[NodeKey, Sequence[_GraphEdge]],
    scan_limit: int,
) -> tuple[NodeKey, NodeKey, float, dict[NodeKey, tuple[NodeKey, str]], str, int]:
    """Return a deterministic, low-miss estimate of component diameter.

    Small components are solved exactly by scanning every graph node.  Large
    tree-like routes scan all terminal and junction nodes when the configured
    budget permits.  Dense cyclic components use a deterministic spatial
    sample, bounding runtime while improving on a single arbitrary double
    sweep.
    """

    ordered = tuple(sorted(nodes))
    allowed = set(ordered)
    limit = max(2, scan_limit)
    if len(ordered) <= limit:
        sources = ordered
        method = "exact_all_nodes"
    else:
        structural = tuple(node for node in ordered if len(adjacency.get(node, ())) != 2)
        pool = structural or ordered
        if len(pool) <= limit:
            sources = pool
            method = "terminal_junction_scan" if structural else "all_nodes_scan"
        else:
            sources = _evenly_sample_nodes(pool, limit)
            method = "sampled_terminal_junction_scan" if structural else "sampled_cycle_scan"

    best_start = sources[0]
    best_end = sources[0]
    best_distance = -1.0
    best_predecessor: dict[NodeKey, tuple[NodeKey, str]] = {}
    for source in sources:
        farthest, path_length, predecessor = _dijkstra_farthest(source, adjacency, allowed)
        candidate = (path_length, source, farthest)
        current = (best_distance, best_start, best_end)
        if candidate > current:
            best_start = source
            best_end = farthest
            best_distance = path_length
            best_predecessor = predecessor
    return best_start, best_end, best_distance, best_predecessor, method, len(sources)


def _evenly_sample_nodes(nodes: Sequence[NodeKey], limit: int) -> tuple[NodeKey, ...]:
    """Return deterministic samples that include both ends of a sorted pool."""

    if len(nodes) <= limit:
        return tuple(nodes)
    indices = {round(index * (len(nodes) - 1) / (limit - 1)) for index in range(limit)}
    return tuple(nodes[index] for index in sorted(indices))


def _dijkstra_farthest(
    start: NodeKey,
    adjacency: Mapping[NodeKey, Sequence[_GraphEdge]],
    allowed: set[NodeKey],
) -> tuple[NodeKey, float, dict[NodeKey, tuple[NodeKey, str]]]:
    """Return the farthest node, distance, and predecessor map."""

    distances: dict[NodeKey, float] = {start: 0.0}
    predecessor: dict[NodeKey, tuple[NodeKey, str]] = {}
    heap: list[tuple[float, NodeKey]] = [(0.0, start)]
    while heap:
        current_distance, node = heapq.heappop(heap)
        if current_distance > distances.get(node, math.inf) + 1.0e-12:
            continue
        for edge in adjacency.get(node, ()):
            if edge.other not in allowed:
                continue
            candidate = current_distance + edge.length_mm
            if candidate + 1.0e-12 < distances.get(edge.other, math.inf):
                distances[edge.other] = candidate
                predecessor[edge.other] = (node, edge.track.item_id)
                heapq.heappush(heap, (candidate, edge.other))
    farthest = max(distances, key=lambda node: (distances[node], node))
    return farthest, distances[farthest], predecessor


def _reconstruct_path_track_ids(
    start: NodeKey,
    end: NodeKey,
    predecessor: Mapping[NodeKey, tuple[NodeKey, str]],
) -> tuple[str, ...]:
    """Return route item identifiers along a shortest path."""

    node = end
    track_ids: list[str] = []
    seen: set[NodeKey] = set()
    while node != start and node in predecessor and node not in seen:
        seen.add(node)
        node, track_id = predecessor[node]
        track_ids.append(track_id)
    track_ids.reverse()
    return tuple(track_ids)


def _route_node_key(
    anchor_index: _AnchorIndex,
    track: TrackSegment,
    point: Point,
    snap: float,
) -> NodeKey:
    """Return a route graph key with layer collapse only at conductive anchors."""

    qx = round(point.x / snap)
    qy = round(point.y / snap)
    if anchor_index.collapses_route_layer(track, point, snap * 2.0):
        return ("*", qx, qy)
    return (track.layer, qx, qy)


def _copper_layer_count(snapshot: BoardSnapshot) -> int:
    """Return the detected copper-layer count with a geometry fallback."""

    stackup = snapshot.metadata.get("stackup", {})
    if isinstance(stackup, Mapping):
        raw = stackup.get("copper_layer_count")
        try:
            count = int(raw) if raw is not None else 0
        except (TypeError, ValueError):
            count = 0
        if count > 0:
            return count
    layers = {layer for track in snapshot.tracks for layer in (track.layer,) if layer.endswith(".Cu")}
    layers.update(layer for pad in snapshot.pads for layer in pad.layers if layer.endswith(".Cu"))
    layers.update(layer for zone in snapshot.zones for layer in zone.layers if layer.endswith(".Cu"))
    for via in snapshot.vias:
        if via.start_layer.endswith(".Cu"):
            layers.add(via.start_layer)
        if via.end_layer.endswith(".Cu"):
            layers.add(via.end_layer)
    return max(1, len(layers))


def _reference_layer_for_track(track: TrackSegment, layer_count: int) -> str:
    """Return a conservative reference-layer candidate for an outer trace."""

    if layer_count <= 2:
        if track.layer == "F.Cu":
            return "B.Cu"
        if track.layer == "B.Cu":
            return "F.Cu"
    return ""


def _ground_polygons_by_layer(
    snapshot: BoardSnapshot,
    ground_pattern: re.Pattern[str],
) -> dict[str, tuple[Polygon, ...]]:
    """Collect filled ground polygons by copper layer."""

    result: dict[str, list[Polygon]] = defaultdict(list)
    for zone in snapshot.zones:
        if zone.is_rule_area or not ground_pattern.search(zone.net or ""):
            continue
        for layer, polygons in zone.filled.items():
            result[layer].extend(polygons)
    return {layer: tuple(polygons) for layer, polygons in result.items()}


def _point_has_ground_reference(
    point: Point,
    layer: str,
    polygons_by_layer: Mapping[str, Sequence[Polygon]],
    ground_tracks_by_layer: Mapping[str, Sequence[TrackSegment]],
) -> bool:
    """Return whether ground copper exists below one sampled signal point."""

    if any(point_in_polygon(point, polygon) for polygon in polygons_by_layer.get(layer, ())):
        return True
    return any(
        point_segment_distance(point, track.start, track.end) <= track.width / 2.0 + 1.0e-6
        for track in ground_tracks_by_layer.get(layer, ())
    )


def _detect_reference_plane_gaps(
    snapshot: BoardSnapshot,
    config: NoiseConfig,
    ground_pattern: re.Pattern[str],
    layer_count: int,
) -> list[Finding]:
    """Detect signal segments traversing a sustained gap in a known GND reference.

    The check is intentionally limited to two-layer outer-layer routing where
    the opposite copper layer is unambiguous.  On multilayer boards, stackup
    layer-function data is required before assigning a reference plane.
    """

    if layer_count > 2:
        return []
    ignore_pattern = re.compile(config.reference_gap_ignore_regex, re.IGNORECASE)
    polygons_by_layer = _ground_polygons_by_layer(snapshot, ground_pattern)
    ground_tracks: dict[str, list[TrackSegment]] = defaultdict(list)
    for track in snapshot.tracks:
        if ground_pattern.search(track.net or ""):
            ground_tracks[track.layer].append(track)
    ground_tracks_by_layer = {layer: tuple(items) for layer, items in ground_tracks.items()}
    step = max(0.10, config.reference_plane_sample_step_mm)
    findings: list[Finding] = []
    missing_reference_candidates: dict[tuple[str, str, str], TrackSegment] = {}
    for track in snapshot.tracks:
        if not track.net or ground_pattern.search(track.net) or ignore_pattern.search(track.net):
            continue
        reference_layer = _reference_layer_for_track(track, layer_count)
        if not reference_layer:
            continue
        length_mm = distance(track.start, track.end)
        if length_mm < max(config.reference_gap_min_length_mm, config.reference_gap_min_track_length_mm):
            continue
        reference_has_ground = bool(
            polygons_by_layer.get(reference_layer) or ground_tracks_by_layer.get(reference_layer)
        )
        if not reference_has_ground:
            # When the opposite layer contains no known GND copper at all,
            # emitting one finding for every segment overwhelms the useful
            # geometry-specific results. Keep only the longest representative
            # segment for each signal net and layer pair.
            key = (track.net, track.layer, reference_layer)
            previous = missing_reference_candidates.get(key)
            if previous is None or distance(previous.start, previous.end) < length_mm:
                missing_reference_candidates[key] = track
            continue
        samples = max(2, math.ceil(length_mm / step))
        unsupported_start: int | None = None
        longest: tuple[int, int] | None = None
        for index in range(samples + 1):
            ratio = index / samples
            point = Point(
                track.start.x + (track.end.x - track.start.x) * ratio,
                track.start.y + (track.end.y - track.start.y) * ratio,
            )
            distance_from_start = ratio * length_mm
            endpoint_excluded = (
                distance_from_start < config.reference_gap_endpoint_exclusion_mm
                or length_mm - distance_from_start < config.reference_gap_endpoint_exclusion_mm
            )
            supported = endpoint_excluded or _point_has_ground_reference(
                point,
                reference_layer,
                polygons_by_layer,
                ground_tracks_by_layer,
            )
            if not supported and unsupported_start is None:
                unsupported_start = index
            if supported and unsupported_start is not None:
                candidate = (unsupported_start, index - 1)
                if longest is None or candidate[1] - candidate[0] > longest[1] - longest[0]:
                    longest = candidate
                unsupported_start = None
        if unsupported_start is not None:
            candidate = (unsupported_start, samples)
            if longest is None or candidate[1] - candidate[0] > longest[1] - longest[0]:
                longest = candidate
        if longest is None:
            continue
        start_ratio = longest[0] / samples
        end_ratio = longest[1] / samples
        gap_length = max(0.0, (end_ratio - start_ratio) * length_mm)
        if gap_length + step * 0.51 < config.reference_gap_min_length_mm:
            continue
        evaluable_length = max(
            step,
            length_mm - 2.0 * config.reference_gap_endpoint_exclusion_mm,
        )
        unsupported_fraction = min(1.0, gap_length / evaluable_length)
        if unsupported_fraction < config.reference_gap_min_fraction:
            continue
        midpoint_ratio = (start_ratio + end_ratio) / 2.0
        location = Point(
            track.start.x + (track.end.x - track.start.x) * midpoint_ratio,
            track.start.y + (track.end.y - track.start.y) * midpoint_ratio,
        )
        severity_score = _clamp(gap_length / max(config.reference_gap_min_length_mm * 5.0, 1.0e-9))
        source_id = _source_item_id(track)
        findings.append(
            Finding(
                finding_id=_finding_id(
                    "reference-gap", source_id, round(start_ratio, 3), round(end_ratio, 3)
                ),
                category="return_path",
                title="Signal route crosses a GND reference gap",
                description=(
                    "A sustained part of this two-layer signal segment has no detected GND fill or explicit "
                    "GND conductor on the opposite copper layer. The return current may detour around a void, "
                    "slot, keepout, or plane edge and increase loop inductance."
                ),
                severity=_severity(0.28 + 0.58 * severity_score),
                confidence=0.88,
                score_penalty=3.0 + 10.0 * severity_score,
                location=location,
                item_ids=(source_id,),
                metrics={
                    "net": track.net,
                    "signal_layer": track.layer,
                    "reference_layer": reference_layer,
                    "reference_copper_present": True,
                    "unsupported_length_mm": round(gap_length, 4),
                    "unsupported_fraction": round(unsupported_fraction, 4),
                    "endpoint_exclusion_mm": config.reference_gap_endpoint_exclusion_mm,
                    "sample_step_mm": step,
                },
                recommendation=(
                    "Restore continuous GND copper below the route, move the signal away from the gap, or add "
                    "a nearby low-inductance return connection where the reference must change."
                ),
                rule_id="noise.reference_gap",
            )
        )

    for (net, signal_layer, reference_layer), track in sorted(missing_reference_candidates.items()):
        length_mm = distance(track.start, track.end)
        source_id = _source_item_id(track)
        severity_score = _clamp(length_mm / max(config.reference_gap_min_length_mm * 8.0, 1.0e-9))
        findings.append(
            Finding(
                finding_id=_finding_id("reference-absent", net, signal_layer, reference_layer),
                category="return_path",
                title="Signal net has no detected opposite-layer GND reference",
                description=(
                    "No filled GND copper or explicit GND conductor was detected on the opposite outer "
                    "layer for this two-layer signal net. One representative segment is reported instead "
                    "of repeating the same board-level condition for every segment."
                ),
                severity=_severity(0.30 + 0.52 * severity_score),
                confidence=0.82,
                score_penalty=3.0 + 8.0 * severity_score,
                location=Point(
                    (track.start.x + track.end.x) / 2.0,
                    (track.start.y + track.end.y) / 2.0,
                ),
                item_ids=(source_id,),
                metrics={
                    "net": net,
                    "signal_layer": signal_layer,
                    "reference_layer": reference_layer,
                    "reference_copper_present": False,
                    "unsupported_length_mm": round(length_mm, 4),
                    "unsupported_fraction": 1.0,
                    "endpoint_exclusion_mm": config.reference_gap_endpoint_exclusion_mm,
                    "sample_step_mm": step,
                },
                recommendation=(
                    "Provide a continuous GND reference on the opposite layer, shorten the route, or "
                    "verify the intended return conductor and loop geometry explicitly."
                ),
                rule_id="noise.reference_gap",
            )
        )
    return findings


def _pad_touches_ground_fill(
    pad: Pad,
    polygons_by_layer: Mapping[str, Sequence[Polygon]],
) -> bool:
    """Return whether a ground pad center or corners touch filled ground copper."""

    probes = (
        pad.position,
        Point(pad.bounds.min_x, pad.bounds.min_y),
        Point(pad.bounds.max_x, pad.bounds.min_y),
        Point(pad.bounds.max_x, pad.bounds.max_y),
        Point(pad.bounds.min_x, pad.bounds.max_y),
    )
    raw_layers = {str(layer) for layer in pad.layers}
    layers = (
        tuple(polygons_by_layer)
        if not raw_layers or raw_layers & {"*.Cu", "*.Copper", "All.Cu"}
        else tuple(layer for layer in raw_layers if layer.endswith(".Cu"))
    )
    for layer in layers:
        if any(
            point_in_polygon(probe, polygon)
            for probe in probes
            for polygon in polygons_by_layer.get(layer, ())
        ):
            return True
    return False


def _shortest_pad_exit_route(
    snapshot: BoardSnapshot,
    pad: Pad,
    anchor_index: _AnchorIndex,
    polygons_by_layer: Mapping[str, Sequence[Polygon]] | None = None,
) -> tuple[float, tuple[str, ...]]:
    """Return shortest explicit route from a pad to another pad or target plane."""

    tracks = tuple(track for track in snapshot.tracks if track.net == pad.net)
    if not tracks:
        return math.inf, ()
    adjacency: dict[NodeKey, list[_GraphEdge]] = defaultdict(list)
    seed_nodes: set[NodeKey] = set()
    target_nodes: set[NodeKey] = set()
    external_pads = tuple(
        item for item in snapshot.pads if item.net == pad.net and item.footprint_id != pad.footprint_id
    )
    seed_box = pad.bounds.inflate(0.08)
    target_boxes = tuple(target.bounds.inflate(0.08) for target in external_pads)
    for track in tracks:
        first = _route_node_key(anchor_index, track, track.start, 0.05)
        second = _route_node_key(anchor_index, track, track.end, 0.05)
        edge_length = distance(track.start, track.end)
        adjacency[first].append(_GraphEdge(second, edge_length, track))
        adjacency[second].append(_GraphEdge(first, edge_length, track))
        for node, point in ((first, track.start), (second, track.end)):
            if seed_box.min_x <= point.x <= seed_box.max_x and seed_box.min_y <= point.y <= seed_box.max_y:
                seed_nodes.add(node)
            if any(
                box.min_x <= point.x <= box.max_x and box.min_y <= point.y <= box.max_y
                for box in target_boxes
            ):
                target_nodes.add(node)
            if polygons_by_layer and any(
                point_in_polygon(point, polygon) for polygon in polygons_by_layer.get(track.layer, ())
            ):
                target_nodes.add(node)
    target_nodes.difference_update(seed_nodes)
    if not seed_nodes or not target_nodes:
        return math.inf, ()
    queue: list[tuple[float, NodeKey]] = [(0.0, node) for node in sorted(seed_nodes)]
    heapq.heapify(queue)
    distances: dict[NodeKey, float] = {node: 0.0 for node in seed_nodes}
    predecessor: dict[NodeKey, tuple[NodeKey, str]] = {}
    reached: NodeKey | None = None
    while queue:
        current_distance, node = heapq.heappop(queue)
        if current_distance > distances.get(node, math.inf) + 1.0e-12:
            continue
        if node in target_nodes:
            reached = node
            break
        for edge in adjacency.get(node, ()):
            candidate = current_distance + edge.length_mm
            if candidate + 1.0e-12 >= distances.get(edge.other, math.inf):
                continue
            distances[edge.other] = candidate
            predecessor[edge.other] = (node, _source_item_id(edge.track))
            heapq.heappush(queue, (candidate, edge.other))
    if reached is None:
        return math.inf, ()
    track_ids: list[str] = []
    node = reached
    while node not in seed_nodes and node in predecessor:
        node, track_id = predecessor[node]
        track_ids.append(track_id)
    track_ids.reverse()
    return distances[reached], tuple(dict.fromkeys(track_ids))


def _detect_ground_return_detours(
    snapshot: BoardSnapshot,
    config: NoiseConfig,
    ground_pattern: re.Pattern[str],
    anchor_index: _AnchorIndex,
) -> list[Finding]:
    """Detect a component whose explicit GND path is far longer than its active path."""

    polygons_by_layer = _ground_polygons_by_layer(snapshot, ground_pattern)
    findings: list[Finding] = []
    pads_by_footprint: dict[str, list[Pad]] = defaultdict(list)
    for pad in snapshot.pads:
        pads_by_footprint[pad.footprint_id].append(pad)
    for footprint_id, pads in pads_by_footprint.items():
        ground_pads = [pad for pad in pads if pad.net and ground_pattern.search(pad.net)]
        active_pads = [pad for pad in pads if pad.net and not ground_pattern.search(pad.net)]
        if not ground_pads or not active_pads:
            continue
        active_candidates = [_shortest_pad_exit_route(snapshot, pad, anchor_index)[0] for pad in active_pads]
        active_length = min(
            (
                value
                for value in active_candidates
                if math.isfinite(value) and value >= config.ground_detour_min_active_length_mm
            ),
            default=math.inf,
        )
        if not math.isfinite(active_length):
            continue
        for ground_pad in ground_pads:
            if _pad_touches_ground_fill(ground_pad, polygons_by_layer):
                continue
            ground_length, route_ids = _shortest_pad_exit_route(
                snapshot,
                ground_pad,
                anchor_index,
                polygons_by_layer,
            )
            if not math.isfinite(ground_length) or ground_length < config.ground_detour_min_length_mm:
                continue
            ratio = ground_length / max(active_length, config.ground_detour_min_active_length_mm)
            excess = ground_length - active_length
            if ratio < config.ground_detour_warning_ratio or excess < config.ground_detour_min_excess_mm:
                continue
            severity_score = _clamp((ratio - config.ground_detour_warning_ratio) / 6.0 + excess / 60.0)
            findings.append(
                Finding(
                    finding_id=_finding_id("ground-detour", ground_pad.item_id, round(ratio, 3)),
                    category="return_path",
                    title="Component GND route is abnormally indirect",
                    description=(
                        "This component's shortest detected explicit GND route is substantially longer than the "
                        "shortest routed non-GND connection from the same footprint, and the GND pad does not "
                        "touch a filled ground plane. This can enlarge local current loops and create ground bounce."
                    ),
                    severity=_severity(0.25 + 0.60 * severity_score),
                    confidence=0.78,
                    score_penalty=2.5 + 9.0 * severity_score,
                    location=ground_pad.position,
                    item_ids=tuple(dict.fromkeys((ground_pad.item_id, *route_ids))),
                    metrics={
                        "footprint_id": footprint_id,
                        "ground_net": ground_pad.net,
                        "ground_route_length_mm": round(ground_length, 4),
                        "shortest_active_route_mm": round(active_length, 4),
                        "ground_to_active_ratio": round(ratio, 3),
                        "excess_ground_length_mm": round(excess, 4),
                        "minimum_ratio": config.ground_detour_warning_ratio,
                    },
                    recommendation=(
                        "Connect the GND pad directly to the local plane with short, wide copper and a nearby via "
                        "where appropriate. Verify the actual current loop and avoid routing the return around slots."
                    ),
                    rule_id="noise.ground_detour",
                )
            )
    return findings


def _detect_ground_bottlenecks(
    snapshot: BoardSnapshot,
    config: NoiseConfig,
    ground_pattern: re.Pattern[str],
) -> list[Finding]:
    """Detect narrow plane necks that separate independently anchored GND regions."""

    findings: list[Finding] = []
    for zone in snapshot.zones:
        if zone.is_rule_area or not ground_pattern.search(zone.net or ""):
            continue
        for layer, polygons in zone.filled.items():
            layer_pads = tuple(
                pad
                for pad in snapshot.pads
                if pad.net == zone.net and (not pad.layers or layer in pad.layers)
            )
            if len(layer_pads) < config.ground_bottleneck_min_anchor_count:
                continue
            for polygon_index, polygon in enumerate(polygons):
                anchors = tuple(pad for pad in layer_pads if point_in_polygon(pad.position, polygon))
                if len(anchors) < config.ground_bottleneck_min_anchor_count:
                    continue
                try:
                    features = detect_narrow_features(
                        polygon,
                        raster_step_mm=max(
                            0.10,
                            min(
                                config.reference_plane_sample_step_mm,
                                config.ground_bottleneck_width_mm / 3.0,
                            ),
                        ),
                        neck_width_mm=config.ground_bottleneck_width_mm,
                        max_cells=500_000,
                    )
                except ValueError:
                    # A very large plane should not abort every other noise
                    # check. The report caveats still identify raster limits.
                    continue
                for feature_index, feature in enumerate(features):
                    if feature.isolated:
                        continue
                    feature_polygon = cells_to_outline(feature)
                    inside = tuple(pad for pad in anchors if point_in_polygon(pad.position, feature_polygon))
                    outside = tuple(pad for pad in anchors if pad not in inside)
                    if not inside or not outside:
                        continue
                    width = max(feature.step_mm, feature.width_mm)
                    if width > config.ground_bottleneck_width_mm * 1.15:
                        continue
                    anchor_span = max(
                        distance(first.position, second.position) for first in inside for second in outside
                    )
                    severity_score = _clamp(
                        (config.ground_bottleneck_width_mm - width)
                        / max(config.ground_bottleneck_width_mm, 1.0e-9)
                        + anchor_span / 50.0
                    )
                    findings.append(
                        Finding(
                            finding_id=_finding_id(
                                "ground-bottleneck", zone.item_id, layer, polygon_index, feature_index
                            ),
                            category="return_path",
                            title="Ground plane bottleneck may develop local voltage gradient",
                            description=(
                                "A narrow filled-copper neck separates GND regions that each contain footprint GND "
                                "pads. Shared return current through this constriction can increase local impedance "
                                "and produce a potential difference between the two regions."
                            ),
                            severity=_severity(0.26 + 0.58 * severity_score),
                            confidence=0.80,
                            score_penalty=3.0 + 9.0 * severity_score,
                            location=feature.gate,
                            item_ids=tuple(
                                dict.fromkeys(
                                    (
                                        zone.item_id,
                                        *(pad.item_id for pad in inside),
                                        *(pad.item_id for pad in outside),
                                    )
                                )
                            ),
                            metrics={
                                "net": zone.net,
                                "layer": layer,
                                "estimated_neck_width_mm": round(width, 4),
                                "anchors_on_appendage_side": len(inside),
                                "anchors_on_main_side": len(outside),
                                "anchor_span_mm": round(anchor_span, 4),
                                "feature_polygon": feature_polygon.to_dict(),
                            },
                            recommendation=(
                                "Widen the GND connection, remove the slot or keepout causing the neck, or add "
                                "parallel low-inductance return paths and stitching vias without creating a new stub."
                            ),
                            rule_id="noise.ground_bottleneck",
                        )
                    )
    return findings


def _detect_return_via_gaps(
    snapshot: BoardSnapshot,
    config: NoiseConfig,
    ground_pattern: re.Pattern[str],
) -> list[Finding]:
    """Detect signal layer transitions without a nearby ground stitching via."""

    ground_vias = tuple(via for via in snapshot.vias if ground_pattern.search(via.net or ""))
    findings: list[Finding] = []
    for via in snapshot.vias:
        if not via.net or ground_pattern.search(via.net):
            continue
        nearest = min((distance(via.position, ground.position) for ground in ground_vias), default=math.inf)
        if nearest <= config.return_via_radius_mm:
            continue
        severity_score = 1.0 if math.isinf(nearest) else _clamp(nearest / (config.return_via_radius_mm * 4.0))
        findings.append(
            Finding(
                finding_id=_finding_id("return-via", via.item_id),
                category="return_path",
                title="Layer transition lacks a nearby GND return via",
                description=(
                    "A signal via changes layers without a detected ground stitching via inside the configured "
                    "radius. The return current may take a longer path and enlarge the loop area."
                ),
                severity=_severity(0.35 + 0.60 * severity_score),
                confidence=0.86,
                score_penalty=4.0 + 11.0 * severity_score,
                location=via.position,
                item_ids=(via.item_id,),
                metrics={
                    "net": via.net,
                    "nearest_ground_via_mm": None if math.isinf(nearest) else round(nearest, 4),
                    "required_radius_mm": config.return_via_radius_mm,
                },
                recommendation="Add one or more GND stitching vias adjacent to the signal transition.",
                rule_id="noise.return_via",
            )
        )
    return findings


def _detect_edge_proximity(
    snapshot: BoardSnapshot,
    config: NoiseConfig,
    ground_pattern: re.Pattern[str],
) -> list[Finding]:
    """Detect non-ground copper routed too close to the board edge."""

    if not snapshot.edges:
        return []
    findings: list[Finding] = []
    for track in snapshot.tracks:
        if not track.net or ground_pattern.search(track.net):
            continue
        nearest = min(
            segment_distance(track.start, track.end, edge.start, edge.end) for edge in snapshot.edges
        )
        if nearest >= config.board_edge_signal_clearance_mm:
            continue
        severity_score = _clamp(
            (config.board_edge_signal_clearance_mm - nearest)
            / max(config.board_edge_signal_clearance_mm, 1.0e-9)
        )
        source_id = _source_item_id(track)
        findings.append(
            Finding(
                finding_id=_finding_id("edge", source_id),
                category="other",
                title="Signal trace close to board edge",
                description=(
                    "A non-ground trace is close to Edge.Cuts. Edge fields, enclosure coupling, and manufacturing "
                    "tolerances can increase risk near the perimeter."
                ),
                severity=_severity(0.20 + 0.55 * severity_score),
                confidence=0.91,
                score_penalty=1.5 + 6.0 * severity_score,
                location=track.start,
                item_ids=(source_id,),
                metrics={
                    "net": track.net,
                    "layer": track.layer,
                    "edge_distance_mm": round(nearest, 4),
                    "required_clearance_mm": config.board_edge_signal_clearance_mm,
                },
                recommendation=(
                    "Move the signal inward and preserve the perimeter for a continuous GND pour or guard structure."
                ),
                rule_id="noise.edge",
            )
        )
    return findings


def _detect_differential_mismatch(snapshot: BoardSnapshot, config: NoiseConfig) -> list[Finding]:
    """Detect differential-pair length mismatch using configurable net naming."""

    pattern = re.compile(config.differential_pair_name_regex, re.IGNORECASE)
    lengths: dict[str, float] = defaultdict(float)
    for track in snapshot.tracks:
        lengths[track.net] += distance(track.start, track.end)

    groups: dict[str, dict[str, tuple[str, float]]] = defaultdict(dict)
    for net, total_length in lengths.items():
        match = pattern.match(net)
        if not match:
            continue
        polarity = match.group("polarity").upper().replace("+", "P").replace("-", "N")
        groups[match.group("base")][polarity] = (net, total_length)

    findings: list[Finding] = []
    for base, pair in groups.items():
        if "P" not in pair or "N" not in pair:
            continue
        positive_net, positive_length = pair["P"]
        negative_net, negative_length = pair["N"]
        mismatch = abs(positive_length - negative_length)
        if mismatch <= config.differential_pair_mismatch_warning_mm:
            continue
        severity_score = _clamp(mismatch / (config.differential_pair_mismatch_warning_mm * 5.0))
        representative = next(
            (track for track in snapshot.tracks if track.net in {positive_net, negative_net}),
            None,
        )
        item_ids = tuple(
            dict.fromkeys(
                _source_item_id(track)
                for track in snapshot.tracks
                if track.net in {positive_net, negative_net}
            )
        )
        findings.append(
            Finding(
                finding_id=_finding_id("diff", base),
                category="other",
                title="Differential-pair routed-length mismatch",
                description=(
                    "Two nets matched by the differential-pair naming rule have different total routed lengths."
                ),
                severity=_severity(0.20 + 0.60 * severity_score),
                confidence=0.72,
                score_penalty=2.0 + 8.0 * severity_score,
                location=representative.start if representative else None,
                item_ids=item_ids,
                metrics={
                    "pair_base": base,
                    "positive_net": positive_net,
                    "negative_net": negative_net,
                    "positive_length_mm": round(positive_length, 4),
                    "negative_length_mm": round(negative_length, 4),
                    "mismatch_mm": round(mismatch, 4),
                },
                recommendation=(
                    "Length-match the pair while preserving pair spacing and continuous reference geometry."
                ),
                rule_id="noise.diff_mismatch",
            )
        )
    return findings


def _nearby_track_pairs(
    tracks: Iterable[TrackSegment],
    bucket_size: float,
) -> Iterator[tuple[TrackSegment, TrackSegment]]:
    """Yield each spatially nearby track pair once using a uniform grid index."""

    track_list = tuple(tracks)
    size = max(bucket_size, 2.0)
    buckets: dict[tuple[int, int], list[int]] = defaultdict(list)
    seen: set[tuple[int, int]] = set()
    for index, track in enumerate(track_list):
        min_x = min(track.start.x, track.end.x)
        max_x = max(track.start.x, track.end.x)
        min_y = min(track.start.y, track.end.y)
        max_y = max(track.start.y, track.end.y)
        x_start = math.floor(min_x / size)
        x_end = math.floor(max_x / size)
        y_start = math.floor(min_y / size)
        y_end = math.floor(max_y / size)
        candidate_indices: set[int] = set()
        for x_index in range(x_start - 1, x_end + 2):
            for y_index in range(y_start - 1, y_end + 2):
                candidate_indices.update(buckets.get((x_index, y_index), ()))
        for other_index in candidate_indices:
            pair = (other_index, index)
            if pair in seen:
                continue
            seen.add(pair)
            yield track_list[other_index], track
        for x_index in range(x_start, x_end + 1):
            for y_index in range(y_start, y_end + 1):
                buckets[(x_index, y_index)].append(index)


def _endpoint_key(net: str, layer: str, point: Point, snap: float) -> tuple[str, str, int, int]:
    """Return a stable graph key for a routed endpoint."""

    return (net, layer, round(point.x / snap), round(point.y / snap))


def _source_item_id(track: TrackSegment) -> str:
    """Return a KiCad-selectable source identifier for a snapshot segment."""

    return track.source_item_id or track.item_id.split(":", 1)[0]


def _finding_id(*parts: object) -> str:
    """Return a stable finding identifier."""

    payload = "|".join(str(part) for part in parts).encode("utf-8")
    return "EMI-" + hashlib.sha1(payload, usedforsecurity=False).hexdigest()[:12].upper()


def _severity(score: float) -> Severity:
    """Map a normalized score to a severity."""

    if score >= 0.82:
        return Severity.CRITICAL
    if score >= 0.62:
        return Severity.HIGH
    if score >= 0.38:
        return Severity.MEDIUM
    if score >= 0.18:
        return Severity.LOW
    return Severity.INFO


def _clamp(value: float) -> float:
    """Clamp a value to ``[0, 1]``."""

    return max(0.0, min(1.0, value))


def _median(values: Iterable[float]) -> float:
    """Return the median or zero for an empty iterable."""

    ordered = sorted(values)
    if not ordered:
        return 0.0
    middle = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[middle]
    return (ordered[middle - 1] + ordered[middle]) / 2.0
