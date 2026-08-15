# EMI Guardian v0.0.2

[日本語版](RELEASE_NOTES.ja.md)

EMI Guardian v0.0.2 is a **pre-release engineering build** for KiCad 10.0.5 and later. It is intended for live-KiCad acceptance testing before any stable release.

## Highlights / 主な変更

### Safer installation and update

- Windows, macOS, and Linux installers create **no copy of the previous plugin**, including in the operating-system temporary directory.
- The installer stages and validates only the new payload. It removes legacy `_emi-guardian-backups` and stale `emi-guardian.installing-*` directories before replacement so KiCad cannot scan an old duplicate plugin.
- Automatic rollback is intentionally disabled. If final placement fails, the incomplete destination is removed and the installer must be run again after the cause is corrected.

### Ground-pour antenna detection and remediation

- Replaced local narrow-tail heuristics with a conservative protected-backbone model. The morphological opening width is the larger of the configured narrow-neck width and mandatory connection width `t`.
- The largest broad region is treated as the primary GND core. Every secondary broad region, same-net GND pad, same-net via, explicit same-net GND track, and protected perimeter-GND component must remain connected to that primary core through existing copper.
- Every physical pad on the layer is excluded from antenna candidates. Same-net pad bodies, launch/thermal regions, vias, explicit GND tracks, perimeter GND, and their required width-`t` corridors are protected from automatic copper removal.
- Candidate residuals use four-neighbor electrical connectivity and are accepted only when virtual removal preserves every mandatory connection. Missing filled geometry, missing GND pad anchoring, ambiguous raster topology, or invalid/missing closed Edge.Cuts causes automatic removal to fail closed.
- Rule areas are generated only from the exact proven residual, with no outward margin. A proposal is rejected if it touches any pad, mandatory corridor, explicit GND track, protected perimeter GND, board boundary, or internal cutout.
- Proposed tracks and vias are validated with their complete copper width or annulus against outer Edge.Cuts, internal cutouts, other-net tracks, pads, vias, and filled zones. A track entirely covered by existing same-plane GND copper is rejected as redundant.
- Immediately before mutation, the controller rereads the active board, reruns the full analysis and fix planner, and compares each selected action's safety-relevant target, net, layer, geometry, dimensions, and parameters with the preview. Any missing or changed action aborts the entire request without modifying the board.

### Return path and initial placement

- Relaxed two-layer return-path screening. The generic nearby-return-via warning is disabled by default for two-layer boards. Reference-plane gaps now require sustained unsupported length and fraction after endpoint breakout exclusion; common power nets are excluded by default; GND-detour findings require both ratio and absolute-excess thresholds.
- Expanded schematic-block initial-placement previews to show destination footprint bodies, translated pads, reference and value fields, block boxes, component identity labels, and movement vectors instead of anonymous points.

### Existing v0.0.1 workflow corrections retained

- Finding navigation converts UUID strings to KiCad `KIID` protobuf messages before `Board.get_items_by_id()`.
- Finding markers support click-for-detail, hover summaries, list-to-preview highlighting, and preview focus. Preview layers support Show all/Hide all while findings remain visible.
- Board layers are available in outline, antenna-fix, silkscreen, via-stitching, and placement previews.
- Outline optimization rejects area-increasing replacements, preserves compact source outlines when safer, and provides separate optimize, smooth-current-outline, and fillet-current-outline operations.
- Antenna, silkscreen, stitching, and placement proposals support partial adoption.
- Silkscreen defaults to a 0.10 mm stroke and supports 0°, 90°, and ±45° orientation candidates, bounded owner distance, MountingHole/LOGO suppression, hidden Fab references, and manual-review fallback.
- Track-width and via presets are multi-select; diagonal outline mode synchronizes `allow_diagonal_edges`; dashboard idle shutdown is disabled by default with heartbeat/reconnect support.

## Requirements / 動作条件

- KiCad 10.0.5 or later in the KiCad 10 series.
- Python 3.9 or later selected in KiCad's Plugins preferences.
- KiCad API enabled.

## Safety and limitations / 安全上の制限

- Dry-run is enabled by default. Review every selected modification and run zone refill, KiCad DRC, Gerber review, mechanical review, and manufacturer DFM before fabrication.
- Finding navigation is non-destructive selection-and-zoom, not a persistent native DRC marker.
- EMI findings are geometry- and configuration-based screening. They do not prove EMC compliance, absence of every radiating structure, or full-wave electromagnetic behavior.
- The antenna proof is conservative but discretized. Raster resolution, filled-zone freshness, stackup assumptions, and missing circuit intent can suppress automation or require manual review.
- A screenshot is insufficient to validate every copper connection on the reported board; acceptance testing of the original `.kicad_pcb` is required.
- Live KiCad 10.0.5 IPC, native Windows PowerShell, macOS Finder/Gatekeeper, and physical EMC behavior remain target-environment acceptance items.

## Verification performed for this build / このビルドで実施した検証

- 146 automated regression, geometry, randomized safety, localization, controller, server, installer, documentation, and package tests passed.
- Fixed-seed randomized suites covered 48 tail/pad geometries, 32 broad-region bridge geometries, and 960 random full-width track proposals on concave outlines.
- Python 3.9 parsing, bytecode compilation, JavaScript syntax, POSIX shell syntax, manifest/config validation, safety-contract validation, and documentation consistency checks passed.
- Every release ZIP passed CRC, duplicate-entry, path-traversal, cache-artifact, fixed-timestamp, and executable-permission checks.
- Extracted Linux and macOS installer packages completed fresh install, replacement update, legacy-backup/staging cleanup, managed-environment cache refresh, and backup-free uninstall lifecycles in isolated home directories.
- Two clean builds produced identical SHA-256 values for every release artifact. Native Windows execution remains an acceptance-test item because PowerShell is unavailable in this build container.
