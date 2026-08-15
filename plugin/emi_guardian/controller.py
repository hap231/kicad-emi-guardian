"""Thread-safe application controller used by the local dashboard.

The controller is the only layer allowed to coordinate KiCad reads and writes.
HTTP handlers remain deliberately thin, while the analysis algorithms stay
independent from both KiCad and the user interface.
"""

from __future__ import annotations

import json
import threading
from collections.abc import Mapping
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .analysis import analyze_board
from .config import AppConfig, config_from_mapping, load_config, save_config
from .edge_optimizer import EdgeProposal, propose_edge_outline
from .errors import EmiGuardianError, MutationSafetyError
from .fixes import plan_antenna_fixes
from .kicad_adapter import KicadIpcAdapter, MutationResult
from .manufacturing import (
    ManufacturingReport,
    catalog_payload,
    evaluate_manufacturability,
    profile_patch,
    write_manufacturing_bundle,
)
from .models import (
    AnalysisReport,
    BoardSnapshot,
    BoundingBox,
    FixAction,
    FixPlan,
    Point,
    bounds_from_points,
)
from .placement import ComponentPlacementPlan, plan_component_placement
from .report import write_report_bundle
from .silkscreen import SilkscreenPlan, plan_silkscreen
from .solver_export import export_solver_manifest
from .stitching import ViaStitchingPlan, plan_via_stitching


