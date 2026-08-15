"""Conservative automatic-remediation planning for ground antennas.

The planner deliberately distinguishes between connected narrow appendages and
truly disconnected copper.  A track laid entirely on an already connected
same-net plane does not create a lower-impedance return path, so such proposals
are rejected.  Narrow appendages therefore normally produce a shape-matched
copper-pour keepout, while a bridge or via is retained only when it establishes
new electrical connectivity.
"""

from __future__ import annotations

import hashlib
import math
import re
from collections.abc import Iterable, Sequence

from .antenna_geometry import detect_protected_ground_features
from .config import AntennaConfig, FixConfig
from .edge_optimizer import current_outline_polygon
from .geometry import (
    distance,
    pairwise_closed,
    point_in_polygon,
    point_segment_distance,
    segment_distance,
    segments_intersect,
)
from .models import (
    BoardSnapshot,
    BoundingBox,
    Finding,
    FixAction,
    FixKind,
    FixPlan,
    Point,
    Polygon,
)
from .raster import cells_to_outline


def plan_antenna_fixes(
    snapshot: BoardSnapshot,
    findings: Iterable[Finding],
    antenna_config: AntennaConfig,
    fix_config: FixConfig,
) -> FixPlan:
    """Choose the highest-utility safe fix for each antenna finding."""

    ground_pattern = re.compile(antenna_config.ground_net_regex, re.IGNORECASE)
    actions: list[FixAction] = []
    alternatives: dict[str, tuple[FixAction, ...]] = {}
    warnings: list[str] = []
    safe_keepout_cache: dict[tuple[str, str, str], frozenset[tuple[object, ...]]] = {}
    for finding in findings:
        if finding.category != "antenna":
            continue
        finding_net = str(
            finding.metrics.get("net") or _zone_net(snapshot, str(finding.metrics.get("zone_id", "")))
        )
        if not finding_net or not ground_pattern.search(finding_net):
            warnings.append(
                f"{finding.finding_id}: the source GND net could not be verified; no automatic fix was selected."
            )
            alternatives[finding.finding_id] = ()
            continue
        zone_id = str(finding.metrics.get("zone_id", ""))
        layer = str(finding.metrics.get("layer") or "F.Cu")
        cache_key = (zone_id, layer, finding_net)
        if cache_key not in safe_keepout_cache:
            safe_keepout_cache[cache_key] = _current_safe_keepout_fingerprints(
                snapshot,
                zone_id,
                finding_net,
                layer,
                antenna_config,
            )
        candidates = _candidates_for_finding(
            snapshot,
            finding,
            fix_config,
            safe_keepout_cache[cache_key],
        )
        ranked = tuple(sorted(candidates, key=lambda action: action.utility, reverse=True))
        alternatives[finding.finding_id] = ranked
        acceptable = [action for action in ranked if action.confidence >= fix_config.minimum_apply_confidence]
        if acceptable:
            actions.append(acceptable[0])
        elif ranked:
            warnings.append(
                f"{finding.finding_id}: no candidate reached the minimum apply confidence; review manually."
            )
        else:
            warnings.append(f"{finding.finding_id}: no geometrically effective fix candidate was found.")

    return FixPlan(actions=tuple(actions), alternatives=alternatives, warnings=tuple(warnings))


