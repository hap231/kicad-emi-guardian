"""Configuration schema, defaults, validation, and persistence."""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from copy import deepcopy
from dataclasses import asdict, dataclass, field, fields, is_dataclass
from pathlib import Path
from typing import Any, TypeVar, cast

from .errors import ValidationError
from .manufacturing_profiles import (
    JLCPCB_2L_COPPER_WEIGHTS_OZ,
    JLCPCB_2L_THICKNESSES_MM,
    JLCPCB_BOARD_SEPARATION_METHODS,
    JLCPCB_SILKSCREEN_COLORS,
    JLCPCB_SOLDER_MASK_COLORS,
    JLCPCB_SURFACE_FINISHES,
    JLCPCB_VERIFIED_DATE,
    MANUFACTURING_PROFILES,
    VIA_PRESETS,
)

CURRENT_SCHEMA_VERSION = 5


@dataclass
class AntennaConfig:
    """Ground-pour antenna detector settings."""

    ground_net_regex: str = r"^(?:GND|AGND|DGND|PGND|GNDA|GNDD|VSS)(?:[_-].*)?$"
    raster_step_mm: float = 0.20
    max_raster_cells: int = 1_500_000
    narrow_neck_width_mm: float = 0.80
    minimum_appendage_area_mm2: float = 0.40
    minimum_appendage_length_mm: float = 2.00
    maximum_anchor_distance_mm: float = 8.00
    island_area_warning_mm2: float = 8.00
    connectivity_tolerance_mm: float = 0.08
    minimum_unanchored_component_area_mm2: float = 0.50
    target_max_resonance_mhz: float = 1500.0
    effective_permittivity: float = 3.3
    aggressor_search_radius_mm: float = 4.0
    required_ground_connection_width_mm: float = 1.00
    pad_protection_margin_mm: float = 0.30
    via_protection_margin_mm: float = 0.20
    explicit_track_protection_margin_mm: float = 0.15
    perimeter_ground_protection_mm: float = 1.00
    require_safe_removal_connectivity: bool = True
    protect_perimeter_ground: bool = True
    protect_explicit_ground_tracks: bool = True
    severity_weights: dict[str, float] = field(
        default_factory=lambda: {
            "slenderness": 0.25,
            "length": 0.20,
            "anchor_distance": 0.20,
            "resonance": 0.20,
            "aggressor": 0.15,
        }
    )


@dataclass
class FixConfig:
    """Automatic remediation planner and mutation settings."""

    dry_run: bool = True
    minimum_apply_confidence: float = 0.75
    track_width_mm: float = 0.20
    maximum_bridge_length_mm: float = 6.00
    via_diameter_mm: float = 0.60
    via_drill_mm: float = 0.30
    via_clearance_mm: float = 0.25
    maximum_via_search_radius_mm: float = 3.00
    rule_area_margin_mm: float = 0.00
    allow_rule_area_fallback: bool = True
    allow_combined_track_via: bool = True
    refill_zones_after_apply: bool = True
    create_single_undo_group: bool = True
    adaptive_track_width: bool = True
    maximum_track_width_mm: float = 2.00
    prefer_rule_area_for_appendages: bool = True
    reject_redundant_same_plane_tracks: bool = True
    board_edge_clearance_mm: float = 0.10
    require_board_outline_for_new_copper: bool = True
    require_proven_safe_rule_area: bool = True


