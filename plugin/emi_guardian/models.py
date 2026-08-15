"""KiCad-independent domain models used by the analysis core.

All coordinates and dimensions are expressed in millimeters.  Keeping the
analysis core independent from KiCad's protobuf wrappers makes the algorithms
testable without a running KiCad process and confines API compatibility work
to :mod:`emi_guardian.kicad_adapter`.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any


@dataclass(frozen=True)
class Point:
    """Two-dimensional point in millimeters."""

    x: float
    y: float

    def to_dict(self) -> dict[str, float]:
        """Return a JSON-serializable representation."""

        return {"x": self.x, "y": self.y}


@dataclass(frozen=True)
class BoundingBox:
    """Axis-aligned bounding box in millimeters."""

    min_x: float
    min_y: float
    max_x: float
    max_y: float

    @property
    def width(self) -> float:
        """Return the box width."""

        return max(0.0, self.max_x - self.min_x)

    @property
    def height(self) -> float:
        """Return the box height."""

        return max(0.0, self.max_y - self.min_y)

    @property
    def area(self) -> float:
        """Return the box area."""

        return self.width * self.height

    @property
    def center(self) -> Point:
        """Return the box center."""

        return Point((self.min_x + self.max_x) / 2.0, (self.min_y + self.max_y) / 2.0)

    def inflate(self, margin: float) -> BoundingBox:
        """Return a box expanded by *margin* on all sides."""

        return BoundingBox(
            self.min_x - margin,
            self.min_y - margin,
            self.max_x + margin,
            self.max_y + margin,
        )

    def intersects(self, other: BoundingBox, clearance: float = 0.0) -> bool:
        """Return whether this box intersects *other* with optional clearance."""

        return not (
            self.max_x + clearance < other.min_x
            or self.min_x - clearance > other.max_x
            or self.max_y + clearance < other.min_y
            or self.min_y - clearance > other.max_y
        )


@dataclass(frozen=True)
class Polygon:
    """Simple polygon with optional holes."""

    outline: tuple[Point, ...]
    holes: tuple[tuple[Point, ...], ...] = ()

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable representation."""

        return {
            "outline": [point.to_dict() for point in self.outline],
            "holes": [[point.to_dict() for point in hole] for hole in self.holes],
        }


@dataclass(frozen=True)
class TrackSegment:
    """Straight copper trace segment."""

    item_id: str
    start: Point
    end: Point
    width: float
    layer: str
    layer_id: int
    net: str
    locked: bool = False
    source_item_id: str = ""
    is_curve_approximation: bool = False


@dataclass(frozen=True)
class Via:
    """Board via."""

    item_id: str
    position: Point
    diameter: float
    drill: float
    net: str
    start_layer: str = "F.Cu"
    end_layer: str = "B.Cu"
    locked: bool = False


@dataclass(frozen=True)
class Pad:
    """Footprint pad represented by a conservative bounding box."""

    item_id: str
    footprint_id: str
    number: str
    position: Point
    bounds: BoundingBox
    net: str
    layers: tuple[str, ...] = ()


@dataclass(frozen=True)
class CopperZone:
    """Copper zone or rule area."""

    item_id: str
    net: str
    layers: tuple[str, ...]
    layer_ids: tuple[int, ...]
    outline: Polygon
    filled: Mapping[str, tuple[Polygon, ...]] = field(default_factory=dict)
    is_rule_area: bool = False
    locked: bool = False


@dataclass(frozen=True)
class BoardEdge:
    """Line-segment approximation of the board outline."""

    item_id: str
    start: Point
    end: Point
    width: float = 0.05
    kind: str = "segment"
    mid: Point | None = None


@dataclass(frozen=True)
class TextSnapshot:
    """Text field state used by the silkscreen optimizer."""

    value: str
    position: Point
    layer: str
    visible: bool
    width: float
    height: float
    thickness: float
    angle_deg: float = 0.0


@dataclass(frozen=True)
class FootprintSnapshot:
    """Footprint information required by the optimizers."""

    item_id: str
    reference: str
    value: str
    position: Point
    layer: str
    bounds: BoundingBox
    reference_field: TextSnapshot
    value_field: TextSnapshot
    pads: tuple[Pad, ...] = ()
    locked: bool = False
    sheet_path: str = ""
    library_id: str = ""
    description: str = ""


@dataclass(frozen=True)
class StackupInfo:
    """Simplified electrical stackup information."""

    dielectric_constant: float = 4.2
    loss_tangent: float = 0.02
    signal_to_reference_height: float = 0.18
    copper_thickness: float = 0.035


@dataclass(frozen=True)
class BoardSnapshot:
    """Immutable board snapshot consumed by all analysis modules."""

    board_name: str
    board_path: str
    kicad_version: str
    tracks: tuple[TrackSegment, ...] = ()
    vias: tuple[Via, ...] = ()
    pads: tuple[Pad, ...] = ()
    zones: tuple[CopperZone, ...] = ()
    footprints: tuple[FootprintSnapshot, ...] = ()
    edges: tuple[BoardEdge, ...] = ()
    stackup: StackupInfo = StackupInfo()
    metadata: Mapping[str, Any] = field(default_factory=dict)


