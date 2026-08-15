"""KiCad adapter safety gates that can be tested without a running KiCad GUI."""

from __future__ import annotations

import sys
from dataclasses import dataclass
from types import ModuleType

import pytest

from emi_guardian.config import AppConfig
from emi_guardian.errors import CapabilityError, MutationSafetyError
from emi_guardian.kicad_adapter import (
    KicadIpcAdapter,
    _configure_copper_keepout,
    _layer_id_from_name,
    _layer_name,
    _parent_item_id,
    _require_supported_kicad_version,
)
from emi_guardian.models import FixPlan


@dataclass
class FakeNet:
    """Simple net wrapper."""

    name: str


class BoardWithoutTransactions:
    """Expose item creation but deliberately omit commit methods."""

    def create_items(self, items):
        """Pretend to support item creation."""

        return items

    def get_nets(self):
        """Return two existing nets."""

        return [FakeNet("GND"), FakeNet("AGND")]


class ParentId:
    """Identifier wrapper used by parent extraction."""

    value = "footprint-123"


class PadWrapper:
    """Pad-like wrapper with a parent identifier."""

    parent_id = ParentId()


def _adapter() -> KicadIpcAdapter:
    """Construct an adapter instance without importing kicad-python."""

    adapter = object.__new__(KicadIpcAdapter)
    adapter._board = BoardWithoutTransactions()  # type: ignore[attr-defined]
    return adapter


def test_default_write_policy_requires_transaction_support() -> None:
    """Do not perform non-rollbackable writes when single-undo mode is enabled."""

    config = AppConfig()
    config.fixes.dry_run = False
    with pytest.raises(CapabilityError, match="transaction support"):
        _adapter().apply_fix_plan(FixPlan(()), config)


def test_dry_run_gate_precedes_runtime_item_construction() -> None:
    """Reject writes before importing or constructing KiCad board items."""

    with pytest.raises(MutationSafetyError, match="Dry-run"):
        _adapter().apply_fix_plan(FixPlan(()), AppConfig())


def test_existing_net_resolution_is_exact() -> None:
    """Never create a same-named replacement net object by accident."""

    adapter = _adapter()
    assert adapter._resolve_net("GND").name == "GND"
    with pytest.raises(CapabilityError, match="no longer exists"):
        adapter._resolve_net("DGND")


def test_parent_footprint_identifier_is_extracted_defensively() -> None:
    """Prefer exact parent association over bounding-box inference when available."""

    assert _parent_item_id(PadWrapper()) == "footprint-123"


class BoardWithCustomLayerNames:
    """Board wrapper whose user-visible names differ from canonical names."""

    def get_layer_name(self, layer_id):
        """Return a custom display name."""

        return {3: "Top Signal", 47: "Mechanical Outline"}.get(layer_id, "Unknown")

    def get_enabled_layers(self):
        """Return representative KiCad 10 protobuf layer identifiers."""

        return [3, 47]


@dataclass
class FakeRuleAreaSettings:
    """Minimal KiCad 10 RuleAreaSettings-compatible record."""

    keepout_copper: bool = False
    keepout_vias: bool = True
    keepout_tracks: bool = True
    keepout_pads: bool = True
    keepout_footprints: bool = True


@dataclass
class FakeZoneProto:
    """Minimal zone protobuf wrapper."""

    rule_area_settings: FakeRuleAreaSettings


@dataclass
class FakeZone:
    """Zone wrapper exposing the internal protobuf used by kicad-python 0.7.x."""

    _proto: FakeZoneProto


def _install_fake_layer_util(monkeypatch: pytest.MonkeyPatch) -> None:
    """Install a minimal kipy.util module for canonical-layer tests."""

    kipy = ModuleType("kipy")
    util = ModuleType("kipy.util")
    names = {3: "F.Cu", 47: "Edge.Cuts"}
    identifiers = {value: key for key, value in names.items()}
    util.canonical_name = lambda layer_id: names[int(layer_id)]  # type: ignore[attr-defined]
    util.layer_from_canonical_name = lambda name: identifiers[name]  # type: ignore[attr-defined]
    kipy.util = util  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "kipy", kipy)
    monkeypatch.setitem(sys.modules, "kipy.util", util)


def test_layer_helpers_prefer_canonical_names_over_custom_display_names(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Keep geometry logic stable when users rename board layers."""

    _install_fake_layer_util(monkeypatch)
    board = BoardWithCustomLayerNames()
    assert _layer_name(board, 3) == "F.Cu"
    assert _layer_name(board, 47) == "Edge.Cuts"
    assert _layer_id_from_name(board, "Edge.Cuts", -1) == 47


def test_layer_id_helper_accepts_custom_display_name_as_secondary_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Permit explicit user-visible names when no canonical name matches."""

    _install_fake_layer_util(monkeypatch)
    board = BoardWithCustomLayerNames()
    assert _layer_id_from_name(board, "Top Signal", -1) == 3


def test_rule_area_proto_fallback_configures_only_copper_keepout() -> None:
    """Use KiCad 10 RuleAreaSettings without accidentally blocking routing items."""

    settings = FakeRuleAreaSettings()
    zone = FakeZone(FakeZoneProto(settings))
    assert _configure_copper_keepout(zone) is True
    assert settings.keepout_copper is True
    assert settings.keepout_vias is False
    assert settings.keepout_tracks is False
    assert settings.keepout_pads is False
    assert settings.keepout_footprints is False


def test_version_gate_accepts_kicad_10_and_future_major_versions() -> None:
    """Keep the compatibility gate aligned with the KiCad 10+ requirement."""

    _require_supported_kicad_version("10.0.5")
    _require_supported_kicad_version("KiCad 11.1.0-rc1")


def test_version_gate_rejects_pre_ipc_baseline() -> None:
    """Do not attempt writes through unsupported KiCad 9 or older runtimes."""

    with pytest.raises(CapabilityError, match="requires KiCad 10"):
        _require_supported_kicad_version("9.0.7")
