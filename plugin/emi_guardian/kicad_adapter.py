"""KiCad 10+ IPC API adapter.

The module deliberately imports :mod:`kipy` lazily.  The analysis core can be
unit-tested without KiCad, while this adapter absorbs API-version differences
through capability checks and conservative fallbacks.
"""

from __future__ import annotations

import logging
import math
import shutil
import time
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

from .config import AppConfig
from .edge_optimizer import EdgeProposal
from .errors import CapabilityError, EmiGuardianError, MutationSafetyError
from .models import (
    BoardEdge,
    BoardSnapshot,
    BoundingBox,
    CopperZone,
    FixAction,
    FixKind,
    FixPlan,
    FootprintSnapshot,
    Pad,
    Point,
    Polygon,
    StackupInfo,
    TextSnapshot,
    TrackSegment,
)
from .models import (
    Via as ViaSnapshot,
)
from .placement import ComponentPlacementPlan
from .silkscreen import SilkscreenPlan
from .stitching import ViaStitchingPlan

LOGGER = logging.getLogger(__name__)
PLUGIN_IDENTIFIER = "com.openai.kicad.emi-guardian"
NM_PER_MM = 1_000_000.0


@dataclass(frozen=True)
class MutationResult:
    """Result of one board mutation transaction."""

    applied_count: int
    skipped_count: int
    messages: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        """Return a JSON-serializable representation."""

        return {
            "applied_count": self.applied_count,
            "skipped_count": self.skipped_count,
            "messages": list(self.messages),
        }


