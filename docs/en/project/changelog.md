# Changelog

[日本語版](../../ja/project/changelog.md)

## 0.0.1 — 2026-08-13

- Added a KiCad 10.0.5+ IPC plugin with geometry-based EMI screening, a bilingual local dashboard, report export, silkscreen planning, board-outline proposals, and dry-run-by-default mutations.
- Added conservative GND-pour analysis that protects pads, same-net pads, vias, explicit traces, perimeter ground, and the required copper path to the broad ground core before classifying a residual appendage.
- Added fail-closed connectivity checks, current-board revalidation, exact shape-matched keepouts, and full-width trace/via containment for concave outlines, internal cutouts, and other-net copper.
- Added ranked GND bridges, stitching vias, combined bridge-and-via actions, partial proposal adoption, and transaction-backed writes where KiCad exposes the required capability.
- Added route screening for stubs, coupling, acute corners, electrical path length, reference gaps, return detours, bottlenecks, edge proximity, and differential mismatch, with bounded category scoring.
- Added impedance, delay, critical-length, resonance, skin-depth, and normalized-crosstalk estimates.
- Added JLCPCB two-layer economy and capability-limit profiles, geometric DFM checks, routing and via presets, order records, custom-rule export, and bilingual manufacturing guidance.
- Added interactive board, finding, fix, silkscreen, stitching, outline, and schematic-block placement previews with layer controls, pan/zoom, and non-destructive KiCad selection-and-zoom navigation.
- Added Windows, macOS, Linux, manual-install, PCM, source, demonstration-report, and bilingual-manual packages with deterministic archives and checksums.
- Added Python compatibility, package, installer-lifecycle, geometry, localization, randomized safety, documentation, and API-boundary regression tests.
- Added GitHub Actions for quality, unit tests, documentation, dependency auditing, reproducible packaging, CodeQL, Renovate, and bilingual GitHub Pages publication.
