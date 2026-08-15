# KiCad 10.0.5 live acceptance test

This procedure covers KiCad GUI, public IPC, platform installers, and real board mutations that automated tests cannot prove. Use a disposable board copy.

## 1. Record

Record OS/version, KiCad version, KiCad Python version, EMI Guardian version, installer name and SHA-256, board commit/hash, operator, time, result, and screenshots.

## 2. Install, update, and uninstall

On every target OS, close KiCad, run the platform installer, verify `plugins/emi-guardian/plugin.json`, launch KiCad, and confirm managed-environment creation. Update from an older version and verify that exactly one `plugins/emi-guardian` directory remains. Confirm that `_emi-guardian-backups` and `emi-guardian.installing-*` do not remain below the KiCad `plugins` directory. Inspect the installer and its temporary directory during a controlled run and confirm that it never copies the previous plugin. Exercise a controlled final-placement failure and confirm that the incomplete destination is removed, no rollback copy exists, and a clean rerun succeeds. Uninstall and confirm that the plugin and managed environment are removed while settings remain, then reinstall.

Also review PowerShell policy on Windows, Gatekeeper/executable permissions on macOS, and executable bits on Linux.

## 3. Discovery and launch

Enable the KiCad API in the KiCad-wide Plugins preferences. Test Python 3.9. Open a board and confirm `Open EMI Guardian` and `Quick EMI Scan` under Tools → External Plugins. Launch the dashboard and verify no unresolved plugin warning.

## 4. UI and language

Confirm the blue theme. Switch to Japanese and generate at least one EMI and one JLCPCB DFM finding. Verify Japanese title, description, recommendation, category, and metrics. Switch to English and verify the same fields.

## 5. Board preview

Use a board with front/back copper, front/back silk, pads, vias, zones, and Edge.Cuts. Verify geometry, findings, fit, buttons, wheel/trackpad zoom, drag pan, individual layer toggles, all/hide-all, finding-marker click, and responsive behavior with truncation on a large board.

## 6. Locate in KiCad

Open a track-backed finding and press Show location in KiCad. Confirm evidence selection, layer activation, and zoom when supported. In an environment where the action is unavailable, verify selection remains safe without a board mutation. Delete an item after analysis and confirm a safe unavailable result. Persistent DRC markers are intentionally not created.

## 7. Corner detector

Create 90-degree, normal 45-degree routing style, truly acute, rectangular-pad entry, via-centered, three-way branch, 0.3 mm micro-segment, and arc fixtures. Under the 75-degree default, confirm that only the genuine acute corner outside exclusion regions is reported. Confirm the category is not incorrectly pinned at 0.0 and that threshold/exclusion settings work.

## 8. Long-route detector

Create a 60 mm route, a branched net whose total copper is long but endpoint paths are short, disconnected components with the same net, and different rise-time/trigger settings. Confirm the displayed value is the maximum endpoint path rather than a blind branch sum and that common ground/power nets are excluded by default.

## 9. Multi-presets and JLCPCB

Under economy, select all 11 widths and both vias. Save/reload and confirm retention. Confirm automatic fixes remain 0.20 mm and 0.60/0.30 mm. Under capability, confirm 0.10 mm and 0.25/0.15 mm. Verify DFM flags fine geometry under economy and validate thickness, color, silk color, finish, and manufacturing bundle.

## 10. Antenna fix preview and apply

Use several filled-GND fixtures: a harmless overhang, a GND-pad thermal/escape corridor, an explicit GND trace, an existing perimeter band, a true floating island, an internal Edge.Cuts cutout, and a concave outer outline. Confirm the following before applying anything:

- every physical pad and its configured protection margin remain outside all antenna findings and keepout polygons;
- each same-net GND pad, via, explicit GND trace, and existing perimeter-GND component remains connected to the broad GND core by the configured width-`t` protected backbone;
- only residual copper outside that backbone receives a shape-matched rule-area proposal;
- removing the proposed residual in the preview does not disconnect a protected terminal or remove the perimeter band;
- a finding generated before a board edit is rejected after a new pad or GND route overlaps its old keepout;
- even when a deterministic action ID remains the same, a changed keepout polygon or dimension is rejected by the final apply-time safety signature;
- applying an unchanged preview triggers one fresh active-board scan and succeeds only when the selected action is reproduced exactly;
- a proposed bridge and its complete width, and a proposed via and its complete annulus, stay inside the outer Edge.Cuts, outside internal cutouts, and clear other-net tracks, pads, vias, and filled zones;
- a track already lying entirely in same-net filled copper is rejected as redundant;
- GND and AGND are never joined.