class KicadIpcAdapter:
    """Read and mutate the active PCB through the official KiCad IPC API."""

    def __init__(self, timeout_ms: int = 5000) -> None:
        """Connect to the KiCad process that launched the plugin."""

        try:
            from kipy import KiCad
        except ImportError as exc:
            raise CapabilityError(
                "The kicad-python package is not installed in the plugin environment."
            ) from exc
        self._KiCad = KiCad
        self._timeout_ms = timeout_ms
        self._retry_count = 2
        self._kicad = KiCad(client_name="EMI Guardian", timeout_ms=timeout_ms)
        _require_supported_kicad_version(str(self._kicad.get_version()))
        self._board = self._kicad.get_board()
        if self._board is None:
            raise EmiGuardianError("No PCB is open in KiCad.")
        self._raw_footprints: dict[str, Any] = {}
        self._raw_vias: dict[str, Any] = {}
        self._raw_edge_shapes: list[Any] = []

    @property
    def settings_directory(self) -> Path:
        """Return the persistent plugin settings directory."""

        try:
            return Path(self._kicad.get_plugin_settings_path(PLUGIN_IDENTIFIER))
        except Exception:
            return Path.home() / ".kicad" / "emi-guardian"

    @property
    def capabilities(self) -> dict[str, bool]:
        """Return detected runtime capabilities."""

        kicad = getattr(self, "_kicad", None)
        board = getattr(self, "_board", None)
        return {
            "ipc_api": True,
            "transactions": all(
                hasattr(board, name) for name in ("begin_commit", "push_commit", "drop_commit")
            ),
            "zone_refill": hasattr(board, "refill_zones"),
            "item_creation": hasattr(board, "create_items"),
            "item_update": hasattr(board, "update_items"),
            "item_removal": hasattr(board, "remove_items"),
            "rule_area_write": _kipy_rule_area_capable(),
            "edge_write": _kipy_edge_capable(),
            "stackup_read": hasattr(board, "get_stackup"),
            "stackup_write": hasattr(board, "set_stackup"),
            "design_rules_write": hasattr(board, "set_design_rules"),
            "selection": all(
                hasattr(board, name) for name in ("clear_selection", "get_items_by_id", "add_to_selection")
            ),
            "active_layer": hasattr(board, "set_active_layer"),
            "zoom_to_selection": hasattr(kicad, "run_action"),
            "ping": hasattr(kicad, "ping"),
        }

    def configure_connection(self, retry_count: int) -> None:
        """Apply validated reconnect behavior from the user configuration."""

        self._retry_count = max(0, min(10, int(retry_count)))

    def ping(self, reconnect: bool = True) -> dict[str, object]:
        """Check the IPC session and reconnect once when it became stale."""

        try:
            if hasattr(self._kicad, "ping"):
                self._kicad.ping()
            else:
                self._kicad.get_version()
            return {"connected": True, "reconnected": False}
        except Exception as first_error:
            if not reconnect:
                raise CapabilityError(f"KiCad IPC ping failed: {first_error}") from first_error
            last_error: Exception = first_error
            for attempt in range(self._retry_count + 1):
                try:
                    self._reconnect()
                    if hasattr(self._kicad, "ping"):
                        self._kicad.ping()
                    return {"connected": True, "reconnected": True, "attempt": attempt + 1}
                except Exception as exc:
                    last_error = exc
                    time.sleep(0.10 * (attempt + 1))
            raise CapabilityError(f"KiCad IPC connection could not be restored: {last_error}") from last_error

    def locate_items(
        self,
        item_ids: Sequence[str],
        *,
        layer: str = "",
        position: Point | None = None,
    ) -> dict[str, object]:
        """Select finding evidence in KiCad and zoom to it when supported.

        KiCad 10 does not expose creation of custom DRC markers through the
        stable IPC surface.  Selection plus zoom is therefore the closest
        non-destructive DRC-like navigation that remains inside supported APIs.
        """

        self.ping()
        if not self.capabilities["selection"]:
            raise CapabilityError("The running KiCad API does not expose board-item selection.")
        normalized_ids = tuple(dict.fromkeys(str(value).split(":", 1)[0] for value in item_ids if value))
        selected: list[Any] = []
        self._board.clear_selection()
        if normalized_ids:
            try:
                kiids = _kiid_messages(normalized_ids)
                selected = list(self._board.get_items_by_id(list(kiids)))
            except Exception as exc:
                raise CapabilityError(
                    f"Finding items could not be resolved in the active board: {exc}"
                ) from exc
            if selected:
                self._board.add_to_selection(selected)
        if layer and self.capabilities["active_layer"]:
            try:
                self._board.set_active_layer(cast(Any, _layer_id_from_name(self._board, layer, 0)))
            except Exception:
                LOGGER.debug("Failed to activate finding layer %s", layer, exc_info=True)
        zoomed = False
        zoom_action = ""
        if selected and self.capabilities["zoom_to_selection"]:
            for action_name in (
                "common.Control.zoomFitSelection",
                "common.Control.zoomFitObjects",
            ):
                try:
                    self._kicad.run_action(action_name)
                    zoomed = True
                    zoom_action = action_name
                    break
                except Exception:
                    LOGGER.debug("KiCad navigation action %s is unavailable", action_name, exc_info=True)
        return {
            "selected_count": len(selected),
            "requested_item_count": len(normalized_ids),
            "zoomed": zoomed,
            "zoom_action": zoom_action,
            "layer": layer,
            "position": position.to_dict() if position else None,
            "navigation_mode": "selection_zoom" if selected else "selection_only",
        }

    def _reconnect(self) -> None:
        """Replace a stale IPC client without keeping simultaneous connections."""

        try:
            close = getattr(self._kicad, "close", None)
            if callable(close):
                close()
        except Exception:
            LOGGER.debug("Closing stale KiCad IPC client failed", exc_info=True)
        self._kicad = self._KiCad(client_name="EMI Guardian", timeout_ms=self._timeout_ms)
        _require_supported_kicad_version(str(self._kicad.get_version()))
        board = self._kicad.get_board()
        if board is None:
            raise EmiGuardianError("No PCB is open in KiCad.")
        self._board = board
        self._raw_footprints.clear()
        self._raw_vias.clear()
        self._raw_edge_shapes.clear()

    def close(self) -> None:
        """Close the IPC client."""

        try:
            close = getattr(self._kicad, "close", None)
            if callable(close):
                close()
        except Exception:
            LOGGER.debug("KiCad IPC close failed", exc_info=True)

    def snapshot(self) -> BoardSnapshot:
        """Read the active board into the KiCad-independent domain model."""

        self.ping()
        tracks = tuple(self._read_tracks())
        vias = tuple(self._read_vias())
        pads = tuple(self._read_pads())
        zones = tuple(self._read_zones())
        footprints = tuple(self._read_footprints(pads))
        edges = tuple(self._read_edges())
        stackup, stackup_metadata = self._read_stackup()
        version = str(self._kicad.get_version())
        board_path = _document_path(getattr(self._board, "document", None))
        return BoardSnapshot(
            board_name=str(getattr(self._board, "name", Path(board_path).name or "Untitled")),
            board_path=board_path,
            kicad_version=version,
            tracks=tracks,
            vias=vias,
            pads=pads,
            zones=zones,
            footprints=footprints,
            edges=edges,
            stackup=stackup,
            metadata={
                "api_version": str(self._kicad.get_api_version()),
                "capabilities": self.capabilities,
                "stackup": stackup_metadata,
            },
        )

    def apply_fix_plan(self, plan: FixPlan, config: AppConfig) -> MutationResult:
        """Apply selected antenna fixes as one undoable transaction."""

        if config.fixes.dry_run:
            raise MutationSafetyError("Dry-run mode is enabled; no board changes were made.")
        if not self.capabilities["item_creation"]:
            raise CapabilityError("The running KiCad IPC API cannot create board items.")
        self._require_transaction(config, "automatic copper fixes")

        items: list[Any] = []
        messages: list[str] = []
        skipped = 0
        for action in plan.actions:
            if action.confidence < config.fixes.minimum_apply_confidence:
                skipped += 1
                messages.append(f"Skipped {action.action_id}: confidence below threshold.")
                continue
            try:
                items.extend(self._items_for_fix(action))
            except CapabilityError as exc:
                skipped += 1
                messages.append(f"Skipped {action.action_id}: {exc}")

        if not items:
            return MutationResult(0, skipped, tuple(messages))
        self._commit_create(items, "EMI Guardian: resolve ground-pour antennas")
        if config.fixes.refill_zones_after_apply and self.capabilities["zone_refill"]:
            try:
                self._board.refill_zones(block=True)
            except Exception as exc:
                LOGGER.exception("Zone refill failed after applying antenna fixes")
                messages.append(f"Board items were created, but zone refill failed: {exc}")
        return MutationResult(len(items), skipped, tuple(messages))

    def apply_component_placement_plan(
        self,
        plan: ComponentPlacementPlan,
        config: AppConfig,
    ) -> MutationResult:
        """Move selected unlocked footprints as one undoable transaction."""

        if config.fixes.dry_run:
            raise MutationSafetyError("Dry-run mode is enabled; no board changes were made.")
        if config.placement.dry_run_only:
            raise MutationSafetyError("Component placement is configured as preview-only.")
        if not self.capabilities["item_update"]:
            raise CapabilityError("The running KiCad IPC API cannot update footprints.")
        self._require_transaction(config, "component placement")
        if not self._raw_footprints:
            tuple(self._read_footprints(tuple(self._read_pads())))

        try:
            from kipy.geometry import Vector2
        except ImportError as exc:
            raise CapabilityError("Required kicad-python geometry types are unavailable.") from exc

        updated: list[Any] = []
        messages: list[str] = []
        for placement in plan.placements:
            raw = self._raw_footprints.get(placement.footprint_id)
            if raw is None:
                messages.append(f"Skipped {placement.reference}: footprint no longer exists.")
                continue
            if placement.locked or bool(getattr(raw, "locked", False)):
                messages.append(f"Skipped {placement.reference}: footprint is locked.")
                continue
            raw.position = Vector2.from_xy_mm(placement.position.x, placement.position.y)
            updated.append(raw)

        if not updated:
            return MutationResult(0, len(plan.placements), tuple(messages))
        self._commit_update(updated, "EMI Guardian: place schematic blocks")
        return MutationResult(len(updated), len(plan.placements) - len(updated), tuple(messages))

    def apply_via_stitching_plan(
        self,
        plan: ViaStitchingPlan,
        config: AppConfig,
    ) -> MutationResult:
        """Apply selected ground-via additions and conservative removals."""

        if config.fixes.dry_run:
            raise MutationSafetyError("Dry-run mode is enabled; no board changes were made.")
        if not self.capabilities["item_creation"]:
            raise CapabilityError("The running KiCad IPC API cannot create vias.")
        if plan.rebuild_perimeter and not self.capabilities["item_removal"]:
            raise CapabilityError("The running KiCad IPC API cannot remove existing perimeter vias.")
        self._require_transaction(config, "ground-via stitching")
        if plan.rebuild_perimeter and not plan.candidates:
            raise MutationSafetyError("Perimeter vias cannot be removed without replacement candidates.")

        try:
            from kipy.board_types import Via
            from kipy.geometry import Vector2
        except ImportError as exc:
            raise CapabilityError("Required kicad-python via types are unavailable.") from exc

        net = self._resolve_net(plan.net)
        additions: list[Any] = []
        for candidate in plan.candidates:
            via = Via()
            via.position = Vector2.from_xy_mm(candidate.position.x, candidate.position.y)
            via.diameter = _to_nm(candidate.diameter_mm)
            via.drill_diameter = _to_nm(candidate.drill_mm)
            via.net = net
            additions.append(via)

        removals: list[Any] = []
        messages: list[str] = []
        if plan.rebuild_perimeter and plan.removable_via_ids:
            if not self._raw_vias:
                tuple(self._read_vias())
            for item_id in plan.removable_via_ids:
                raw = self._raw_vias.get(item_id)
                if raw is None:
                    messages.append(f"Skipped removal of {item_id}: via no longer exists.")
                    continue
                if bool(getattr(raw, "locked", False)):
                    messages.append(f"Skipped removal of {item_id}: via is locked.")
                    continue
                removals.append(raw)

        if not additions and not removals:
            return MutationResult(0, len(plan.candidates) + len(plan.removable_via_ids), tuple(messages))

        commit = self._begin_commit()
        try:
            if removals:
                self._board.remove_items(removals)
            if additions:
                self._board.create_items(additions)
            self._push_commit(commit, "EMI Guardian: rebuild and stitch ground perimeter")
        except Exception:
            self._drop_commit(commit)
            raise
        if config.fixes.refill_zones_after_apply and self.capabilities["zone_refill"]:
            try:
                self._board.refill_zones(block=True)
            except Exception as exc:
                LOGGER.exception("Zone refill failed after applying ground-via stitching")
                messages.append(f"Via changes were committed, but zone refill failed: {exc}")
        return MutationResult(len(additions) + len(removals), 0, tuple(messages))

    def apply_silkscreen_plan(self, plan: SilkscreenPlan, config: AppConfig) -> MutationResult:
        """Apply footprint reference/value visibility and value placement updates."""

        if config.fixes.dry_run:
            raise MutationSafetyError("Dry-run mode is enabled; no board changes were made.")
        if not self.capabilities["item_update"]:
            raise CapabilityError("The running KiCad IPC API cannot update board items.")
        self._require_transaction(config, "silkscreen updates")
        if not self._raw_footprints:
            tuple(self._read_footprints(tuple(self._read_pads())))

        try:
            from kipy.geometry import Vector2
        except ImportError as exc:
            raise CapabilityError("Required kicad-python geometry types are unavailable.") from exc

        updated: list[Any] = []
        messages: list[str] = []
        for placement in plan.placements:
            footprint = self._raw_footprints.get(placement.footprint_id)
            if footprint is None:
                messages.append(f"Skipped {placement.reference}: footprint no longer exists.")
                continue
            reference_field = footprint.reference_field
            value_field = footprint.value_field
            reference_field.visible = not placement.hide_reference
            if config.silkscreen.move_reference_to_fab:
                reference_field.layer = _layer_id_from_name(
                    self._board,
                    placement.reference_layer,
                    reference_field.layer,
                )
                if hasattr(reference_field.text, "layer"):
                    reference_field.text.layer = reference_field.layer
            value_field.visible = placement.show_value
            value_field.layer = _layer_id_from_name(self._board, placement.layer, value_field.layer)
            if hasattr(value_field.text, "layer"):
                value_field.text.layer = value_field.layer
            value_field.text.value = placement.value
            value_field.text.position = Vector2.from_xy_mm(placement.position.x, placement.position.y)
            attributes = value_field.text.attributes
            attributes.size = Vector2.from_xy_mm(
                placement.text_width_mm,
                placement.text_height_mm,
            )
            attributes.stroke_width = _to_nm(placement.text_thickness_mm)
            attributes.angle = placement.angle_deg
            attributes.keep_upright = config.silkscreen.keep_upright
            updated.append(footprint)

        if not updated:
            return MutationResult(0, len(plan.placements), tuple(messages))
        self._commit_update(updated, "EMI Guardian: optimize silkscreen values")
        return MutationResult(len(updated), len(plan.placements) - len(updated), tuple(messages))

    def apply_edge_proposal(
        self,
        proposal: EdgeProposal,
        config: AppConfig,
    ) -> MutationResult:
        """Replace Edge.Cuts after all destructive-operation guards pass."""

        if config.fixes.dry_run:
            raise MutationSafetyError("Dry-run mode is enabled; no board changes were made.")
        if not config.edge.allow_destructive_edge_replacement:
            raise MutationSafetyError("Destructive Edge.Cuts replacement is disabled.")
        if not proposal.ground_band_verified:
            raise MutationSafetyError("The required continuous perimeter GND band was not verified.")
        if not self.capabilities["transactions"]:
            raise CapabilityError("Edge.Cuts replacement requires KiCad transaction support.")
        if not all(self.capabilities[name] for name in ("edge_write", "item_creation", "item_removal")):
            raise CapabilityError("The running KiCad API cannot safely replace Edge.Cuts.")

        board_path = Path(_document_path(getattr(self._board, "document", None)))
        if config.edge.require_explicit_backup:
            if not board_path.exists():
                raise MutationSafetyError(
                    "Save the board before replacing Edge.Cuts so a backup can be created."
                )
            backup_path = board_path.with_suffix(board_path.suffix + ".emi-guardian.bak")
            shutil.copy2(board_path, backup_path)

        if not self._raw_edge_shapes:
            tuple(self._read_edges())
        new_shapes = self._edge_items(proposal, config.edge.edge_width_mm)
        commit = self._begin_commit()
        try:
            self._board.remove_items(self._raw_edge_shapes)
            self._board.create_items(new_shapes)
            self._push_commit(commit, "EMI Guardian: replace and fillet Edge.Cuts")
        except Exception:
            self._drop_commit(commit)
            raise
        return MutationResult(len(new_shapes), 0, ())

    def _read_tracks(self) -> Iterable[TrackSegment]:
        """Yield straight segments, splitting arc tracks into two chords."""

        for raw in self._board.get_tracks():
            item_id = _item_id(raw)
            layer_id = int(getattr(raw, "layer", 0))
            layer = _layer_name(self._board, layer_id)
            net = _net_name(getattr(raw, "net", None))
            width = _to_mm(getattr(raw, "width", 0))
            start = _point(getattr(raw, "start", None))
            end = _point(getattr(raw, "end", None))
            mid_raw = getattr(raw, "mid", None)
            if mid_raw is not None:
                mid = _point(mid_raw)
                yield TrackSegment(
                    f"{item_id}:a",
                    start,
                    mid,
                    width,
                    layer,
                    layer_id,
                    net,
                    bool(getattr(raw, "locked", False)),
                    source_item_id=item_id,
                    is_curve_approximation=True,
                )
                yield TrackSegment(
                    f"{item_id}:b",
                    mid,
                    end,
                    width,
                    layer,
                    layer_id,
                    net,
                    bool(getattr(raw, "locked", False)),
                    source_item_id=item_id,
                    is_curve_approximation=True,
                )
            else:
                yield TrackSegment(
                    item_id,
                    start,
                    end,
                    width,
                    layer,
                    layer_id,
                    net,
                    bool(getattr(raw, "locked", False)),
                    source_item_id=item_id,
                    is_curve_approximation=False,
                )

    def _read_vias(self) -> Iterable[ViaSnapshot]:
        """Yield via snapshots and retain raw objects for safe removals."""

        self._raw_vias.clear()
        for raw in self._board.get_vias():
            item_id = _item_id(raw)
            self._raw_vias[item_id] = raw
            padstack = getattr(raw, "padstack", None)
            drill = getattr(padstack, "drill", None)
            start_layer_id = int(getattr(drill, "start_layer", 0))
            end_layer_id = int(getattr(drill, "end_layer", 31))
            yield ViaSnapshot(
                item_id=item_id,
                position=_point(raw.position),
                diameter=_to_mm(getattr(raw, "diameter", 0)),
                drill=_to_mm(getattr(raw, "drill_diameter", 0)),
                net=_net_name(getattr(raw, "net", None)),
                start_layer=_layer_name(self._board, start_layer_id),
                end_layer=_layer_name(self._board, end_layer_id),
                locked=bool(getattr(raw, "locked", False)),
            )

    def _read_pads(self) -> Iterable[Pad]:
        """Yield pad snapshots with KiCad-computed bounding boxes."""

        for raw in self._board.get_pads():
            try:
                bounds = _box(self._board.get_item_bounding_box(raw))
            except Exception:
                position = _point(raw.position)
                size = _pad_size(raw)
                bounds = BoundingBox(
                    position.x - size[0] / 2.0,
                    position.y - size[1] / 2.0,
                    position.x + size[0] / 2.0,
                    position.y + size[1] / 2.0,
                )
            layers = tuple(
                _layer_name(self._board, int(layer))
                for layer in getattr(getattr(raw, "padstack", None), "layers", ())
            )
            yield Pad(
                item_id=_item_id(raw),
                footprint_id=_parent_item_id(raw),
                number=str(getattr(raw, "number", "")),
                position=_point(raw.position),
                bounds=bounds,
                net=_net_name(getattr(raw, "net", None)),
                layers=layers,
            )

    def _read_zones(self) -> Iterable[CopperZone]:
        """Yield copper zones and rule areas."""

        for raw in self._board.get_zones():
            layer_ids = tuple(int(layer) for layer in getattr(raw, "layers", ()))
            layer_names = tuple(_layer_name(self._board, layer) for layer in layer_ids)
            outline = _polygon(getattr(raw, "outline", None))
            filled: dict[str, tuple[Polygon, ...]] = {}
            for layer_id, polygons in getattr(raw, "filled_polygons", {}).items():
                filled[_layer_name(self._board, int(layer_id))] = tuple(
                    _polygon(polygon) for polygon in polygons
                )
            yield CopperZone(
                item_id=_item_id(raw),
                net=_net_name(getattr(raw, "net", None)),
                layers=layer_names,
                layer_ids=layer_ids,
                outline=outline,
                filled=filled,
                is_rule_area=_is_rule_area(raw),
                locked=bool(getattr(raw, "locked", False)),
            )

    def _read_footprints(self, pads: Sequence[Pad]) -> Iterable[FootprintSnapshot]:
        """Yield footprint snapshots and retain raw objects for later updates."""

        self._raw_footprints.clear()
        for raw in self._board.get_footprints():
            item_id = _item_id(raw)
            self._raw_footprints[item_id] = raw
            reference_field = raw.reference_field
            value_field = raw.value_field
            try:
                bounds = _box(self._board.get_item_bounding_box(raw))
            except Exception:
                position = _point(raw.position)
                bounds = BoundingBox(position.x - 1.0, position.y - 1.0, position.x + 1.0, position.y + 1.0)
            position = _point(raw.position)
            reference_text = _text_snapshot(self._board, reference_field)
            value_text = _text_snapshot(self._board, value_field)
            footprint_pads = tuple(
                pad
                for pad in pads
                if pad.footprint_id == item_id or (not pad.footprint_id and pad.bounds.intersects(bounds))
            )
            yield FootprintSnapshot(
                item_id=item_id,
                reference=reference_text.value,
                value=value_text.value,
                position=position,
                layer=_layer_name(self._board, int(getattr(raw, "layer", 0))),
                bounds=bounds,
                reference_field=reference_text,
                value_field=value_text,
                pads=footprint_pads,
                locked=bool(getattr(raw, "locked", False)),
                sheet_path=_footprint_sheet_path(raw),
                library_id=_footprint_library_id(raw),
                description=_footprint_description(raw),
            )

    def _read_edges(self) -> Iterable[BoardEdge]:
        """Yield Edge.Cuts shapes as segment or arc records."""

        self._raw_edge_shapes.clear()
        for raw in self._board.get_shapes():
            layer_id = int(getattr(raw, "layer", -1))
            if _layer_name(self._board, layer_id) != "Edge.Cuts":
                continue
            start_raw = getattr(raw, "start", None)
            end_raw = getattr(raw, "end", None)
            if start_raw is None or end_raw is None:
                continue
            self._raw_edge_shapes.append(raw)
            mid_raw = getattr(raw, "mid", None)
            width = _stroke_width_mm(raw, 0.05)
            yield BoardEdge(
                item_id=_item_id(raw),
                start=_point(start_raw),
                end=_point(end_raw),
                width=width,
                kind="arc" if mid_raw is not None else "segment",
                mid=_point(mid_raw) if mid_raw is not None else None,
            )

    def _read_stackup(self) -> tuple[StackupInfo, dict[str, object]]:
        """Read electrical and manufacturing stackup fields defensively."""

        defaults = StackupInfo()
        try:
            stackup = self._board.get_stackup()
            layers = tuple(getattr(stackup, "layers", ()))
        except Exception as exc:
            return defaults, {"source": "defaults", "reason": str(exc)}

        epsilon_values: list[float] = []
        loss_values: list[float] = []
        dielectric_thicknesses: list[float] = []
        copper_thicknesses: list[float] = []
        physical_thicknesses: list[float] = []
        solder_mask_colors: list[str] = []
        layer_records: list[dict[str, object]] = []
        detected_copper_layers = 0

        for index, layer in enumerate(layers):
            name = _stackup_layer_name(layer, index)
            layer_type = str(getattr(layer, "type", getattr(layer, "layer_type", "")) or "")
            color = _stackup_color(getattr(layer, "color", ""))
            thickness = _to_mm(getattr(layer, "thickness", 0))
            dielectric = getattr(layer, "dielectric", None)
            nested_thicknesses: list[float] = []
            if dielectric is not None:
                nested_thicknesses = _extract_numeric(dielectric, "thickness", convert_nm=True)
                dielectric_thicknesses.extend(nested_thicknesses)
                epsilon_values.extend(_extract_numeric(dielectric, "epsilon_r"))
                loss_values.extend(_extract_numeric(dielectric, "loss_tangent"))
            if thickness > 0.0:
                physical_thicknesses.append(thickness)
            elif nested_thicknesses:
                physical_thicknesses.append(sum(nested_thicknesses))

            normalized = f"{name} {layer_type}".lower()
            is_copper = name.endswith(".Cu") or "copper" in normalized
            is_dielectric = dielectric is not None or "dielectric" in normalized
            is_mask = "mask" in normalized
            if is_copper:
                detected_copper_layers += 1
                if thickness > 0.0:
                    copper_thicknesses.append(thickness)
            elif is_dielectric and thickness > 0.0:
                dielectric_thicknesses.append(thickness)
            if is_mask and color:
                solder_mask_colors.append(color)

            layer_records.append(
                {
                    "name": name,
                    "type": layer_type,
                    "thickness_mm": thickness,
                    "color": color,
                }
            )

        try:
            copper_layer_count = int(self._board.get_copper_layer_count())
        except Exception:
            copper_layer_count = detected_copper_layers

        explicit_thickness = 0.0
        for attribute in ("board_thickness", "total_thickness", "thickness"):
            explicit_thickness = _to_mm(getattr(stackup, attribute, 0))
            if explicit_thickness > 0.0:
                break
        board_thickness = explicit_thickness or sum(physical_thicknesses)
        info = StackupInfo(
            dielectric_constant=_median(epsilon_values) or defaults.dielectric_constant,
            loss_tangent=_median(loss_values) or defaults.loss_tangent,
            signal_to_reference_height=_median(dielectric_thicknesses) or defaults.signal_to_reference_height,
            copper_thickness=_median(copper_thicknesses) or defaults.copper_thickness,
        )
        return info, {
            "source": "board",
            "layer_count": len(layers),
            "copper_layer_count": copper_layer_count,
            "board_thickness_mm": board_thickness,
            "solder_mask_colors": sorted(set(solder_mask_colors)),
            "copper_finish": str(getattr(stackup, "copper_finish", "") or ""),
            "layers": layer_records,
        }

    def _items_for_fix(self, action: FixAction) -> list[Any]:
        """Build KiCad board items for one fix action."""

        try:
            from kipy.board_types import Track, Via, Zone, ZoneType
            from kipy.geometry import Vector2
        except ImportError as exc:
            raise CapabilityError("Required kicad-python board types are unavailable.") from exc

        net = None if action.kind == FixKind.RULE_AREA else self._resolve_net(action.net)
        items: list[Any] = []
        if action.kind in {FixKind.TRACK_BRIDGE, FixKind.TRACK_AND_VIA}:
            if action.start is None or action.end is None:
                raise CapabilityError("Track fix lacks start or end coordinates.")
            track = Track()
            track.start = Vector2.from_xy_mm(action.start.x, action.start.y)
            track.end = Vector2.from_xy_mm(action.end.x, action.end.y)
            track.width = _to_nm(float(action.parameters.get("width_mm", 0.40)))
            track.layer = cast(Any, action.layer_id)
            assert net is not None
            track.net = net
            items.append(track)
        if action.kind in {FixKind.STITCHING_VIA, FixKind.TRACK_AND_VIA}:
            if action.position is None:
                raise CapabilityError("Via fix lacks a position.")
            via = Via()
            via.position = Vector2.from_xy_mm(action.position.x, action.position.y)
            via.diameter = _to_nm(float(action.parameters.get("diameter_mm", 0.60)))
            via.drill_diameter = _to_nm(float(action.parameters.get("drill_mm", 0.30)))
            assert net is not None
            via.net = net
            items.append(via)
        if action.kind == FixKind.RULE_AREA:
            if action.polygon is None:
                raise CapabilityError("Rule-area fix lacks a polygon.")
            zone = Zone()
            zone.layers = [cast(Any, action.layer_id)]
            zone.outline = _kipy_polygon(action.polygon)
            value = _zone_type_value(ZoneType)
            if value is None:
                raise CapabilityError(
                    "The installed kicad-python package does not expose rule-area zone types."
                )
            zone.type = cast(Any, value)
            zone.name = f"EMI Guardian {action.finding_id}"
            if not _configure_copper_keepout(zone):
                raise CapabilityError(
                    "The running API cannot explicitly configure copper-pour keepout flags; no ineffective rule area was created."
                )
            items.append(zone)
        return items

    def _resolve_net(self, name: str) -> Any:
        """Return the existing KiCad net object with an exact name match."""

        try:
            nets = self._board.get_nets()
        except Exception as exc:
            raise CapabilityError(f"The active board net table could not be read: {exc}") from exc
        values = nets.values() if isinstance(nets, Mapping) else nets
        for net in values:
            if _net_name(net) == name:
                return net
        raise CapabilityError(f"Net '{name}' no longer exists on the active board.")

    def _edge_items(self, proposal: EdgeProposal, width_mm: float) -> list[Any]:
        """Build line and arc board shapes on Edge.Cuts."""

        try:
            from kipy.board_types import BoardArc, BoardSegment
            from kipy.geometry import Vector2
        except ImportError as exc:
            raise CapabilityError("Required edge-shape types are unavailable.") from exc
        edge_layer = _layer_id_from_name(self._board, "Edge.Cuts", 47)
        items: list[Any] = []
        for primitive in proposal.primitives:
            item: Any
            if primitive.kind == "arc":
                if primitive.mid is None:
                    raise CapabilityError("An arc primitive lacks its middle point.")
                item = BoardArc()
                item.start = Vector2.from_xy_mm(primitive.start.x, primitive.start.y)
                item.mid = Vector2.from_xy_mm(primitive.mid.x, primitive.mid.y)
                item.end = Vector2.from_xy_mm(primitive.end.x, primitive.end.y)
            else:
                item = BoardSegment()
                item.start = Vector2.from_xy_mm(primitive.start.x, primitive.start.y)
                item.end = Vector2.from_xy_mm(primitive.end.x, primitive.end.y)
            item.layer = cast(Any, edge_layer)
            item.attributes.stroke.width = _to_nm(width_mm)
            items.append(item)
        return items

    def _commit_create(self, items: Sequence[Any], message: str) -> None:
        """Create items inside one transaction."""

        commit = self._begin_commit()
        try:
            self._board.create_items(items)
            self._push_commit(commit, message)
        except Exception:
            self._drop_commit(commit)
            raise

    def _commit_update(self, items: Sequence[Any], message: str) -> None:
        """Update items inside one transaction."""

        commit = self._begin_commit()
        try:
            self._board.update_items(items)
            self._push_commit(commit, message)
        except Exception:
            self._drop_commit(commit)
            raise

    def _require_transaction(self, config: AppConfig, operation: str) -> None:
        """Reject configured single-undo writes when transactions are unavailable."""

        if config.fixes.create_single_undo_group and not self.capabilities["transactions"]:
            raise CapabilityError(
                f"{operation.capitalize()} require KiCad transaction support because "
                "create_single_undo_group is enabled."
            )

    def _begin_commit(self) -> Any | None:
        """Begin a transaction when supported."""

        return self._board.begin_commit() if self.capabilities["transactions"] else None

    def _push_commit(self, commit: Any | None, message: str) -> None:
        """Push a transaction when one was opened."""

        if commit is not None:
            self._board.push_commit(commit, message)

    def _drop_commit(self, commit: Any | None) -> None:
        """Drop a transaction without masking the original exception."""

        if commit is not None:
            try:
                self._board.drop_commit(commit)
            except Exception:
                LOGGER.exception("Failed to drop KiCad transaction")


