"""Versioned manufacturing profiles and routing presets.

The values in this module are intentionally data-only.  Configuration,
analysis, UI, and export code all consume the same immutable catalogue so
that a profile cannot silently diverge between features.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

JLCPCB_VERIFIED_DATE = "2026-08-13"
JLCPCB_CAPABILITY_URL = "https://jlcpcb.com/jp/capabilities/PCB"
JLCPCB_QUOTE_URL = "https://cart.jlcpcb.com/jp/quote"
JLCPCB_TRACE_SPACING_URL = "https://jlcpcb.com/jp/blog/optimize-pcb-trace-spacing"
KICAD_DEFAULTS_URL = "https://docs.kicad.org/doxygen/netclass_8cpp.html"

TRACK_WIDTH_PRESETS_MM: tuple[float, ...] = (
    0.10,
    0.20,
    0.30,
    0.40,
    0.50,
    0.80,
    1.00,
    1.50,
    2.00,
    3.00,
    5.00,
)

JLCPCB_2L_THICKNESSES_MM: tuple[float, ...] = (0.4, 0.6, 0.8, 1.0, 1.2, 1.6, 2.0)
JLCPCB_SOLDER_MASK_COLORS: tuple[str, ...] = (
    "green",
    "purple",
    "red",
    "yellow",
    "blue",
    "white",
    "black",
)
JLCPCB_SILKSCREEN_COLORS: tuple[str, ...] = ("white", "black")
JLCPCB_2L_COPPER_WEIGHTS_OZ: tuple[float, ...] = (1.0, 2.0, 2.5, 3.5, 4.5)
JLCPCB_SURFACE_FINISHES: tuple[str, ...] = ("hasl_leaded", "hasl_lead_free", "enig")
JLCPCB_BOARD_SEPARATION_METHODS: tuple[str, ...] = ("routing", "v_cut")


@dataclass(frozen=True)
class ViaPreset:
    """One selectable through-via geometry preset."""

    preset_id: str
    name_en: str
    name_ja: str
    diameter_mm: float
    drill_mm: float
    cost_class: str
    surcharge_risk: bool
    description_en: str
    description_ja: str

    @property
    def annular_ring_mm(self) -> float:
        """Return the radial copper annular ring."""

        return (self.diameter_mm - self.drill_mm) / 2.0

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable mapping."""

        payload = asdict(self)
        payload["annular_ring_mm"] = self.annular_ring_mm
        return payload