Inspect all overlays. Confirm Dry-run blocks writes. Apply selected proposals on a disposable copy and verify one undo group, exact-net behavior, zone refill, and post-apply KiCad DRC.

## 11. Silkscreen preview and apply

Use front/back, rotated, locked, and congested footprints. Verify 0.8 × 0.8 mm and 0.10 mm defaults, current/proposed layer toggles, collision avoidance, safe skip, reference/value behavior, upright orientation, Undo, and Gerber result.

## 12. Outline optimizer

Test convex and originally concave boards. Confirm convex-first output, retention of only safe source concavities, no new concavity, target counts of 4/6/8/12/16, orthogonal/diagonal modes, 0.1/0.5/1.0 mm grids, fillets, ground-band blocking, exact-board-name confirmation, backup, Undo, DRC, Gerber, and enclosure fit.

## 13. Long-session connection

Confirm defaults of idle 0, heartbeat 20 seconds, and retry 2. Leave the dashboard idle for more than 90 minutes. Test KiCad restart/board reopen and OS sleep/resume. Failures must produce a clear error without board mutation.

## 14. Performance

Record runtime and memory on small, medium, and large fixtures. Review stage timing and compare raster-step speed/sensitivity. Confirm the large-board UI remains usable.

## 15. Final manufacturing review

Refill zones, run KiCad DRC, inspect Gerbers, drill, Edge.Cuts, mask, silk, 3D/mechanical fit, JLCPCB uploaded-file DFM, and the live quote. Perform the required SI/EMC validation separately.

## 16. Finding interaction and layer controls

- [ ] Clicking a finding marker opens detail
- [ ] Hovering a marker shows the localized summary
- [ ] Hovering a finding card highlights the matching marker
- [ ] Show location in preview centers on the finding
- [ ] Findings remain visible after hiding all ordinary layers

## 17. Ground connectivity, antenna repair, and stitching

- [ ] Connected ground fill with a `*.Cu` through-hole pad is not reported as an island
- [ ] A physical pad is never reported as an antenna and never overlaps a proposed rule area
- [ ] Pad/thermal escape, explicit GND tracks, width-`t` corridors, and existing perimeter GND are protected
- [ ] A narrow residual outside the protected backbone prefers an exact shape-matched rule area
- [ ] A stale finding is revalidated against the current board before a rule area is offered
- [ ] Immediately before apply, the active board is rescanned and a missing or geometry-changed selected action aborts the entire request without mutation
- [ ] An unchanged selected action is reproduced exactly and applied once after final revalidation
- [ ] A redundant track entirely on existing same-net fill is not proposed
- [ ] The complete width of every proposed track remains inside concave Edge.Cuts and outside cutouts
- [ ] Proposed tracks and vias clear filled copper belonging to other nets
- [ ] A bridge overlay uses the proposal's actual width
- [ ] Stitching includes vertex-near candidates and avoids density, copper, and other-net violations
- [ ] Partial adoption disables bulk removal of an existing perimeter ring

## 18. Outline regression

- [ ] A compact pentagonal board is not replaced by a larger rectangle
- [ ] Optimize, smooth-current-outline, and fillet-current-outline are separate operations
- [ ] Pre-fillet polygon vertices are multiples of the selected grid
- [ ] The outline preview shows copper, silk, pads, vias, and footprints

## 19. Silkscreen and initial placement

- [ ] Default silk stroke is 0.10 mm
- [ ] 0°, 90°, and ±45° candidates are available
- [ ] MountingHole and LOGO values are hidden by default
- [ ] References are moved hidden to F.Fab/B.Fab
- [ ] A distant orphan label falls back to an on-footprint manual-review proposal
- [ ] Footprints are grouped by schematic sheet and locked parts remain fixed
- [ ] A matching-net capacitor is proposed near its associated pad
- [ ] Each placement proposal shows the component identity, destination body, translated pads, reference/value fields, and movement vector