def _footprint_sheet_path(raw: Any) -> str:
    """Return the most specific available schematic sheet path."""

    for name in ("sheet_path", "path", "schematic_path"):
        value = getattr(raw, name, None)
        if value:
            return str(getattr(value, "value", value))
    definition = getattr(raw, "definition", None)
    for name in ("sheet_path", "path"):
        value = getattr(definition, name, None) if definition is not None else None
        if value:
            return str(getattr(value, "value", value))
    return ""


def _footprint_library_id(raw: Any) -> str:
    """Return a stable footprint-library identifier when exposed by KiCad."""

    definition = getattr(raw, "definition", None)
    candidates = (
        getattr(raw, "library_id", None),
        getattr(raw, "library_link", None),
        getattr(definition, "library_id", None) if definition is not None else None,
        getattr(definition, "library_link", None) if definition is not None else None,
        getattr(definition, "name", None) if definition is not None else None,
    )
    for value in candidates:
        if value:
            return str(getattr(value, "value", value))
    return ""


def _footprint_description(raw: Any) -> str:
    """Return footprint description text when available."""

    description_field = getattr(raw, "description_field", None)
    text = getattr(description_field, "text", None) if description_field is not None else None
    value = getattr(text, "value", None) if text is not None else None
    if value:
        return str(value)
    definition = getattr(raw, "definition", None)
    for candidate in (
        getattr(raw, "description", None),
        getattr(definition, "description", None) if definition is not None else None,
    ):
        if candidate:
            return str(candidate)
    return ""


