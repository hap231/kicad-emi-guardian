"""Silkscreen value-placement tests."""

from __future__ import annotations

from conftest import footprint, rectangular_edges, snapshot
from emi_guardian.config import SilkscreenConfig
from emi_guardian.models import BoundingBox, Pad, Point, Via
from emi_guardian.silkscreen import plan_silkscreen


def test_own_reference_and_value_fields_do_not_block_replacement_value() -> None:
    """Allow the value to occupy space that its soon-hidden reference currently uses."""

    pad = Pad("p1", "fp1", "1", Point(5.0, 5.0), BoundingBox(4.6, 4.6, 5.4, 5.4), "N1", ("F.Cu",))
    fp = footprint(pads=(pad,))
    plan = plan_silkscreen(
        snapshot(
            pads=(pad,),
            footprints=(fp,),
            edges=rectangular_edges(0.0, 0.0, 20.0, 20.0),
        ),
        SilkscreenConfig(),
    )
    assert len(plan.placements) == 1
    placement = plan.placements[0]
    assert placement.value == "10k"
    assert placement.hide_reference is True
    assert placement.text_width_mm == 0.8
    assert placement.text_height_mm == 0.8
    assert placement.text_thickness_mm == 0.10


def test_via_collision_moves_text_to_an_alternative_candidate() -> None:
    """Keep value text clear of vias instead of accepting a broken legend."""

    fp = footprint()
    blocking_via = Via("v1", fp.value_field.position, 1.0, 0.4, "GND")
    plan = plan_silkscreen(
        snapshot(
            vias=(blocking_via,),
            footprints=(fp,),
            edges=rectangular_edges(0.0, 0.0, 20.0, 20.0),
        ),
        SilkscreenConfig(),
    )
    assert len(plan.placements) == 1
    assert plan.placements[0].position != fp.value_field.position