class Severity(str, Enum):
    """Finding severity."""

    INFO = "info"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


_SEVERITY_ORDER: dict[Severity, int] = {
    Severity.INFO: 0,
    Severity.LOW: 1,
    Severity.MEDIUM: 2,
    Severity.HIGH: 3,
    Severity.CRITICAL: 4,
}


@dataclass(frozen=True)
class Finding:
    """One analysis result with traceable evidence and remediation guidance."""

    finding_id: str
    category: str
    title: str
    description: str
    severity: Severity
    confidence: float
    score_penalty: float
    location: Point | None = None
    item_ids: tuple[str, ...] = ()
    metrics: Mapping[str, Any] = field(default_factory=dict)
    recommendation: str = ""
    rule_id: str = ""

    @property
    def severity_rank(self) -> int:
        """Return a sortable severity rank."""

        return _SEVERITY_ORDER[self.severity]

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable representation."""

        payload = asdict(self)
        payload["severity"] = self.severity.value
        from .localization import localize_finding

        payload["localized"] = localize_finding(
            self.rule_id,
            self.title,
            self.description,
            self.recommendation,
            self.metrics,
        )
        return payload


class FixKind(str, Enum):
    """Supported automatic remediation operations."""

    TRACK_BRIDGE = "track_bridge"
    STITCHING_VIA = "stitching_via"
    TRACK_AND_VIA = "track_and_via"
    RULE_AREA = "rule_area"


@dataclass(frozen=True)
class FixAction:
    """Concrete board-mutation proposal."""

    action_id: str
    finding_id: str
    kind: FixKind
    description: str
    expected_risk_reduction: float
    implementation_cost: float
    confidence: float
    layer: str
    layer_id: int
    net: str
    start: Point | None = None
    end: Point | None = None
    position: Point | None = None
    polygon: Polygon | None = None
    parameters: Mapping[str, Any] = field(default_factory=dict)

    @property
    def utility(self) -> float:
        """Return the planner utility used to choose between alternatives."""

        return self.expected_risk_reduction * self.confidence - self.implementation_cost

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable representation."""

        payload = asdict(self)
        payload["kind"] = self.kind.value
        return payload


@dataclass(frozen=True)
class FixPlan:
    """Selected remediation actions and rejected alternatives."""

    actions: tuple[FixAction, ...]
    alternatives: Mapping[str, tuple[FixAction, ...]] = field(default_factory=dict)
    warnings: tuple[str, ...] = ()

    @property
    def expected_risk_reduction(self) -> float:
        """Return the sum of expected normalized risk reductions."""

        return sum(action.expected_risk_reduction for action in self.actions)

    def selected(self, action_ids: Iterable[str] | None) -> FixPlan:
        """Return a plan containing only explicitly selected actions."""

        if action_ids is None:
            return self
        selected_ids = {str(value) for value in action_ids}
        return FixPlan(
            actions=tuple(action for action in self.actions if action.action_id in selected_ids),
            alternatives=self.alternatives,
            warnings=self.warnings,
        )

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable representation."""

        return {
            "actions": [action.to_dict() for action in self.actions],
            "alternatives": {
                finding_id: [action.to_dict() for action in actions]
                for finding_id, actions in self.alternatives.items()
            },
            "warnings": list(self.warnings),
            "expected_risk_reduction": self.expected_risk_reduction,
        }


@dataclass(frozen=True)
class AnalysisReport:
    """Complete analysis result."""

    board_name: str
    kicad_version: str
    score: float
    category_scores: Mapping[str, float]
    findings: tuple[Finding, ...]
    quantitative: Mapping[str, Any]
    statistics: Mapping[str, Any]
    caveats: tuple[str, ...]

    def sorted_findings(self) -> tuple[Finding, ...]:
        """Return findings ordered by severity, penalty, and confidence."""

        return tuple(
            sorted(
                self.findings,
                key=lambda item: (item.severity_rank, item.score_penalty, item.confidence),
                reverse=True,
            )
        )

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable representation."""

        return {
            "board_name": self.board_name,
            "kicad_version": self.kicad_version,
            "score": self.score,
            "category_scores": dict(self.category_scores),
            "findings": [finding.to_dict() for finding in self.sorted_findings()],
            "quantitative": dict(self.quantitative),
            "statistics": dict(self.statistics),
            "caveats": list(self.caveats),
        }


def bounds_from_points(points: Iterable[Point]) -> BoundingBox:
    """Return the smallest bounding box containing *points*."""

    collected = tuple(points)
    if not collected:
        return BoundingBox(0.0, 0.0, 0.0, 0.0)
    return BoundingBox(
        min(point.x for point in collected),
        min(point.y for point in collected),
        max(point.x for point in collected),
        max(point.y for point in collected),
    )