def _kiid_messages(values: Sequence[str]) -> tuple[Any, ...]:
    """Convert UUID strings to KiCad KIID protobuf messages.

    ``Board.get_items_by_id`` accepts ``KIID`` messages, not plain strings.
    The import remains lazy so the analysis core and unit tests can run without
    a KiCad-managed Python environment.
    """

    try:
        from kipy.proto.common.types import KIID
    except ImportError:
        LOGGER.debug("kipy KIID type is unavailable; passing identifiers through for test compatibility")
        return tuple(values)
    result: list[Any] = []
    for value in values:
        try:
            result.append(KIID(value=str(value)))
        except Exception as exc:
            raise CapabilityError(f"Invalid KiCad item identifier '{value}': {exc}") from exc
    return tuple(result)


def _point(vector: Any) -> Point:
    """Convert a KiCad nanometer vector to a millimeter point."""

    if vector is None:
        return Point(0.0, 0.0)
    return Point(_to_mm(getattr(vector, "x", 0)), _to_mm(getattr(vector, "y", 0)))


def _box(raw: Any) -> BoundingBox:
    """Convert a KiCad box to a millimeter bounding box."""

    position = _point(getattr(raw, "pos", None))
    size = _point(getattr(raw, "size", None))
    return BoundingBox(position.x, position.y, position.x + size.x, position.y + size.y)


