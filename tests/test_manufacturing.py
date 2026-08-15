"""JLCPCB profile, preset, DFM, and export regression tests."""

from __future__ import annotations

import json
from pathlib import Path

from conftest import rectangular_edges, snapshot
from emi_guardian.config import AppConfig, config_from_mapping
from emi_guardian.manufacturing import (
    catalog_payload,
    evaluate_manufacturability,
    profile_patch,
    render_kicad_custom_rules,
    write_manufacturing_bundle,
)
from emi_guardian.manufacturing_profiles import TRACK_WIDTH_PRESETS_MM, VIA_PRESETS
from emi_guardian.models import Point, TrackSegment, Via


def test_catalog_contains_requested_track_and_via_presets() -> None:
    """Expose every requested track width and both requested via reference points."""

    catalog = catalog_payload(AppConfig())
    assert catalog["track_width_presets_mm"] == list(TRACK_WIDTH_PRESETS_MM)
    assert catalog["track_width_presets_mm"] == [0.1, 0.2, 0.3, 0.4, 0.5, 0.8, 1.0, 1.5, 2.0, 3.0, 5.0]
    assert VIA_PRESETS["jlcpcb_capability_limit"].diameter_mm == 0.25
    assert VIA_PRESETS["jlcpcb_capability_limit"].drill_mm == 0.15
    assert VIA_PRESETS["kicad_default"].diameter_mm == 0.60
    assert VIA_PRESETS["kicad_default"].drill_mm == 0.30
    assert len(VIA_PRESETS) == 2


def test_economy_and_capability_profiles_apply_consistent_defaults() -> None:
    """Keep low-cost defaults separate from published process limits."""

    economy = config_from_mapping(profile_patch("jlcpcb_2l_economy"))
    assert economy.manufacturing.layer_count == 2
    assert economy.manufacturing.board_thickness_mm == 1.6
    assert economy.manufacturing.solder_mask_color == "green"
    assert economy.manufacturing.minimum_track_width_mm == 0.20
    assert economy.fixes.track_width_mm == 0.20
    assert economy.fixes.via_diameter_mm == 0.60
    assert economy.fixes.via_drill_mm == 0.30
    assert economy.silkscreen.text_height_mm == 0.80

    capability = config_from_mapping(profile_patch("jlcpcb_2l_capability"))
    assert capability.manufacturing.minimum_track_width_mm == 0.10
    assert capability.manufacturing.minimum_clearance_mm == 0.10
    assert capability.fixes.via_diameter_mm == 0.25
    assert capability.fixes.via_drill_mm == 0.15


def test_profile_can_set_thickness_color_and_requested_presets() -> None:
    """Apply user-selected order values and routing geometry in one patch."""

    config = config_from_mapping(
        profile_patch(
            "jlcpcb_2l_economy",
            track_width_mm=0.80,
            via_preset_id="kicad_default",
            board_thickness_mm=1.20,
            solder_mask_color="white",
        )
    )
    assert config.manufacturing.board_thickness_mm == 1.20
    assert config.manufacturing.solder_mask_color == "white"
    assert config.manufacturing.silkscreen_color == "black"
    assert config.manufacturing.selected_track_width_mm == 0.80
    assert config.fixes.track_width_mm == 0.80
    assert config.fixes.via_diameter_mm == 0.60
    assert config.fixes.via_drill_mm == 0.30


def test_multi_preset_selection_keeps_automatic_fixes_profile_safe() -> None:
    """Treat multi-selection as a catalogue without violating economy limits."""

    config = config_from_mapping(
        profile_patch(
            "jlcpcb_2l_economy",
            track_widths_mm=TRACK_WIDTH_PRESETS_MM,
            via_preset_ids=("jlcpcb_capability_limit", "kicad_default"),
        )
    )
    assert config.manufacturing.selected_track_widths_mm == list(TRACK_WIDTH_PRESETS_MM)
    assert config.manufacturing.selected_via_preset_ids == [
        "jlcpcb_capability_limit",
        "kicad_default",
    ]
    assert config.manufacturing.selected_track_width_mm == 0.20
    assert config.manufacturing.selected_via_preset_id == "kicad_default"
    assert config.fixes.track_width_mm == 0.20
    assert config.fixes.via_diameter_mm == 0.60
    assert config.fixes.via_drill_mm == 0.30


def test_capability_profile_prefers_its_selected_fine_geometry() -> None:
    """Use process-limit geometry automatically only under that profile."""

    config = config_from_mapping(
        profile_patch(
            "jlcpcb_2l_capability",
            track_widths_mm=(0.10, 0.20),
            via_preset_ids=("jlcpcb_capability_limit", "kicad_default"),
        )
    )
    assert config.manufacturing.selected_track_width_mm == 0.10
    assert config.manufacturing.selected_via_preset_id == "jlcpcb_capability_limit"
    assert config.fixes.track_width_mm == 0.10
    assert config.fixes.via_diameter_mm == 0.25
    assert config.fixes.via_drill_mm == 0.15


