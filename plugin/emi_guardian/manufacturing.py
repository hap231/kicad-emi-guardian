"""JLCPCB profile application, manufacturability checks, and export support."""

from __future__ import annotations

import json
import math
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from .config import AppConfig
from .geometry import point_segment_distance, segment_distance
from .localization import localize_manufacturing_issue
from .manufacturing_profiles import (
    JLCPCB_2L_THICKNESSES_MM,
    JLCPCB_SOLDER_MASK_COLORS,
    JLCPCB_VERIFIED_DATE,
    MANUFACTURING_PROFILES,
    TRACK_WIDTH_PRESETS_MM,
    VIA_PRESETS,
    ManufacturingProfile,
    manufacturing_catalog,
    profile,
    via_preset,
)
from .models import BoardEdge, BoardSnapshot, BoundingBox, Point, TrackSegment, Via, bounds_from_points


@dataclass(frozen=True)
class ManufacturingIssue:
    """One JLCPCB DFM finding."""

    issue_id: str
    code: str
    severity: str
    category: str
    title: str
    description: str
    recommendation: str
    item_ids: tuple[str, ...] = ()
    measured: float | str | None = None
    limit: float | str | None = None
    unit: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable mapping with localized presentation text."""

        payload = asdict(self)
        payload["localized"] = localize_manufacturing_issue(
            self.code,
            self.title,
            self.description,
            self.recommendation,
        )
        return payload


@dataclass(frozen=True)
class ManufacturingReport:
    """Complete profile-based manufacturability result."""

    board_name: str
    profile_id: str
    profile_name_en: str
    profile_name_ja: str
    verified_date: str
    status: str
    score: float
    issues: tuple[ManufacturingIssue, ...]
    detected: Mapping[str, Any]
    order_settings: Mapping[str, Any]
    constraints: Mapping[str, Any]
    statistics: Mapping[str, Any]
    assumptions: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable mapping."""

        return {
            "schema_version": 1,
            "vendor": "JLCPCB",
            "board_name": self.board_name,
            "profile_id": self.profile_id,
            "profile_name_en": self.profile_name_en,
            "profile_name_ja": self.profile_name_ja,
            "verified_date": self.verified_date,
            "status": self.status,
            "score": self.score,
            "issues": [item.to_dict() for item in self.issues],
            "detected": dict(self.detected),
            "order_settings": dict(self.order_settings),
            "constraints": dict(self.constraints),
            "statistics": dict(self.statistics),
            "assumptions": list(self.assumptions),
        }


def catalog_payload(config: AppConfig) -> dict[str, Any]:
    """Return catalogue data with the active selections attached."""

    payload = manufacturing_catalog()
    payload["selected"] = config.manufacturing.to_dict()
    payload["ipc_behavior"] = {
        "stackup_read": True,
        "stackup_write_kicad_10": False,
        "design_rule_write_kicad_10": False,
        "workflow": "validate_and_export",
    }
    return payload