def _text_snapshot(board: Any, field: Any) -> TextSnapshot:
    """Convert a KiCad footprint field to a text snapshot."""

    text = field.text
    attributes = text.attributes
    size = getattr(attributes, "size", None)
    return TextSnapshot(
        value=str(getattr(text, "value", "")),
        position=_point(getattr(text, "position", None)),
        layer=_layer_name(board, int(getattr(field, "layer", getattr(text, "layer", 0)))),
        visible=bool(getattr(field, "visible", False)),
        width=_to_mm(getattr(size, "x", 0)),
        height=_to_mm(getattr(size, "y", 0)),
        thickness=_to_mm(getattr(attributes, "stroke_width", 0)),
        angle_deg=float(getattr(attributes, "angle", 0.0)),
    )


def _polygon(raw: Any) -> Polygon:
    """Convert a KiCad polygon-with-holes wrapper."""

    if raw is None:
        return Polygon(())
    outline = _polyline_points(getattr(raw, "outline", None))
    holes = tuple(_polyline_points(hole) for hole in getattr(raw, "holes", ()))
    return Polygon(outline=outline, holes=holes)


def _polyline_points(raw: Any) -> tuple[Point, ...]:
    """Flatten points and arc control points from a KiCad polyline."""

    if raw is None:
        return ()
    result: list[Point] = []
    for node in getattr(raw, "nodes", ()):
        if bool(getattr(node, "has_point", False)):
            result.append(_point(node.point))
        elif bool(getattr(node, "has_arc", False)):
            arc = node.arc
            for vector in (getattr(arc, "start", None), getattr(arc, "mid", None), getattr(arc, "end", None)):
                point = _point(vector)
                if not result or point != result[-1]:
                    result.append(point)
        elif hasattr(node, "point"):
            result.append(_point(node.point))
    if len(result) > 1 and result[0] == result[-1]:
        result.pop()
    return tuple(result)


