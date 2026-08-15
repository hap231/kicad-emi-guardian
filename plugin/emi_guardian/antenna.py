"""Ground-pour antenna candidate detection and severity assessment."""

from __future__ import annotations

import hashlib
import math
import re
from collections.abc import Iterable

from .antenna_geometry import ProtectedGroundFeature, detect_protected_ground_features
from .config import AntennaConfig
from .geometry import distance, point_in_polygon, point_segment_distance, polygon_area, polygon_perimeter
from .ground_connectivity import GroundConnectivity, RegionKey, build_ground_connectivity
from .models import BoardSnapshot, CopperZone, Finding, Point, Polygon, Severity
from .quantitative import quarter_wave_frequency_mhz
from .raster import cells_to_outline


def detect_ground_antennas(snapshot: BoardSnapshot, config: AntennaConfig) -> tuple[Finding, ...]:
    """Return all geometric ground-antenna candidates at the configured resolution."""

    ground_pattern = re.compile(config.ground_net_regex, re.IGNORECASE)
    ground_nets = {
        net
        for net in (
            *(zone.net for zone in snapshot.zones),
            *(via.net for via in snapshot.vias),
            *(pad.net for pad in snapshot.pads),
        )
        if net and ground_pattern.search(net)
    }
    connectivity = build_ground_connectivity(
        snapshot,
        config.ground_net_regex,
        config.connectivity_tolerance_mm,
    )
    findings: list[Finding] = []
    emitted_unanchored_components: set[str] = set()
    for zone in snapshot.zones:
        if zone.is_rule_area or zone.net not in ground_nets:
            continue
        for layer_name, polygons in _zone_polygons(zone):
            anchors = tuple(
                point
                for point in (
                    *(via.position for via in snapshot.vias if via.net == zone.net),
                    *(pad.position for pad in snapshot.pads if pad.net == zone.net),
                )
                if any(point_in_polygon(point, polygon) for polygon in polygons)
            )
            for polygon_index, polygon in enumerate(polygons):
                findings.extend(
                    _analyze_polygon(
                        snapshot=snapshot,
                        config=config,
                        zone=zone,
                        layer_name=layer_name,
                        polygon=polygon,
                        polygon_index=polygon_index,
                        anchors=anchors,
                        connectivity=connectivity,
                        emitted_unanchored_components=emitted_unanchored_components,
                    )
                )
    return tuple(findings)


def _zone_polygons(zone: CopperZone) -> Iterable[tuple[str, tuple[Polygon, ...]]]:
    """Yield filled polygons per layer with an outline fallback."""

    emitted = False
    for layer, polygons in zone.filled.items():
        if polygons:
            emitted = True
            yield layer, polygons
    if not emitted:
        for layer in zone.layers:
            yield layer, (zone.outline,)