class GuardianController:
    """Coordinate configuration, analysis, planning, reporting, and mutations."""

    def __init__(self, adapter: KicadIpcAdapter) -> None:
        """Create a controller for one active KiCad board."""

        self._adapter = adapter
        self._lock = threading.RLock()
        self._settings_directory = adapter.settings_directory
        self._config_path = self._settings_directory / "config.json"
        self._config = load_config(self._config_path)
        self._configure_adapter_connection()
        self._snapshot: BoardSnapshot | None = None
        self._report: AnalysisReport | None = None
        self._fix_plan: FixPlan | None = None
        self._silkscreen_plan: SilkscreenPlan | None = None
        self._edge_proposal: EdgeProposal | None = None
        self._stitching_plan: ViaStitchingPlan | None = None
        self._placement_plan: ComponentPlacementPlan | None = None
        self._manufacturing_report: ManufacturingReport | None = None
        self._last_export: dict[str, str] = {}

    def _configure_adapter_connection(self) -> None:
        """Apply reconnect settings when the active adapter exposes the hook."""

        configure = getattr(self._adapter, "configure_connection", None)
        if callable(configure):
            configure(self._config.ui.ipc_retry_count)

    @property
    def config(self) -> AppConfig:
        """Return the active configuration object."""

        return self._config

    def status(self) -> dict[str, Any]:
        """Return runtime status and a concise active-board summary."""

        with self._lock:
            if self._snapshot is None:
                self._snapshot = self._adapter.snapshot()
            snapshot = self._snapshot
            return {
                "plugin_version": "0.0.2",
                "connection": {"connected": True, "message": ""},
                "board": {
                    "name": snapshot.board_name,
                    "path": snapshot.board_path,
                    "kicad_version": snapshot.kicad_version,
                    "tracks": len(snapshot.tracks),
                    "vias": len(snapshot.vias),
                    "pads": len(snapshot.pads),
                    "zones": len(snapshot.zones),
                    "footprints": len(snapshot.footprints),
                },
                "capabilities": self._adapter.capabilities,
                "dry_run": self._config.fixes.dry_run,
                "has_analysis": self._report is not None,
                "manufacturing": {
                    "profile_id": self._config.manufacturing.profile_id,
                    "board_thickness_mm": self._config.manufacturing.board_thickness_mm,
                    "solder_mask_color": self._config.manufacturing.solder_mask_color,
                    "has_report": self._manufacturing_report is not None,
                },
                "last_export": dict(self._last_export),
                "settings_directory": str(self._settings_directory),
            }

    def keep_alive(self) -> dict[str, object]:
        """Verify that the dashboard and KiCad IPC session are still live."""

        with self._lock:
            return self._adapter.ping()

    def locate_finding(self, finding_id: str) -> dict[str, object]:
        """Select and zoom to one finding's evidence in KiCad."""

        with self._lock:
            self._ensure_analysis()
            assert self._report is not None
            finding = next(
                (item for item in self._report.findings if item.finding_id == finding_id),
                None,
            )
            if finding is None:
                raise EmiGuardianError(f"Finding '{finding_id}' is not present in the current analysis.")
            layer = str(finding.metrics.get("layer", ""))
            return self._adapter.locate_items(
                finding.item_ids,
                layer=layer,
                position=finding.location,
            )

    def get_config(self) -> dict[str, Any]:
        """Return the complete configuration mapping."""

        with self._lock:
            return self._config.to_dict()

    def update_config(self, values: Mapping[str, Any]) -> dict[str, Any]:
        """Validate, persist, and activate a complete or partial mapping."""

        with self._lock:
            merged = _deep_merge(self._config.to_dict(), values)
            self._config = config_from_mapping(merged)
            self._configure_adapter_connection()
            save_config(self._config_path, self._config)
            self._invalidate_plans()
            return self._config.to_dict()

    def analyze(self, refresh: bool = True) -> dict[str, Any]:
        """Analyze the board and return report plus a lightweight preview."""

        with self._lock:
            if refresh or self._snapshot is None:
                self._snapshot = self._adapter.snapshot()
            self._report = analyze_board(self._snapshot, self._config)
            self._manufacturing_report = evaluate_manufacturability(self._snapshot, self._config)
            self._fix_plan = None
            self._silkscreen_plan = None
            self._edge_proposal = None
            self._stitching_plan = None
            self._placement_plan = None
            return self.analysis_payload()

    def analysis_payload(self) -> dict[str, Any]:
        """Return the current analysis payload without forcing a scan."""

        with self._lock:
            if self._report is None or self._snapshot is None:
                return {"analysis": None, "preview": None}
            return {
                "analysis": self._report.to_dict(),
                "preview": _preview_payload(self._snapshot, self._report),
                "manufacturing": (
                    self._manufacturing_report.to_dict() if self._manufacturing_report else None
                ),
            }

    def manufacturing_catalog(self) -> dict[str, Any]:
        """Return JLCPCB profiles, presets, and active selections."""

        with self._lock:
            payload = catalog_payload(self._config)
            behavior = payload.get("ipc_behavior")
            if isinstance(behavior, dict):
                behavior["stackup_write_runtime"] = bool(
                    self._adapter.capabilities.get("stackup_write", False)
                )
                behavior["design_rule_write_runtime"] = bool(
                    self._adapter.capabilities.get("design_rules_write", False)
                )
            return payload

    def apply_manufacturing_profile(self, values: Mapping[str, Any]) -> dict[str, Any]:
        """Apply a named JLCPCB profile and selected routing/order presets."""

        with self._lock:
            profile_id = str(values.get("profile_id", self._config.manufacturing.profile_id))
            patch = profile_patch(
                profile_id,
                track_width_mm=_optional_float(values.get("track_width_mm")),
                via_preset_id=(
                    str(values["via_preset_id"]) if values.get("via_preset_id") is not None else None
                ),
                track_widths_mm=_optional_float_list(values.get("track_widths_mm")),
                via_preset_ids=_optional_string_list(values.get("via_preset_ids")),
                board_thickness_mm=_optional_float(values.get("board_thickness_mm")),
                solder_mask_color=(
                    str(values["solder_mask_color"]) if values.get("solder_mask_color") is not None else None
                ),
                apply_silkscreen_limits=bool(values.get("apply_silkscreen_limits", False)),
            )
            order_patch = {
                key: values[key]
                for key in (
                    "copper_weight_oz",
                    "surface_finish",
                    "board_separation",
                )
                if key in values
            }
            if order_patch:
                patch = _deep_merge(patch, {"manufacturing": order_patch})
            merged = _deep_merge(self._config.to_dict(), patch)
            self._config = config_from_mapping(merged)
            save_config(self._config_path, self._config)
            self._invalidate_plans()
            report = None
            if self._snapshot is not None:
                self._manufacturing_report = evaluate_manufacturability(self._snapshot, self._config)
                report = self._manufacturing_report.to_dict()
            return {
                "config": self._config.to_dict(),
                "catalog": self.manufacturing_catalog(),
                "report": report,
            }

    def check_manufacturing(self, refresh: bool = True) -> dict[str, Any]:
        """Run the active JLCPCB profile against the board snapshot."""

        with self._lock:
            if refresh or self._snapshot is None:
                self._snapshot = self._adapter.snapshot()
            assert self._snapshot is not None
            self._manufacturing_report = evaluate_manufacturability(self._snapshot, self._config)
            return self._manufacturing_report.to_dict()

    def current_manufacturing_report(self) -> dict[str, Any] | None:
        """Return the current JLCPCB DFM report without forcing a scan."""

        with self._lock:
            return self._manufacturing_report.to_dict() if self._manufacturing_report else None

    def export_manufacturing(self, output_directory: str = "") -> dict[str, str]:
        """Write a JLCPCB order, DFM, preset, and KiCad-rule bundle."""

        with self._lock:
            self._ensure_snapshot()
            assert self._snapshot is not None
            if self._manufacturing_report is None:
                self._manufacturing_report = evaluate_manufacturability(self._snapshot, self._config)
            directory = self._resolve_output_directory(output_directory, "jlcpcb")
            paths = write_manufacturing_bundle(
                directory,
                self._snapshot,
                self._config,
                self._manufacturing_report,
            )
            result = {name: str(path) for name, path in paths.items()}
            self._last_export = result
            return result

    def plan_fixes(self) -> dict[str, Any]:
        """Create ranked automatic-remediation proposals for antenna findings."""

        with self._lock:
            self._ensure_analysis()
            assert self._snapshot is not None
            assert self._report is not None
            self._fix_plan = plan_antenna_fixes(
                self._snapshot,
                self._report.findings,
                self._config.antenna,
                self._config.fixes,
            )
            return self._fix_plan.to_dict()

    def current_fix_plan(self) -> dict[str, Any] | None:
        """Return the latest fix plan."""

        with self._lock:
            return self._fix_plan.to_dict() if self._fix_plan else None

    def apply_fixes(
        self,
        confirmed: bool,
        action_ids: list[str] | None = None,
    ) -> dict[str, Any]:
        """Revalidate and apply only explicitly selected antenna fixes.

        The dashboard may remain open while the board is edited in KiCad. A
        rule area that was safe when previewed can become destructive after a
        pad, track, zone, or outline change. Therefore every apply request
        reads the active board again, re-runs the detector and planner, and
        requires each selected action to have an identical safety-relevant
        signature before any board mutation is attempted.
        """

        with self._lock:
            self._require_confirmation(confirmed)
            if self._fix_plan is None:
                self.plan_fixes()
            assert self._fix_plan is not None

            cached_plan = self._fix_plan
            cached_by_id = {action.action_id: action for action in cached_plan.actions}
            requested_ids = (
                tuple(cached_by_id)
                if action_ids is None
                else tuple(dict.fromkeys(str(value) for value in action_ids))
            )
            if not requested_ids:
                raise MutationSafetyError("At least one antenna-fix action must be selected.")
            unknown_ids = [action_id for action_id in requested_ids if action_id not in cached_by_id]
            if unknown_ids:
                raise MutationSafetyError(
                    "The selected antenna-fix action is not present in the current preview; "
                    "regenerate the preview before applying changes."
                )

            current_snapshot = self._adapter.snapshot()
            current_report = analyze_board(current_snapshot, self._config)
            current_plan = plan_antenna_fixes(
                current_snapshot,
                current_report.findings,
                self._config.antenna,
                self._config.fixes,
            )
            current_by_id = {action.action_id: action for action in current_plan.actions}
            stale_ids = [
                action_id
                for action_id in requested_ids
                if action_id not in current_by_id
                or _fix_action_safety_signature(cached_by_id[action_id])
                != _fix_action_safety_signature(current_by_id[action_id])
            ]

            # Keep the dashboard synchronized with the active board even when
            # the apply request is rejected, so the next preview is not stale.
            self._snapshot = current_snapshot
            self._report = current_report
            self._manufacturing_report = evaluate_manufacturability(
                current_snapshot,
                self._config,
            )
            self._fix_plan = current_plan
            self._silkscreen_plan = None
            self._edge_proposal = None
            self._stitching_plan = None
            self._placement_plan = None

            if stale_ids:
                raise MutationSafetyError(
                    "The board changed after the antenna-fix preview was generated. "
                    "The current board was rescanned and no changes were applied. Rebuild and "
                    "review the antenna-fix preview before applying it."
                )

            selected_plan = FixPlan(
                actions=tuple(current_by_id[action_id] for action_id in requested_ids),
                alternatives=current_plan.alternatives,
                warnings=current_plan.warnings,
            )
            result = self._adapter.apply_fix_plan(selected_plan, self._config)
            return self._post_mutation(result)

    def plan_silkscreen(self) -> dict[str, Any]:
        """Create value-field placement proposals."""

        with self._lock:
            self._ensure_snapshot()
            assert self._snapshot is not None
            self._silkscreen_plan = plan_silkscreen(self._snapshot, self._config.silkscreen)
            return self._silkscreen_plan.to_dict()

    def current_silkscreen_plan(self) -> dict[str, Any] | None:
        """Return the latest silkscreen plan."""

        with self._lock:
            return self._silkscreen_plan.to_dict() if self._silkscreen_plan else None

    def apply_silkscreen(
        self,
        confirmed: bool,
        placement_ids: list[str] | None = None,
    ) -> dict[str, Any]:
        """Apply only explicitly selected value-field updates."""

        with self._lock:
            self._require_confirmation(confirmed)
            if self._silkscreen_plan is None:
                self.plan_silkscreen()
            assert self._silkscreen_plan is not None
            selected_plan = self._silkscreen_plan.selected(placement_ids)
            if not selected_plan.placements:
                raise MutationSafetyError("At least one silkscreen placement must be selected.")
            result = self._adapter.apply_silkscreen_plan(selected_plan, self._config)
            return self._post_mutation(result)

    def plan_edge(self, operation: str = "optimize") -> dict[str, Any]:
        """Create an optimized, smoothed, or filleted board-outline proposal."""

        with self._lock:
            self._ensure_snapshot()
            assert self._snapshot is not None
            self._edge_proposal = propose_edge_outline(
                self._snapshot,
                self._config.edge,
                self._config.antenna.ground_net_regex,
                operation=operation,
            )
            return self._edge_proposal.to_dict()

    def current_edge_proposal(self) -> dict[str, Any] | None:
        """Return the latest board-outline proposal."""

        with self._lock:
            return self._edge_proposal.to_dict() if self._edge_proposal else None

    def plan_component_placement(self) -> dict[str, Any]:
        """Create a schematic-block-aware initial footprint placement proposal."""

        with self._lock:
            self._ensure_snapshot()
            assert self._snapshot is not None
            self._placement_plan = plan_component_placement(
                self._snapshot,
                self._config.placement,
            )
            return self._placement_plan.to_dict()

    def current_component_placement_plan(self) -> dict[str, Any] | None:
        """Return the latest component-placement proposal."""

        with self._lock:
            return self._placement_plan.to_dict() if self._placement_plan else None

    def apply_component_placement(
        self,
        confirmed: bool,
        placement_ids: list[str] | None = None,
    ) -> dict[str, Any]:
        """Apply selected component-placement proposals when explicitly enabled."""

        with self._lock:
            self._require_confirmation(confirmed)
            if self._placement_plan is None:
                self.plan_component_placement()
            assert self._placement_plan is not None
            selected_plan = self._placement_plan.selected(placement_ids)
            selected_plan = ComponentPlacementPlan(
                placements=tuple(item for item in selected_plan.placements if not item.locked),
                groups=selected_plan.groups,
                warnings=selected_plan.warnings,
            )
            if not selected_plan.placements:
                raise MutationSafetyError("At least one unlocked component placement must be selected.")
            result = self._adapter.apply_component_placement_plan(selected_plan, self._config)
            return self._post_mutation(result)

    def plan_stitching(
        self,
        rebuild_perimeter: bool | None = None,
        use_edge_proposal: bool = True,
    ) -> dict[str, Any]:
        """Create a safe GND-via stitching or perimeter-rebuild proposal."""

        with self._lock:
            self._ensure_snapshot()
            assert self._snapshot is not None
            outline = None
            if use_edge_proposal and self._edge_proposal is not None:
                outline = self._edge_proposal.polygon.outline
            self._stitching_plan = plan_via_stitching(
                self._snapshot,
                self._config.stitching,
                outline=outline,
                rebuild_perimeter=rebuild_perimeter,
            )
            return self._stitching_plan.to_dict()

    def current_stitching_plan(self) -> dict[str, Any] | None:
        """Return the latest ground-via stitching proposal."""

        with self._lock:
            return self._stitching_plan.to_dict() if self._stitching_plan else None

    def apply_stitching(
        self,
        confirmed: bool,
        candidate_ids: list[str] | None = None,
        rebuild_perimeter: bool | None = None,
    ) -> dict[str, Any]:
        """Apply selected stitching vias and optional safe perimeter rebuild."""

        with self._lock:
            self._require_confirmation(confirmed)
            if self._stitching_plan is None:
                self.plan_stitching(rebuild_perimeter=rebuild_perimeter)
            assert self._stitching_plan is not None
            selected_plan = self._stitching_plan.selected(
                candidate_ids,
                rebuild_perimeter=rebuild_perimeter,
            )
            if not selected_plan.candidates:
                raise MutationSafetyError("At least one ground-via candidate must be selected.")
            result = self._adapter.apply_via_stitching_plan(selected_plan, self._config)
            return self._post_mutation(result)

    def apply_edge(self, confirmed: bool, board_name: str) -> dict[str, Any]:
        """Apply Edge.Cuts only after a board-name confirmation challenge."""

        with self._lock:
            self._require_confirmation(confirmed)
            self._ensure_snapshot()
            assert self._snapshot is not None
            if board_name.strip() != self._snapshot.board_name:
                raise MutationSafetyError("The board-name confirmation does not match the active board.")
            if self._edge_proposal is None:
                self.plan_edge()
            assert self._edge_proposal is not None
            result = self._adapter.apply_edge_proposal(self._edge_proposal, self._config)
            return self._post_mutation(result)

    def export_report(self, output_directory: str = "") -> dict[str, str]:
        """Write HTML, JSON, and Markdown reports and return their paths."""

        with self._lock:
            self._ensure_analysis()
            assert self._report is not None
            directory = self._resolve_output_directory(output_directory, "reports")
            paths = write_report_bundle(
                directory,
                self._report,
                fix_plan=self._fix_plan,
                silkscreen_plan=(self._silkscreen_plan.to_dict() if self._silkscreen_plan else None),
                edge_proposal=(self._edge_proposal.to_dict() if self._edge_proposal else None),
                manufacturing_report=(
                    self._manufacturing_report.to_dict() if self._manufacturing_report else None
                ),
            )
            result = {name: str(path) for name, path in paths.items()}
            self._last_export = result
            return result

    def export_solver(self, output_directory: str = "") -> dict[str, str]:
        """Write a solver interchange bundle without claiming a solved model."""

        with self._lock:
            self._ensure_snapshot()
            assert self._snapshot is not None
            directory = self._resolve_output_directory(output_directory, "solver")
            paths = export_solver_manifest(self._snapshot, directory, self._config.quantitative)
            result = {name: str(path) for name, path in paths.items()}
            self._last_export = result
            return result

    def close(self) -> None:
        """Close the KiCad IPC connection."""

        with self._lock:
            self._adapter.close()

    def _ensure_snapshot(self) -> None:
        """Read the active board when no cached snapshot exists."""

        if self._snapshot is None:
            self._snapshot = self._adapter.snapshot()

    def _ensure_analysis(self) -> None:
        """Run an analysis when no current report exists."""

        if self._report is None:
            self.analyze(refresh=True)

    def _require_confirmation(self, confirmed: bool) -> None:
        """Reject all write operations unless the safety gates are open."""

        if not confirmed:
            raise MutationSafetyError("Explicit confirmation is required before changing the board.")
        if self._config.fixes.dry_run:
            raise MutationSafetyError(
                "Dry-run mode is enabled; disable it in Settings before applying changes."
            )

    def _post_mutation(self, result: MutationResult) -> dict[str, Any]:
        """Refresh the board and analysis after a successful mutation."""

        self._snapshot = self._adapter.snapshot()
        self._report = analyze_board(self._snapshot, self._config)
        self._manufacturing_report = evaluate_manufacturability(self._snapshot, self._config)
        self._fix_plan = None
        self._silkscreen_plan = None
        self._edge_proposal = None
        self._stitching_plan = None
        self._placement_plan = None
        return {
            "mutation": result.to_dict(),
            "analysis": self._report.to_dict(),
            "preview": _preview_payload(self._snapshot, self._report),
            "manufacturing": self._manufacturing_report.to_dict(),
        }

    def _resolve_output_directory(self, requested: str, category: str) -> Path:
        """Resolve a user path or create a timestamped settings subdirectory."""

        if requested.strip():
            return Path(requested).expanduser().resolve()
        if self._config.ui.report_directory.strip():
            root = Path(self._config.ui.report_directory).expanduser().resolve()
        else:
            root = self._settings_directory / "exports"
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        return root / f"{category}-{stamp}"

    def _invalidate_plans(self) -> None:
        """Discard plans that were generated under older settings."""

        self._fix_plan = None
        self._silkscreen_plan = None
        self._edge_proposal = None
        self._stitching_plan = None
        self._placement_plan = None
        self._manufacturing_report = None