@dataclass
class NoiseConfig:
    """Qualitative board-noise analyzer settings."""

    endpoint_snap_mm: float = 0.05
    dangling_stub_min_length_mm: float = 0.80
    parallel_angle_tolerance_deg: float = 5.0
    parallel_spacing_warning_mm: float = 0.50
    parallel_overlap_warning_mm: float = 5.0
    acute_corner_warning_deg: float = 75.0
    corner_pad_exclusion: bool = True
    corner_pad_clearance_mm: float = 0.10
    corner_min_segment_length_mm: float = 0.50
    corner_skip_complex_junctions: bool = True
    trace_length_warning_mm: float = 50.0
    signal_rise_time_ns: float = 1.0
    critical_length_fraction: float = 1.0 / 6.0
    long_net_trigger_mode: str = "both_or_severe"
    long_net_severe_multiplier: float = 1.50
    long_net_diameter_scan_limit: int = 32
    long_net_ignore_regex: str = r"^(?:GND|AGND|DGND|PGND|VSS|VCC|VDD|VBAT|3V3|5V|12V)(?:[_-].*)?$"
    return_via_radius_mm: float = 2.0
    skip_return_via_check_on_two_layer: bool = True
    reference_plane_sample_step_mm: float = 0.50
    reference_gap_min_length_mm: float = 3.00
    reference_gap_min_track_length_mm: float = 5.00
    reference_gap_min_fraction: float = 0.30
    reference_gap_endpoint_exclusion_mm: float = 0.75
    reference_gap_ignore_regex: str = r"^(?:GND|AGND|DGND|PGND|VSS|VCC|VDD|VBAT|3V3|5V|12V)(?:[_-].*)?$"
    ground_bottleneck_width_mm: float = 1.00
    ground_bottleneck_min_anchor_count: int = 2
    ground_detour_warning_ratio: float = 4.00
    ground_detour_min_length_mm: float = 5.00
    ground_detour_min_active_length_mm: float = 1.00
    ground_detour_min_excess_mm: float = 5.00
    board_edge_signal_clearance_mm: float = 1.0
    differential_pair_name_regex: str = r"(?P<base>.+?)(?P<polarity>[PN+-])$"
    differential_pair_mismatch_warning_mm: float = 1.0
    score_weights: dict[str, float] = field(
        default_factory=lambda: {
            "antenna": 0.30,
            "parallel": 0.20,
            "corner": 0.10,
            "length": 0.15,
            "return_path": 0.15,
            "other": 0.10,
        }
    )


@dataclass
class QuantitativeConfig:
    """Fast electrical-estimate settings."""

    enabled: bool = True
    default_dielectric_constant: float = 4.2
    default_loss_tangent: float = 0.02
    default_reference_height_mm: float = 0.18
    default_copper_thickness_mm: float = 0.035
    frequency_samples_mhz: list[float] = field(default_factory=lambda: [30.0, 100.0, 300.0, 1000.0])
    external_solver: str = "none"
    openems_executable: str = ""
    openems_mesh_mm: float = 0.25
    openems_max_cells: int = 5_000_000


@dataclass
class SilkscreenConfig:
    """Footprint value-field placement settings."""

    text_width_mm: float = 0.80
    text_height_mm: float = 0.80
    text_thickness_mm: float = 0.10
    hide_reference: bool = True
    show_value: bool = True
    minimum_via_clearance_mm: float = 0.20
    minimum_pad_clearance_mm: float = 0.20
    minimum_edge_clearance_mm: float = 0.30
    minimum_text_clearance_mm: float = 0.15
    candidate_offset_mm: float = 0.50
    candidate_ring_step_mm: float = 0.60
    candidate_rings: int = 3
    preserve_existing_angle: bool = False
    allowed_angles_deg: list[float] = field(default_factory=lambda: [0.0, 90.0, 45.0, -45.0])
    maximum_distance_from_footprint_mm: float = 2.50
    allow_on_footprint_fallback: bool = True
    hide_value_patterns: list[str] = field(
        default_factory=lambda: [r"(?i)mounting\s*hole", r"(?i)^logo(?:$|[_-])"]
    )
    move_reference_to_fab: bool = True
    keep_upright: bool = True
    skip_locked_footprints: bool = True


@dataclass
class EdgeConfig:
    """Board-outline optimizer settings."""

    mode: str = "diagonal"
    grid_mm: float = 0.50
    component_margin_mm: float = 1.50
    copper_margin_mm: float = 0.50
    minimum_ground_band_mm: float = 1.00
    fillet_radius_mm: float = 1.00
    edge_width_mm: float = 0.05
    simplify_tolerance_mm: float = 0.25
    outline_strategy: str = "convex_preserve_existing_concavities"
    target_vertex_count: int = 8
    preserve_existing_concavities: bool = True
    allow_concave_outline: bool = False
    allow_diagonal_edges: bool = True
    preserve_mounting_holes: bool = True
    maximum_area_reduction_percent: float = 35.0
    allow_destructive_edge_replacement: bool = False
    require_explicit_backup: bool = True
    reject_area_increase: bool = True
    maximum_area_increase_percent: float = 0.0
    preserve_existing_outline_when_smaller: bool = True
    perimeter_via_rebuild_default: bool = False