def profile_patch(
    profile_id: str,
    *,
    track_width_mm: float | None = None,
    via_preset_id: str | None = None,
    track_widths_mm: Sequence[float] | None = None,
    via_preset_ids: Sequence[str] | None = None,
    board_thickness_mm: float | None = None,
    solder_mask_color: str | None = None,
    apply_silkscreen_limits: bool = False,
) -> dict[str, Any]:
    """Build a configuration patch for one manufacturing profile.

    The patch updates automatic-fix geometry because those items are written by
    the plugin.  Silkscreen dimensions are changed only when explicitly
    requested so the original 0.8 mm user default remains available.
    """

    selected = profile(profile_id)
    requested_widths = list(dict.fromkeys(float(value) for value in (track_widths_mm or ())))
    if not requested_widths:
        requested_widths = [
            float(track_width_mm) if track_width_mm is not None else selected.default_track_width_mm
        ]
    requested_vias = list(dict.fromkeys(str(value) for value in (via_preset_ids or ())))
    if not requested_vias:
        requested_vias = [via_preset_id or selected.default_via_preset_id]
    available_vias = [via_preset(preset_id) for preset_id in requested_vias]

    # Preset checkboxes describe the routing catalogue available to the user.
    # Automatic repairs must still honor the active profile.  Prefer the
    # profile default when it was selected, otherwise choose the first
    # compatible selection and finally fall back to the safe profile default.
    compatible_widths = [
        value for value in requested_widths if value + 1e-9 >= selected.minimum_track_width_mm
    ]
    if selected.default_track_width_mm in requested_widths:
        selected_width = selected.default_track_width_mm
    elif compatible_widths:
        selected_width = min(compatible_widths)
    else:
        selected_width = selected.default_track_width_mm

    def via_is_compatible(candidate: Any) -> bool:
        return bool(
            candidate.diameter_mm + 1e-9 >= selected.minimum_via_diameter_mm
            and candidate.drill_mm + 1e-9 >= selected.minimum_via_drill_mm
            and candidate.annular_ring_mm + 1e-9 >= selected.minimum_via_annular_ring_mm
        )

    default_via = via_preset(selected.default_via_preset_id)
    selected_via = next(
        (candidate for candidate in available_vias if candidate.preset_id == selected.default_via_preset_id),
        None,
    )
    if selected_via is None:
        selected_via = next(
            (candidate for candidate in available_vias if via_is_compatible(candidate)), default_via
        )
    thickness = board_thickness_mm if board_thickness_mm is not None else selected.default_board_thickness_mm
    mask_color = solder_mask_color or selected.default_solder_mask_color
    silk_color = "black" if mask_color == "white" else "white"

    patch: dict[str, Any] = {
        "manufacturing": {
            "vendor": "jlcpcb",
            "profile_id": selected.profile_id,
            "layer_count": selected.layer_count,
            "board_thickness_mm": thickness,
            "solder_mask_color": mask_color,
            "silkscreen_color": silk_color,
            "copper_weight_oz": selected.default_copper_weight_oz,
            "surface_finish": selected.default_surface_finish,
            "selected_track_width_mm": selected_width,
            "selected_track_widths_mm": requested_widths,
            "selected_via_preset_id": selected_via.preset_id,
            "selected_via_preset_ids": requested_vias,
            "minimum_track_width_mm": selected.minimum_track_width_mm,
            "minimum_clearance_mm": selected.minimum_clearance_mm,
            "minimum_via_diameter_mm": selected.minimum_via_diameter_mm,
            "minimum_via_drill_mm": selected.minimum_via_drill_mm,
            "minimum_via_annular_ring_mm": selected.minimum_via_annular_ring_mm,
            "minimum_via_to_track_mm": selected.minimum_via_to_track_mm,
            "minimum_hole_to_hole_mm": selected.minimum_hole_to_hole_mm,
            "minimum_copper_to_routed_edge_mm": selected.minimum_copper_to_routed_edge_mm,
            "minimum_copper_to_v_cut_mm": selected.minimum_copper_to_v_cut_mm,
            "minimum_npth_diameter_mm": selected.minimum_npth_diameter_mm,
            "minimum_plated_slot_width_mm": selected.minimum_plated_slot_width_mm,
            "minimum_unplated_slot_width_mm": selected.minimum_unplated_slot_width_mm,
            "minimum_solder_mask_bridge_mm": selected.minimum_solder_mask_bridge_mm,
            "minimum_silkscreen_line_width_mm": selected.minimum_silkscreen_line_width_mm,
            "minimum_silkscreen_text_height_mm": selected.minimum_silkscreen_text_height_mm,
            "minimum_pad_to_silkscreen_mm": selected.minimum_pad_to_silkscreen_mm,
            "apply_profile_to_silkscreen": apply_silkscreen_limits,
            "verified_date": JLCPCB_VERIFIED_DATE,
        },
        "fixes": {
            "track_width_mm": selected_width,
            "via_diameter_mm": selected_via.diameter_mm,
            "via_drill_mm": selected_via.drill_mm,
            "via_clearance_mm": max(0.25, selected.minimum_via_to_track_mm),
        },
        "edge": {
            "copper_margin_mm": max(
                selected.minimum_copper_to_routed_edge_mm,
                0.50
                if selected.profile_id.endswith("economy")
                else selected.minimum_copper_to_routed_edge_mm,
            )
        },
    }
    if apply_silkscreen_limits:
        patch["silkscreen"] = {
            "text_width_mm": max(1.0, selected.minimum_silkscreen_text_height_mm),
            "text_height_mm": selected.minimum_silkscreen_text_height_mm,
            "text_thickness_mm": selected.minimum_silkscreen_line_width_mm,
            "minimum_pad_clearance_mm": selected.minimum_pad_to_silkscreen_mm,
        }
    return patch


def evaluate_manufacturability(snapshot: BoardSnapshot, config: AppConfig) -> ManufacturingReport:
    """Evaluate a board against the active JLCPCB profile.

    This is a geometric DFM pre-check.  It deliberately does not claim to
    replace JLCPCB's own file parser, quote engine, CAM review, or electrical
    test.
    """

    selected_profile = _active_profile(config)
    issues: list[ManufacturingIssue] = []
    counter = 0

    def add(
        code: str,
        severity: str,
        category: str,
        title: str,
        description: str,
        recommendation: str,
        *,
        item_ids: Sequence[str] = (),
        measured: float | str | None = None,
        limit: float | str | None = None,
        unit: str = "",
    ) -> None:
        nonlocal counter
        counter += 1
        issues.append(
            ManufacturingIssue(
                issue_id=f"JLC-{counter:04d}",
                code=code,
                severity=severity,
                category=category,
                title=title,
                description=description,
                recommendation=recommendation,
                item_ids=tuple(item_ids),
                measured=measured,
                limit=limit,
                unit=unit,
            )
        )

    _check_order_settings(config, selected_profile, add)
    board_bounds = _board_bounds(snapshot)
    _check_board_dimensions(board_bounds, config, add)
    _check_stackup_match(snapshot, config, add)
    _check_tracks(snapshot.tracks, config, add)
    _check_track_clearances(snapshot.tracks, config, add)
    _check_vias(snapshot.vias, snapshot.tracks, config, add)
    _check_copper_to_edge(snapshot, config, add)
    _check_silkscreen(snapshot, config, add)

    errors = sum(item.severity == "error" for item in issues)
    warnings = sum(item.severity == "warning" for item in issues)
    infos = sum(item.severity == "info" for item in issues)
    score = max(0.0, min(100.0, 100.0 - errors * 12.0 - warnings * 4.0 - infos * 0.5))
    status = "fail" if errors else ("review" if warnings else "pass")
    detected_stackup = snapshot.metadata.get("stackup", {})
    detected = {
        "board_width_mm": board_bounds.width,
        "board_height_mm": board_bounds.height,
        "track_count": len(snapshot.tracks),
        "via_count": len(snapshot.vias),
        "footprint_count": len(snapshot.footprints),
        "stackup": dict(detected_stackup) if isinstance(detected_stackup, Mapping) else detected_stackup,
    }
    statistics = {
        "error_count": errors,
        "warning_count": warnings,
        "info_count": infos,
        "issue_count": len(issues),
        "checked_track_count": len(snapshot.tracks),
        "checked_via_count": len(snapshot.vias),
    }
    assumptions = (
        "The active profile is based on JLCPCB information verified on 2026-08-13.",
        "Economy means no known fine-feature surcharge condition; it is not a price guarantee.",
        "KiCad 10 public IPC stackup/design-rule writes are not assumed; exported rules require user review.",
        "Pad drills, slots, solder-mask apertures, and arbitrary graphics may require JLCPCB's final DFM parser.",
    )
    return ManufacturingReport(
        board_name=snapshot.board_name,
        profile_id=selected_profile.profile_id,
        profile_name_en=selected_profile.name_en,
        profile_name_ja=selected_profile.name_ja,
        verified_date=JLCPCB_VERIFIED_DATE,
        status=status,
        score=score,
        issues=tuple(issues),
        detected=detected,
        order_settings=config.manufacturing.order_settings(),
        constraints=_constraint_values(config),
        statistics=statistics,
        assumptions=assumptions,
    )


