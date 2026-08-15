"""Regression tests for the v0.0.2 localization, scoring, preview, and navigation features."""

from __future__ import annotations

from pathlib import Path

from conftest import footprint, rectangular_edges, snapshot
from emi_guardian.analysis import _category_scores, analyze_board
from emi_guardian.config import AppConfig, EdgeConfig
from emi_guardian.controller import GuardianController, _preview_payload
from emi_guardian.edge_optimizer import _reflex_vertices, propose_edge_outline
from emi_guardian.kicad_adapter import KicadIpcAdapter
from emi_guardian.models import (
    BoundingBox,
    Finding,
    FootprintSnapshot,
    Pad,
    Point,
    Severity,
    TextSnapshot,
    TrackSegment,
    Via,
)


def _corner_finding(index: int) -> Finding:
    """Return one low-order corner finding for score saturation tests."""

    return Finding(
        finding_id=f"corner-{index}",
        category="corner",
        title="Sharp trace corner",
        description="English description",
        severity=Severity.LOW,
        confidence=0.93,
        score_penalty=3.5,
        location=Point(float(index), 0.0),
        item_ids=(f"t{index}",),
        metrics={"included_angle_deg": 30.0, "layer": "F.Cu"},
        recommendation="English recommendation",
        rule_id="noise.corner",
    )


def test_finding_payload_contains_complete_japanese_presentation() -> None:
    """Keep Japanese titles, details, recommendations, and metric labels together."""

    payload = _corner_finding(1).to_dict()
    japanese = payload["localized"]["ja"]
    assert japanese["title"] == "鋭角な配線コーナー"
    assert "配線頂点" in japanese["description"]
    assert "45度" in japanese["recommendation"]
    assert japanese["metric_labels"]["included_angle_deg"] == "内角 (度)"
    assert japanese["metric_labels"]["layer"] == "レイヤー"


def test_many_corner_findings_keep_nonzero_score_resolution() -> None:
    """Do not collapse the corner category to an unexplained exact zero."""

    scores = _category_scores(_corner_finding(index) for index in range(200))
    assert 1.0 <= scores["corner"] < 100.0


def test_analysis_records_stage_runtime_and_localized_findings() -> None:
    """Expose timing and localized evidence in one stable report payload."""

    board = snapshot(
        tracks=(
            TrackSegment("a", Point(0, 0), Point(10, 0), 0.2, "F.Cu", 0, "SIG"),
            TrackSegment("b", Point(10, 0), Point(6, 3), 0.2, "F.Cu", 0, "SIG"),
        ),
        edges=rectangular_edges(-2, -2, 20, 10),
    )
    report = analyze_board(board, AppConfig()).to_dict()
    assert set(report["statistics"]["performance_seconds"]) == {
        "antenna",
        "noise",
        "quantitative",
        "total",
    }
    corner = next(item for item in report["findings"] if item["rule_id"] == "noise.corner")
    assert corner["localized"]["ja"]["title"] == "鋭角な配線コーナー"


def test_preview_payload_includes_layers_silkscreen_and_selectable_ids() -> None:
    """Provide enough board context for zoomable, layer-filtered browser previews."""

    value = TextSnapshot("10k", Point(5, 3), "F.SilkS", True, 0.8, 0.8, 0.12)
    reference = TextSnapshot("R1", Point(5, 2), "F.SilkS", True, 0.8, 0.8, 0.12)
    fp = FootprintSnapshot(
        item_id="fp1",
        reference="R1",
        value="10k",
        position=Point(5, 5),
        layer="F.Cu",
        bounds=BoundingBox(4, 4, 6, 6),
        reference_field=reference,
        value_field=value,
    )
    board = snapshot(
        tracks=(
            TrackSegment("arc:a", Point(0, 0), Point(4, 0), 0.2, "F.Cu", 0, "SIG", source_item_id="arc"),
        ),
        vias=(Via("v1", Point(3, 3), 0.6, 0.3, "GND"),),
        pads=(Pad("p1", "fp1", "1", Point(5, 5), BoundingBox(4.5, 4.5, 5.5, 5.5), "SIG", ("F.Cu",)),),
        footprints=(fp,),
        edges=rectangular_edges(-1, -1, 10, 10),
    )
    report = analyze_board(board, AppConfig())
    payload = _preview_payload(board, report)
    assert payload["tracks"][0]["source_item_id"] == "arc"
    assert payload["pads"][0]["item_id"] == "p1"
    assert {entry["text"] for entry in payload["silkscreen"]} == {"R1", "10k"}
    assert {"F.Cu", "F.SilkS", "Edge.Cuts"}.issubset(payload["available_layers"])