def _candidates_for_finding(
    snapshot: BoardSnapshot,
    finding: Finding,
    config: FixConfig,
    current_safe_keepouts: frozenset[tuple[object, ...]] = frozenset(),
) -> list[FixAction]:
    """Generate only electrically meaningful bridge, via, and keepout alternatives."""

    metrics = finding.metrics
    net = str(metrics.get("net") or _zone_net(snapshot, str(metrics.get("zone_id", ""))) or "GND")
    layer = str(metrics.get("layer") or "F.Cu")
    layer_id = int(metrics.get("layer_id") or 0)
    kind = str(metrics.get("kind") or "appendage")
    isolated = bool(metrics.get("isolated")) or kind == "island"
    location = finding.location or _point_from_mapping(metrics.get("centroid")) or Point(0.0, 0.0)
    gate = _point_from_mapping(metrics.get("gate")) or location
    feature_polygon = _feature_polygon(metrics)
    candidates: list[FixAction] = []

    # A connected appendage is already part of the same plane.  Routing from its
    # tip to a pad/via through that plane is normally redundant and can even add
    # an unnecessary current constriction.  Bridges are considered only when a
    # segment leaves existing same-layer copper or when the source is isolated.
    ground_anchors = _same_net_anchors(snapshot, net, layer)
    bridge_start = gate if isolated and distance(gate, location) > 0.05 else location
    effective_anchors = (
        tuple(
            anchor
            for anchor in ground_anchors
            if feature_polygon is None or not point_in_polygon(anchor, feature_polygon)
        )
        or ground_anchors
    )
    nearest_anchor = min(effective_anchors, key=lambda point: distance(bridge_start, point), default=None)
    if nearest_anchor is not None:
        bridge_length = distance(bridge_start, nearest_anchor)
        redundant = _segment_inside_same_net_copper(
            snapshot,
            bridge_start,
            nearest_anchor,
            net,
            layer,
            sample_step_mm=0.20,
        )
        if not config.reject_redundant_same_plane_tracks:
            redundant = False
        width = _widest_safe_track_width(
            snapshot,
            bridge_start,
            nearest_anchor,
            net,
            layer,
            config,
        )
        if (
            bridge_length > 0.05
            and bridge_length <= config.maximum_bridge_length_mm
            and width is not None
            and (isolated or not redundant)
        ):
            candidates.append(
                FixAction(
                    action_id=_action_id(finding.finding_id, "track"),
                    finding_id=finding.finding_id,
                    kind=FixKind.TRACK_BRIDGE,
                    description="Connect the copper component to an existing GND anchor with a wide, clearance-safe bridge.",
                    expected_risk_reduction=min(
                        1.0, (0.72 if isolated else 0.48) + finding.confidence * 0.24
                    ),
                    implementation_cost=0.10
                    + bridge_length / max(config.maximum_bridge_length_mm, 0.1) * 0.22,
                    confidence=min(0.95, finding.confidence * (0.98 if isolated else 0.90)),
                    layer=layer,
                    layer_id=layer_id,
                    net=net,
                    start=bridge_start,
                    end=nearest_anchor,
                    parameters={
                        "width_mm": width,
                        "length_mm": bridge_length,
                        "selection_reason": "connects_disconnected_or_uncovered_copper",
                        "redundant_same_plane_track": False,
                    },
                )
            )

    # A via is useful only when it reaches same-net copper on another layer and
    # there is no existing same-net via close enough to provide the same link.
    if (
        not _near_existing_same_net_via(snapshot, location, net, config.via_diameter_mm)
        and _via_clear(
            snapshot, location, net, layer, config.via_diameter_mm, config.via_clearance_mm, config
        )
        and _via_reaches_remote_ground(snapshot, location, net, layer, config.via_diameter_mm)
    ):
        candidates.append(
            FixAction(
                action_id=_action_id(finding.finding_id, "via"),
                finding_id=finding.finding_id,
                kind=FixKind.STITCHING_VIA,
                description="Add a GND stitching via where it creates a new inter-layer connection.",
                expected_risk_reduction=min(1.0, (0.68 if isolated else 0.52) + finding.confidence * 0.28),
                implementation_cost=0.17,
                confidence=min(0.94, finding.confidence * 0.96),
                layer=layer,
                layer_id=layer_id,
                net=net,
                position=location,
                parameters={
                    "diameter_mm": config.via_diameter_mm,
                    "drill_mm": config.via_drill_mm,
                    "selection_reason": "new_interlayer_ground_connection",
                },
            )
        )

    if config.allow_combined_track_via:
        via_position = gate if distance(location, gate) <= config.maximum_via_search_radius_mm else location
        bridge_start = location
        bridge_length = distance(bridge_start, via_position)
        redundant = _segment_inside_same_net_copper(
            snapshot,
            bridge_start,
            via_position,
            net,
            layer,
            sample_step_mm=0.20,
        )
        if not config.reject_redundant_same_plane_tracks:
            redundant = False
        width = _widest_safe_track_width(snapshot, bridge_start, via_position, net, layer, config)
        if (
            bridge_length > 0.05
            and bridge_length <= config.maximum_bridge_length_mm
            and width is not None
            and not redundant
            and not _near_existing_same_net_via(snapshot, via_position, net, config.via_diameter_mm)
            and _via_clear(
                snapshot, via_position, net, layer, config.via_diameter_mm, config.via_clearance_mm, config
            )
            and _via_reaches_remote_ground(snapshot, via_position, net, layer, config.via_diameter_mm)
        ):
            candidates.append(
                FixAction(
                    action_id=_action_id(finding.finding_id, "track-via"),
                    finding_id=finding.finding_id,
                    kind=FixKind.TRACK_AND_VIA,
                    description="Bridge across an uncovered gap and terminate it with a new GND stitching via.",
                    expected_risk_reduction=min(1.0, 0.72 + finding.confidence * 0.25),
                    implementation_cost=0.25
                    + bridge_length / max(config.maximum_bridge_length_mm, 0.1) * 0.12,
                    confidence=min(0.93, finding.confidence * 0.95),
                    layer=layer,
                    layer_id=layer_id,
                    net=net,
                    start=bridge_start,
                    end=via_position,
                    position=via_position,
                    parameters={
                        "width_mm": width,
                        "diameter_mm": config.via_diameter_mm,
                        "drill_mm": config.via_drill_mm,
                        "selection_reason": "gap_bridge_with_new_interlayer_connection",
                        "redundant_same_plane_track": False,
                    },
                )
            )

    if config.allow_rule_area_fallback:
        polygon = _rule_area_polygon(metrics, location, config.rule_area_margin_mm)
        current_geometry_proven = _polygon_fingerprint(polygon) in current_safe_keepouts
        proven_safe = (
            bool(metrics.get("safe_keepout"))
            and bool(metrics.get("critical_connectivity_preserved"))
            and current_geometry_proven
        )
        pad_overlap = bool(metrics.get("pad_overlap"))
        perimeter_overlap = bool(metrics.get("perimeter_overlap"))
        geometry_safe = _rule_area_is_safe(snapshot, polygon, net, layer, config)
        if (
            geometry_safe
            and not pad_overlap
            and not perimeter_overlap
            and (proven_safe or not config.require_proven_safe_rule_area)
        ):
            appendage_preferred = kind == "appendage" and config.prefer_rule_area_for_appendages
            candidates.append(
                FixAction(
                    action_id=_action_id(finding.finding_id, "rule-area"),
                    finding_id=finding.finding_id,
                    kind=FixKind.RULE_AREA,
                    description=(
                        "Remove only the proven-removable GND overhang using an exact shape-matched "
                        "copper-pour keepout. Pads, width-t GND corridors, and perimeter GND are protected."
                    ),
                    expected_risk_reduction=min(
                        1.0, (0.95 if appendage_preferred else 0.84) + finding.confidence * 0.05
                    ),
                    implementation_cost=0.10 if appendage_preferred else 0.34,
                    confidence=min(0.99, finding.confidence + (0.04 if appendage_preferred else 0.0)),
                    layer=layer,
                    layer_id=layer_id,
                    net=net,
                    polygon=polygon,
                    parameters={
                        "margin_mm": 0.0,
                        "keepout_copper_pour": True,
                        "keepout_tracks": False,
                        "keepout_vias": False,
                        "selection_reason": (
                            "connectivity_proven_residual_overhang"
                            if appendage_preferred
                            else "proven_safe_copper_removal_fallback"
                        ),
                        "shape_source": (
                            "safe_keepout_polygon"
                            if isinstance(metrics.get("safe_keepout_polygon"), dict)
                            else "feature_polygon"
                        ),
                        "safe_keepout": proven_safe,
                        "critical_connectivity_preserved": proven_safe,
                        "current_geometry_revalidated": current_geometry_proven,
                        "pad_overlap": False,
                        "perimeter_overlap": False,
                        "required_ground_connection_width_mm": metrics.get(
                            "required_ground_connection_width_mm"
                        ),
                    },
                )
            )
    return candidates