def _kipy_polygon(polygon: Polygon) -> Any:
    """Convert a domain polygon to a kicad-python polygon wrapper."""

    try:
        from kipy.geometry import PolygonWithHoles, PolyLine, PolyLineNode
    except ImportError as exc:
        raise CapabilityError("Required polygon geometry types are unavailable.") from exc
    outline = PolyLine()
    outline.closed = True
    for point in polygon.outline:
        outline.append(PolyLineNode.from_xy(_to_nm(point.x), _to_nm(point.y)))
    result = PolygonWithHoles()
    result.outline = outline
    for hole_points in polygon.holes:
        hole = PolyLine()
        hole.closed = True
        for point in hole_points:
            hole.append(PolyLineNode.from_xy(_to_nm(point.x), _to_nm(point.y)))
        result.add_hole(hole)
    return result


def _configure_copper_keepout(zone: Any) -> bool:
    """Configure a rule area to block copper pours without blocking routed items.

    KiCad 10.0 exposes ``RuleAreaSettings`` in the API protobuf while
    kicad-python 0.7.x does not yet provide a public wrapper property.  The
    narrow ``_proto`` fallback is therefore isolated here and followed by
    descriptor-based compatibility handling for later wrapper revisions.
    """

    proto = getattr(zone, "proto", getattr(zone, "_proto", None))
    if proto is None:
        return False

    settings = getattr(proto, "rule_area_settings", None)
    if settings is not None:
        required_fields = (
            "keepout_copper",
            "keepout_vias",
            "keepout_tracks",
            "keepout_pads",
            "keepout_footprints",
        )
        if all(hasattr(settings, field) for field in required_fields):
            settings.keepout_copper = True
            settings.keepout_vias = False
            settings.keepout_tracks = False
            settings.keepout_pads = False
            settings.keepout_footprints = False
            return True

    configured = False
    candidates = [proto]
    for name in (
        "rule_area_settings",
        "keepout_settings",
        "rules",
        "keepout",
    ):
        value = getattr(proto, name, None)
        if value is not None:
            candidates.append(value)
    for candidate in candidates:
        descriptor = getattr(candidate, "DESCRIPTOR", None)
        if descriptor is None:
            continue
        for field in descriptor.fields:
            lower = field.name.lower()
            if field.type != field.TYPE_BOOL:
                continue
            if "copper" in lower and ("keepout" in lower or "pour" in lower or "zone" in lower):
                setattr(candidate, field.name, True)
                configured = True
            elif any(token in lower for token in ("track", "via", "pad", "footprint")) and "keepout" in lower:
                setattr(candidate, field.name, False)
    return configured


