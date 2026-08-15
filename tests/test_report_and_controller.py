"""Report generation and controller integration tests."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from conftest import rectangular_edges, snapshot
from emi_guardian.controller import GuardianController
from emi_guardian.errors import MutationSafetyError
from emi_guardian.kicad_adapter import MutationResult
from emi_guardian.models import (
    AnalysisReport,
    BoundingBox,
    CopperZone,
    Pad,
    Point,
    Polygon,
)
from emi_guardian.report import write_report_bundle


class FakeAdapter:
    """Minimal adapter used to exercise controller orchestration."""

    def __init__(self, root: Path) -> None:
        self.settings_directory = root
        self.capabilities = {
            "ipc_api": True,
            "transactions": True,
            "zone_refill": True,
            "item_creation": True,
            "item_update": True,
            "item_removal": True,
            "rule_area_write": False,
            "edge_write": False,
            "stackup_read": True,
            "stackup_write": False,
            "design_rules_write": False,
        }
        self.closed = False
        self._snapshot = snapshot()
        self.apply_fix_calls = []

    def snapshot(self):
        """Return the active synthetic board."""

        return self._snapshot

    def apply_fix_plan(self, plan, config):
        """Record the exact revalidated plan and return a mutation result."""

        self.apply_fix_calls.append(plan)
        return MutationResult(len(plan.actions), 0, ())

    def apply_silkscreen_plan(self, plan, config):
        """Return a deterministic mutation result."""

        return MutationResult(len(plan.placements), 0, ())

    def apply_edge_proposal(self, proposal, config):
        """Return a deterministic mutation result."""

        return MutationResult(len(proposal.primitives), 0, ())

    def close(self) -> None:
        """Record closure."""

        self.closed = True


def _report() -> AnalysisReport:
    """Return a compact report fixture."""

    return AnalysisReport(
        board_name="demo.kicad_pcb",
        kicad_version="10.0.5",
        score=95.0,
        category_scores={"antenna": 95.0},
        findings=(),
        quantitative={"enabled": True},
        statistics={"finding_count": 0},
        caveats=("Engineering review required.",),
    )


def test_report_bundle_contains_html_json_and_markdown(tmp_path) -> None:
    """Write all user-facing and machine-readable report representations."""

    paths = write_report_bundle(tmp_path, _report())
    assert set(paths) == {"json", "html", "markdown"}
    assert all(path.is_file() for path in paths.values())
    payload = json.loads(paths["json"].read_text(encoding="utf-8"))
    assert payload["analysis"]["score"] == 95.0
    assert "EMI Guardian" in paths["html"].read_text(encoding="utf-8")
    assert "# EMI Guardian Report" in paths["markdown"].read_text(encoding="utf-8")


def test_report_bundle_embeds_manufacturing_results(tmp_path) -> None:
    """Keep the JLCPCB DFM result in all report representations."""

    manufacturing = {
        "profile_id": "jlcpcb_2l_economy",
        "profile_name_en": "JLCPCB 2-layer economy",
        "status": "review",
        "score": 92.0,
        "statistics": {"error_count": 0, "warning_count": 2, "info_count": 0},
        "issues": [],
        "order_settings": {"layer_count": 2, "board_thickness_mm": 1.6},
        "constraints": {"minimum_track_width_mm": 0.2},
    }
    paths = write_report_bundle(tmp_path, _report(), manufacturing_report=manufacturing)
    payload = json.loads(paths["json"].read_text(encoding="utf-8"))
    assert payload["schema_version"] == 2
    assert payload["manufacturing_report"]["profile_id"] == "jlcpcb_2l_economy"
    assert "JLCPCB manufacturability" in paths["html"].read_text(encoding="utf-8")
    assert "## JLCPCB manufacturability" in paths["markdown"].read_text(encoding="utf-8")


def test_controller_exports_report_with_correct_argument_order(tmp_path) -> None:
    """Regression test for the report-directory/report positional argument boundary."""

    adapter = FakeAdapter(tmp_path / "settings")
    controller = GuardianController(adapter)  # type: ignore[arg-type]
    controller.analyze()
    output = tmp_path / "explicit-report"
    paths = controller.export_report(str(output))
    assert Path(paths["json"]).parent == output
    assert Path(paths["html"]).is_file()
    payload = json.loads(Path(paths["json"]).read_text(encoding="utf-8"))
    assert payload["manufacturing_report"]["profile_id"] == "jlcpcb_2l_economy"


def test_controller_applies_and_exports_jlcpcb_profile(tmp_path) -> None:
    """Exercise the manufacturing catalogue, profile, DFM, and export workflow."""

    controller = GuardianController(FakeAdapter(tmp_path / "settings"))  # type: ignore[arg-type]
    catalog = controller.manufacturing_catalog()
    assert catalog["selected"]["layer_count"] == 2
    assert catalog["ipc_behavior"]["stackup_write_runtime"] is False
    applied = controller.apply_manufacturing_profile(
        {
            "profile_id": "jlcpcb_2l_capability",
            "track_width_mm": 0.1,
            "via_preset_id": "jlcpcb_capability_limit",
            "board_thickness_mm": 1.2,
            "solder_mask_color": "white",
            "surface_finish": "enig",
        }
    )
    config = applied["config"]
    assert config["manufacturing"]["profile_id"] == "jlcpcb_2l_capability"
    assert config["manufacturing"]["board_thickness_mm"] == 1.2
    assert config["manufacturing"]["solder_mask_color"] == "white"
    assert config["manufacturing"]["silkscreen_color"] == "black"
    report = controller.check_manufacturing()
    assert report["profile_id"] == "jlcpcb_2l_capability"
    output = tmp_path / "jlcpcb-export"
    paths = controller.export_manufacturing(str(output))
    assert Path(paths["order_settings"]).is_file()
    assert Path(paths["kicad_custom_rules"]).is_file()


def test_controller_blocks_unconfirmed_or_dry_run_mutations(tmp_path) -> None:
    """Keep board writes behind both explicit confirmation and dry-run gates."""

    controller = GuardianController(FakeAdapter(tmp_path / "settings"))  # type: ignore[arg-type]
    with pytest.raises(MutationSafetyError, match="Explicit confirmation"):
        controller.apply_fixes(False)
    with pytest.raises(MutationSafetyError, match="Dry-run"):
        controller.apply_fixes(True)


def test_analysis_timestamp_can_be_injected_for_reproducible_artifacts() -> None:
    """Allow deterministic demonstration and release report generation."""

    from emi_guardian.analysis import analyze_board
    from emi_guardian.config import AppConfig

    board = snapshot()
    report = analyze_board(board, AppConfig(), generated_at_utc="2026-08-11T00:00:00+00:00")
    assert report.statistics["generated_at_utc"] == "2026-08-11T00:00:00+00:00"


def _antenna_board(*, include_tail_pad: bool = False, tail_end_x: float = 17.0):
    """Return a board with a removable GND overhang for controller tests."""

    polygon = Polygon(
        (
            Point(0.0, 0.0),
            Point(10.0, 0.0),
            Point(10.0, 4.4),
            Point(tail_end_x, 4.4),
            Point(tail_end_x, 5.6),
            Point(10.0, 5.6),
            Point(10.0, 10.0),
            Point(0.0, 10.0),
        )
    )
    zone = CopperZone(
        "zone-gnd",
        "GND",
        ("F.Cu",),
        (0,),
        polygon,
        {"F.Cu": (polygon,)},
    )
    pads = [
        Pad(
            "pad-anchor",
            "u1",
            "1",
            Point(2.0, 2.0),
            BoundingBox(1.5, 1.5, 2.5, 2.5),
            "GND",
            ("F.Cu",),
        )
    ]
    if include_tail_pad:
        pads.append(
            Pad(
                "pad-new",
                "j1",
                "1",
                Point(15.8, 5.0),
                BoundingBox(15.3, 4.5, 16.3, 5.5),
                "GND",
                ("F.Cu",),
            )
        )
    return snapshot(
        zones=(zone,),
        pads=tuple(pads),
        edges=rectangular_edges(-2.0, -2.0, 25.0, 12.0),
    )


def _enable_controller_antenna_mutations(controller: GuardianController) -> None:
    """Use deterministic fine geometry while opening the write gate."""

    controller.update_config(
        {
            "fixes": {"dry_run": False},
            "antenna": {
                "raster_step_mm": 0.20,
                "narrow_neck_width_mm": 1.60,
                "minimum_appendage_area_mm2": 0.20,
                "minimum_appendage_length_mm": 0.50,
                "required_ground_connection_width_mm": 1.00,
                "pad_protection_margin_mm": 0.30,
                "perimeter_ground_protection_mm": 1.00,
            },
        }
    )


def test_controller_revalidates_unchanged_antenna_plan_before_apply(tmp_path) -> None:
    """Apply the current action only after a fresh board scan reproduces it."""

    adapter = FakeAdapter(tmp_path / "settings")
    adapter._snapshot = _antenna_board()
    controller = GuardianController(adapter)  # type: ignore[arg-type]
    _enable_controller_antenna_mutations(controller)
    controller.analyze(refresh=True)
    plan = controller.plan_fixes()
    action_id = plan["actions"][0]["action_id"]

    result = controller.apply_fixes(True, [action_id])

    assert result["mutation"]["applied_count"] == 1
    assert len(adapter.apply_fix_calls) == 1
    assert [action.action_id for action in adapter.apply_fix_calls[0].actions] == [action_id]


def test_controller_rejects_stale_antenna_plan_after_pad_is_added(tmp_path) -> None:
    """Never apply a cached keepout after the active board geometry changes."""

    adapter = FakeAdapter(tmp_path / "settings")
    adapter._snapshot = _antenna_board()
    controller = GuardianController(adapter)  # type: ignore[arg-type]
    _enable_controller_antenna_mutations(controller)
    controller.analyze(refresh=True)
    plan = controller.plan_fixes()
    action_id = plan["actions"][0]["action_id"]

    adapter._snapshot = _antenna_board(include_tail_pad=True)
    with pytest.raises(
        MutationSafetyError, match="board changed.*Rebuild and.*review the antenna-fix preview"
    ):
        controller.apply_fixes(True, [action_id])

    assert not adapter.apply_fix_calls
    refreshed = controller.current_fix_plan()
    assert refreshed is not None
    assert action_id not in {item["action_id"] for item in refreshed["actions"]}


def test_controller_rejects_stale_antenna_geometry_with_same_action_id(tmp_path) -> None:
    """Reject a changed keepout even when its deterministic action ID is unchanged."""

    adapter = FakeAdapter(tmp_path / "settings")
    adapter._snapshot = _antenna_board(tail_end_x=17.0)
    controller = GuardianController(adapter)  # type: ignore[arg-type]
    _enable_controller_antenna_mutations(controller)
    controller.analyze(refresh=True)
    old_plan = controller.plan_fixes()
    action_id = old_plan["actions"][0]["action_id"]
    old_polygon = old_plan["actions"][0]["polygon"]

    adapter._snapshot = _antenna_board(tail_end_x=18.0)
    with pytest.raises(
        MutationSafetyError, match="board changed.*Rebuild and.*review the antenna-fix preview"
    ):
        controller.apply_fixes(True, [action_id])

    assert not adapter.apply_fix_calls
    refreshed = controller.current_fix_plan()
    assert refreshed is not None
    matching = [item for item in refreshed["actions"] if item["action_id"] == action_id]
    assert matching
    assert matching[0]["polygon"] != old_polygon