def _current_safe_keepout_fingerprints(
    snapshot: BoardSnapshot,
    zone_id: str,
    net: str,
    layer: str,
    antenna_config: AntennaConfig,
) -> frozenset[tuple[object, ...]]:
    """Recompute safe residuals against the current board before planning.

    Dashboard findings can become stale after the user edits the board.  A
    previously safe keepout must not be applied to a new pad, perimeter band,
    or width-t connection corridor.  Re-running the protected-backbone proof
    for the source zone makes rule-area planning fail closed on stale data.
    """

    zone = next(
        (
            item
            for item in snapshot.zones
            if item.item_id == zone_id and item.net == net and not item.is_rule_area
        ),
        None,
    )
    if zone is None:
        return frozenset()
    polygons = zone.filled.get(layer, ())
    if not polygons and layer in zone.layers:
        polygons = (zone.outline,)
    result: set[tuple[object, ...]] = set()
    for polygon in polygons:
        try:
            features = detect_protected_ground_features(
                snapshot,
                net,
                layer,
                polygon,
                antenna_config,
            )
        except ValueError:
            # Excessive raster size or invalid geometry must disable automatic
            # copper removal, not weaken the proof.
            return frozenset()
        for feature in features:
            if feature.safe_keepout and feature.critical_connectivity_preserved:
                result.add(_polygon_fingerprint(cells_to_outline(feature.feature)))
    return frozenset(result)