@dataclass
class StitchingConfig:
    """Ground-via stitching planner settings."""

    enabled: bool = True
    net_regex: str = r"^(?:GND|AGND|DGND|PGND|GNDA|GNDD|VSS)(?:[_-].*)?$"
    spacing_mm: float = 5.00
    edge_offset_mm: float = 1.00
    vertex_offset_mm: float = 1.20
    minimum_spacing_mm: float = 2.50
    via_diameter_mm: float = 0.60
    via_drill_mm: float = 0.30
    clearance_mm: float = 0.25
    require_ground_on_both_layers: bool = True
    maximum_vias: int = 1000
    rebuild_perimeter: bool = False
    removable_band_mm: float = 2.00


@dataclass
class PlacementConfig:
    """Schematic-block initial-placement proposal settings."""

    group_spacing_mm: float = 8.00
    component_spacing_mm: float = 1.50
    block_max_width_mm: float = 45.00
    capacitor_reference_regex: str = r"^C[0-9]+"
    capacitor_value_regex: str = r"(?i)(?:[0-9.]+\s*(?:p|n|u|µ|m)?f|decoupl|bypass)"
    connector_reference_regex: str = r"^(?:J|P|CN)[0-9]+"
    preserve_locked_footprints: bool = True
    use_sheet_path: bool = True
    dry_run_only: bool = True