def _zone_type_value(zone_type: Any) -> int | None:
    """Resolve the rule-area enum across compatible kicad-python versions."""

    for name in ("ZT_RULE_AREA", "ZONE_TYPE_RULE_AREA", "RULE_AREA"):
        value = getattr(zone_type, name, None)
        if value is not None:
            return int(value)
        try:
            return int(zone_type.Value(name))
        except Exception:
            pass
    return None


def _kipy_rule_area_capable() -> bool:
    """Return whether rule-area construction types are importable."""

    try:
        from kipy.board_types import Zone, ZoneType  # noqa: F401
        from kipy.geometry import PolygonWithHoles  # noqa: F401
    except ImportError:
        return False
    return _zone_type_value(ZoneType) is not None


def _kipy_edge_capable() -> bool:
    """Return whether line and arc board-shape constructors are importable."""

    try:
        from kipy.board_types import BoardArc, BoardSegment  # noqa: F401
    except ImportError:
        return False
    return True


def _stackup_layer_name(layer: Any, index: int) -> str:
    """Return a readable stackup layer name across wrapper revisions."""

    for attribute in ("name", "canonical_name", "layer_name"):
        value = getattr(layer, attribute, "")
        if value:
            return str(value)
    layer_id = getattr(layer, "layer", None)
    if layer_id is not None:
        return str(layer_id)
    return f"stackup-{index}"