def _polygon_fingerprint(polygon: Polygon, precision: int = 6) -> tuple[object, ...]:
    """Return an orientation- and start-index-independent polygon fingerprint."""

    def normalize_ring(ring: Sequence[Point]) -> tuple[tuple[float, float], ...]:
        points = tuple((round(point.x, precision), round(point.y, precision)) for point in ring)
        if not points:
            return ()
        if len(points) > 1 and points[0] == points[-1]:
            points = points[:-1]
        rotations: list[tuple[tuple[float, float], ...]] = []
        for sequence in (points, tuple(reversed(points))):
            rotations.extend(sequence[index:] + sequence[:index] for index in range(len(sequence)))
        return min(rotations)

    outline = normalize_ring(polygon.outline)
    holes = tuple(sorted(normalize_ring(hole) for hole in polygon.holes))
    return (outline, holes)


def _same_net_anchors(snapshot: BoardSnapshot, net: str, source_layer: str) -> tuple[Point, ...]:
    """Return exact-net pads and vias that are compatible with the source layer."""

    via_points = [via.position for via in snapshot.vias if via.net == net]
    pad_points = [
        pad.position
        for pad in snapshot.pads
        if pad.net == net and _pad_contacts_layer(pad.layers, source_layer)
    ]
    return tuple((*via_points, *pad_points))


def _pad_contacts_layer(layers: tuple[str, ...], layer: str) -> bool:
    """Return whether a KiCad padstack can contact one copper layer."""

    if not layers:
        return True
    normalized = {str(item) for item in layers}
    return layer in normalized or bool(normalized & {"*.Cu", "*.Copper", "All.Cu"})


def _pad_reaches_remote_layer(layers: tuple[str, ...], source_layer: str) -> bool:
    """Return whether a padstack can electrically reach another copper layer."""

    if not layers:
        return True
    normalized = {str(item) for item in layers}
    if normalized & {"*.Cu", "*.Copper", "All.Cu"}:
        return True
    return any(item.endswith(".Cu") and item != source_layer for item in normalized)


def _same_net_layer_polygons(snapshot: BoardSnapshot, net: str, layer: str) -> tuple[Polygon, ...]:
    """Return all filled same-net polygons on one layer."""

    return tuple(
        polygon
        for zone in snapshot.zones
        if not zone.is_rule_area and zone.net == net
        for polygon in zone.filled.get(layer, ())
    )


def _segment_inside_same_net_copper(
    snapshot: BoardSnapshot,
    start: Point,
    end: Point,
    net: str,
    layer: str,
    sample_step_mm: float,
) -> bool:
    """Return whether an entire proposed bridge lies in existing same-net fill."""

    polygons = _same_net_layer_polygons(snapshot, net, layer)
    if not polygons:
        return False
    length = distance(start, end)
    count = max(2, int(math.ceil(length / max(sample_step_mm, 0.02))))
    for index in range(count + 1):
        ratio = index / count
        point = Point(start.x + (end.x - start.x) * ratio, start.y + (end.y - start.y) * ratio)
        if not any(point_in_polygon(point, polygon) for polygon in polygons):
            return False
    return True


