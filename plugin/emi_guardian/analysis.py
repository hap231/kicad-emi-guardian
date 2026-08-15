"""Top-level board analysis orchestration and score aggregation."""

from __future__ import annotations

import math
from collections import Counter, defaultdict
from collections.abc import Iterable
from datetime import datetime, timezone
from time import perf_counter

from .antenna import detect_ground_antennas
from .config import AppConfig
from .models import AnalysisReport, BoardSnapshot, Finding
from .noise import analyze_noise
from .quantitative import analyze_quantitative


def analyze_board(
    snapshot: BoardSnapshot,
    config: AppConfig,
    *,
    generated_at_utc: str | None = None,
) -> AnalysisReport:
    """Run all enabled checks and return a complete analysis report.

    ``generated_at_utc`` is injectable so demonstration and release artifacts can
    be reproduced byte-for-byte. Runtime callers normally leave it unset.
    """

    config.validate()
    started = perf_counter()
    stage_started = started
    antenna_findings = detect_ground_antennas(snapshot, config.antenna)
    antenna_seconds = perf_counter() - stage_started
    stage_started = perf_counter()
    noise_findings = analyze_noise(
        snapshot,
        config.noise,
        config.antenna.ground_net_regex,
    )
    noise_seconds = perf_counter() - stage_started
    findings = _deduplicate((*antenna_findings, *noise_findings))
    stage_started = perf_counter()
    quantitative = analyze_quantitative(snapshot, config.quantitative)
    quantitative_seconds = perf_counter() - stage_started
    category_scores = _category_scores(findings)
    overall_score = _weighted_score(category_scores, config.noise.score_weights)
    counts = Counter(finding.severity.value for finding in findings)
    statistics = {
        "generated_at_utc": generated_at_utc or datetime.now(timezone.utc).isoformat(),
        "track_count": len(snapshot.tracks),
        "via_count": len(snapshot.vias),
        "pad_count": len(snapshot.pads),
        "zone_count": len(snapshot.zones),
        "footprint_count": len(snapshot.footprints),
        "edge_primitive_count": len(snapshot.edges),
        "finding_count": len(findings),
        "severity_counts": dict(counts),
        "antenna_sampling_step_mm": config.antenna.raster_step_mm,
        "performance_seconds": {
            "antenna": round(antenna_seconds, 6),
            "noise": round(noise_seconds, 6),
            "quantitative": round(quantitative_seconds, 6),
            "total": round(perf_counter() - started, 6),
        },
    }
    caveats = (
        "Ground-pour coverage is exhaustive only at the configured raster resolution; sub-grid geometry can be missed.",
        "A geometric candidate is not proof of radiated or conducted EMI. Current spectra, return paths, stackup, enclosure, and cables affect actual emissions.",
        "The quantitative section uses closed-form estimates unless an external solver workflow is configured.",
        "Automatic mutations require a current DRC run and engineering review before fabrication.",
    )
    return AnalysisReport(
        board_name=snapshot.board_name,
        kicad_version=snapshot.kicad_version,
        score=round(overall_score, 2),
        category_scores={key: round(value, 2) for key, value in category_scores.items()},
        findings=tuple(findings),
        quantitative=quantitative,
        statistics=statistics,
        caveats=caveats,
    )


def _category_scores(findings: Iterable[Finding]) -> dict[str, float]:
    """Convert penalties into stable scores with diminishing repeated impact.

    A linear subtraction made a board with many ordinary corner findings hit
    exactly zero even when every individual issue was low severity.  Repeated
    findings now have diminishing marginal impact and an exponential response,
    preserving useful score resolution across dense boards.
    """

    grouped: dict[str, list[float]] = defaultdict(list)
    for finding in findings:
        grouped[finding.category].append(finding.score_penalty * max(0.35, finding.confidence))
    categories = ("antenna", "parallel", "corner", "length", "return_path", "other")
    scores: dict[str, float] = {}
    for category in categories:
        weighted_penalty = sum(
            penalty / math.sqrt(index)
            for index, penalty in enumerate(sorted(grouped.get(category, ()), reverse=True), start=1)
        )
        scores[category] = max(1.0, 100.0 * math.exp(-weighted_penalty / 90.0))
    return scores


def _weighted_score(category_scores: dict[str, float], weights: dict[str, float]) -> float:
    """Return a weighted board score in ``[0, 100]``."""

    normalized_weights = {
        "antenna": weights.get("antenna", 0.30),
        "parallel": weights.get("parallel", 0.20),
        "corner": weights.get("corner", 0.10),
        "length": weights.get("length", 0.15),
        "return_path": weights.get("return_path", 0.15),
        "other": weights.get("other", 0.10),
    }
    denominator = sum(normalized_weights.values()) or 1.0
    return max(
        0.0,
        min(
            100.0,
            sum(
                category_scores.get(category, 100.0) * weight
                for category, weight in normalized_weights.items()
            )
            / denominator,
        ),
    )


def _deduplicate(findings: Iterable[Finding]) -> list[Finding]:
    """Remove duplicate finding identifiers while preserving order."""

    seen: set[str] = set()
    result: list[Finding] = []
    for finding in findings:
        if finding.finding_id in seen:
            continue
        seen.add(finding.finding_id)
        result.append(finding)
    return result