def write_manufacturing_bundle(
    output_directory: Path,
    snapshot: BoardSnapshot,
    config: AppConfig,
    report: ManufacturingReport | None = None,
) -> dict[str, Path]:
    """Write JLCPCB settings, DFM results, presets, and custom-rule templates."""

    output_directory.mkdir(parents=True, exist_ok=True)
    result = report or evaluate_manufacturability(snapshot, config)
    selected_profile = _active_profile(config)

    report_json = output_directory / "jlcpcb-dfm-report.json"
    report_json.write_text(
        json.dumps(result.to_dict(), ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    order_json = output_directory / "jlcpcb-order-settings.json"
    order_json.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "vendor": "JLCPCB",
                "profile": selected_profile.to_dict(),
                "selected_order_settings": config.manufacturing.order_settings(),
                "verified_date": JLCPCB_VERIFIED_DATE,
                "price_disclaimer_en": selected_profile.cost_warning_en,
                "price_disclaimer_ja": selected_profile.cost_warning_ja,
            },
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    presets_json = output_directory / "routing-presets.json"
    presets_json.write_text(
        json.dumps(
            {
                "track_widths_mm": list(TRACK_WIDTH_PRESETS_MM),
                "via_presets": [item.to_dict() for item in VIA_PRESETS.values()],
            },
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    rules_path = output_directory / "emi-guardian-jlcpcb.kicad_dru"
    rules_path.write_text(render_kicad_custom_rules(config), encoding="utf-8")
    notes_path = output_directory / "JLCPCB-ORDER-NOTES.md"
    notes_path.write_text(render_order_notes(snapshot, config, result), encoding="utf-8")
    readme_path = output_directory / "README.txt"
    readme_path.write_text(_bundle_readme(), encoding="utf-8")
    return {
        "dfm_json": report_json,
        "order_settings": order_json,
        "routing_presets": presets_json,
        "kicad_custom_rules": rules_path,
        "order_notes": notes_path,
        "readme": readme_path,
    }


def render_kicad_custom_rules(config: AppConfig) -> str:
    """Render a KiCad 10 custom-rule template for the active profile."""

    values = config.manufacturing
    edge_clearance = (
        values.minimum_copper_to_v_cut_mm
        if values.board_separation == "v_cut"
        else values.minimum_copper_to_routed_edge_mm
    )
    return f"""# EMI Guardian JLCPCB custom-rule template
# Generated from profile: {values.profile_id}
# Capability data verified: {values.verified_date}
# Review and merge this file with existing project rules. Do not overwrite an
# existing <board-name>.kicad_dru without preserving its contents.

(version 1)

(rule "JLCPCB minimum copper clearance"
  (constraint clearance (min {_mm(values.minimum_clearance_mm)})))

(rule "JLCPCB minimum track width"
  (constraint track_width (min {_mm(values.minimum_track_width_mm)})))

(rule "JLCPCB minimum via diameter"
  (constraint via_diameter (min {_mm(values.minimum_via_diameter_mm)}))
  (condition "A.Type == 'Via'"))

(rule "JLCPCB minimum via drill"
  (constraint hole_size (min {_mm(values.minimum_via_drill_mm)}))
  (condition "A.Type == 'Via'"))

(rule "JLCPCB minimum via annular ring"
  (constraint annular_width (min {_mm(values.minimum_via_annular_ring_mm)}))
  (condition "A.Type == 'Via'"))

(rule "JLCPCB minimum mechanical hole spacing"
  (constraint hole_to_hole (min {_mm(values.minimum_hole_to_hole_mm)})))

(rule "JLCPCB copper to board edge"
  (constraint edge_clearance (min {_mm(edge_clearance)}))
  (condition "A.Type == 'Track' || A.Type == 'Via' || A.Type == 'Pad' || A.Type == 'Zone'"))

(rule "JLCPCB silkscreen clearance"
  (constraint silk_clearance (min {_mm(values.minimum_pad_to_silkscreen_mm)})))

(rule "JLCPCB minimum silkscreen text height"
  (layer "?.Silkscreen")
  (constraint text_height (min {_mm(values.minimum_silkscreen_text_height_mm)}))
  (condition "A.Type == 'Text' || A.Type == 'Text Box'"))

(rule "JLCPCB minimum silkscreen stroke"
  (layer "?.Silkscreen")
  (constraint text_thickness (min {_mm(values.minimum_silkscreen_line_width_mm)}))
  (condition "A.Type == 'Text' || A.Type == 'Text Box'"))
"""


def render_order_notes(
    snapshot: BoardSnapshot,
    config: AppConfig,
    report: ManufacturingReport,
) -> str:
    """Render bilingual, human-readable order notes."""

    selected_profile = _active_profile(config)
    settings = config.manufacturing.order_settings()
    issues = report.issues
    issue_lines = [
        f"- [{item.severity.upper()}] `{item.code}`: {item.title} — {item.description}" for item in issues
    ] or ["- No issues were found by the available geometric checks."]
    return "\n".join(
        [
            "# JLCPCB Order Notes / JLCPCB 発注メモ",
            "",
            f"- Board / 基板: `{snapshot.board_name}`",
            f"- Profile / プロファイル: **{selected_profile.name_en} / {selected_profile.name_ja}**",
            f"- Layers / 層数: **{settings['layer_count']}**",
            f"- Thickness / 板厚: **{settings['board_thickness_mm']} mm**",
            f"- Solder mask / レジスト色: **{settings['solder_mask_color']}**",
            f"- Silkscreen / シルク色: **{settings['silkscreen_color']}**",
            f"- Copper / 外層銅厚: **{settings['copper_weight_oz']} oz**",
            f"- Surface finish / 表面処理: **{settings['surface_finish']}**",
            f"- Separation / 分割方法: **{settings['board_separation']}**",
            f"- DFM status / DFM判定: **{report.status.upper()} ({report.score:.1f}/100)**",
            "",
            "## Review items / 確認事項",
            "",
            *issue_lines,
            "",
            "## Important / 重要",
            "",
            f"- {selected_profile.cost_warning_en}",
            f"- {selected_profile.cost_warning_ja}",
            "- Re-run KiCad DRC, JLCPCB DFM, Gerber preview, and the live quote before ordering.",
            "- 発注前にKiCad DRC、JLCPCB DFM、Gerberプレビュー、最新見積を再確認してください。",
            "",
        ]
    )


def _constraint_values(config: AppConfig) -> dict[str, float]:
    """Return the active numeric DFM limits for reports and exports."""

    values = config.manufacturing
    return {
        "minimum_track_width_mm": values.minimum_track_width_mm,
        "minimum_clearance_mm": values.minimum_clearance_mm,
        "minimum_via_diameter_mm": values.minimum_via_diameter_mm,
        "minimum_via_drill_mm": values.minimum_via_drill_mm,
        "minimum_via_annular_ring_mm": values.minimum_via_annular_ring_mm,
        "minimum_via_to_track_mm": values.minimum_via_to_track_mm,
        "minimum_hole_to_hole_mm": values.minimum_hole_to_hole_mm,
        "minimum_copper_to_routed_edge_mm": values.minimum_copper_to_routed_edge_mm,
        "minimum_copper_to_v_cut_mm": values.minimum_copper_to_v_cut_mm,
        "minimum_solder_mask_bridge_mm": values.minimum_solder_mask_bridge_mm,
        "minimum_silkscreen_line_width_mm": values.minimum_silkscreen_line_width_mm,
        "minimum_silkscreen_text_height_mm": values.minimum_silkscreen_text_height_mm,
        "minimum_pad_to_silkscreen_mm": values.minimum_pad_to_silkscreen_mm,
    }


def _active_profile(config: AppConfig) -> ManufacturingProfile:
    """Return the active profile while tolerating a custom derived profile."""

    return MANUFACTURING_PROFILES.get(
        config.manufacturing.profile_id,
        MANUFACTURING_PROFILES["jlcpcb_2l_economy"],
    )


def _check_order_settings(config: AppConfig, selected: ManufacturingProfile, add: Any) -> None:
    """Check selected order settings for profile compatibility."""

    values = config.manufacturing
    if values.layer_count != selected.layer_count:
        add(
            "ORDER_LAYER_COUNT",
            "error",
            "order",
            "Layer count does not match the selected profile",
            f"The profile is defined for {selected.layer_count} copper layers, but {values.layer_count} is selected.",
            "Select the 2-layer profile settings or create a separately validated multilayer profile.",
            measured=values.layer_count,
            limit=selected.layer_count,
            unit="layers",
        )
    if values.board_thickness_mm not in JLCPCB_2L_THICKNESSES_MM:
        add(
            "ORDER_THICKNESS_UNSUPPORTED",
            "error",
            "order",
            "Unsupported 2-layer board thickness",
            f"{values.board_thickness_mm:g} mm is not in the published 2-layer FR-4 selection list.",
            "Choose 0.4, 0.6, 0.8, 1.0, 1.2, 1.6, or 2.0 mm.",
            measured=values.board_thickness_mm,
            limit="published selection",
            unit="mm",
        )
    if values.solder_mask_color not in JLCPCB_SOLDER_MASK_COLORS:
        add(
            "ORDER_MASK_COLOR_UNSUPPORTED",
            "error",
            "order",
            "Unsupported solder-mask color",
            f"The selected color '{values.solder_mask_color}' is not in the published rigid-PCB color list.",
            "Choose green, purple, red, yellow, blue, white, or black.",
            measured=values.solder_mask_color,
            limit="published color list",
        )
    expected_silk = "black" if values.solder_mask_color == "white" else "white"
    if values.silkscreen_color != expected_silk:
        add(
            "ORDER_SILK_COLOR_MISMATCH",
            "warning",
            "order",
            "Silkscreen color differs from the standard mask-color pairing",
            f"JLCPCB normally uses {expected_silk} silkscreen with {values.solder_mask_color} solder mask.",
            f"Use {expected_silk} unless a supported special option is confirmed in the live quote.",
            measured=values.silkscreen_color,
            limit=expected_silk,
        )
    if values.board_thickness_mm == 0.4 and values.surface_finish != "enig":
        add(
            "ORDER_04MM_REQUIRES_ENIG",
            "error",
            "order",
            "0.4 mm boards require ENIG in the current quote workflow",
            "The selected surface finish is incompatible with the published 0.4 mm order restriction.",
            "Select ENIG or use a thicker board.",
            measured=values.surface_finish,
            limit="enig",
        )
    if values.board_thickness_mm == 0.4 and values.board_separation != "routing":
        add(
            "ORDER_04MM_NO_PANEL",
            "error",
            "order",
            "0.4 mm boards cannot use a panel separation workflow",
            "The current quote workflow states that 0.4 mm boards cannot be made as a panel.",
            "Select routed single-board delivery or use a thicker board.",
            measured=values.board_separation,
            limit="routing",
        )
    if values.board_thickness_mm == 0.6 and values.surface_finish == "hasl_leaded":
        add(
            "ORDER_06MM_HASL_LEADED",
            "error",
            "order",
            "0.6 mm two-layer boards do not support leaded HASL",
            "The quote page excludes leaded HASL for 0.6 mm two-layer boards.",
            "Select lead-free HASL or ENIG, or use another thickness.",
            measured=values.surface_finish,
            limit="hasl_lead_free or enig",
        )
    for preset_id in dict.fromkeys(values.selected_via_preset_ids):
        selected_via = VIA_PRESETS.get(preset_id)
        if selected_via and selected_via.surcharge_risk:
            add(
                "ORDER_SMALL_VIA_COST_RISK",
                "warning",
                "cost",
                "Selected via preset can trigger a paid small-via option",
                selected_via.description_en,
                "Use the KiCad 10 default / JLCPCB economy via preset unless density requires the limit preset.",
                measured=f"{selected_via.diameter_mm}/{selected_via.drill_mm}",
                limit="no-known-surcharge baseline",
                unit="mm diameter/drill",
            )


def _check_board_dimensions(bounds: BoundingBox, config: AppConfig, add: Any) -> None:
    """Check minimum and thickness-dependent maximum board dimensions."""

    if bounds.width <= 0.0 or bounds.height <= 0.0:
        add(
            "BOARD_OUTLINE_UNAVAILABLE",
            "warning",
            "outline",
            "Board dimensions could not be determined",
            "A closed Edge.Cuts outline was not available in the snapshot.",
            "Close the board outline and run the check again.",
        )
        return
    if bounds.width < 3.0 or bounds.height < 3.0:
        add(
            "BOARD_TOO_SMALL",
            "error",
            "outline",
            "Board is below the published 3 × 3 mm minimum",
            f"The detected bounding box is {bounds.width:.3f} × {bounds.height:.3f} mm.",
            "Panelize the design or enlarge the board.",
            measured=f"{bounds.width:.3f} x {bounds.height:.3f}",
            limit="3 x 3",
            unit="mm",
        )
    thickness = config.manufacturing.board_thickness_mm
    if thickness == 0.6:
        maximum = (100.0, 100.0)
    elif thickness in {0.8, 1.0}:
        maximum = (300.0, 300.0)
    elif thickness < 0.8:
        maximum = (599.0, 497.0)
    else:
        maximum = (670.0, 600.0)
    if bounds.width > maximum[0] or bounds.height > maximum[1]:
        add(
            "BOARD_TOO_LARGE_FOR_THICKNESS",
            "error",
            "outline",
            "Board exceeds the published size range for the selected thickness",
            f"The detected board is {bounds.width:.1f} × {bounds.height:.1f} mm; the applied limit is {maximum[0]:.0f} × {maximum[1]:.0f} mm.",
            "Use a supported thickness, reduce the outline, or confirm a special-size quote with JLCPCB.",
            measured=f"{bounds.width:.1f} x {bounds.height:.1f}",
            limit=f"{maximum[0]:.0f} x {maximum[1]:.0f}",
            unit="mm",
        )
    if bounds.width <= 30.0 or bounds.height <= 30.0:
        add(
            "BOARD_SMALL_SINGLE_COST_RISK",
            "info",
            "cost",
            "Small single-board orders can incur an extra handling charge",
            "JLCPCB documents an additional charge when either side is 30 mm or less and delivery is a single PCB.",
            "Use panelization or confirm the delivery format in the live quote.",
            measured=f"{bounds.width:.1f} x {bounds.height:.1f}",
            limit=">30 on both sides for this cost condition",
            unit="mm",
        )


def _check_stackup_match(snapshot: BoardSnapshot, config: AppConfig, add: Any) -> None:
    """Compare the active KiCad stackup with selected order assumptions."""

    raw = snapshot.metadata.get("stackup", {})
    if not isinstance(raw, Mapping):
        return
    detected_layers = raw.get("copper_layer_count")
    if isinstance(detected_layers, (int, float)) and int(detected_layers) != config.manufacturing.layer_count:
        add(
            "STACKUP_LAYER_MISMATCH",
            "error",
            "stackup",
            "KiCad copper-layer count differs from the order setting",
            f"KiCad reports {int(detected_layers)} copper layers while the JLCPCB order setting is {config.manufacturing.layer_count}.",
            "Align Board Setup and the plugin order setting before generating fabrication files.",
            measured=int(detected_layers),
            limit=config.manufacturing.layer_count,
            unit="layers",
        )
    detected_thickness = raw.get("board_thickness_mm")
    if (
        isinstance(detected_thickness, (int, float))
        and detected_thickness > 0
        and not math.isclose(float(detected_thickness), config.manufacturing.board_thickness_mm, abs_tol=0.05)
    ):
        add(
            "STACKUP_THICKNESS_MISMATCH",
            "warning",
            "stackup",
            "KiCad board thickness differs from the order setting",
            f"KiCad reports approximately {float(detected_thickness):.3f} mm while {config.manufacturing.board_thickness_mm:.3f} mm is selected for JLCPCB.",
            "Update Board Setup or the plugin order setting so both values agree.",
            measured=float(detected_thickness),
            limit=config.manufacturing.board_thickness_mm,
            unit="mm",
        )
    mask_colors = raw.get("solder_mask_colors")
    if isinstance(mask_colors, Sequence) and not isinstance(mask_colors, (str, bytes)):
        normalized = {str(value).strip().lower() for value in mask_colors if str(value).strip()}
        selected_color = config.manufacturing.solder_mask_color.lower()
        if normalized and selected_color not in normalized:
            add(
                "STACKUP_MASK_COLOR_MISMATCH",
                "warning",
                "stackup",
                "KiCad solder-mask color differs from the order setting",
                f"KiCad stackup colors are {sorted(normalized)}, while '{selected_color}' is selected for JLCPCB.",
                "Update the board stackup color manually or change the order setting.",
                measured=", ".join(sorted(normalized)),
                limit=selected_color,
            )


def _check_tracks(tracks: Sequence[TrackSegment], config: AppConfig, add: Any) -> None:
    """Check every routed segment width."""

    limit = config.manufacturing.minimum_track_width_mm
    for track in tracks:
        if track.width + 1e-9 < limit:
            add(
                "TRACK_WIDTH",
                "error",
                "copper",
                "Track is narrower than the active JLCPCB profile",
                f"Track {track.item_id} on {track.layer} is {track.width:.3f} mm wide.",
                f"Increase the segment to at least {limit:.3f} mm or use a separately reviewed local neck-down rule.",
                item_ids=(track.item_id,),
                measured=track.width,
                limit=limit,
                unit="mm",
            )


def _check_track_clearances(tracks: Sequence[TrackSegment], config: AppConfig, add: Any) -> None:
    """Check electrical copper clearance between different-net tracks."""

    limit = config.manufacturing.minimum_clearance_mm
    for first, second in _candidate_track_pairs(tracks, limit):
        if first.layer != second.layer or first.net == second.net:
            continue
        clearance = (
            segment_distance(first.start, first.end, second.start, second.end)
            - (first.width + second.width) / 2.0
        )
        if clearance + 1e-9 < limit:
            add(
                "TRACK_CLEARANCE",
                "error",
                "copper",
                "Different-net track clearance is below the profile",
                f"Tracks {first.item_id} and {second.item_id} have approximately {max(0.0, clearance):.3f} mm edge clearance on {first.layer}.",
                f"Increase clearance to at least {limit:.3f} mm.",
                item_ids=(first.item_id, second.item_id),
                measured=max(0.0, clearance),
                limit=limit,
                unit="mm",
            )


def _check_vias(vias: Sequence[Via], tracks: Sequence[TrackSegment], config: AppConfig, add: Any) -> None:
    """Check via geometry, hole spacing, and via-to-track clearance."""

    values = config.manufacturing
    for via in vias:
        if via.diameter + 1e-9 < values.minimum_via_diameter_mm:
            add(
                "VIA_DIAMETER",
                "error",
                "drill",
                "Via diameter is below the active profile",
                f"Via {via.item_id} has a {via.diameter:.3f} mm copper diameter.",
                f"Increase the diameter to at least {values.minimum_via_diameter_mm:.3f} mm.",
                item_ids=(via.item_id,),
                measured=via.diameter,
                limit=values.minimum_via_diameter_mm,
                unit="mm",
            )
        if via.drill + 1e-9 < values.minimum_via_drill_mm:
            severity = "warning" if via.drill >= 0.15 else "error"
            add(
                "VIA_DRILL",
                severity,
                "drill",
                "Via drill is below the active profile",
                f"Via {via.item_id} uses a {via.drill:.3f} mm drill.",
                f"Use at least {values.minimum_via_drill_mm:.3f} mm for this profile, or explicitly select the capability-limit profile.",
                item_ids=(via.item_id,),
                measured=via.drill,
                limit=values.minimum_via_drill_mm,
                unit="mm",
            )
        annular = (via.diameter - via.drill) / 2.0
        if annular + 1e-9 < values.minimum_via_annular_ring_mm:
            add(
                "VIA_ANNULAR_RING",
                "error",
                "drill",
                "Via annular ring is below the active profile",
                f"Via {via.item_id} has an estimated {annular:.3f} mm radial annular ring.",
                f"Increase the via diameter or reduce the drill so the ring is at least {values.minimum_via_annular_ring_mm:.3f} mm.",
                item_ids=(via.item_id,),
                measured=annular,
                limit=values.minimum_via_annular_ring_mm,
                unit="mm",
            )
        surcharge_reason = _small_via_surcharge_reason(via)
        if surcharge_reason is not None:
            add(
                "VIA_SMALL_FEATURE_SURCHARGE",
                "warning",
                "cost",
                "Via matches the published small-feature surcharge condition",
                (
                    f"Via {via.item_id} is {via.diameter:.3f}/{via.drill:.3f} mm diameter/drill. "
                    f"{surcharge_reason}"
                ),
                (
                    "Prefer the 0.60/0.30 mm economy preset. When density requires a 0.20 or "
                    "0.25 mm drill, use at least a 0.45 mm via diameter and confirm the live quote."
                ),
                item_ids=(via.item_id,),
                measured=f"{via.diameter:.3f}/{via.drill:.3f}",
                limit="0.15 mm drill: paid option; 0.20/0.25 mm drill: diameter >=0.45 mm",
                unit="mm",
            )

    for index, first in enumerate(vias):
        for second in vias[index + 1 :]:
            spacing = (
                math.hypot(first.position.x - second.position.x, first.position.y - second.position.y)
                - (first.drill + second.drill) / 2.0
            )
            if spacing + 1e-9 < values.minimum_hole_to_hole_mm:
                add(
                    "VIA_HOLE_TO_HOLE",
                    "error",
                    "drill",
                    "Via holes are too close",
                    f"Vias {first.item_id} and {second.item_id} have approximately {max(0.0, spacing):.3f} mm drill-edge spacing.",
                    f"Increase hole-to-hole spacing to at least {values.minimum_hole_to_hole_mm:.3f} mm.",
                    item_ids=(first.item_id, second.item_id),
                    measured=max(0.0, spacing),
                    limit=values.minimum_hole_to_hole_mm,
                    unit="mm",
                )

    for via in vias:
        via_layers = {via.start_layer, via.end_layer}
        for track in tracks:
            if track.net == via.net or track.layer not in via_layers:
                continue
            clearance = (
                point_segment_distance(via.position, track.start, track.end)
                - via.diameter / 2.0
                - track.width / 2.0
            )
            if clearance + 1e-9 < values.minimum_via_to_track_mm:
                add(
                    "VIA_TO_TRACK",
                    "error",
                    "copper",
                    "Via-to-track clearance is below the published value",
                    f"Via {via.item_id} and track {track.item_id} have approximately {max(0.0, clearance):.3f} mm edge clearance.",
                    f"Increase the separation to at least {values.minimum_via_to_track_mm:.3f} mm.",
                    item_ids=(via.item_id, track.item_id),
                    measured=max(0.0, clearance),
                    limit=values.minimum_via_to_track_mm,
                    unit="mm",
                )


def _check_copper_to_edge(snapshot: BoardSnapshot, config: AppConfig, add: Any) -> None:
    """Check routed copper against Edge.Cuts."""

    if not snapshot.edges:
        return
    limit = (
        config.manufacturing.minimum_copper_to_v_cut_mm
        if config.manufacturing.board_separation == "v_cut"
        else config.manufacturing.minimum_copper_to_routed_edge_mm
    )
    for track in snapshot.tracks:
        clearance = min(
            segment_distance(track.start, track.end, edge.start, edge.end) - track.width / 2.0
            for edge in snapshot.edges
        )
        if clearance + 1e-9 < limit:
            add(
                "TRACK_TO_EDGE",
                "error",
                "outline",
                "Track is too close to the board edge",
                f"Track {track.item_id} has approximately {max(0.0, clearance):.3f} mm copper-to-edge clearance.",
                f"Maintain at least {limit:.3f} mm for the selected separation method.",
                item_ids=(track.item_id,),
                measured=max(0.0, clearance),
                limit=limit,
                unit="mm",
            )
    for via in snapshot.vias:
        clearance = min(
            point_segment_distance(via.position, edge.start, edge.end) - via.diameter / 2.0
            for edge in snapshot.edges
        )
        if clearance + 1e-9 < limit:
            add(
                "VIA_TO_EDGE",
                "error",
                "outline",
                "Via is too close to the board edge",
                f"Via {via.item_id} has approximately {max(0.0, clearance):.3f} mm copper-to-edge clearance.",
                f"Maintain at least {limit:.3f} mm for the selected separation method.",
                item_ids=(via.item_id,),
                measured=max(0.0, clearance),
                limit=limit,
                unit="mm",
            )
    for pad in snapshot.pads:
        clearance = min(_bbox_to_segment_distance(pad.bounds, edge) for edge in snapshot.edges)
        if clearance + 1e-9 < limit:
            add(
                "PAD_TO_EDGE",
                "error",
                "outline",
                "Pad copper is too close to the board edge",
                f"Pad {pad.item_id} has approximately {max(0.0, clearance):.3f} mm clearance to Edge.Cuts.",
                f"Move the footprint or increase the outline clearance to at least {limit:.3f} mm.",
                item_ids=(pad.item_id,),
                measured=max(0.0, clearance),
                limit=limit,
                unit="mm",
            )


def _check_silkscreen(snapshot: BoardSnapshot, config: AppConfig, add: Any) -> None:
    """Check visible footprint fields that are available through the snapshot."""

    minimum_height = config.manufacturing.minimum_silkscreen_text_height_mm
    minimum_line = config.manufacturing.minimum_silkscreen_line_width_mm
    for footprint in snapshot.footprints:
        for field_name, text in (
            ("reference", footprint.reference_field),
            ("value", footprint.value_field),
        ):
            if not text.visible or "SilkS" not in text.layer:
                continue
            if text.height + 1e-9 < minimum_height:
                add(
                    "SILK_TEXT_HEIGHT",
                    "warning",
                    "silkscreen",
                    "Silkscreen text is below JLCPCB's published readable height",
                    f"{footprint.reference} {field_name} text is {text.height:.3f} mm high.",
                    f"Use at least {minimum_height:.3f} mm for production-readable text, or accept reduced readability after preview.",
                    item_ids=(footprint.item_id,),
                    measured=text.height,
                    limit=minimum_height,
                    unit="mm",
                )
            if text.thickness + 1e-9 < minimum_line:
                add(
                    "SILK_LINE_WIDTH",
                    "warning",
                    "silkscreen",
                    "Silkscreen stroke is below JLCPCB's published line width",
                    f"{footprint.reference} {field_name} stroke is {text.thickness:.3f} mm.",
                    f"Increase the stroke to at least {minimum_line:.3f} mm.",
                    item_ids=(footprint.item_id,),
                    measured=text.thickness,
                    limit=minimum_line,
                    unit="mm",
                )


def _candidate_track_pairs(
    tracks: Sequence[TrackSegment],
    clearance: float,
) -> Iterable[tuple[TrackSegment, TrackSegment]]:
    """Yield spatially nearby track pairs without quadratic full-board scanning."""

    if len(tracks) < 2:
        return
    cell_size = max(1.0, clearance * 4.0)
    buckets: dict[tuple[str, int, int], list[int]] = {}
    seen: set[tuple[int, int]] = set()
    for index, track in enumerate(tracks):
        radius = track.width / 2.0 + clearance
        min_x = min(track.start.x, track.end.x) - radius
        max_x = max(track.start.x, track.end.x) + radius
        min_y = min(track.start.y, track.end.y) - radius
        max_y = max(track.start.y, track.end.y) + radius
        x0 = math.floor(min_x / cell_size)
        x1 = math.floor(max_x / cell_size)
        y0 = math.floor(min_y / cell_size)
        y1 = math.floor(max_y / cell_size)
        for x in range(x0, x1 + 1):
            for y in range(y0, y1 + 1):
                key = (track.layer, x, y)
                for other_index in buckets.get(key, ()):
                    pair = (other_index, index)
                    if pair not in seen:
                        seen.add(pair)
                        yield tracks[other_index], track
                buckets.setdefault(key, []).append(index)


def _small_via_surcharge_reason(via: Via) -> str | None:
    """Return the documented JLCPCB surcharge reason for a via, if any.

    JLCPCB currently documents a paid option for every 0.15 mm via drill and
    for 0.20 mm or 0.25 mm drills whose via diameter is below 0.45 mm.  The
    comparisons use a small tolerance to absorb unit-conversion noise from the
    KiCad IPC representation without broadening the published conditions.
    """

    tolerance = 1e-6
    if math.isclose(via.drill, 0.15, abs_tol=tolerance):
        return "JLCPCB lists every 0.15 mm via drill as a paid option."
    uses_intermediate_drill = math.isclose(via.drill, 0.20, abs_tol=tolerance) or math.isclose(
        via.drill,
        0.25,
        abs_tol=tolerance,
    )
    if uses_intermediate_drill and via.diameter < 0.45 - tolerance:
        return "JLCPCB lists 0.20/0.25 mm drills below a 0.45 mm via diameter as a paid option."
    return None


def _board_bounds(snapshot: BoardSnapshot) -> BoundingBox:
    """Return board bounds from Edge.Cuts with a geometry fallback."""

    points: list[Point] = []
    for edge in snapshot.edges:
        points.extend((edge.start, edge.end))
        if edge.mid is not None:
            points.append(edge.mid)
    if not points:
        for track in snapshot.tracks:
            points.extend((track.start, track.end))
        for footprint in snapshot.footprints:
            points.extend(
                (
                    Point(footprint.bounds.min_x, footprint.bounds.min_y),
                    Point(footprint.bounds.max_x, footprint.bounds.max_y),
                )
            )
    return bounds_from_points(points)


def _bbox_to_segment_distance(bounds: BoundingBox, edge: BoardEdge) -> float:
    """Return a conservative axis-aligned box to line-segment distance."""

    corners = (
        Point(bounds.min_x, bounds.min_y),
        Point(bounds.max_x, bounds.min_y),
        Point(bounds.max_x, bounds.max_y),
        Point(bounds.min_x, bounds.max_y),
    )
    sides = tuple((corners[index], corners[(index + 1) % 4]) for index in range(4))
    return min(segment_distance(start, end, edge.start, edge.end) for start, end in sides)


def _mm(value: float) -> str:
    """Format a millimeter value for KiCad custom rules."""

    return f"{value:.3f}mm"


def _bundle_readme() -> str:
    """Return safety instructions for a manufacturing export bundle."""

    return (
        "EMI Guardian JLCPCB manufacturing bundle\n"
        "=========================================\n\n"
        "1. Review JLCPCB-ORDER-NOTES.md and jlcpcb-dfm-report.json.\n"
        "2. Merge emi-guardian-jlcpcb.kicad_dru into your project rules.\n"
        "   Do not overwrite an existing board-name.kicad_dru without preserving it.\n"
        "3. In KiCad 10, set board thickness and solder-mask colors manually in\n"
        "   Board Setup so they match jlcpcb-order-settings.json.\n"
        "4. Run KiCad DRC, refill zones, inspect Gerbers, and run JLCPCB DFM.\n"
        "5. Verify the live quote. Published capabilities do not guarantee price.\n"
    )