def _widest_safe_track_width(
    snapshot: BoardSnapshot,
    start: Point,
    end: Point,
    net: str,
    layer: str,
    config: FixConfig,
) -> float | None:
    """Return the widest configured clearance-safe width for one bridge."""

    maximum = max(config.track_width_mm, config.maximum_track_width_mm)
    if not config.adaptive_track_width:
        return (
            config.track_width_mm
            if _track_clear(
                snapshot, start, end, net, layer, config.track_width_mm, config.via_clearance_mm, config
            )
            else None
        )
    candidates = {
        config.track_width_mm,
        maximum,
        1.5,
        1.0,
        0.8,
        0.5,
        0.4,
        0.3,
        0.2,
        0.1,
    }
    for width in sorted(
        (value for value in candidates if config.track_width_mm <= value <= maximum), reverse=True
    ):
        if _track_clear(snapshot, start, end, net, layer, width, config.via_clearance_mm, config):
            return round(width, 4)
    return None


def _near_existing_same_net_via(snapshot: BoardSnapshot, position: Point, net: str, diameter: float) -> bool:
    """Return whether an existing same-net via already serves this location."""

    threshold = max(diameter, 0.4)
    return any(via.net == net and distance(position, via.position) <= threshold for via in snapshot.vias)


def _via_reaches_remote_ground(
    snapshot: BoardSnapshot,
    position: Point,
    net: str,
    source_layer: str,
    diameter: float,
) -> bool:
    """Return whether a new via would contact same-net copper on another layer."""

    radius = diameter / 2.0
    for zone in snapshot.zones:
        if zone.is_rule_area or zone.net != net:
            continue
        for layer, polygons in zone.filled.items():
            if layer != source_layer and any(point_in_polygon(position, polygon) for polygon in polygons):
                return True
    for track in snapshot.tracks:
        if (
            track.net == net
            and track.layer != source_layer
            and point_segment_distance(position, track.start, track.end) <= radius + track.width / 2.0
        ):
            return True
    for pad in snapshot.pads:
        if pad.net != net:
            continue
        remote_layers = _pad_reaches_remote_layer(pad.layers, source_layer)
        if remote_layers and pad.bounds.inflate(radius).intersects(
            BoundingBox(position.x, position.y, position.x, position.y)
        ):
            return True
    return False


def _track_clear(
    snapshot: BoardSnapshot,
    start: Point,
    end: Point,
    net: str,
    layer: str,
    width: float,
    clearance: float,
    config: FixConfig,
) -> bool:
    """Return whether a proposed track is on-board and clears same-layer copper."""

    if not _track_inside_board(snapshot, start, end, width, config):
        return False
    required = width / 2.0 + clearance
    for track in snapshot.tracks:
        if track.layer != layer or track.net == net:
            continue
        if segment_distance(start, end, track.start, track.end) < required + track.width / 2.0:
            return False
    for via in snapshot.vias:
        if via.net == net:
            continue
        if point_segment_distance(via.position, start, end) < required + via.diameter / 2.0:
            return False
    for pad in snapshot.pads:
        if pad.net == net or not _pad_contacts_layer(pad.layers, layer):
            continue
        if _segment_intersects_box(start, end, pad.bounds.inflate(required)):
            return False
    for zone in snapshot.zones:
        if zone.is_rule_area or zone.net == net:
            continue
        for polygon in zone.filled.get(layer, ()):
            if _segment_crosses_polygon_area(start, end, polygon, required):
                return False
    return True


def _via_clear(
    snapshot: BoardSnapshot,
    position: Point,
    net: str,
    source_layer: str,
    diameter: float,
    clearance: float,
    config: FixConfig,
) -> bool:
    """Return whether a proposed via is on-board and clears known copper."""

    if not _disk_inside_board(snapshot, position, diameter / 2.0, config):
        return False
    radius = diameter / 2.0 + clearance
    for via in snapshot.vias:
        required = radius + via.diameter / 2.0
        if distance(position, via.position) < required:
            return False
    for track in snapshot.tracks:
        if (
            track.net != net
            and point_segment_distance(position, track.start, track.end) < radius + track.width / 2.0
        ):
            return False
    for pad in snapshot.pads:
        if pad.net != net and pad.bounds.inflate(radius).intersects(
            BoundingBox(position.x, position.y, position.x, position.y)
        ):
            return False
    for zone in snapshot.zones:
        if zone.is_rule_area or zone.net == net:
            continue
        for layer, polygons in zone.filled.items():
            if not layer.endswith(".Cu"):
                continue
            for polygon in polygons:
                if _disk_overlaps_polygon(position, radius, polygon):
                    return False
    return True