def _optional_float(value: Any) -> float | None:
    """Convert an optional request value to float."""

    if value is None or value == "":
        return None
    return float(value)


def _optional_float_list(value: Any) -> list[float] | None:
    """Convert an optional JSON array to a float list."""

    if value is None:
        return None
    if not isinstance(value, list):
        raise ValueError("track_widths_mm must be an array.")
    return [float(item) for item in value]


def _optional_string_list(value: Any) -> list[str] | None:
    """Convert an optional JSON array to a string list."""

    if value is None:
        return None
    if not isinstance(value, list):
        raise ValueError("via_preset_ids must be an array.")
    return [str(item) for item in value]


def _fix_action_safety_signature(action: FixAction) -> str:
    """Return a deterministic signature of mutation-relevant action data.

    Human-facing descriptions and ranking scores may change without changing
    the proposed board geometry. All fields that identify the target, net,
    layer, geometry, dimensions, and safety proof remain in the signature.
    """

    payload = action.to_dict()
    for key in (
        "description",
        "expected_risk_reduction",
        "implementation_cost",
        "confidence",
    ):
        payload.pop(key, None)
    return json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    )


def _deep_merge(base: Mapping[str, Any], patch: Mapping[str, Any]) -> dict[str, Any]:
    """Recursively merge mappings without mutating either input."""

    result: dict[str, Any] = dict(base)
    for key, value in patch.items():
        current = result.get(key)
        if isinstance(current, Mapping) and isinstance(value, Mapping):
            result[key] = _deep_merge(current, value)
        else:
            result[key] = value
    return result


