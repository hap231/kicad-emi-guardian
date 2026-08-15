"""Closed-form electrical estimate sanity tests."""

from __future__ import annotations

import math

from conftest import snapshot
from emi_guardian.config import QuantitativeConfig
from emi_guardian.models import Point, TrackSegment
from emi_guardian.quantitative import (
    analyze_quantitative,
    critical_length_mm,
    microstrip_impedance_ohm,
    quarter_wave_frequency_mhz,
    skin_depth_um,
    stripline_impedance_ohm,
)


def test_closed_form_estimates_are_finite_and_physical() -> None:
    """Catch unit errors and invalid domains in the fast estimator."""

    impedance = microstrip_impedance_ohm(0.2, 0.18, 0.035, 4.2)
    assert 20.0 < impedance < 150.0
    assert critical_length_mm(1.0, 3.3) > 20.0
    assert 1000.0 < quarter_wave_frequency_mhz(20.0, 3.3) < 3000.0
    assert skin_depth_um(100.0) > skin_depth_um(1000.0) > 0.0


def test_board_quantitative_payload_exposes_assumptions_and_disclaimer() -> None:
    """Keep estimates traceable and clearly separated from field-solver evidence."""

    board = snapshot(tracks=(TrackSegment("t", Point(0.0, 0.0), Point(25.0, 0.0), 0.2, "F.Cu", 0, "SIG"),))
    payload = analyze_quantitative(board, QuantitativeConfig())
    assert payload["enabled"] is True
    assert math.isfinite(float(payload["microstrip_impedance_ohm"]))
    assert payload["assumptions"]["representative_trace_width_mm"] == 0.2
    assert "compliance" in str(payload["disclaimer"]).lower()


def test_stripline_estimate_remains_positive_for_extreme_geometry() -> None:
    """Prevent logarithm-domain artifacts from producing negative impedance."""

    assert stripline_impedance_ohm(10.0, 0.05, 0.07, 4.2) > 0.0
    assert math.isfinite(stripline_impedance_ohm(10.0, 0.05, 0.07, 4.2))