def _disk_overlaps_polygon(center: Point, radius: float, polygon: Polygon) -> bool:
    """Return whether a circular copper feature overlaps filled polygon copper."""

    if point_in_polygon(center, polygon):
        return True
    return any(
        point_segment_distance(center, first, second) < radius - 1.0e-9
        for ring in (polygon.outline, *polygon.holes)
        for first, second in pairwise_closed(ring)
    )


def _board_polygon(snapshot: BoardSnapshot) -> Polygon | None:
    """Return the sampled board area including internal Edge.Cuts cutouts."""

    if not snapshot.edges:
        return None
    try:
        return current_outline_polygon(snapshot, maximum_step_mm=0.05)
    except (RuntimeError, ValueError):
        return None


def _track_inside_board(
    snapshot: BoardSnapshot,
    start: Point,
    end: Point,
    width: float,
    config: FixConfig,
) -> bool:
    """Return whether the complete round-capped track stays inside Edge.Cuts.

    Endpoint-only or coarse sampling can miss a narrow concavity.  This check
    combines endpoint disk containment with exact segment-to-boundary distance
    against the sampled outer outline and every internal cutout.
    """

    board = _board_polygon(snapshot)
    if board is None:
        return not config.require_board_outline_for_new_copper
    radius = max(0.0, width / 2.0 + config.board_edge_clearance_mm)
    if not _disk_inside_polygon(start, radius, board) or not _disk_inside_polygon(end, radius, board):
        return False
    if distance(start, end) <= 1.0e-12:
        return True
    boundaries = tuple(edge for ring in (board.outline, *board.holes) for edge in pairwise_closed(ring))
    if any(segment_distance(start, end, first, second) < radius - 1.0e-9 for first, second in boundaries):
        return False
    # The boundary-distance test catches crossings and width excursions.  A
    # few centerline probes guard against degenerate or numerically imperfect
    # imported outlines without relying on a coarse fixed step.
    for ratio in (0.25, 0.50, 0.75):
        probe = Point(
            start.x + (end.x - start.x) * ratio,
            start.y + (end.y - start.y) * ratio,
        )
        if not point_in_polygon(probe, board):
            return False
    return True


def _disk_inside_board(
    snapshot: BoardSnapshot,
    center: Point,
    radius: float,
    config: FixConfig,
) -> bool:
    """Return whether a circular via plus edge margin stays inside Edge.Cuts."""

    board = _board_polygon(snapshot)
    if board is None:
        return not config.require_board_outline_for_new_copper
    return _disk_inside_polygon(center, radius + config.board_edge_clearance_mm, board)


def _disk_inside_polygon(center: Point, radius: float, polygon: Polygon) -> bool:
    """Return whether a full disk is contained in a polygon with holes."""

    if not point_in_polygon(center, polygon):
        return False
    if radius <= 1.0e-9:
        return True
    clearance = min(
        point_segment_distance(center, first, second)
        for ring in (polygon.outline, *polygon.holes)
        for first, second in pairwise_closed(ring)
    )
    return clearance + 1.0e-9 >= radius


def _rule_area_is_safe(
    snapshot: BoardSnapshot,
    polygon: Polygon,
    net: str,
    layer: str,
    config: FixConfig,
) -> bool:
    """Reject keepouts that touch pads, leave the board, or lack a valid shape."""

    if len(polygon.outline) < 3:
        return False
    board = _board_polygon(snapshot)
    if board is None:
        # A rule area removes existing zone fill rather than adding copper.  If
        # Edge.Cuts are unavailable in the snapshot, containment in the exact
        # same-net filled polygon is a sufficient fail-closed substitute.
        if not _polygon_inside_same_net_fill(snapshot, polygon, net, layer):
            return False
    elif not _polygon_inside_polygon(polygon, board):
        return False
    for pad in snapshot.pads:
        if not _pad_contacts_layer(pad.layers, layer):
            continue
        # Pads are mandatory electrical features regardless of net.  A zone
        # keepout that overlaps any pad can remove thermals or isolate its GND
        # connection after refill, so it is always rejected.
        if _polygon_intersects_box(polygon, pad.bounds):
            return False
    # Explicit same-net GND traces are protected by the detector.  Recheck here
    # because stale findings can otherwise outlive a board edit.
    for track in snapshot.tracks:
        if track.net != net or track.layer != layer:
            continue
        if _segment_crosses_polygon_area(track.start, track.end, polygon, track.width / 2.0):
            return False
    return True


