"""Fast transmission-line and resonance estimates.

These calculations are engineering estimates, not a field-solver replacement.
They are deliberately exposed with assumptions so a report cannot be mistaken
for compliance evidence or electromagnetic sign-off.
"""

from __future__ import annotations

import math
from collections.abc import Iterable

from .config import QuantitativeConfig
from .models import BoardSnapshot, TrackSegment

SPEED_OF_LIGHT_M_PER_S = 299_792_458.0


def effective_permittivity_microstrip(width_mm: float, height_mm: float, er: float) -> float:
    """Estimate microstrip effective permittivity using a Hammerstad form."""

    width = max(width_mm, 1.0e-6)
    height = max(height_mm, 1.0e-6)
    ratio = width / height
    correction = 0.04 * (1.0 - ratio) ** 2 if ratio < 1.0 else 0.0
    return (er + 1.0) / 2.0 + (er - 1.0) / 2.0 * (1.0 / math.sqrt(1.0 + 12.0 / ratio) + correction)


def microstrip_impedance_ohm(
    width_mm: float,
    height_mm: float,
    copper_thickness_mm: float,
    er: float,
) -> float:
    """Estimate single-ended microstrip characteristic impedance."""

    width = max(width_mm + copper_thickness_mm / math.pi, 1.0e-6)
    height = max(height_mm, 1.0e-6)
    ratio = width / height
    effective_er = effective_permittivity_microstrip(width, height, er)
    if ratio <= 1.0:
        return 60.0 / math.sqrt(effective_er) * math.log(8.0 / ratio + 0.25 * ratio)
    return 120.0 * math.pi / (math.sqrt(effective_er) * (ratio + 1.393 + 0.667 * math.log(ratio + 1.444)))


def stripline_impedance_ohm(
    width_mm: float,
    plane_spacing_mm: float,
    copper_thickness_mm: float,
    er: float,
) -> float:
    """Estimate symmetric stripline impedance with a closed-form approximation."""

    width = max(width_mm, 1.0e-6)
    spacing = max(plane_spacing_mm, 1.0e-6)
    dielectric = max(er, 1.0)
    effective_width = width + max(copper_thickness_mm, 0.0) / math.pi
    denominator = max(0.1, 0.67 * math.pi * effective_width / spacing + 0.8)
    logarithm_argument = max(4.0 / denominator, 1.000001)
    return max(0.01, 60.0 / math.sqrt(dielectric) * math.log(logarithm_argument))


def propagation_delay_ps_per_mm(effective_er: float) -> float:
    """Return propagation delay in picoseconds per millimeter."""

    velocity = SPEED_OF_LIGHT_M_PER_S / math.sqrt(max(effective_er, 1.0))
    return 1.0e9 / velocity


def critical_length_mm(rise_time_ns: float, effective_er: float, fraction: float = 1.0 / 6.0) -> float:
    """Return the conservative distributed-line critical length."""

    velocity_mm_per_ns = SPEED_OF_LIGHT_M_PER_S * 1.0e-6 / math.sqrt(max(effective_er, 1.0))
    return velocity_mm_per_ns * max(rise_time_ns, 0.0) * fraction


def quarter_wave_frequency_mhz(length_mm: float, effective_er: float) -> float:
    """Return the quarter-wave resonance frequency for a physical length."""

    if length_mm <= 0.0:
        return math.inf
    length_m = length_mm / 1000.0
    return SPEED_OF_LIGHT_M_PER_S / (4.0 * length_m * math.sqrt(max(effective_er, 1.0))) / 1.0e6


def skin_depth_um(frequency_mhz: float, conductivity_s_per_m: float = 5.8e7) -> float:
    """Return copper-like skin depth in micrometers."""

    if frequency_mhz <= 0.0:
        return math.inf
    permeability = 4.0e-7 * math.pi
    angular_frequency = 2.0 * math.pi * frequency_mhz * 1.0e6
    return math.sqrt(2.0 / (angular_frequency * permeability * conductivity_s_per_m)) * 1.0e6


def crosstalk_proxy(
    overlap_mm: float,
    spacing_mm: float,
    reference_height_mm: float,
    rise_time_ns: float,
    effective_er: float,
) -> float:
    """Return a normalized near-end crosstalk risk proxy in ``[0, 1]``."""

    if overlap_mm <= 0.0:
        return 0.0
    spacing = max(spacing_mm, 0.01)
    field_coupling = (reference_height_mm / spacing) ** 2
    electrical_length = overlap_mm / max(critical_length_mm(rise_time_ns, effective_er), 0.01)
    return max(0.0, min(1.0, field_coupling * electrical_length))


def analyze_quantitative(snapshot: BoardSnapshot, config: QuantitativeConfig) -> dict[str, object]:
    """Calculate board-wide electrical estimates."""

    if not config.enabled:
        return {"enabled": False}

    stackup = snapshot.stackup
    er = stackup.dielectric_constant or config.default_dielectric_constant
    height = stackup.signal_to_reference_height or config.default_reference_height_mm
    copper = stackup.copper_thickness or config.default_copper_thickness_mm
    widths = [track.width for track in snapshot.tracks if track.width > 0.0]
    representative_width = _median(widths) if widths else 0.20
    effective_er = effective_permittivity_microstrip(representative_width, height, er)
    longest = max((_track_length(track) for track in snapshot.tracks), default=0.0)
    impedance = microstrip_impedance_ohm(representative_width, height, copper, er)
    return {
        "enabled": True,
        "method": "closed-form engineering estimates",
        "assumptions": {
            "dielectric_constant": er,
            "reference_height_mm": height,
            "copper_thickness_mm": copper,
            "representative_trace_width_mm": representative_width,
            "effective_permittivity": effective_er,
        },
        "microstrip_impedance_ohm": impedance,
        "propagation_delay_ps_per_mm": propagation_delay_ps_per_mm(effective_er),
        "longest_trace_mm": longest,
        "longest_trace_quarter_wave_mhz": quarter_wave_frequency_mhz(longest, effective_er),
        "skin_depth_um": {
            str(frequency): skin_depth_um(frequency) for frequency in config.frequency_samples_mhz
        },
        "external_solver": {
            "configured": config.external_solver != "none",
            "name": config.external_solver,
            "status": "export-only hook; solver execution is not part of the fast analysis",
        },
        "disclaimer": (
            "Values are first-order estimates and must not be used as EMC compliance or field-solver evidence."
        ),
    }


def _median(values: Iterable[float]) -> float:
    """Return a deterministic median."""

    ordered = sorted(values)
    if not ordered:
        return 0.0
    middle = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[middle]
    return (ordered[middle - 1] + ordered[middle]) / 2.0


def _track_length(track: TrackSegment) -> float:
    """Return track length in millimeters."""

    return math.hypot(track.end.x - track.start.x, track.end.y - track.start.y)
