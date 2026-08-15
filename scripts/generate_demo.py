#!/usr/bin/env python3
"""Generate a synthetic EMI Guardian report without a running KiCad process."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import replace
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PLUGIN_ROOT = ROOT / "plugin"
if str(PLUGIN_ROOT) not in sys.path:
    sys.path.insert(0, str(PLUGIN_ROOT))

from emi_guardian.analysis import analyze_board  # noqa: E402
from emi_guardian.config import AppConfig  # noqa: E402
from emi_guardian.edge_optimizer import propose_edge_outline  # noqa: E402
from emi_guardian.fixes import plan_antenna_fixes  # noqa: E402
from emi_guardian.manufacturing import (  # noqa: E402
    evaluate_manufacturability,
    write_manufacturing_bundle,
)
from emi_guardian.models import (  # noqa: E402
    BoardEdge,
    BoardSnapshot,
    BoundingBox,
    CopperZone,
    FootprintSnapshot,
    Pad,
    Point,
    Polygon,
    TextSnapshot,
    TrackSegment,
    Via,
)
from emi_guardian.report import write_report_bundle  # noqa: E402
from emi_guardian.silkscreen import plan_silkscreen  # noqa: E402
from emi_guardian.solver_export import export_solver_manifest  # noqa: E402


def rectangle(min_x: float, min_y: float, max_x: float, max_y: float) -> Polygon:
    """Return a counter-clockwise rectangle."""

    return Polygon(
        (
            Point(min_x, min_y),
            Point(max_x, min_y),
            Point(max_x, max_y),
            Point(min_x, max_y),
        )
    )


def text(value: str, position: Point, layer: str = "F.SilkS") -> TextSnapshot:
    """Return a standard silkscreen field."""

    return TextSnapshot(value, position, layer, True, 0.8, 0.8, 0.12, 0.0)


def footprint(
    item_id: str,
    reference: str,
    value: str,
    bounds: BoundingBox,
    pads: tuple[Pad, ...],
) -> FootprintSnapshot:
    """Return a compact synthetic footprint."""

    center = bounds.center
    field_position = Point(center.x, bounds.min_y - 1.0)
    return FootprintSnapshot(
        item_id=item_id,
        reference=reference,
        value=value,
        position=center,
        layer="F.Cu",
        bounds=bounds,
        reference_field=text(reference, field_position),
        value_field=text(value, field_position),
        pads=pads,
    )


def demo_snapshot() -> BoardSnapshot:
    """Build a board containing representative geometry risks."""

    appendage = Polygon(
        (
            Point(3.0, 3.0),
            Point(23.0, 3.0),
            Point(23.0, 11.0),
            Point(34.0, 11.0),
            Point(34.0, 11.4),
            Point(23.0, 11.4),
            Point(23.0, 23.0),
            Point(3.0, 23.0),
        )
    )
    full_ground = rectangle(0.0, 0.0, 80.0, 40.0)
    isolated = rectangle(58.0, 30.0, 62.0, 33.0)
    zones = (
        CopperZone(
            "zone-f-gnd",
            "GND",
            ("F.Cu", "B.Cu"),
            (3, 34),
            appendage,
            {"F.Cu": (appendage,), "B.Cu": (full_ground,)},
        ),
        CopperZone(
            "zone-agnd-island",
            "AGND",
            ("F.Cu",),
            (3,),
            isolated,
            {"F.Cu": (isolated,)},
        ),
    )

    pads = (
        Pad(
            "pad-gnd", "fp-r1", "2", Point(6.0, 6.0), BoundingBox(5.4, 5.4, 6.6, 6.6), "GND", ("F.Cu", "B.Cu")
        ),
        Pad("pad-stub", "fp-u1", "1", Point(4.0, 27.0), BoundingBox(3.4, 26.4, 4.6, 27.6), "STUB", ("F.Cu",)),
        Pad(
            "pad-other",
            "fp-u1",
            "2",
            Point(14.0, 27.0),
            BoundingBox(13.4, 26.4, 14.6, 27.6),
            "OTHER",
            ("F.Cu",),
        ),
        Pad("pad-r1-a", "fp-r1", "1", Point(9.0, 7.0), BoundingBox(8.4, 6.5, 9.6, 7.5), "SIG", ("F.Cu",)),
    )
    footprints = (
        footprint("fp-r1", "R1", "10k", BoundingBox(5.0, 5.0, 10.0, 9.0), (pads[0], pads[3])),
        footprint("fp-u1", "U1", "MCU", BoundingBox(3.0, 25.0, 15.0, 32.0), (pads[1], pads[2])),
    )

    tracks = (
        TrackSegment("stub", Point(4.0, 27.0), Point(14.0, 27.0), 0.20, "F.Cu", 3, "STUB"),
        TrackSegment("parallel-a", Point(38.0, 6.0), Point(52.0, 6.0), 0.20, "F.Cu", 3, "CLK"),
        TrackSegment("parallel-b", Point(38.0, 6.35), Point(52.0, 6.35), 0.20, "F.Cu", 3, "DATA"),
        TrackSegment("corner-a", Point(38.0, 12.0), Point(46.0, 12.0), 0.20, "F.Cu", 3, "CORNER"),
        TrackSegment("corner-b", Point(46.0, 12.0), Point(46.0, 20.0), 0.20, "F.Cu", 3, "CORNER"),
        TrackSegment("long", Point(3.0, 35.0), Point(75.0, 35.0), 0.20, "F.Cu", 3, "LONG"),
        TrackSegment("edge", Point(0.60, 18.0), Point(15.0, 18.0), 0.20, "F.Cu", 3, "EDGE"),
        TrackSegment("usb-p", Point(55.0, 20.0), Point(67.0, 20.0), 0.20, "F.Cu", 3, "USB_P"),
        TrackSegment("usb-n", Point(55.0, 21.0), Point(73.0, 21.0), 0.20, "F.Cu", 3, "USB_N"),
    )
    vias = (
        Via("gnd-anchor", Point(21.0, 10.0), 0.60, 0.30, "GND"),
        Via("signal-transition", Point(30.0, 28.0), 0.60, 0.30, "SIG"),
        Via("silk-blocker", Point(7.5, 4.0), 1.00, 0.40, "GND"),
    )
    edge_points = (Point(0.0, 0.0), Point(80.0, 0.0), Point(80.0, 40.0), Point(0.0, 40.0))
    edges = tuple(
        BoardEdge(f"edge-{index}", edge_points[index], edge_points[(index + 1) % 4]) for index in range(4)
    )
    return BoardSnapshot(
        board_name="emi-guardian-demo.kicad_pcb",
        board_path="/synthetic/emi-guardian-demo.kicad_pcb",
        kicad_version="10.0.5",
        tracks=tracks,
        vias=vias,
        pads=pads,
        zones=zones,
        footprints=footprints,
        edges=edges,
        metadata={
            "source": "synthetic regression/demo board",
            "stackup": {
                "copper_layer_count": 2,
                "board_thickness_mm": 1.6,
                "solder_mask_colors": ["green"],
                "copper_finish": "hasl",
            },
        },
    )


def generate(output_directory: Path) -> dict[str, object]:
    """Generate reports, plans, and a solver interchange bundle."""

    output_directory.mkdir(parents=True, exist_ok=True)
    snapshot = demo_snapshot()
    config = AppConfig()
    config.edge.maximum_area_reduction_percent = 99.0
    report = analyze_board(snapshot, config, generated_at_utc="2026-08-13T00:00:00+00:00")
    # Release demonstration files must be byte-for-byte reproducible. Runtime
    # reports retain real timing measurements; only the synthetic release demo
    # substitutes stable values.
    deterministic_statistics = dict(report.statistics)
    deterministic_statistics["performance_seconds"] = {
        "antenna": 0.0,
        "noise": 0.0,
        "quantitative": 0.0,
        "total": 0.0,
    }
    report = replace(report, statistics=deterministic_statistics)
    fix_plan = plan_antenna_fixes(snapshot, report.findings, config.antenna, config.fixes)
    silk_plan = plan_silkscreen(snapshot, config.silkscreen)
    edge_proposal = propose_edge_outline(snapshot, config.edge, config.antenna.ground_net_regex)
    manufacturing_report = evaluate_manufacturability(snapshot, config)
    report_paths = write_report_bundle(
        output_directory,
        report,
        fix_plan=fix_plan,
        silkscreen_plan=silk_plan.to_dict(),
        edge_proposal=edge_proposal.to_dict(),
        manufacturing_report=manufacturing_report.to_dict(),
    )
    manufacturing_paths = write_manufacturing_bundle(
        output_directory / "jlcpcb",
        snapshot,
        config,
        manufacturing_report,
    )
    solver_paths = export_solver_manifest(snapshot, output_directory / "solver", config.quantitative)
    summary = {
        "board": snapshot.board_name,
        "score": report.score,
        "finding_count": len(report.findings),
        "selected_fix_count": len(fix_plan.actions),
        "silkscreen_placement_count": len(silk_plan.placements),
        "edge_ground_band_verified": edge_proposal.ground_band_verified,
        "manufacturing_status": manufacturing_report.status,
        "manufacturing_score": manufacturing_report.score,
        "manufacturing_issue_count": len(manufacturing_report.issues),
        "reports": {name: path.name for name, path in report_paths.items()},
        "jlcpcb": {
            name: str(path.relative_to(output_directory)) for name, path in manufacturing_paths.items()
        },
        "solver": {name: str(path.relative_to(output_directory)) for name, path in solver_paths.items()},
    }
    (output_directory / "demo-summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return summary


def main() -> int:
    """Command-line entry point."""

    parser = argparse.ArgumentParser()
    parser.add_argument(
        "output_directory",
        nargs="?",
        type=Path,
        default=ROOT / "dist" / "demo-report",
    )
    args = parser.parse_args()
    summary = generate(args.output_directory.resolve())
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