def _polygon_inside_same_net_fill(
    snapshot: BoardSnapshot,
    candidate: Polygon,
    net: str,
    layer: str,
) -> bool:
    """Return whether a keepout boundary is contained in existing same-net fill."""

    containers = _same_net_layer_polygons(snapshot, net, layer)
    if not containers:
        return False
    for ring in (candidate.outline, *candidate.holes):
        for first, second in pairwise_closed(ring):
            length = distance(first, second)
            samples = max(1, int(math.ceil(length / 0.10)))
            for index in range(samples + 1):
                ratio = index / samples
                point = Point(
                    first.x + (second.x - first.x) * ratio,
                    first.y + (second.y - first.y) * ratio,
                )
                if not any(point_in_polygon(point, container) for container in containers):
                    return False
    return True


def _polygon_inside_polygon(candidate: Polygon, container: Polygon) -> bool:
    """Return whether the complete filled candidate is inside container."""

    candidate_edges = tuple(
        edge for ring in (candidate.outline, *candidate.holes) for edge in pairwise_closed(ring)
    )
    container_edges = tuple(
        edge for ring in (container.outline, *container.holes) for edge in pairwise_closed(ring)
    )
    if not candidate_edges or not all(point_in_polygon(point, container) for point in candidate.outline):
        return False
    if any(
        segments_intersect(first, second, other_first, other_second)
        for first, second in candidate_edges
        for other_first, other_second in container_edges
    ):
        return False
    # A candidate can surround an internal board cutout while keeping its own
    # boundary inside the outer outline.  Reject when any cutout vertex lies in
    # the candidate's filled region.
    return not any(point_in_polygon(point, candidate) for hole in container.holes for point in hole)


def _polygon_intersects_box(polygon: Polygon, bounds: BoundingBox) -> bool:
    """Return whether a filled polygon overlaps an axis-aligned pad box."""

    corners = (
        Point(bounds.min_x, bounds.min_y),
        Point(bounds.max_x, bounds.min_y),
        Point(bounds.max_x, bounds.max_y),
        Point(bounds.min_x, bounds.max_y),
    )
    if any(point_in_polygon(point, polygon) for point in (*corners, bounds.center)):
        return True
    if any(
        bounds.min_x <= point.x <= bounds.max_x and bounds.min_y <= point.y <= bounds.max_y
        for point in polygon.outline
    ):
        return True
    return any(
        segments_intersect(first, second, box_first, box_second)
        for ring in (polygon.outline, *polygon.holes)
        for first, second in pairwise_closed(ring)
        for box_first, box_second in pairwise_closed(corners)
    )


def _segment_crosses_polygon_area(
    start: Point,
    end: Point,
    polygon: Polygon,
    radius: float,
) -> bool:
    """Return whether a finite-width segment overlaps a filled polygon."""

    if point_in_polygon(start, polygon) or point_in_polygon(end, polygon):
        return True
    boundaries = tuple(edge for ring in (polygon.outline, *polygon.holes) for edge in pairwise_closed(ring))
    if any(segments_intersect(start, end, first, second) for first, second in boundaries):
        return True
    return radius > 0.0 and any(
        segment_distance(start, end, first, second) < radius - 1.0e-9 for first, second in boundaries
    )