@dataclass(frozen=True)
class ManufacturingProfile:
    """Manufacturing limits and defaults for one JLCPCB workflow."""

    profile_id: str
    name_en: str
    name_ja: str
    intent_en: str
    intent_ja: str
    layer_count: int
    default_board_thickness_mm: float
    default_solder_mask_color: str
    default_silkscreen_color: str
    default_copper_weight_oz: float
    default_surface_finish: str
    default_track_width_mm: float
    default_via_preset_id: str
    minimum_track_width_mm: float
    minimum_clearance_mm: float
    minimum_via_diameter_mm: float
    minimum_via_drill_mm: float
    minimum_via_annular_ring_mm: float
    minimum_via_to_track_mm: float
    minimum_hole_to_hole_mm: float
    minimum_copper_to_routed_edge_mm: float
    minimum_copper_to_v_cut_mm: float
    minimum_npth_diameter_mm: float
    minimum_plated_slot_width_mm: float
    minimum_unplated_slot_width_mm: float
    minimum_solder_mask_bridge_mm: float
    minimum_silkscreen_line_width_mm: float
    minimum_silkscreen_text_height_mm: float
    minimum_pad_to_silkscreen_mm: float
    cost_warning_en: str
    cost_warning_ja: str

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable mapping."""

        return asdict(self)


VIA_PRESETS: dict[str, ViaPreset] = {
    "jlcpcb_capability_limit": ViaPreset(
        preset_id="jlcpcb_capability_limit",
        name_en="JLCPCB capability limit",
        name_ja="JLCPCB 製造限界",
        diameter_mm=0.25,
        drill_mm=0.15,
        cost_class="capability_limit",
        surcharge_risk=True,
        description_en=(
            "Absolute published 2-layer minimum. Use only for local escape routing; "
            "small-hole options can add cost and reduce process margin."
        ),
        description_ja=(
            "公開されている2層基板の絶対最小値です。局所的な引き出し配線に限定し、"
            "小径穴オプションによる追加料金と製造余裕の低下を考慮してください。"
        ),
    ),
    "kicad_default": ViaPreset(
        preset_id="kicad_default",
        name_en="KiCad 10 default / JLCPCB economy",
        name_ja="KiCad 10デフォルト／JLCPCB低コスト",
        diameter_mm=0.60,
        drill_mm=0.30,
        cost_class="economy",
        surcharge_risk=False,
        description_en=(
            "KiCad 10's built-in default through-via geometry. Its 0.30 mm drill also "
            "avoids JLCPCB's published small-hole surcharge condition."
        ),
        description_ja=(
            "KiCad 10の組み込みデフォルト寸法です。0.30 mmドリルのため、"
            "JLCPCBが公開する小径穴の追加料金条件も避けます。"
        ),
    ),
}


MANUFACTURING_PROFILES: dict[str, ManufacturingProfile] = {
    "jlcpcb_2l_economy": ManufacturingProfile(
        profile_id="jlcpcb_2l_economy",
        name_en="JLCPCB 2-layer economy",
        name_ja="JLCPCB 2層・低コスト",
        intent_en=(
            "Conservative dimensions and standard order options intended to avoid known "
            "small-via surcharges and improve yield."
        ),
        intent_ja=("既知の小径ビア追加料金を避け、歩留まりを高めるための保守的な寸法と標準発注条件です。"),
        layer_count=2,
        default_board_thickness_mm=1.6,
        default_solder_mask_color="green",
        default_silkscreen_color="white",
        default_copper_weight_oz=1.0,
        default_surface_finish="hasl_leaded",
        default_track_width_mm=0.20,
        default_via_preset_id="kicad_default",
        minimum_track_width_mm=0.20,
        minimum_clearance_mm=0.20,
        minimum_via_diameter_mm=0.45,
        minimum_via_drill_mm=0.30,
        minimum_via_annular_ring_mm=0.075,
        minimum_via_to_track_mm=0.20,
        minimum_hole_to_hole_mm=0.20,
        minimum_copper_to_routed_edge_mm=0.30,
        minimum_copper_to_v_cut_mm=0.40,
        minimum_npth_diameter_mm=0.50,
        minimum_plated_slot_width_mm=0.50,
        minimum_unplated_slot_width_mm=1.00,
        minimum_solder_mask_bridge_mm=0.10,
        minimum_silkscreen_line_width_mm=0.15,
        minimum_silkscreen_text_height_mm=1.00,
        minimum_pad_to_silkscreen_mm=0.15,
        cost_warning_en=(
            "This is a no-known-surcharge engineering baseline, not a price guarantee. "
            "Board size, quantity, options, coupons, and current quote rules still determine price."
        ),
        cost_warning_ja=(
            "これは既知の追加料金を避けるための設計基準であり、価格保証ではありません。"
            "基板寸法、数量、オプション、クーポン、発注時の見積条件で価格は変わります。"
        ),
    ),
    "jlcpcb_2l_capability": ManufacturingProfile(
        profile_id="jlcpcb_2l_capability",
        name_en="JLCPCB 2-layer capability limit",
        name_ja="JLCPCB 2層・製造能力限界",
        intent_en=(
            "Published manufacturing limits for dense local routing. These values are not "
            "the recommended board-wide defaults."
        ),
        intent_ja=("高密度な局所配線向けの公開製造限界です。基板全体へ適用する推奨値ではありません。"),
        layer_count=2,
        default_board_thickness_mm=1.6,
        default_solder_mask_color="green",
        default_silkscreen_color="white",
        default_copper_weight_oz=1.0,
        default_surface_finish="hasl_leaded",
        default_track_width_mm=0.10,
        default_via_preset_id="jlcpcb_capability_limit",
        minimum_track_width_mm=0.10,
        minimum_clearance_mm=0.10,
        minimum_via_diameter_mm=0.25,
        minimum_via_drill_mm=0.15,
        minimum_via_annular_ring_mm=0.05,
        minimum_via_to_track_mm=0.20,
        minimum_hole_to_hole_mm=0.20,
        minimum_copper_to_routed_edge_mm=0.20,
        minimum_copper_to_v_cut_mm=0.40,
        minimum_npth_diameter_mm=0.50,
        minimum_plated_slot_width_mm=0.50,
        minimum_unplated_slot_width_mm=1.00,
        minimum_solder_mask_bridge_mm=0.10,
        minimum_silkscreen_line_width_mm=0.15,
        minimum_silkscreen_text_height_mm=1.00,
        minimum_pad_to_silkscreen_mm=0.15,
        cost_warning_en=(
            "Several values are published process limits. Small drills and fine features may "
            "require paid options, manual review, or reduced yield."
        ),
        cost_warning_ja=(
            "複数の値が公開工程限界です。小径ドリルや微細パターンは追加料金、手動確認、"
            "または歩留まり低下の対象になり得ます。"
        ),
    ),
}


def profile(profile_id: str) -> ManufacturingProfile:
    """Return a profile or raise ``KeyError`` for an unknown identifier."""

    return MANUFACTURING_PROFILES[profile_id]


def via_preset(preset_id: str) -> ViaPreset:
    """Return a via preset or raise ``KeyError`` for an unknown identifier."""

    return VIA_PRESETS[preset_id]


def manufacturing_catalog() -> dict[str, Any]:
    """Return the complete user-facing manufacturing catalogue."""

    return {
        "vendor": "JLCPCB",
        "verified_date": JLCPCB_VERIFIED_DATE,
        "sources": {
            "capabilities": JLCPCB_CAPABILITY_URL,
            "quote": JLCPCB_QUOTE_URL,
            "trace_spacing": JLCPCB_TRACE_SPACING_URL,
            "kicad_defaults": KICAD_DEFAULTS_URL,
        },
        "profiles": [item.to_dict() for item in MANUFACTURING_PROFILES.values()],
        "track_width_presets_mm": list(TRACK_WIDTH_PRESETS_MM),
        "via_presets": [item.to_dict() for item in VIA_PRESETS.values()],
        "board_thicknesses_mm": list(JLCPCB_2L_THICKNESSES_MM),
        "solder_mask_colors": list(JLCPCB_SOLDER_MASK_COLORS),
        "silkscreen_colors": list(JLCPCB_SILKSCREEN_COLORS),
        "copper_weights_oz": list(JLCPCB_2L_COPPER_WEIGHTS_OZ),
        "surface_finishes": list(JLCPCB_SURFACE_FINISHES),
        "board_separation_methods": list(JLCPCB_BOARD_SEPARATION_METHODS),
    }