def _analyze_polygon(
    snapshot: BoardSnapshot,
    config: AntennaConfig,
    zone: CopperZone,
    layer_name: str,
    polygon: Polygon,
    polygon_index: int,
    anchors: tuple[Point, ...],
    connectivity: GroundConnectivity,
    emitted_unanchored_components: set[str],
) -> list[Finding]:
    """Analyze one filled polygon."""

    findings: list[Finding] = []
    area = polygon_area(polygon)
    perimeter = polygon_perimeter(polygon.outline)
    local_anchors = tuple(anchor for anchor in anchors if point_in_polygon(anchor, polygon))
    region_key: RegionKey = (zone.item_id, layer_name, polygon_index)
    component = connectivity.component_for_region(region_key)
    component_anchor_points: tuple[Point, ...] = ()
    if component is not None:
        pad_ids = set(component.pad_ids)
        via_ids = set(component.via_ids)
        component_anchor_points = tuple(
            [pad.position for pad in snapshot.pads if pad.item_id in pad_ids]
            + [via.position for via in snapshot.vias if via.item_id in via_ids]
        )
    if component_anchor_points:
        local_anchors = component_anchor_points

    # A via by itself only joins copper layers; it is not an independent
    # electrical anchor.  Emit one finding per complete same-net copper
    # component after zones, tracks, vias, and footprint pads have been unioned.
    component_id = component.component_id if component else ""
    unanchored = bool(component and not component.anchored)
    component_area = component.area_mm2 if component else area
    if (
        unanchored
        and component_area >= config.minimum_unanchored_component_area_mm2
        and component_id not in emitted_unanchored_components
    ):
        emitted_unanchored_components.add(component_id)
        compactness = 4.0 * math.pi * area / max(perimeter * perimeter, 1.0e-9)
        severity_score = min(
            1.0,
            0.35
            + component_area / max(config.island_area_warning_mm2, 0.1) * 0.25
            + (1.0 - compactness) * 0.25,
        )
        findings.append(
            Finding(
                finding_id=_finding_id(zone.item_id, layer_name, polygon_index, component_id, "island"),
                category="antenna",
                title="Unanchored ground copper component",
                description=(
                    "The complete same-net connectivity graph for filled zones, tracks, vias, and pads "
                    "does not connect this copper component to a footprint GND pad. It may be a real "
                    "floating island rather than merely a separate filled-polygon record."
                ),
                severity=_severity(severity_score),
                confidence=0.90,
                score_penalty=6.0 + 10.0 * severity_score,
                location=_safe_centroid(polygon),
                item_ids=tuple(
                    dict.fromkeys(
                        (
                            zone.item_id,
                            *(component.track_ids if component else ()),
                            *(component.via_ids if component else ()),
                        )
                    )
                ),
                metrics={
                    "kind": "island",
                    "net": zone.net,
                    "layer": layer_name,
                    "zone_id": zone.item_id,
                    "component_id": component_id,
                    "area_mm2": round(area, 4),
                    "component_area_mm2": round(component_area, 4),
                    "perimeter_mm": round(perimeter, 4),
                    "anchor_count": 0,
                    "connected_via_count": len(component.via_ids) if component else 0,
                    "connected_track_count": len(component.track_ids) if component else 0,
                    "polygon": polygon.to_dict(),
                },
                recommendation=(
                    "Confirm the net assignment and zone fill. Add a valid low-impedance connection to a GND pad "
                    "when the copper is intentional; otherwise remove it with a copper-pour keepout rule area."
                ),
                rule_id="antenna.island",
            )
        )

    # A component that does not reach any footprint GND pad is already a
    # floating-island problem.  Running the appendage-removal detector on the
    # same copper produces duplicate and potentially contradictory advice
    # (remove a tail versus connect the whole island).  Keep the classifications
    # mutually exclusive and let the island remediation choose connection or
    # manual removal at component scope.
    if unanchored:
        return findings

    try:
        protected_features = detect_protected_ground_features(
            snapshot,
            zone.net,
            layer_name,
            polygon,
            config,
        )
    except ValueError:
        # Invalid or excessively large raster geometry must not abort the
        # remaining analysis stages.  Automatic removal simply remains
        # unavailable for this polygon until the raster resolution or maximum
        # cell count is adjusted.
        return findings
    for feature_index, protected_feature in enumerate(protected_features):
        feature = protected_feature.feature
        if feature.area_mm2 < config.minimum_appendage_area_mm2:
            continue
        if feature.length_mm < config.minimum_appendage_length_mm and not feature.isolated:
            continue
        finding = _feature_finding(
            snapshot=snapshot,
            config=config,
            zone=zone,
            layer_name=layer_name,
            polygon_index=polygon_index,
            feature_index=feature_index,
            protected_feature=protected_feature,
            anchors=local_anchors,
        )
        findings.append(finding)
    return findings


