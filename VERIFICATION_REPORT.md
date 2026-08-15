# EMI Guardian v0.0.2 Verification Report

[日本語版](VERIFICATION_REPORT.ja.md)

**Build status:** pre-release engineering build

**Target:** KiCad 10.0.5+, Python 3.9+

**Verification date:** 2026-08-15

## Automated verification completed

- **146 pytest cases passed** across analysis, scoring, geometry, GND connectivity, protected-backbone antenna detection, antenna remediation, apply-time stale-plan rejection, silkscreen planning, outline operations, via stitching, initial placement, localization, controllers, HTTP endpoints, adapters, installers, documentation, manifests, and packaging.
- Deterministic randomized safety suites exercised:
  - 48 ground-tail cases with random dimensions and physical pads; every generated rule area remained pad-free and on-board.
  - 32 two-lobe GND geometries with a single narrow mandatory bridge; none was misclassified as a removable appendage.
  - 24 concave Edge.Cuts geometries with 40 random trace proposals each; every accepted full-width trace remained inside the outline under dense sampling.
- Python 3.9 grammar parsing for the complete plugin surface.
- Python bytecode compilation for plugin, scripts, and tests.
- JavaScript syntax parsing with Node.js.
- Bash syntax parsing for Linux and macOS scripts.
- KiCad manifest, PCM metadata, configuration schema 5, runtime version, KIID boundary, required modules, zero-backup installer contract, and apply-time antenna-revalidation contract checks.
- Documentation regression checks for bilingual manual coverage, schema version, zero-backup/no-rollback installation behavior, and active-board revalidation guidance.
- ZIP CRC, duplicate-entry, path-traversal, cache-artifact, fixed-timestamp, and executable-bit checks for all nine release archives.
- Extracted Linux and macOS release packages exercised through fresh install, replacement update, removal of legacy backup/staging directories, managed Python-environment cache refresh, and backup-free uninstall in isolated home directories.
- Two clean package builds compared by SHA-256; every release artifact was reproducible.
- The official `kicad-python-packager` validator accepted both the plugin directory and generated PCM ZIP. KiCad CLI 10.0.5 successfully loaded a bundled KiCad template and completed DRC; its reported violations belong to that upstream template and are not plugin findings.

## High-risk regressions covered

### Installer duplicate-plugin crash prevention

- Installer sources never copy the previous `plugins/emi-guardian` tree to KiCad's plugin directory or the OS temporary directory.
- Only the new payload is staged.
- Legacy `_emi-guardian-backups` and `emi-guardian.installing-*` directories are removed before replacement.
- A successful update leaves exactly one installable `plugins/emi-guardian` directory.
- Final-copy failure removes an incomplete destination; automatic rollback is not implemented.

### Pad and mandatory-GND protection

- Every physical pad touching the analyzed layer is excluded from removable antenna geometry.
- Same-net GND pad bodies and launch/thermal capture regions are mandatory terminals.
- Same-net vias, explicit same-net tracks, existing perimeter GND, secondary broad GND cores, and width-`t` paths to the primary core are protected.
- Missing GND-pad anchoring, invalid/missing Edge.Cuts, disconnected rasterization, or an unprovable terminal connection disables automatic keepout generation.
- Virtual candidate removal must preserve connectivity from every mandatory group to the primary broad GND core.

### Rule-area and new-copper containment

- Rule areas use the exact current-board proven residual and zero outward margin.
- Keepouts intersecting any pad, protected corridor, explicit GND trace, protected perimeter band, board boundary, or cutout are rejected.
- Proposed traces and vias use full-width/full-annulus board-containment and other-net-clearance tests.
- Redundant same-plane GND traces already covered by existing fill are rejected.
- The controller reruns analysis and planning immediately before mutation. A changed pad, zone, track, outline, polygon, width, or safety parameter rejects the complete apply request without a board mutation, even when an action ID happens to remain unchanged.

### Two-layer return-path false-positive control

- The generic transition-return-via rule is disabled by default for two-layer boards.
- Reference-gap findings require a minimum routed length, endpoint exclusion, sustained unsupported length, and unsupported fraction.
- Common power nets are excluded by default.
- GND-detour findings require both a high detour ratio and meaningful absolute excess.

### Placement preview readability

- Destination footprint outline, translated pad geometry, reference/value fields, block identity, component label, and movement vector are present in the preview payload.
- Locked footprints remain fixed.

## Verification not possible in this build container

- Live KiCad 10.0.5 GUI/IPC mutation, selection, layer activation, and zoom behavior.
- Native Windows PowerShell execution and Windows security-product interaction.
- macOS Finder/Gatekeeper launch behavior.
- Validation of the user's actual board connectivity and antenna candidates without the original `.kicad_pcb` file.
- Physical EMC, signal-integrity, thermal, mechanical, or fabrication results.

Before fabrication, run the bilingual acceptance procedure on a copy of the real board, refill zones, run KiCad DRC, inspect Gerbers, review the JLCPCB upload DFM, and verify every selected mutation. The plugin is an engineering screening and workflow-assistance tool, not an EMC or manufacturing guarantee.