def test_dfm_detects_fine_track_and_fine_via() -> None:
    """Report geometry that violates the active economy baseline."""

    board = snapshot(
        tracks=(TrackSegment("fine", Point(2, 5), Point(18, 5), 0.10, "F.Cu", 1, "SIG"),),
        vias=(Via("small", Point(10, 10), 0.25, 0.15, "SIG"),),
        edges=rectangular_edges(0, 0, 20, 20),
    )
    report = evaluate_manufacturability(board, AppConfig())
    codes = {issue.code for issue in report.issues}
    assert "TRACK_WIDTH" in codes
    assert "VIA_DIAMETER" in codes
    assert "VIA_DRILL" in codes
    assert report.status == "fail"
    assert report.statistics["error_count"] >= 3


def test_capability_profile_warns_about_small_via_cost() -> None:
    """Keep the process-limit preset visible but never present it as low-cost."""

    config = config_from_mapping(profile_patch("jlcpcb_2l_capability"))
    board = snapshot(edges=rectangular_edges(0, 0, 20, 20))
    report = evaluate_manufacturability(board, config)
    assert any(issue.code == "ORDER_SMALL_VIA_COST_RISK" for issue in report.issues)
    assert report.status == "review"


def test_dfm_uses_current_published_small_via_surcharge_conditions() -> None:
    """Distinguish definite paid small-via combinations from standard geometry."""

    config = config_from_mapping(profile_patch("jlcpcb_2l_capability"))
    board = snapshot(
        vias=(
            Via("paid-015", Point(10, 10), 0.60, 0.15, "GND"),
            Via("paid-020", Point(30, 10), 0.44, 0.20, "GND"),
            Via("paid-025", Point(50, 10), 0.44, 0.25, "GND"),
            Via("standard-020", Point(70, 10), 0.45, 0.20, "GND"),
            Via("standard-030", Point(90, 10), 0.40, 0.30, "GND"),
        ),
        edges=rectangular_edges(0, 0, 100, 20),
    )
    report = evaluate_manufacturability(board, config)
    paid_items = {issue.item_ids[0] for issue in report.issues if issue.code == "VIA_SMALL_FEATURE_SURCHARGE"}
    assert paid_items == {"paid-015", "paid-020", "paid-025"}


def test_dfm_rejects_v_cut_for_04mm_board() -> None:
    """Apply the current no-panel restriction to 0.4 mm selections."""

    patch = profile_patch("jlcpcb_2l_economy", board_thickness_mm=0.4)
    patch["manufacturing"]["surface_finish"] = "enig"
    patch["manufacturing"]["board_separation"] = "v_cut"
    config = config_from_mapping(patch)
    board = snapshot(edges=rectangular_edges(0, 0, 20, 20))
    report = evaluate_manufacturability(board, config)
    assert any(issue.code == "ORDER_04MM_NO_PANEL" for issue in report.issues)


def test_kicad_rules_and_manufacturing_bundle_are_exported(tmp_path: Path) -> None:
    """Create reviewable custom rules, order settings, presets, and DFM results."""

    config = AppConfig()
    board = snapshot(edges=rectangular_edges(0, 0, 20, 20))
    report = evaluate_manufacturability(board, config)
    rules = render_kicad_custom_rules(config)
    assert "(constraint track_width (min 0.200mm))" in rules
    assert "(constraint via_diameter (min 0.450mm))" in rules
    assert "(constraint annular_width (min 0.075mm))" in rules
    assert "(constraint edge_clearance (min 0.300mm))" in rules
    assert "(constraint text_height (min 1.000mm))" in rules
    assert "(constraint text_thickness (min 0.150mm))" in rules

    paths = write_manufacturing_bundle(tmp_path, board, config, report)
    assert set(paths) == {
        "dfm_json",
        "order_settings",
        "routing_presets",
        "kicad_custom_rules",
        "order_notes",
        "readme",
    }
    assert all(path.is_file() for path in paths.values())
    order = json.loads(paths["order_settings"].read_text(encoding="utf-8"))
    assert order["selected_order_settings"]["layer_count"] == 2
    assert order["selected_order_settings"]["board_thickness_mm"] == 1.6
    presets = json.loads(paths["routing_presets"].read_text(encoding="utf-8"))
    assert presets["track_widths_mm"] == list(TRACK_WIDTH_PRESETS_MM)
    dfm = json.loads(paths["dfm_json"].read_text(encoding="utf-8"))
    assert dfm["schema_version"] == 1
    assert dfm["vendor"] == "JLCPCB"
