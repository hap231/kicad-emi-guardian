# Implementation status and requirement traceability

Version 0.0.2 is a **pre-release test build** for KiCad 10.0.5 and later. It is geometry-, connectivity-, and configuration-based engineering screening, not proof of zero EMI, EMC compliance, or manufacturing acceptance.

| Requirement | v0.0.2 implementation | Remaining limit / acceptance condition |
|---|---|---|
| Locate in KiCad | Convert UUIDs to `KIID`, select evidence, request layer activation and zoom-to-selection | Not a persistent native DRC marker; verify in live KiCad |
| Finding interaction | Marker click opens detail, hover shows summary, list hover highlights marker, preview-locate action zooms | Browser pointer behavior needs target-system acceptance |
| Layer controls | Show all/hide all; Findings remains visible | Not a complete 3D/rendering replacement |
| Outline preview | Current copper, silk, pads, vias, footprints, findings, and proposal are overlaid | Preview payload is bounded |
| Outline growth regression | Reject area increase, preserve current outline, separate optimize/smooth/fillet operations | Mechanical constraints remain human-reviewed |
| Perimeter-via rebuild | Vertex-priority and spaced candidates, full-annulus same-net copper, clearance, no old-ring deletion under partial selection | Existing-via deletion requires explicit selection and safety gates |
| Antenna detection/remediation | Protect every pad area/launch margin plus GND pads, vias, explicit traces, width-`t` routes to the broad core, and existing perimeter GND; report only connectivity-proven residuals; revalidate exact rule areas against the current board; reject redundant/off-board copper | Requires closed Edge.Cuts and filled-zone geometry for automatic residual removal; does not solve enclosure/cable excitation or radiation values |
| Silkscreen | 0/90/±45°, 0.10 mm stroke, MountingHole/LOGO suppression, bounded owner distance, manual-review on-footprint fallback, hidden Fab references | Decorative detection is pattern-based |
| Partial adoption | Checkbox selection for antenna, silk, stitching, and initial-placement proposals with selected-state preview | Edge.Cuts replacement remains a whole-outline operation |
| Two-layer return path | Generic transition-via warning disabled by default; sustained-gap length/fraction and endpoint exclusions; common-power ignore; stricter GND detour ratio/excess; bottlenecks retained | Current distribution and frequency-dependent impedance remain approximations |
| Ground islands | Union zones, tracks, pads, `*.Cu` THT padstacks, and vias into exact-net components | Unfilled zones cannot be assessed |
| Via stitching | Vertex-priority moderate spacing with density, copper, clearance, and count limits | Not an optimizer for every wavelength/enclosure resonance |
| Diagonal mode | Selecting diagonal synchronizes `allow_diagonal_edges` | Conflicting orthogonal settings are normalized |
| Noise screening | Stubs, parallel coupling, acute corners, electrical length, reference gaps, ground detour/bottleneck, edge proximity, differential mismatch, pour appendages | No claim of outperforming every checker or having zero omissions; edge-rate inputs matter |
| Schematic-block placement | Group by sheet path, preserve locked parts, bias connectors to perimeter, place likely capacitors near matching-net pads; preview full destination footprint, pads, fields, group, identity, and move vector | Dry-run planning aid, not full circuit-intent autorouting |
| Performance | Spatial indexes, components, bounded searches, deduplication, preview limits | Raster cost still scales with area/resolution |
| Distribution | v0.0.2, three OS installers, bilingual docs, deterministic ZIPs, CI inputs; no old-plugin backup creation and automatic legacy-backup cleanup | A failed final copy requires a clean installer rerun; OS-specific Windows/macOS protection requires native acceptance |

## Public IPC boundary

The plugin uses public IPC for snapshots, selection, layers, transactions, item mutations, and zone refill where available. It does not edit `.kicad_pcb` text to force stackup color, thickness, or project rules.

## Completion gate

Automated tests, Python 3.9 parsing, JavaScript, POSIX shell, package structure, archive safety, isolated-HOME installer lifecycle, and two clean reproducible builds must pass. Live-KiCad items that cannot be exercised in this container are explicitly listed as unverified.