@dataclass
class ManufacturingConfig:
    """JLCPCB order assumptions and active DFM constraint values."""

    vendor: str = "jlcpcb"
    profile_id: str = "jlcpcb_2l_economy"
    layer_count: int = 2
    board_thickness_mm: float = 1.60
    solder_mask_color: str = "green"
    silkscreen_color: str = "white"
    copper_weight_oz: float = 1.00
    surface_finish: str = "hasl_leaded"
    board_separation: str = "routing"
    selected_track_width_mm: float = 0.20
    selected_track_widths_mm: list[float] = field(default_factory=lambda: [0.20])
    selected_via_preset_id: str = "kicad_default"
    selected_via_preset_ids: list[str] = field(default_factory=lambda: ["kicad_default"])
    enforce_on_automatic_fixes: bool = True
    apply_profile_to_silkscreen: bool = False
    minimum_track_width_mm: float = 0.20
    minimum_clearance_mm: float = 0.20
    minimum_via_diameter_mm: float = 0.45
    minimum_via_drill_mm: float = 0.30
    minimum_via_annular_ring_mm: float = 0.075
    minimum_via_to_track_mm: float = 0.20
    minimum_hole_to_hole_mm: float = 0.20
    minimum_copper_to_routed_edge_mm: float = 0.30
    minimum_copper_to_v_cut_mm: float = 0.40
    minimum_npth_diameter_mm: float = 0.50
    minimum_plated_slot_width_mm: float = 0.50
    minimum_unplated_slot_width_mm: float = 1.00
    minimum_solder_mask_bridge_mm: float = 0.10
    minimum_silkscreen_line_width_mm: float = 0.15
    minimum_silkscreen_text_height_mm: float = 1.00
    minimum_pad_to_silkscreen_mm: float = 0.15
    verified_date: str = JLCPCB_VERIFIED_DATE

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable mapping."""

        return asdict(self)

    def order_settings(self) -> dict[str, Any]:
        """Return the subset copied into JLCPCB order notes."""

        return {
            "vendor": self.vendor,
            "profile_id": self.profile_id,
            "layer_count": self.layer_count,
            "board_thickness_mm": self.board_thickness_mm,
            "solder_mask_color": self.solder_mask_color,
            "silkscreen_color": self.silkscreen_color,
            "copper_weight_oz": self.copper_weight_oz,
            "surface_finish": self.surface_finish,
            "board_separation": self.board_separation,
            "selected_track_width_mm": self.selected_track_width_mm,
            "selected_track_widths_mm": list(self.selected_track_widths_mm),
            "selected_via_preset_id": self.selected_via_preset_id,
            "selected_via_preset_ids": list(self.selected_via_preset_ids),
            "verified_date": self.verified_date,
        }


@dataclass
class UiConfig:
    """Local dashboard settings."""

    language: str = "auto"
    open_browser: bool = True
    bind_address: str = "127.0.0.1"
    inactivity_timeout_minutes: int = 0
    heartbeat_seconds: int = 20
    ipc_retry_count: int = 2
    report_directory: str = ""


@dataclass
class AppConfig:
    """Top-level configuration."""

    schema_version: int = CURRENT_SCHEMA_VERSION
    antenna: AntennaConfig = field(default_factory=AntennaConfig)
    fixes: FixConfig = field(default_factory=FixConfig)
    noise: NoiseConfig = field(default_factory=NoiseConfig)
    quantitative: QuantitativeConfig = field(default_factory=QuantitativeConfig)
    silkscreen: SilkscreenConfig = field(default_factory=SilkscreenConfig)
    edge: EdgeConfig = field(default_factory=EdgeConfig)
    stitching: StitchingConfig = field(default_factory=StitchingConfig)
    placement: PlacementConfig = field(default_factory=PlacementConfig)
    manufacturing: ManufacturingConfig = field(default_factory=ManufacturingConfig)
    ui: UiConfig = field(default_factory=UiConfig)

    def validate(self) -> None:
        """Validate values and raise :class:`ValidationError` on failure."""

        positive_values = {
            "antenna.raster_step_mm": self.antenna.raster_step_mm,
            "antenna.narrow_neck_width_mm": self.antenna.narrow_neck_width_mm,
            "antenna.max_raster_cells": self.antenna.max_raster_cells,
            "fixes.track_width_mm": self.fixes.track_width_mm,
            "fixes.via_diameter_mm": self.fixes.via_diameter_mm,
            "fixes.via_drill_mm": self.fixes.via_drill_mm,
            "fixes.maximum_bridge_length_mm": self.fixes.maximum_bridge_length_mm,
            "fixes.maximum_track_width_mm": self.fixes.maximum_track_width_mm,
            "antenna.connectivity_tolerance_mm": self.antenna.connectivity_tolerance_mm,
            "antenna.minimum_unanchored_component_area_mm2": self.antenna.minimum_unanchored_component_area_mm2,
            "antenna.required_ground_connection_width_mm": self.antenna.required_ground_connection_width_mm,
            "antenna.pad_protection_margin_mm": self.antenna.pad_protection_margin_mm,
            "antenna.via_protection_margin_mm": self.antenna.via_protection_margin_mm,
            "antenna.explicit_track_protection_margin_mm": self.antenna.explicit_track_protection_margin_mm,
            "antenna.perimeter_ground_protection_mm": self.antenna.perimeter_ground_protection_mm,
            "fixes.board_edge_clearance_mm": self.fixes.board_edge_clearance_mm,
            "noise.corner_pad_clearance_mm": self.noise.corner_pad_clearance_mm,
            "noise.corner_min_segment_length_mm": self.noise.corner_min_segment_length_mm,
            "noise.long_net_severe_multiplier": self.noise.long_net_severe_multiplier,
            "noise.long_net_diameter_scan_limit": self.noise.long_net_diameter_scan_limit,
            "noise.reference_plane_sample_step_mm": self.noise.reference_plane_sample_step_mm,
            "noise.reference_gap_min_length_mm": self.noise.reference_gap_min_length_mm,
            "noise.reference_gap_min_track_length_mm": self.noise.reference_gap_min_track_length_mm,
            "noise.reference_gap_endpoint_exclusion_mm": self.noise.reference_gap_endpoint_exclusion_mm,
            "noise.ground_detour_min_length_mm": self.noise.ground_detour_min_length_mm,
            "noise.ground_detour_min_active_length_mm": self.noise.ground_detour_min_active_length_mm,
            "noise.ground_detour_min_excess_mm": self.noise.ground_detour_min_excess_mm,
            "noise.ground_bottleneck_width_mm": self.noise.ground_bottleneck_width_mm,
            "noise.ground_bottleneck_min_anchor_count": self.noise.ground_bottleneck_min_anchor_count,
            "noise.ground_detour_warning_ratio": self.noise.ground_detour_warning_ratio,
            "silkscreen.text_width_mm": self.silkscreen.text_width_mm,
            "silkscreen.text_height_mm": self.silkscreen.text_height_mm,
            "silkscreen.text_thickness_mm": self.silkscreen.text_thickness_mm,
            "silkscreen.candidate_rings": self.silkscreen.candidate_rings,
            "edge.grid_mm": self.edge.grid_mm,
            "edge.fillet_radius_mm": self.edge.fillet_radius_mm,
            "edge.minimum_ground_band_mm": self.edge.minimum_ground_band_mm,
            "stitching.spacing_mm": self.stitching.spacing_mm,
            "stitching.edge_offset_mm": self.stitching.edge_offset_mm,
            "stitching.vertex_offset_mm": self.stitching.vertex_offset_mm,
            "stitching.minimum_spacing_mm": self.stitching.minimum_spacing_mm,
            "stitching.via_diameter_mm": self.stitching.via_diameter_mm,
            "stitching.via_drill_mm": self.stitching.via_drill_mm,
            "stitching.clearance_mm": self.stitching.clearance_mm,
            "stitching.maximum_vias": self.stitching.maximum_vias,
            "stitching.removable_band_mm": self.stitching.removable_band_mm,
            "placement.group_spacing_mm": self.placement.group_spacing_mm,
            "placement.component_spacing_mm": self.placement.component_spacing_mm,
            "placement.block_max_width_mm": self.placement.block_max_width_mm,
            "quantitative.openems_mesh_mm": self.quantitative.openems_mesh_mm,
            "quantitative.openems_max_cells": self.quantitative.openems_max_cells,
            "manufacturing.layer_count": self.manufacturing.layer_count,
            "manufacturing.board_thickness_mm": self.manufacturing.board_thickness_mm,
            "manufacturing.selected_track_width_mm": self.manufacturing.selected_track_width_mm,
            "manufacturing.minimum_track_width_mm": self.manufacturing.minimum_track_width_mm,
            "manufacturing.minimum_clearance_mm": self.manufacturing.minimum_clearance_mm,
            "manufacturing.minimum_via_diameter_mm": self.manufacturing.minimum_via_diameter_mm,
            "manufacturing.minimum_via_drill_mm": self.manufacturing.minimum_via_drill_mm,
            "manufacturing.minimum_via_annular_ring_mm": self.manufacturing.minimum_via_annular_ring_mm,
            "manufacturing.minimum_via_to_track_mm": self.manufacturing.minimum_via_to_track_mm,
            "manufacturing.minimum_hole_to_hole_mm": self.manufacturing.minimum_hole_to_hole_mm,
            "manufacturing.minimum_copper_to_routed_edge_mm": self.manufacturing.minimum_copper_to_routed_edge_mm,
            "manufacturing.minimum_copper_to_v_cut_mm": self.manufacturing.minimum_copper_to_v_cut_mm,
            "manufacturing.minimum_silkscreen_line_width_mm": self.manufacturing.minimum_silkscreen_line_width_mm,
            "manufacturing.minimum_silkscreen_text_height_mm": self.manufacturing.minimum_silkscreen_text_height_mm,
            "ui.heartbeat_seconds": self.ui.heartbeat_seconds,
        }
        invalid = [name for name, value in positive_values.items() if value <= 0]
        if invalid:
            raise ValidationError("Values must be positive: " + ", ".join(invalid))
        if self.fixes.via_drill_mm >= self.fixes.via_diameter_mm:
            raise ValidationError("Via drill diameter must be smaller than the via diameter.")
        if self.stitching.via_drill_mm >= self.stitching.via_diameter_mm:
            raise ValidationError("Stitching-via drill diameter must be smaller than its diameter.")
        if self.fixes.maximum_track_width_mm < self.fixes.track_width_mm:
            raise ValidationError("fixes.maximum_track_width_mm must not be smaller than track_width_mm.")
        if self.edge.mode not in {"orthogonal", "diagonal"}:
            raise ValidationError("edge.mode must be either 'orthogonal' or 'diagonal'.")
        if self.edge.outline_strategy not in {
            "convex",
            "convex_preserve_existing_concavities",
            "legacy_concave",
        }:
            raise ValidationError("Unknown edge.outline_strategy.")
        if not 4 <= self.edge.target_vertex_count <= 64:
            raise ValidationError("edge.target_vertex_count must be between 4 and 64.")
        if not 0.0 < self.noise.reference_gap_min_fraction <= 1.0:
            raise ValidationError("noise.reference_gap_min_fraction must be in (0, 1].")
        if not 0.0 < self.noise.acute_corner_warning_deg < 180.0:
            raise ValidationError("noise.acute_corner_warning_deg must be in (0, 180).")
        if not 2 <= self.noise.long_net_diameter_scan_limit <= 128:
            raise ValidationError("noise.long_net_diameter_scan_limit must be between 2 and 128.")
        if self.noise.long_net_trigger_mode not in {"either", "both", "both_or_severe"}:
            raise ValidationError("Unknown noise.long_net_trigger_mode.")
        if self.ui.inactivity_timeout_minutes < 0:
            raise ValidationError("ui.inactivity_timeout_minutes must be zero or positive.")
        if self.ui.ipc_retry_count < 0 or self.ui.ipc_retry_count > 10:
            raise ValidationError("ui.ipc_retry_count must be between 0 and 10.")
        if not 0.0 <= self.edge.maximum_area_reduction_percent < 100.0:
            raise ValidationError("maximum_area_reduction_percent must be in [0, 100).")
        if not 0.0 <= self.edge.maximum_area_increase_percent < 100.0:
            raise ValidationError("maximum_area_increase_percent must be in [0, 100).")
        if not self.silkscreen.allowed_angles_deg:
            raise ValidationError("At least one silkscreen angle must be configured.")
        if any(not -360.0 <= float(value) <= 360.0 for value in self.silkscreen.allowed_angles_deg):
            raise ValidationError("Silkscreen angles must be in [-360, 360].")
        if not 0.0 <= self.fixes.minimum_apply_confidence <= 1.0:
            raise ValidationError("minimum_apply_confidence must be between 0 and 1.")
        if sum(self.antenna.severity_weights.values()) <= 0.0:
            raise ValidationError("antenna.severity_weights must have a positive sum.")
        if sum(self.noise.score_weights.values()) <= 0.0:
            raise ValidationError("noise.score_weights must have a positive sum.")
        if any(value <= 0.0 for value in self.quantitative.frequency_samples_mhz):
            raise ValidationError("All quantitative frequency samples must be positive.")
        if self.manufacturing.vendor != "jlcpcb":
            raise ValidationError("Only the JLCPCB manufacturing provider is supported in this release.")
        if self.manufacturing.profile_id not in MANUFACTURING_PROFILES:
            raise ValidationError("Unknown manufacturing.profile_id.")
        if self.manufacturing.layer_count != 2:
            raise ValidationError("The bundled JLCPCB profiles currently support exactly two copper layers.")
        if self.manufacturing.board_thickness_mm not in JLCPCB_2L_THICKNESSES_MM:
            raise ValidationError("Unsupported JLCPCB two-layer board thickness.")
        if self.manufacturing.solder_mask_color not in JLCPCB_SOLDER_MASK_COLORS:
            raise ValidationError("Unsupported JLCPCB solder-mask color.")
        if self.manufacturing.silkscreen_color not in JLCPCB_SILKSCREEN_COLORS:
            raise ValidationError("Unsupported JLCPCB silkscreen color.")
        if self.manufacturing.copper_weight_oz not in JLCPCB_2L_COPPER_WEIGHTS_OZ:
            raise ValidationError("Unsupported JLCPCB two-layer copper weight.")
        if self.manufacturing.surface_finish not in JLCPCB_SURFACE_FINISHES:
            raise ValidationError("Unsupported JLCPCB surface finish.")
        if self.manufacturing.board_separation not in JLCPCB_BOARD_SEPARATION_METHODS:
            raise ValidationError("manufacturing.board_separation must be 'routing' or 'v_cut'.")
        if self.manufacturing.selected_via_preset_id not in VIA_PRESETS:
            raise ValidationError("Unknown manufacturing.selected_via_preset_id.")
        if not self.manufacturing.selected_track_widths_mm:
            raise ValidationError("At least one manufacturing track-width preset must be selected.")
        if any(float(value) <= 0.0 for value in self.manufacturing.selected_track_widths_mm):
            raise ValidationError("Selected manufacturing track widths must be positive.")
        if not self.manufacturing.selected_via_preset_ids:
            raise ValidationError("At least one manufacturing via preset must be selected.")
        unknown_vias = [
            value for value in self.manufacturing.selected_via_preset_ids if value not in VIA_PRESETS
        ]
        if unknown_vias:
            raise ValidationError("Unknown manufacturing selected_via_preset_ids: " + ", ".join(unknown_vias))
        if self.manufacturing.enforce_on_automatic_fixes:
            if self.fixes.track_width_mm < self.manufacturing.minimum_track_width_mm:
                raise ValidationError("Automatic-fix track width is below the active manufacturing profile.")
            if self.fixes.via_diameter_mm < self.manufacturing.minimum_via_diameter_mm:
                raise ValidationError("Automatic-fix via diameter is below the active manufacturing profile.")
            if self.fixes.via_drill_mm < self.manufacturing.minimum_via_drill_mm:
                raise ValidationError("Automatic-fix via drill is below the active manufacturing profile.")
            annular_ring = (self.fixes.via_diameter_mm - self.fixes.via_drill_mm) / 2.0
            if annular_ring < self.manufacturing.minimum_via_annular_ring_mm:
                raise ValidationError(
                    "Automatic-fix via annular ring is below the active manufacturing profile."
                )
        if self.ui.bind_address not in {"127.0.0.1", "localhost", "::1"}:
            raise ValidationError("ui.bind_address must be a loopback address.")
        try:
            re.compile(self.antenna.ground_net_regex)
            re.compile(self.noise.differential_pair_name_regex)
            re.compile(self.noise.long_net_ignore_regex)
            re.compile(self.noise.reference_gap_ignore_regex)
            re.compile(self.stitching.net_regex)
            re.compile(self.placement.capacitor_reference_regex)
            re.compile(self.placement.capacitor_value_regex)
            re.compile(self.placement.connector_reference_regex)
            for pattern in self.silkscreen.hide_value_patterns:
                re.compile(pattern)
        except re.error as exc:
            raise ValidationError(f"Invalid regular expression: {exc}") from exc

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable mapping."""

        return asdict(self)


