"""Configuration defaults, persistence, and safety validation tests."""

from __future__ import annotations

import json

import pytest

from emi_guardian.config import AppConfig, config_from_mapping, load_config, save_config
from emi_guardian.errors import ValidationError


def test_defaults_match_user_facing_requirements() -> None:
    """Keep the documented default behavior stable."""

    config = AppConfig()
    config.validate()
    assert config.fixes.dry_run is True
    assert config.silkscreen.text_width_mm == 0.8
    assert config.silkscreen.text_height_mm == 0.8
    assert config.silkscreen.text_thickness_mm == 0.10
    assert config.edge.fillet_radius_mm > 0.0
    assert config.edge.mode == "diagonal"
    assert config.edge.outline_strategy == "convex_preserve_existing_concavities"
    assert config.edge.target_vertex_count == 8
    assert config.edge.preserve_existing_concavities is True
    assert config.edge.allow_destructive_edge_replacement is False
    assert config.manufacturing.profile_id == "jlcpcb_2l_economy"
    assert config.manufacturing.layer_count == 2
    assert config.manufacturing.board_thickness_mm == 1.6
    assert config.manufacturing.solder_mask_color == "green"
    assert config.manufacturing.selected_track_width_mm == 0.2
    assert config.manufacturing.selected_track_widths_mm == [0.2]
    assert config.manufacturing.selected_via_preset_id == "kicad_default"
    assert config.manufacturing.selected_via_preset_ids == ["kicad_default"]
    assert config.fixes.track_width_mm == 0.2


def test_partial_mapping_is_merged_and_unknown_keys_are_ignored() -> None:
    """Allow forward-compatible settings files without losing defaults."""

    config = config_from_mapping(
        {
            "silkscreen": {"text_width_mm": 1.0, "future_key": 42},
            "future_section": {"enabled": True},
        }
    )
    assert config.silkscreen.text_width_mm == 1.0
    assert config.silkscreen.text_height_mm == 0.8


@pytest.mark.parametrize(
    "patch",
    [
        {"fixes": {"via_diameter_mm": 0.3, "via_drill_mm": 0.3}},
        {"fixes": {"minimum_apply_confidence": 1.1}},
        {"edge": {"maximum_area_reduction_percent": 100.0}},
        {"ui": {"bind_address": "0.0.0.0"}},
        {"quantitative": {"frequency_samples_mhz": [100.0, 0.0]}},
        {"antenna": {"ground_net_regex": "["}},
    ],
)
def test_invalid_safety_settings_are_rejected(patch: dict[str, object]) -> None:
    """Reject configurations that can create ambiguous or unsafe behavior."""

    with pytest.raises(ValidationError):
        config_from_mapping(patch)


def test_atomic_config_round_trip(tmp_path) -> None:
    """Persist and reload settings as stable UTF-8 JSON."""

    path = tmp_path / "config.json"
    config = AppConfig()
    config.ui.language = "ja"
    save_config(path, config)
    loaded = load_config(path)
    assert loaded.ui.language == "ja"
    assert json.loads(path.read_text(encoding="utf-8"))["schema_version"] == 5


def test_default_config_template_matches_runtime_defaults() -> None:
    """Keep the distributed JSON template synchronized with code defaults."""

    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    template = json.loads((root / "plugin" / "default-config.json").read_text(encoding="utf-8"))
    assert template == AppConfig().to_dict()


def test_schema_one_settings_migrate_to_current_defaults() -> None:
    """Load pre-manufacturing settings without discarding user overrides."""

    config = config_from_mapping(
        {
            "schema_version": 1,
            "fixes": {"track_width_mm": 0.4},
            "ui": {"language": "ja"},
        }
    )
    assert config.schema_version == 5
    assert config.fixes.track_width_mm == 0.4
    assert config.ui.language == "ja"
    assert config.manufacturing.profile_id == "jlcpcb_2l_economy"


def test_obsolete_economy_via_identifier_migrates_to_kicad_default() -> None:
    """Preserve draft 0.2 settings after the KiCad-default preset correction."""

    config = config_from_mapping(
        {
            "schema_version": 2,
            "manufacturing": {"selected_via_preset_id": "jlcpcb_economy"},
        }
    )
    assert config.manufacturing.selected_via_preset_id == "kicad_default"
    assert config.manufacturing.selected_via_preset_ids == ["kicad_default"]


def test_long_net_diameter_scan_limit_is_validated() -> None:
    """Bound the advanced graph scan budget to predictable runtime."""

    from emi_guardian.config import AppConfig, ValidationError

    config = AppConfig()
    config.noise.long_net_diameter_scan_limit = 1
    with pytest.raises(ValidationError):
        config.validate()
    config.noise.long_net_diameter_scan_limit = 129
    with pytest.raises(ValidationError):
        config.validate()