class _SelectableBoard:
    """Minimal board surface for selection-and-zoom navigation."""

    def __init__(self) -> None:
        self.cleared = False
        self.requested: list[str] = []
        self.selected: list[object] = []

    def clear_selection(self) -> None:
        self.cleared = True

    def get_items_by_id(self, ids):
        self.requested = list(ids)
        return [object() for _ in ids]

    def add_to_selection(self, items):
        self.selected = list(items)
        return self.selected


class _SelectableKiCad:
    """Minimal KiCad client for heartbeat and zoom tests."""

    def __init__(self) -> None:
        self.actions: list[str] = []

    def ping(self) -> None:
        return None

    def run_action(self, action: str) -> None:
        self.actions.append(action)


def test_locate_items_selects_source_ids_and_requests_zoom() -> None:
    """Offer DRC-like navigation without mutating the board."""

    adapter = object.__new__(KicadIpcAdapter)
    adapter._board = _SelectableBoard()  # type: ignore[attr-defined]
    adapter._kicad = _SelectableKiCad()  # type: ignore[attr-defined]
    adapter._retry_count = 0  # type: ignore[attr-defined]
    adapter._timeout_ms = 5000  # type: ignore[attr-defined]
    result = adapter.locate_items(("track-uuid:a", "via-uuid"), position=Point(2, 3))
    requested = [getattr(item, "value", item) for item in adapter._board.requested]  # type: ignore[attr-defined]
    assert requested == ["track-uuid", "via-uuid"]
    assert result["selected_count"] == 2
    assert result["zoomed"] is True
    assert adapter._kicad.actions == ["common.Control.zoomFitSelection"]  # type: ignore[attr-defined]


def test_default_outline_is_convex_and_honors_target_vertex_count() -> None:
    """Default optimization must not invent a concavity on a convex board."""

    board = snapshot(
        footprints=(footprint(bounds=BoundingBox(4, 4, 16, 12)),),
        edges=rectangular_edges(0, 0, 20, 16),
    )
    config = EdgeConfig(
        target_vertex_count=8,
        maximum_area_reduction_percent=99.0,
        minimum_ground_band_mm=0.0,
        preserve_existing_concavities=True,
    )
    proposal = propose_edge_outline(board, config, r"^GND$")
    assert proposal.actual_vertex_count == 8
    assert proposal.outline_strategy == "convex_preserve_existing_concavities"
    assert _reflex_vertices(proposal.polygon.outline) == ()


class _ControllerAdapter:
    """Controller adapter that records heartbeat and location requests."""

    def __init__(self, root: Path, board) -> None:
        self.settings_directory = root
        self.capabilities = {"ipc_api": True}
        self._board = board
        self.located = None

    def configure_connection(self, retry_count):
        self.retry_count = retry_count

    def snapshot(self):
        return self._board

    def ping(self):
        return {"connected": True, "reconnected": False}

    def locate_items(self, item_ids, *, layer="", position=None):
        self.located = (tuple(item_ids), layer, position)
        return {"selected_count": len(item_ids), "zoomed": True}

    def close(self):
        return None


def test_controller_keepalive_and_locate_use_current_analysis(tmp_path: Path) -> None:
    """Keep long-lived sessions active and navigate by finding identifier."""

    board = snapshot(
        tracks=(
            TrackSegment("a", Point(0, 0), Point(10, 0), 0.2, "F.Cu", 0, "SIG"),
            TrackSegment("b", Point(10, 0), Point(6, 3), 0.2, "F.Cu", 0, "SIG"),
        ),
        edges=rectangular_edges(-2, -2, 20, 10),
    )
    adapter = _ControllerAdapter(tmp_path, board)
    controller = GuardianController(adapter)  # type: ignore[arg-type]
    assert controller.keep_alive()["connected"] is True
    analysis = controller.analyze()
    finding = next(item for item in analysis["analysis"]["findings"] if item["rule_id"] == "noise.corner")
    result = controller.locate_finding(finding["finding_id"])
    assert result["selected_count"] == len(finding["item_ids"])
    assert adapter.located is not None