T = TypeVar("T")


def _merge_dataclass(instance: T, values: Mapping[str, Any]) -> T:
    """Merge a mapping into a dataclass instance, ignoring unknown keys."""

    known_fields = {item.name: item for item in fields(cast(Any, instance))}
    for key, value in values.items():
        descriptor = known_fields.get(key)
        if descriptor is None:
            continue
        current = getattr(instance, key)
        if is_dataclass(current) and isinstance(value, Mapping):
            _merge_dataclass(current, value)
        else:
            setattr(instance, key, deepcopy(value))
    return instance


def config_from_mapping(values: Mapping[str, Any]) -> AppConfig:
    """Build and validate a configuration from a mapping."""

    supplied_version = values.get("schema_version", 1)
    if isinstance(supplied_version, int) and supplied_version > CURRENT_SCHEMA_VERSION:
        raise ValidationError("The configuration was created by a newer EMI Guardian schema.")
    migrated_values = deepcopy(dict(values))
    manufacturing_values = migrated_values.get("manufacturing")
    if isinstance(manufacturing_values, Mapping):
        manufacturing_values = dict(manufacturing_values)
        if manufacturing_values.get("selected_via_preset_id") == "jlcpcb_economy":
            manufacturing_values["selected_via_preset_id"] = "kicad_default"
        primary_width = float(manufacturing_values.get("selected_track_width_mm", 0.20))
        widths = manufacturing_values.get("selected_track_widths_mm")
        if not isinstance(widths, list) or not widths:
            manufacturing_values["selected_track_widths_mm"] = [primary_width]
        primary_via = str(manufacturing_values.get("selected_via_preset_id", "kicad_default"))
        via_ids = manufacturing_values.get("selected_via_preset_ids")
        if not isinstance(via_ids, list) or not via_ids:
            manufacturing_values["selected_via_preset_ids"] = [primary_via]
        migrated_values["manufacturing"] = manufacturing_values
    edge_values = migrated_values.get("edge")
    if isinstance(edge_values, Mapping):
        edge_values = dict(edge_values)
        if edge_values.get("mode") == "diagonal":
            edge_values["allow_diagonal_edges"] = True
        migrated_values["edge"] = edge_values
    config = _merge_dataclass(AppConfig(), migrated_values)
    config.schema_version = CURRENT_SCHEMA_VERSION
    config.validate()
    return config


def load_config(path: Path) -> AppConfig:
    """Load a configuration file, creating it with defaults when absent."""

    if not path.exists():
        config = AppConfig()
        save_config(path, config)
        return config
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, Mapping):
        raise ValidationError("The configuration root must be a JSON object.")
    return config_from_mapping(data)


def save_config(path: Path, config: AppConfig) -> None:
    """Persist a validated configuration atomically."""

    config.validate()
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(config.to_dict(), ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)
