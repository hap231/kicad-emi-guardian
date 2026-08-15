# Changelog

[日本語版](CHANGELOG.ja.md)

## 0.0.2 — 2026-08-13

- Reworked ground-pour antenna detection around a conservative protected-backbone model. Every physical pad is excluded, same-net GND pads/vias/explicit traces and existing perimeter GND are mandatory, and a shortest existing-copper path to the broad GND core is protected to configurable width `t`.
- Added fail-closed behavior when a closed Edge.Cuts outline or current connectivity proof is unavailable. Floating islands and connected residual appendages are now mutually exclusive classifications.
- Revalidate every rule-area proposal against the current board immediately before planning. Stale findings cannot create a keepout after a pad, GND route, perimeter band, or zone geometry changes.
- Restricted rule areas to the exact proven residual without outward expansion. Rule areas that touch any pad, explicit same-net GND trace, internal cutout, outer board boundary, or unproven geometry are rejected.
- Strengthened new-copper containment for concave boards and internal Edge.Cuts holes. The complete proposed trace width and via annulus must remain on-board and clear other-net tracks, pads, vias, and filled zones.
- Relaxed two-layer return-path screening with minimum route length, endpoint exclusion, sustained unsupported-length/fraction gates, common power-net exclusion, and larger GND-detour ratio/excess thresholds.
- Expanded initial-placement previews to show the schematic block, component identity, destination footprint body, translated pads, reference/value fields, and movement vector.
- Removed installer backup creation entirely. The new payload is staged without copying the old plugin; successful install/update leaves exactly one `plugins/emi-guardian` directory and removes legacy backup/staging folders.
- Added regression tests for pad/thermal protection, perimeter protection, missing Edge.Cuts, stale-finding revalidation, narrow concavities, other-net filled-zone clearance, installer cleanup, and full placement-preview geometry.
- Updated bilingual manuals, acceptance procedures, package metadata, release checks, and deterministic build inputs for v0.0.2.

## 0.0.1 — 2026-08-13

- Fixed KiCad finding location lookup by passing `KIID` protobuf objects rather than raw UUID strings.
- Restored marker click detail, hover summaries, list-to-preview highlighting, and preview-location actions.
- Added show-all/hide-all preview layer controls while keeping finding markers visible.
- Added existing-board layers to outline, repair, silkscreen, stitching, and placement previews.
- Added area-increase rejection, current-outline smoothing, and current-outline filleting with grid-snapped pre-fillet vertices.
- Added safe GND via-stitching and optional perimeter-via rebuilding with vertex priority, full-annulus copper checks, spacing/clearance checks, and partial-selection deletion safeguards.
- Added filled-zone/track/pad/via ground-connectivity components, including wildcard through-hole padstacks, to reduce false island findings.
- Made shape-matched rule areas the normal repair for narrow connected ground-pour appendages and rejected redundant tracks already covered by same-net fill.
- Added partial adoption for antenna, silkscreen, stitching, and component-placement proposals.
- Replaced the generic two-layer return-via warning with reference-gap, ground-return-detour, and ground-bottleneck screening.
- Added 0°/90°/±45° silkscreen candidates, 0.10 mm default stroke, MountingHole/LOGO suppression, bounded label distance, manual-review fallback, and hidden Fab references.
- Added schematic-block-aware dry-run initial placement and matching-net capacitor proximity planning.
- Corrected diagonal-mode synchronization, sharp-corner scoring, electrically-long-net path estimation, and long-idle reconnect behavior.
- Added Python 3.9, package, installer-lifecycle, deterministic-build, geometry, localization, and API-boundary regression checks.

## 0.2.0 — 2026-08-11

- Added JLCPCB two-layer manufacturing support based on public capability and quote information verified on 2026-08-11.
- Added separate **economy** and **capability-limit** profiles. The economy profile defaults to two layers, 1.6 mm FR-4, green solder mask, white silkscreen, 1 oz outer copper, leaded HASL, 0.20/0.20 mm design baselines, and a 0.60/0.30 mm automatic-fix via.
- Added board-thickness, solder-mask color, copper-weight, surface-finish, and routing/V-cut selection in the bilingual dashboard.
- Added the requested routing-width presets: 0.1, 0.2, 0.3, 0.4, 0.5, 0.8, 1.0, 1.5, 2.0, 3.0, and 5.0 mm.
- Added the requested JLCPCB capability-limit (0.25/0.15 mm) and KiCad 10 default (0.60/0.30 mm) via presets. The KiCad default is also the economy-profile geometry.
- Added geometric JLCPCB DFM checks for order combinations, board size, readable stackup mismatch, routing width/clearance, via geometry and spacing, copper-to-edge distance, and available silkscreen fields.
- Added manufacturing export bundles containing DFM JSON, order settings, routing presets, a KiCad custom-rule template, bilingual order notes, and application guidance.
- Added Japanese and English user manuals, JLCPCB profile references, and a dedicated manufacturing acceptance-test procedure.
- Updated report bundles and the synthetic demonstration board to include manufacturing results.
- Migrated configuration schema to version 2 while retaining schema-1 loading compatibility.

## 0.1.0 — 2026-08-11

- Initial engineering-preview release for KiCad 10.0.5+.
- Added official IPC API adapter and canonical-layer compatibility helpers.
- Added raster/morphology ground-pour antenna analysis and ranked remediation plans.
- Added qualitative routing-risk score and closed-form electrical estimates.
- Added bilingual localhost dashboard, report export, silkscreen planner, and filleted Edge.Cuts proposal.
- Added destructive-operation safety gates, backups, exact-net matching, transaction requirements, and regression tests.
- Added complete default-configuration JSON, bilingual requirement traceability, and a KiCad-in-the-loop acceptance-test procedure.
- Added a direct-extraction manual-install archive in addition to the PCM repository package.