def _preview_payload(snapshot: BoardSnapshot, report: AnalysisReport) -> dict[str, Any]:
    """Build bounded geometry for the interactive dashboard preview.

    The payload keeps original KiCad item identifiers so a dashboard finding
    can be selected and zoomed in the active PCB Editor.  Limits prevent very
    large boards from exhausting the browser while still exposing per-layer
    controls, footprint/silkscreen context, vias, pads, and remediation
    overlays.
    """

    all_points: list[Point] = []
    for edge in snapshot.edges:
        all_points.extend((edge.start, edge.end))
        if edge.mid is not None:
            all_points.append(edge.mid)
    for track in snapshot.tracks:
        all_points.extend((track.start, track.end))
    for via in snapshot.vias:
        all_points.append(via.position)
    for footprint in snapshot.footprints:
        all_points.extend(
            (
                Point(footprint.bounds.min_x, footprint.bounds.min_y),
                Point(footprint.bounds.max_x, footprint.bounds.max_y),
            )
        )
    bounds = bounds_from_points(all_points)
    if bounds.area <= 0.0:
        bounds = BoundingBox(0.0, 0.0, 100.0, 80.0)

    limits = {
        "tracks": 5000,
        "vias": 3000,
        "pads": 5000,
        "footprints": 2500,
        "zones": 100,
        "edges": 2500,
        "filled_polygons_per_layer": 250,
        "polygon_points": 2000,
    }
    tracks = [
        {
            "item_id": track.item_id,
            "source_item_id": track.source_item_id or track.item_id,
            "start": track.start.to_dict(),
            "end": track.end.to_dict(),
            "width": track.width,
            "layer": track.layer,
            "net": track.net,
        }
        for track in snapshot.tracks[: limits["tracks"]]
    ]
    vias = [
        {
            "item_id": via.item_id,
            "position": via.position.to_dict(),
            "diameter": via.diameter,
            "drill": via.drill,
            "net": via.net,
            "start_layer": via.start_layer,
            "end_layer": via.end_layer,
        }
        for via in snapshot.vias[: limits["vias"]]
    ]
    pads = [
        {
            "item_id": pad.item_id,
            "footprint_id": pad.footprint_id,
            "number": pad.number,
            "position": pad.position.to_dict(),
            "bounds": asdict(pad.bounds),
            "net": pad.net,
            "layers": list(pad.layers),
        }
        for pad in snapshot.pads[: limits["pads"]]
    ]
    footprints = []
    silkscreen = []
    for footprint in snapshot.footprints[: limits["footprints"]]:
        footprints.append(
            {
                "item_id": footprint.item_id,
                "reference": footprint.reference,
                "value": footprint.value,
                "position": footprint.position.to_dict(),
                "layer": footprint.layer,
                "bounds": asdict(footprint.bounds),
                "locked": footprint.locked,
            }
        )
        for field_name, text in (
            ("reference", footprint.reference_field),
            ("value", footprint.value_field),
        ):
            if not text.visible or not text.value:
                continue
            silkscreen.append(
                {
                    "footprint_id": footprint.item_id,
                    "field": field_name,
                    "text": text.value,
                    "position": text.position.to_dict(),
                    "layer": text.layer,
                    "width": text.width,
                    "height": text.height,
                    "thickness": text.thickness,
                    "angle_deg": text.angle_deg,
                }
            )

    zones = []
    for zone in snapshot.zones[: limits["zones"]]:
        if zone.is_rule_area:
            continue
        filled: dict[str, list[dict[str, Any]]] = {}
        for layer, polygons in zone.filled.items():
            filled[layer] = [
                {
                    "outline": [point.to_dict() for point in polygon.outline[: limits["polygon_points"]]],
                    "holes": [
                        [point.to_dict() for point in hole[: limits["polygon_points"]]]
                        for hole in polygon.holes[:32]
                    ],
                }
                for polygon in polygons[: limits["filled_polygons_per_layer"]]
            ]
        zones.append(
            {
                "item_id": zone.item_id,
                "net": zone.net,
                "layers": list(zone.layers),
                "outline": [point.to_dict() for point in zone.outline.outline[: limits["polygon_points"]]],
                "filled": filled,
            }
        )

    layer_names: set[str] = (
        {track.layer for track in snapshot.tracks}
        | {layer for pad in snapshot.pads for layer in pad.layers}
        | {layer for zone in snapshot.zones for layer in zone.layers}
        | {str(text["layer"]) for text in silkscreen}
    )
    preferred_order = [
        "F.SilkS",
        "F.Mask",
        "F.Cu",
        "In1.Cu",
        "In2.Cu",
        "In3.Cu",
        "In4.Cu",
        "B.Cu",
        "B.Mask",
        "B.SilkS",
        "Edge.Cuts",
    ]
    available_layers = [layer for layer in preferred_order if layer in layer_names or layer == "Edge.Cuts"]
    available_layers.extend(sorted(layer_names - set(available_layers)))

    return {
        "bounds": asdict(bounds),
        "available_layers": available_layers,
        "edges": [
            {
                "item_id": edge.item_id,
                "start": edge.start.to_dict(),
                "end": edge.end.to_dict(),
                "mid": edge.mid.to_dict() if edge.mid else None,
                "kind": edge.kind,
            }
            for edge in snapshot.edges[: limits["edges"]]
        ],
        "tracks": tracks,
        "vias": vias,
        "pads": pads,
        "footprints": footprints,
        "silkscreen": silkscreen,
        "zones": zones,
        "truncated": {
            "tracks": max(0, len(snapshot.tracks) - limits["tracks"]),
            "vias": max(0, len(snapshot.vias) - limits["vias"]),
            "pads": max(0, len(snapshot.pads) - limits["pads"]),
            "footprints": max(0, len(snapshot.footprints) - limits["footprints"]),
            "zones": max(0, len(snapshot.zones) - limits["zones"]),
            "edges": max(0, len(snapshot.edges) - limits["edges"]),
        },
        "findings": [
            {
                "id": finding.finding_id,
                "severity": finding.severity.value,
                "category": finding.category,
                "location": finding.location.to_dict() if finding.location else None,
                "item_ids": list(finding.item_ids),
                "layer": str(finding.metrics.get("layer", "")),
            }
            for finding in report.findings
            if finding.location is not None
        ],
    }