def _segment_intersects_box(start: Point, end: Point, bounds: BoundingBox) -> bool:
    """Return whether a segment intersects an axis-aligned box."""

    if bounds.min_x <= start.x <= bounds.max_x and bounds.min_y <= start.y <= bounds.max_y:
        return True
    if bounds.min_x <= end.x <= bounds.max_x and bounds.min_y <= end.y <= bounds.max_y:
        return True
    corners = (
        Point(bounds.min_x, bounds.min_y),
        Point(bounds.max_x, bounds.min_y),
        Point(bounds.max_x, bounds.max_y),
        Point(bounds.min_x, bounds.max_y),
    )
    return any(
        segment_distance(start, end, corners[index], corners[(index + 1) % 4]) <= 1.0e-9 for index in range(4)
    )


def _feature_polygon(metrics: object) -> Polygon | None:
    """Parse the shape-matched raster polygon carried by an antenna finding."""

    values = metrics if isinstance(metrics, dict) else {}
    raw = values.get("safe_keepout_polygon") or values.get("feature_polygon") or values.get("polygon")
    if not isinstance(raw, dict) or not isinstance(raw.get("outline"), list):
        return None
    outline = tuple(
        point for point in (_point_from_mapping(item) for item in raw["outline"]) if point is not None
    )
    holes = tuple(
        tuple(point for point in (_point_from_mapping(item) for item in hole) if point is not None)
        for hole in raw.get("holes", ())
        if isinstance(hole, list)
    )
    if len(outline) < 3:
        return None
    return Polygon(outline=outline, holes=tuple(hole for hole in holes if len(hole) >= 3))


def _rule_area_polygon(metrics: object, location: Point, margin: float) -> Polygon:
    """Build a shape-matched rule area with a conservative fallback."""

    polygon = _feature_polygon(metrics)
    if polygon is not None:
        # The safe raster residual is already quantized to complete copper cells.
        # Expanding it can overlap pads or mandatory GND corridors, so the exact
        # proven-removable geometry is retained without an outward margin.
        return polygon

    values = metrics if isinstance(metrics, dict) else {}
    bounds = values.get("bounds")
    if isinstance(bounds, dict):
        try:
            box = BoundingBox(
                float(bounds["min_x"]),
                float(bounds["min_y"]),
                float(bounds["max_x"]),
                float(bounds["max_y"]),
            ).inflate(margin)
        except (KeyError, TypeError, ValueError):
            box = BoundingBox(
                location.x - margin, location.y - margin, location.x + margin, location.y + margin
            )
    else:
        box = BoundingBox(location.x - margin, location.y - margin, location.x + margin, location.y + margin)
    return Polygon(
        outline=(
            Point(box.min_x, box.min_y),
            Point(box.max_x, box.min_y),
            Point(box.max_x, box.max_y),
            Point(box.min_x, box.max_y),
        )
    )


def _expand_polygon_radially(polygon: Polygon, margin: float) -> Polygon:
    """Return a small shape-preserving radial expansion of a polygon."""

    if margin <= 1.0e-9:
        return polygon
    center = Point(
        sum(point.x for point in polygon.outline) / len(polygon.outline),
        sum(point.y for point in polygon.outline) / len(polygon.outline),
    )

    def expand_ring(ring: tuple[Point, ...], direction: float) -> tuple[Point, ...]:
        result: list[Point] = []
        for point in ring:
            dx = point.x - center.x
            dy = point.y - center.y
            length = math.hypot(dx, dy)
            if length <= 1.0e-9:
                result.append(point)
            else:
                scale = max(0.01, (length + direction * margin) / length)
                result.append(Point(center.x + dx * scale, center.y + dy * scale))
        return tuple(result)

    return Polygon(
        outline=expand_ring(polygon.outline, 1.0),
        holes=tuple(expand_ring(hole, -1.0) for hole in polygon.holes),
    )


def _zone_net(snapshot: BoardSnapshot, zone_id: str) -> str:
    """Return the net of a zone identifier."""

    return next((zone.net for zone in snapshot.zones if zone.item_id == zone_id), "")


def _point_from_mapping(value: object) -> Point | None:
    """Parse a point from a mapping."""

    if not isinstance(value, dict):
        return None
    try:
        return Point(float(value["x"]), float(value["y"]))
    except (KeyError, TypeError, ValueError):
        return None


def _action_id(finding_id: str, suffix: str) -> str:
    """Return a stable action identifier."""

    payload = f"{finding_id}|{suffix}".encode()
    return "FIX-" + hashlib.sha1(payload, usedforsecurity=False).hexdigest()[:12].upper()
