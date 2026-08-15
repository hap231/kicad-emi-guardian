"""Shared synthetic-board fixtures for the regression suite."""

from __future__ import annotations

from collections.abc import Sequence

from emi_guardian.models import (
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


def rectangle(min_x: float, min_y: float, max_x: float, max_y: float) -> Polygon:
    """Return a counter-clockwise rectangle polygon."""

    return Polygon(
        (
            Point(min_x, min_y),
            Point(max_x, min_y),
            Point(max_x, max_y),
            Point(min_x, max_y),
        )
    )


def rectangular_edges(
    min_x: float,
    min_y: float,
    max_x: float,
    max_y: float,
    *,
    unordered: bool = False,
) -> tuple[BoardEdge, ...]:
    """Return a closed rectangular Edge.Cuts loop."""

    points = (
        Point(min_x, min_y),
        Point(max_x, min_y),
        Point(max_x, max_y),
        Point(min_x, max_y),
    )
    edges = tuple(BoardEdge(f"e{index}", points[index], points[(index + 1) % 4]) for index in range(4))
    if not unordered:
        return edges
    return (edges[2], BoardEdge("er", edges[0].end, edges[0].start), edges[3], edges[1])


def text(
    value: str,
    position: Point,
    layer: str = "F.SilkS",
    *,
    visible: bool = True,
    width: float = 0.8,
    height: float = 0.8,
) -> TextSnapshot:
    """Return a footprint text snapshot."""

    return TextSnapshot(value, position, layer, visible, width, height, 0.10, 0.0)


def footprint(
    item_id: str = "fp1",
    reference: str = "R1",
    value: str = "10k",
    bounds: BoundingBox | None = None,
    layer: str = "F.Cu",
    pads: Sequence[Pad] = (),
) -> FootprintSnapshot:
    """Return a compact footprint fixture."""

    bounds = bounds or BoundingBox(4.0, 4.0, 6.0, 6.0)

    return FootprintSnapshot(
        item_id=item_id,
        reference=reference,
        value=value,
        position=bounds.center,
        layer=layer,
        bounds=bounds,
        reference_field=text(reference, Point(bounds.center.x, bounds.min_y - 1.0)),
        value_field=text(value, Point(bounds.center.x, bounds.min_y - 1.0)),
        pads=tuple(pads),
    )


def snapshot(
    *,
    tracks: Sequence[TrackSegment] = (),
    vias: Sequence[Via] = (),
    pads: Sequence[Pad] = (),
    zones: Sequence[CopperZone] = (),
    footprints: Sequence[FootprintSnapshot] = (),
    edges: Sequence[BoardEdge] = (),
    board_name: str = "synthetic.kicad_pcb",
    metadata: dict[str, object] | None = None,
) -> BoardSnapshot:
    """Return a synthetic immutable board snapshot."""

    return BoardSnapshot(
        board_name=board_name,
        board_path=f"/tmp/{board_name}",
        kicad_version="10.0.5",
        tracks=tuple(tracks),
        vias=tuple(vias),
        pads=tuple(pads),
        zones=tuple(zones),
        footprints=tuple(footprints),
        edges=tuple(edges),
        metadata=metadata or {},
    )