def _feature_finding(
    snapshot: BoardSnapshot,
    config: AntennaConfig,
    zone: CopperZone,
    layer_name: str,
    polygon_index: int,
    feature_index: int,
    protected_feature: ProtectedGroundFeature,
    anchors: tuple[Point, ...],
) -> Finding:
    """Convert a connectivity-safe raster appendage into a scored finding."""

    feature = protected_feature.feature
    anchor_distance = min((distance(feature.tip, anchor) for anchor in anchors), default=math.inf)
    aggressor_distance = _nearest_aggressor_distance(snapshot, feature.tip, zone.net, layer_name)
    resonance_mhz = quarter_wave_frequency_mhz(
        max(feature.length_mm, config.raster_step_mm),
        config.effective_permittivity,
    )
    slenderness = feature.length_mm / max(feature.width_mm, config.raster_step_mm)
    components = {
        "slenderness": _clamp((slenderness - 2.0) / 12.0),
        "length": _clamp(feature.length_mm / 25.0),
        "anchor_distance": 1.0
        if math.isinf(anchor_distance)
        else _clamp(anchor_distance / config.maximum_anchor_distance_mm),
        "resonance": _clamp(config.target_max_resonance_mhz / max(resonance_mhz, 1.0)),
        "aggressor": 0.0
        if math.isinf(aggressor_distance)
        else _clamp(
            (config.aggressor_search_radius_mm - aggressor_distance) / config.aggressor_search_radius_mm
        ),
    }
    severity_score = sum(
        config.severity_weights.get(name, 0.0) * value for name, value in components.items()
    ) / max(sum(config.severity_weights.values()), 1.0e-9)
    confidence = min(0.98, 0.72 + min(feature.area_mm2 / 20.0, 0.10) + min(slenderness / 50.0, 0.12))
    title = "Narrow ground-pour appendage"
    if feature.isolated:
        title = "Narrow isolated ground copper"
    return Finding(
        finding_id=_finding_id(zone.item_id, layer_name, polygon_index, feature_index),
        category="antenna",
        title=title,
        description=(
            "Morphological opening identified copper outside the broad GND core defined by the larger "
            "of the configured neck width and mandatory connection width t, "
            "and remains outside the protected GND backbone. Footprint pads, vias, explicit GND tracks, "
            "the existing perimeter GND band, and width-t connections to the broad GND core are excluded. "
            "The residual overhang can behave as a high-inductance stub or resonant pickup structure."
        ),
        severity=_severity(severity_score),
        confidence=confidence,
        score_penalty=4.0 + 18.0 * severity_score,
        location=feature.tip,
        item_ids=(zone.item_id,),
        metrics={
            "kind": "isolated" if feature.isolated else "appendage",
            "net": zone.net,
            "zone_id": zone.item_id,
            "layer": layer_name,
            "layer_id": _layer_id(zone, layer_name),
            "area_mm2": round(feature.area_mm2, 4),
            "length_mm": round(feature.length_mm, 4),
            "estimated_width_mm": round(feature.width_mm, 4),
            "slenderness": round(slenderness, 3),
            "attachment_cells": feature.attachment_cells,
            "isolated": feature.isolated,
            "nearest_ground_anchor_mm": None if math.isinf(anchor_distance) else round(anchor_distance, 4),
            "nearest_aggressor_mm": None if math.isinf(aggressor_distance) else round(aggressor_distance, 4),
            "quarter_wave_resonance_mhz": round(resonance_mhz, 2),
            "severity_components": {key: round(value, 4) for key, value in components.items()},
            "tip": feature.tip.to_dict(),
            "gate": feature.gate.to_dict(),
            "centroid": feature.centroid.to_dict(),
            "bounds": {
                "min_x": feature.bounds.min_x,
                "min_y": feature.bounds.min_y,
                "max_x": feature.bounds.max_x,
                "max_y": feature.bounds.max_y,
            },
            "feature_polygon": cells_to_outline(feature).to_dict(),
            "safe_keepout_polygon": cells_to_outline(feature).to_dict(),
            "safe_keepout": protected_feature.safe_keepout,
            "critical_connectivity_preserved": protected_feature.critical_connectivity_preserved,
            "pad_overlap": protected_feature.pad_overlap,
            "perimeter_overlap": protected_feature.perimeter_overlap,
            "required_ground_connection_width_mm": protected_feature.required_connection_width_mm,
            "effective_opening_width_mm": max(
                config.narrow_neck_width_mm,
                config.required_ground_connection_width_mm,
            ),
            "protected_cell_count": protected_feature.protected_cell_count,
            "removable_cell_count": protected_feature.removable_cell_count,
            "required_terminal_count": protected_feature.required_terminal_count,
            "connected_terminal_count": protected_feature.connected_terminal_count,
            "raster_step_mm": feature.step_mm,
        },
        recommendation=(
            "Prefer the proven-safe, shape-matched copper-pour keepout for the residual overhang. The keepout must "
            "not touch any pad, mandatory width-t GND corridor, or protected perimeter band. Add a wide short bridge, "
            "a stitching via, or both only when the proposal creates genuinely new connectivity; never add a track "
            "that merely lies on the existing GND fill."
        ),
        rule_id="antenna.isolated" if feature.isolated else "antenna.appendage",
    )


def _nearest_aggressor_distance(
    snapshot: BoardSnapshot,
    point: Point,
    ground_net: str,
    layer_name: str,
) -> float:
    """Return distance to a non-ground trace on the same layer."""

    return min(
        (
            point_segment_distance(point, track.start, track.end)
            for track in snapshot.tracks
            if track.net != ground_net and track.layer == layer_name
        ),
        default=math.inf,
    )


def _severity(score: float) -> Severity:
    """Map a normalized risk score to a severity."""

    if score >= 0.82:
        return Severity.CRITICAL
    if score >= 0.62:
        return Severity.HIGH
    if score >= 0.38:
        return Severity.MEDIUM
    if score >= 0.18:
        return Severity.LOW
    return Severity.INFO


def _finding_id(*parts: object) -> str:
    """Return a stable finding identifier."""

    payload = "|".join(str(part) for part in parts).encode("utf-8")
    return "ANT-" + hashlib.sha1(payload, usedforsecurity=False).hexdigest()[:12].upper()


def _layer_id(zone: CopperZone, layer_name: str) -> int:
    """Return the KiCad layer identifier corresponding to a layer name."""

    try:
        return zone.layer_ids[zone.layers.index(layer_name)]
    except (ValueError, IndexError):
        return zone.layer_ids[0] if zone.layer_ids else 0


def _safe_centroid(polygon: Polygon) -> Point:
    """Return a robust average point for a polygon."""

    if not polygon.outline:
        return Point(0.0, 0.0)
    return Point(
        sum(point.x for point in polygon.outline) / len(polygon.outline),
        sum(point.y for point in polygon.outline) / len(polygon.outline),
    )


def _clamp(value: float) -> float:
    """Clamp a value to ``[0, 1]``."""

    return max(0.0, min(1.0, value))