def _stackup_color(value: Any) -> str:
    """Normalize a stackup color wrapper to a lower-case name or hex value."""

    if value is None:
        return ""
    for attribute in ("name", "value", "hex", "html"):
        candidate = getattr(value, attribute, "")
        if candidate:
            return str(candidate).strip().lower()
    rendered = str(value).strip()
    if rendered in {"", "None"}:
        return ""
    return rendered.lower()


def _layer_name(board: Any, layer_id: int) -> str:
    """Return the canonical KiCad layer name for a protobuf layer identifier."""

    try:
        from kipy import util as kipy_util

        canonical = str(kipy_util.canonical_name(layer_id))  # type: ignore[attr-defined]
        if canonical:
            return canonical
    except Exception:
        pass
    try:
        return str(board.get_layer_name(layer_id))
    except Exception:
        return str(layer_id)


def _layer_id_from_name(board: Any, name: str, fallback: int) -> int:
    """Resolve canonical or user-visible layer names without legacy constants."""

    try:
        from kipy import util as kipy_util

        layer_id = int(kipy_util.layer_from_canonical_name(name))  # type: ignore[attr-defined]
        if str(kipy_util.canonical_name(layer_id)) == name:  # type: ignore[attr-defined]
            return layer_id
    except Exception:
        pass
    try:
        for layer_id in board.get_enabled_layers():
            raw_id = int(layer_id)
            try:
                if str(board.get_layer_name(raw_id)) == name:
                    return raw_id
            except Exception:
                continue
    except Exception:
        pass
    return fallback


def _item_id(item: Any) -> str:
    """Return a stable string representation of a KiCad item identifier."""

    if item is None:
        return ""
    identifier = getattr(item, "id", None)
    for candidate in (identifier, item):
        if candidate is None:
            continue
        for attribute in ("value", "uuid", "kiid"):
            value = getattr(candidate, attribute, None)
            if value:
                return str(value)
    return str(identifier) if identifier is not None else ""


def _parent_item_id(item: Any) -> str:
    """Return a parent footprint identifier when the runtime exposes one."""

    for name in ("parent_footprint_id", "footprint_id", "parent_id"):
        value = getattr(item, name, None)
        if value is None:
            continue
        if isinstance(value, (str, int)):
            return str(value)
        identifier = _item_id(value)
        if identifier not in {"", "None"}:
            return identifier
    for name in ("parent", "footprint"):
        value = getattr(item, name, None)
        if value is not None:
            identifier = _item_id(value)
            if identifier not in {"", "None"}:
                return identifier
    return ""


def _is_rule_area(zone: Any) -> bool:
    """Read rule-area state across method- and property-style wrappers."""

    value = getattr(zone, "is_rule_area", False)
    try:
        return bool(value()) if callable(value) else bool(value)
    except Exception:
        return False


def _stroke_width_mm(item: Any, fallback_mm: float) -> float:
    """Read a board-shape stroke width with defensive wrapper handling."""

    attributes = getattr(item, "attributes", None)
    stroke = getattr(attributes, "stroke", None)
    value = getattr(stroke, "width", None)
    width = _to_mm(value)
    return width if width > 0.0 else fallback_mm


def _net_name(net: Any) -> str:
    """Return a net name or an empty string."""

    return str(getattr(net, "name", "") or "")


def _require_supported_kicad_version(version: str) -> None:
    """Reject KiCad releases older than the supported IPC baseline."""

    match = __import__("re").search(r"(?<!\d)(\d+)(?:\.\d+){0,2}", version)
    if match is None:
        LOGGER.warning("Could not parse KiCad version string %r; using capability checks.", version)
        return
    if int(match.group(1)) < 10:
        raise CapabilityError(f"EMI Guardian requires KiCad 10 or later; the running version is {version}.")


def _document_path(document: Any) -> str:
    """Extract a filesystem path from a document specifier."""

    if document is None:
        return ""
    for name in ("path", "file_path", "filename"):
        value = getattr(document, name, "")
        if value:
            return str(value)
    return ""


def _pad_size(pad: Any) -> tuple[float, float]:
    """Return a representative pad size."""

    padstack = getattr(pad, "padstack", None)
    for layer in getattr(padstack, "copper_layers", ()):
        size = getattr(layer, "size", None)
        if size is not None:
            return (_to_mm(getattr(size, "x", 0)), _to_mm(getattr(size, "y", 0)))
    return (1.0, 1.0)


def _extract_numeric(value: Any, name: str, convert_nm: bool = False) -> list[float]:
    """Recursively extract numeric attributes from protobuf wrappers."""

    result: list[float] = []
    seen: set[int] = set()

    def visit(current: Any, depth: int) -> None:
        if current is None or depth > 3 or id(current) in seen:
            return
        seen.add(id(current))
        direct = getattr(current, name, None)
        if isinstance(direct, (int, float)) and direct > 0:
            result.append(_to_mm(direct) if convert_nm else float(direct))
        if isinstance(current, Mapping):
            for child in current.values():
                visit(child, depth + 1)
        elif isinstance(current, (list, tuple)):
            for child in current:
                visit(child, depth + 1)
        else:
            for child_name in ("layers", "properties", "dielectric", "items"):
                child = getattr(current, child_name, None)
                if child is not None:
                    visit(child, depth + 1)

    visit(value, 0)
    return result


def _median(values: Sequence[float]) -> float:
    """Return the median or zero."""

    ordered = sorted(value for value in values if math.isfinite(value) and value > 0.0)
    if not ordered:
        return 0.0
    middle = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[middle]
    return (ordered[middle - 1] + ordered[middle]) / 2.0


def _to_mm(value_nm: Any) -> float:
    """Convert nanometers to millimeters."""

    try:
        return float(value_nm) / NM_PER_MM
    except (TypeError, ValueError):
        return 0.0


def _to_nm(value_mm: float) -> int:
    """Convert millimeters to integer nanometers."""

    return int(round(float(value_mm) * NM_PER_MM))
