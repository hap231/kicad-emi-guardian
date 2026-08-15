"""Ground-pour antenna detector regression tests."""

from __future__ import annotations

from conftest import rectangle, rectangular_edges, snapshot
from emi_guardian.antenna import detect_ground_antennas
from emi_guardian.config import AntennaConfig
from emi_guardian.models import BoundingBox, CopperZone, Pad, Point, Polygon


def _appendage_polygon() -> Polygon:
    """Return a large body with a long 0.4 mm copper appendage."""

    return Polygon(
        (
            Point(0.0, 0.0),
            Point(20.0, 0.0),
            Point(20.0, 8.0),
            Point(30.0, 8.0),
            Point(30.0, 8.4),
            Point(20.0, 8.4),
            Point(20.0, 20.0),
            Point(0.0, 20.0),
        )
    )


def test_detects_long_narrow_ground_appendage() -> None:
    """Detect the full residual appendage at the configured raster resolution."""

    polygon = _appendage_polygon()
    zone = CopperZone(
        "zone-gnd",
        "GND",
        ("F.Cu",),
        (0,),
        polygon,
        {"F.Cu": (polygon,)},
    )
    pad = Pad("pad-gnd", "fp", "1", Point(5.0, 5.0), BoundingBox(4.5, 4.5, 5.5, 5.5), "GND", ("F.Cu",))
    findings = detect_ground_antennas(
        snapshot(
            zones=(zone,),
            pads=(pad,),
            edges=rectangular_edges(-2.0, -2.0, 34.0, 24.0),
        ),
        AntennaConfig(),
    )
    appendages = [finding for finding in findings if finding.metrics.get("kind") == "appendage"]
    assert appendages
    assert max(float(item.metrics["length_mm"]) for item in appendages) >= 9.0
    assert all(item.metrics["layer"] == "F.Cu" for item in appendages)


def test_detects_unanchored_ground_island() -> None:
    """Report copper with no same-net pad or via anchor."""

    polygon = rectangle(0.0, 0.0, 4.0, 3.0)
    zone = CopperZone(
        "zone-island",
        "GND",
        ("B.Cu",),
        (31,),
        polygon,
        {"B.Cu": (polygon,)},
    )
    findings = detect_ground_antennas(snapshot(zones=(zone,)), AntennaConfig())
    islands = [finding for finding in findings if finding.metrics.get("kind") == "island"]
    assert len(islands) == 1
    assert islands[0].confidence >= 0.9
    assert islands[0].metrics["area_mm2"] == 12.0