def test_manufacturing_issue_payload_is_localized_in_japanese() -> None:
    """Translate DFM details rather than only the EMI finding list."""

    from emi_guardian.config import AppConfig
    from emi_guardian.manufacturing import evaluate_manufacturability

    board = snapshot(
        tracks=(TrackSegment("thin", Point(0, 0), Point(10, 0), 0.10, "F.Cu", 0, "SIG"),),
        edges=rectangular_edges(-2, -2, 20, 10),
    )
    report = evaluate_manufacturability(board, AppConfig()).to_dict()
    issue = next(item for item in report["issues"] if item["code"] == "TRACK_WIDTH")
    assert "配線幅" in issue["localized"]["ja"]["title"]
    assert "最小配線幅" in issue["localized"]["ja"]["description"]
    assert issue["localized"]["en"]["title"] == issue["title"]


def test_noise_analysis_scales_to_large_spatially_sparse_board() -> None:
    """Guard the indexed hot path against accidental quadratic regressions."""

    from time import perf_counter

    from emi_guardian.config import NoiseConfig
    from emi_guardian.noise import analyze_noise

    tracks = tuple(
        TrackSegment(
            f"t{index}",
            Point(float((index % 50) * 12), float((index // 50) * 12)),
            Point(float((index % 50) * 12 + 2), float((index // 50) * 12)),
            0.2,
            "F.Cu",
            0,
            f"N{index}",
        )
        for index in range(1500)
    )
    pads = tuple(
        Pad(
            f"p{index}",
            f"fp{index}",
            "1",
            track.start,
            BoundingBox(track.start.x - 0.4, track.start.y - 0.4, track.start.x + 0.4, track.start.y + 0.4),
            track.net,
            ("F.Cu",),
        )
        for index, track in enumerate(tracks)
    )
    started = perf_counter()
    analyze_noise(snapshot(tracks=tracks, pads=pads), NoiseConfig(), r"^GND$")
    elapsed = perf_counter() - started
    assert elapsed < 5.0


def test_all_literal_emitted_rules_have_japanese_presentations() -> None:
    """Prevent new findings from silently falling back to English in Japanese UI."""

    import ast

    from emi_guardian.localization import _FINDING_TEXT_JA, _MANUFACTURING_TEXT_JA

    rule_ids: set[str] = set()
    manufacturing_codes: set[str] = set()
    source_root = Path(__file__).resolve().parents[1] / "plugin" / "emi_guardian"
    for source_path in source_root.rglob("*.py"):
        tree = ast.parse(source_path.read_text(encoding="utf-8"), filename=str(source_path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            for keyword in node.keywords:
                if (
                    keyword.arg == "rule_id"
                    and isinstance(keyword.value, ast.Constant)
                    and isinstance(keyword.value.value, str)
                ):
                    rule_ids.add(keyword.value.value)
            if isinstance(node.func, ast.Name) and node.func.id == "add" and node.args:
                code = node.args[0]
                if isinstance(code, ast.Constant) and isinstance(code.value, str):
                    manufacturing_codes.add(code.value)

    assert rule_ids <= set(_FINDING_TEXT_JA)
    assert manufacturing_codes <= set(_MANUFACTURING_TEXT_JA)
    assert {"antenna.appendage", "antenna.isolated"} <= set(_FINDING_TEXT_JA)


def test_dashboard_has_blue_theme_and_no_broken_literal_dom_references() -> None:
    """Keep the blue visual system and literal JavaScript element references valid."""

    import re
    from html.parser import HTMLParser

    class IdCollector(HTMLParser):
        def __init__(self) -> None:
            super().__init__()
            self.ids: list[str] = []

        def handle_starttag(self, tag: str, attrs) -> None:
            for key, value in attrs:
                if key == "id" and value:
                    self.ids.append(value)

    web_root = Path(__file__).resolve().parents[1] / "plugin" / "emi_guardian" / "web"
    html = (web_root / "index.html").read_text(encoding="utf-8")
    javascript = (web_root / "app.js").read_text(encoding="utf-8")
    stylesheet = (web_root / "styles.css").read_text(encoding="utf-8")
    parser = IdCollector()
    parser.feed(html)
    assert len(parser.ids) == len(set(parser.ids))
    literal_refs = set(re.findall(r'getElementById\("([A-Za-z0-9_-]+)"\)', javascript))
    assert literal_refs <= set(parser.ids)
    assert "--accent: #2563eb" in stylesheet
    assert "linear-gradient(120deg,#142752,#1d4ed8)" in stylesheet
