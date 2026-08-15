# EMI Guardian User Manual

**Target:** KiCad 10.0.5 and later
**Python:** 3.9 and later
**Primary board type:** Two-layer FR-4
**JLCPCB public information verified:** 2026-08-13

---

## 1. Purpose

EMI Guardian reads the board currently open in PCB Editor through KiCad's public IPC API and presents the following workflows in a form intended to help both experienced designers and beginners:

1. Detection of narrow ground-pour appendages, weak necks, isolated islands, and distant ground anchors
2. Remediation proposals using same-net ground tracks, stitching vias, track-plus-via combinations, and copper-pour keepout rule areas
3. Qualitative screening for stubs, parallel coupling, acute corners, route length, return-via gaps, board-edge proximity, and differential mismatch
4. First-order estimates for propagation delay, critical length, quarter-wave resonance, impedance, and skin depth
5. Silkscreen cleanup that hides references and places component values where they remain readable
6. Convex-first Edge.Cuts proposals that may retain only safe concavities already present in the original outline
7. JLCPCB two-layer economy and capability-limit profiles with geometric DFM pre-checks
8. Install, update, and uninstall workflows for Windows, macOS, and Linux

This plugin is an engineering screening tool. A clean report is not proof that a board has no EMI, EMC, signal-integrity, or manufacturing problem. Final validation requires KiCad DRC, Gerber review, manufacturer DFM, and—where applicable—oscilloscope, TDR, near-field, EMC, or electromagnetic-solver work.

## 2. Safety essentials

- Keep **Dry-run** enabled for the first review.
- Antenna repair, silkscreen edits, and Edge.Cuts replacement require a proposal, preview, explicit confirmation, and enabled write controls.
- Ground repairs never join different net names such as GND and AGND. They still cannot understand every isolation, current-sense, RF, or mixed-signal design intent.
- Edge.Cuts replacement is mechanically destructive. Test it on a copy of the board.
- Refill zones and run KiCad DRC after every copper or outline change. Inspect Gerbers, drill data, mask, and silkscreen before fabrication.
- The JLCPCB economy profile is a no-known-surcharge engineering baseline, not a price guarantee.

## 3. Install, update, and uninstall

### 3.1 Before running an installer

Close PCB Editor, the KiCad project manager, and every other KiCad process. Save the board and create a version-control or file backup.

The platform scripts install only for the current user and do not require administrator privileges. They create **no installer backup** of the old plugin, including in the operating-system temporary directory. The new payload is staged and checked first, then the old destination is removed and replaced. If final placement fails, the incomplete destination is deleted and the installer must be run again; automatic rollback is intentionally disabled. Legacy `_emi-guardian-backups` and stale staging directories are removed. The managed plugin Python environment is also removed so KiCad can recreate a consistent environment on the next launch. Normal uninstall preserves user settings and reports.

### 3.2 Windows

1. Extract the `emi-guardian-*-windows-installer.zip` package.
2. Double-click `Install-or-Update.cmd`.
3. Review any Windows security prompt and verify the source before continuing.
4. Start KiCad after completion.

Use the same launcher for updates. Run `Uninstall.cmd` to remove the plugin.

Direct PowerShell invocation:

```powershell
powershell -ExecutionPolicy Bypass -File .\install-or-update.ps1
powershell -ExecutionPolicy Bypass -File .\uninstall.ps1
```

Default location:

```text
<Documents>\KiCad\10.0\plugins\emi-guardian\plugin.json
```

The script asks Windows for the actual Documents folder, including OneDrive-redirection cases.

### 3.3 macOS

1. Extract the `emi-guardian-*-macos-installer.zip` package.
2. Run `install-or-update.command`.
3. If the executable bit was removed, use Terminal:

```bash
chmod +x install-or-update.command uninstall.command
./install-or-update.command
```

Uninstall:

```bash
./uninstall.command
```

Default location:

```text
~/Documents/KiCad/10.0/plugins/emi-guardian/plugin.json
```

### 3.4 Linux

```bash
unzip emi-guardian-*-linux-installer.zip
cd emi-guardian-*-linux
chmod +x install-or-update.sh uninstall.sh
./install-or-update.sh
```

Uninstall:

```bash
./uninstall.sh
```

Default location:

```text
~/.local/share/KiCad/10.0/plugins/emi-guardian/plugin.json
```

### 3.5 Manual installation

Extract the `emi-guardian` directory from the `emi-guardian-*-manual-install.zip` package into the operating system's KiCad `plugins` directory. The final depth must be:

```text
plugins/
└── emi-guardian/
    ├── plugin.json
    ├── open_dashboard.py
    ├── quick_scan.py
    ├── requirements.txt
    ├── default-config.json
    └── emi_guardian/
```

These are incorrect:

```text
plugins/emi-guardian/emi-guardian/plugin.json
plugins/emi-guardian-manual-install/emi-guardian/plugin.json
```

## 4. KiCad settings and launch location

### 4.1 Enable the API

Open the KiCad-wide preferences page:

```text
Preferences / Settings
└── Preferences...
    └── Plugins
```

Confirm:

- **Enable KiCad API** is on
- A Python interpreter is configured
- Python is version 3.9 or later

Completely restart KiCad, then open a `.kicad_pcb` file in PCB Editor. On first discovery KiCad creates the plugin-specific environment and installs the dependencies from `requirements.txt`.

### 4.2 Launch

In PCB Editor choose:

```text
Tools
└── External Plugins
    ├── Open EMI Guardian
    └── Quick EMI Scan
```

Use **Open EMI Guardian** for the normal dashboard. It opens a local `127.0.0.1` page in the default browser; it is not an Internet-hosted service.

`Quick EMI Scan` is a read-only convenience action.

### 4.3 Plugin does not appear

1. Verify `plugins/emi-guardian/plugin.json`.
2. Verify the KiCad-wide API and Python settings.
3. Fully close and restart KiCad.
4. Open the plugin warning indicator at the lower right of PCB Editor.
5. Look for messages containing `Python interpreter`, `Failed to create plugin environment`, `Failed to install`, or `kicad-python`.
6. Re-running the installer replaces the current plugin, removes any legacy backup/staging folders below `plugins`, and forces the managed environment to be rebuilt. No copy of the previous plugin is created for rollback.

## 5. Interface, language, and blue theme

The dashboard uses a blue visual system. When Japanese is selected, menus, finding titles, descriptions, recommendations, category labels, measurement labels, and JLCPCB DFM details are all presented in Japanese. Saved reports retain both Japanese and English presentation data.

Main views:

| View | Purpose |
|---|---|
| Dashboard | Overall/category scores, board preview, finding list |
| Antenna fixes | Build, compare, preview, and apply ground-remediation proposals |
| Silkscreen cleanup | Plan component-value placement and compare with existing silk |
| Outline optimizer | Convex-first outline, target vertex count, fillets, and ground-band evidence |
| JLCPCB manufacturing | Thickness, color, routing/via presets, DFM, and order bundle |
| Quantitative | Fast first-order estimates and solver exchange data |
| Settings | All thresholds, safety controls, connection controls, and advanced JSON |

## 6. Recommended first workflow

1. Save the board and create a backup or Git commit.
2. Launch the plugin and confirm Dry-run is enabled.
3. Choose the intended thickness, color, and finish in JLCPCB Manufacturing.
4. Apply the JLCPCB two-layer economy profile unless there is a specific reason not to.
5. Select one or more track widths and one or more via presets.
6. Run the manufacturing DFM check.
7. Run the board analysis from the dashboard.
8. Click findings to inspect evidence and preview position.
9. Use **Show location in KiCad** for items requiring board-level review.
10. Build antenna, silkscreen, and outline proposals and inspect their dedicated previews.
11. Apply changes only to a board copy, then run DRC and review Gerbers.

## 7. Board preview

### 7.1 Zoom and pan

Each interactive preview supports:

- **Fit:** restore the full-board view
- **Zoom in/out:** button-controlled steps
- **Mouse wheel or trackpad:** zoom around the pointer
- **Drag:** pan the visible region
- **Finding marker click:** open the finding details

Zoom limits prevent the drawing from becoming irretrievably tiny or unboundedly large.

### 7.2 Layer controls

Controls are generated from layers present on the board. Typical choices include:

- `F.Cu`, `B.Cu`, and internal copper layers
- `F.SilkS`, `B.SilkS`
- `Edge.Cuts`
- Pads
- Vias
- Footprint bounding boxes
- Findings
- Fix Preview
- Silk Preview

**All** and **Hide all** are also available. Zones are drawn from filled polygons, tracks are width-aware lines, and pads/vias are simplified geometry.

### 7.3 Large-board limits

To keep the browser responsive, preview payloads are bounded to 5,000 tracks, 5,000 pads, 3,000 vias, 2,500 footprints, 100 zones, and related polygon limits. Truncation counts are retained in the payload. These limits do not necessarily limit the analysis core itself.

## 8. Showing a finding in KiCad

Press **Show location in KiCad** on a finding card or in the details dialog. The plugin attempts to:

1. Resolve the KiCad item identifiers used as evidence
2. Clear the old selection
3. Select the evidence items
4. Activate the relevant layer when available
5. Request KiCad's zoom-to-selection action

KiCad 10's public IPC does not expose stable creation of plugin-defined persistent DRC markers. EMI Guardian therefore uses non-destructive **selection plus zoom**. KiCad's action identifiers are not a stable API guarantee, so a future KiCad build may still select the items while declining the automatic zoom. Use PCB Editor's manual zoom-to-selection command in that case.

Raster-derived ground-pour findings may correspond to a location or related board objects rather than one exact KiCad item.

## 9. Understanding scores

Overall and category scores range from 0 to 100. Higher values mean fewer geometry-based concerns. Bounded, diminishing impact prevents unbounded linear accumulation from pinning the corner category at zero. Category scores are held above 1.0.

Scores rank work; they do not certify compliance. Review the severity, confidence, measured values, and evidence for each finding. A single severe problem can remain important even when the aggregate score is high.

## 10. Sharp trace corner screening

### 10.1 Default behavior

The default acute threshold is **75 degrees**. Only an included routing angle below 75 degrees is considered. An ordinary 90-degree bend is not flagged. A two-segment 45-degree routing style produces a 135-degree included angle and is not flagged.

The detector excludes by default:

- Vertices inside a pad bounding box plus configured clearance
- Vertices located on vias
- Junctions with three or more attached segments
- Adjacent segments shorter than 0.50 mm
- Internal joints from approximating one KiCad arc
- Duplicate segments derived from the same source item

This removes common false positives from rectangular pads and pad-entry geometry. A genuine acute bend outside the pad exclusion region can still be reported.

### 10.2 Tuning

- `noise.acute_corner_warning_deg`: acute threshold
- `noise.corner_pad_exclusion`: pad/via exclusion
- `noise.corner_pad_clearance_mm`: clearance around pad bounds
- `noise.corner_min_segment_length_mm`: micro-segment rejection
- `noise.corner_skip_complex_junctions`: branch-point rejection

Corners have a default 10% qualitative weight because return-path discontinuity, ground geometry, and parallel coupling are generally more important screening targets.

## 11. Electrically long routed net screening

### 11.1 Route-path estimate

Summing every branch of a net makes a short multi-drop bus appear longer than any source-to-load path. EMI Guardian builds connected route components and estimates the longest endpoint-to-endpoint path. Small components are exhaustively scanned; larger components use a bounded terminal/junction or cyclic-node scan controlled by `long_net_diameter_scan_limit` (default 32). Total copper remains diagnostic evidence but is not blindly added to the electrical path.

### 11.2 Defaults

- Geometric threshold: 50 mm
- Signal rise time: 1.0 ns
- Critical-length fraction: 1/6 of propagation distance
- Trigger mode: `both_or_severe`
- Common ground and power names excluded by default

`both_or_severe` reports a component when both geometric and electrical thresholds are exceeded, or when the route is more than 1.5 times the smaller threshold. This reduces marginal false positives while retaining clearly long routes.

### 11.3 Tuning guidance

Use the actual driver rise time rather than only clock frequency. Increase rise time for slow GPIO. For high-speed buses, save board-specific settings until net-class presets are introduced. Edit `long_net_ignore_regex` to include or remove power nets. Use `either` for maximum sensitivity or `both` for stronger false-positive suppression.

## 12. Other qualitative checks

- **Dangling stub:** route branch not anchored to a pad or via
- **Parallel coupling:** different-net parallel distance, spacing, and overlap
- **Missing return via:** layer transition without nearby ground return via
- **Edge-proximate signal:** signal copper close to Edge.Cuts
- **Differential-pair mismatch:** P/N or +/- route-length mismatch
- **Ground-pour antenna:** necking, slenderness, anchor distance, resonance estimate, and nearby aggressor evidence

These are geometry-based checks. On a two-layer board, the generic layer-transition return-via warning is disabled by default. Reference-plane gaps require a sustained absolute length and route fraction after endpoint breakout exclusion, while GND detour requires both a high ratio and a minimum absolute excess. They cannot completely infer driver current, termination, cable, enclosure, common-mode conversion, or functional net intent.

## 13. Ground-pour detection and fix preview

### 13.1 Detection

The detector rasterizes each filled GND polygon and first constructs a **protected GND backbone**. The morphological opening uses the larger of the configured neck width and required connection width `t` (default 1.0 mm). The largest broad region becomes the primary core; every other broad region is mandatory, so the only narrow bridge between two substantial plane regions cannot be removed. Every physical pad area and a conservative pad-launch/thermal margin are non-removable. Same-net GND pads, vias, explicit GND traces, and each existing perimeter-GND component are mandatory terminals. A shortest occupied-copper path from every secondary core and terminal to the primary core is protected and dilated to width `t`. Only residual copper outside this protected union can become an appendage finding, and removal is reported only after a second connectivity proof shows that every mandatory group still reaches the primary core. A floating component is classified as an island rather than also receiving appendage findings. Refill zones in KiCad before scanning.

Automatic residual removal fails closed when a valid closed Edge.Cuts loop, broad GND core, raster budget, or mandatory-terminal connectivity proof is unavailable. The plugin prefers no automatic keepout over guessing which copper is a required pad launch or perimeter return path.

### 13.2 Candidate actions

For each proven finding, it compares:

1. An exact shape-matched copper-pour keepout rule area
2. A same-net ground bridge only when it crosses a real uncovered gap
3. A GND stitching via only when it creates a new inter-layer connection
4. A bridge plus via when both tests succeed

A rule area is rejected if it touches any pad, a protected width-`t` corridor, an explicit GND trace, or protected perimeter GND, or if it lies outside Edge.Cuts. The shape is never expanded beyond the detector's proven residual. Immediately before planning, the protected-backbone analysis is repeated against the current board and the rule-area polygon must exactly match a currently proven residual; stale findings therefore fail closed after a board edit. New tracks and vias require a reconstructable board outline, full-width containment inside Edge.Cuts including concavities and cutouts, and clearance from other-net tracks, vias, pads, and filled zones. Candidates are ranked by predicted risk reduction, added geometry, manufacturability, and confidence.

The write request performs another independent safety pass. Immediately before mutation, the controller rereads the active board, reruns the complete analysis and planner, and requires the selected action IDs, target net/layer, geometry, dimensions, and safety-proof parameters to match the preview exactly. Any missing or changed action aborts the whole request without modifying the board and requires the fix preview to be rebuilt.

### 13.3 Preview

The fix preview overlays proposed tracks, vias, and rule areas on the existing board layers, pads, vias, silk, and findings. Use zoom, pan, and layer controls to inspect conflicts and design intent. Proposal checkboxes permit partial adoption, and selected/unselected proposals use different preview styling.

### 13.4 Apply

Disable Dry-run only after review, select the confirmation check, and apply actions meeting the confidence threshold. Do not edit pads, GND tracks, zones, or Edge.Cuts between preview and apply; when such an edit is detected, the apply request is rejected and the preview must be rebuilt. Refill zones and run DRC afterward. Supported changes are grouped into a single undo transaction where possible.

## 14. Silkscreen cleanup and preview

Defaults:

- Text width 0.8 mm
- Text height 0.8 mm
- Stroke 0.10 mm
- Hide references
- Show values
- Avoid pads, vias, board edges, and existing text
- Skip locked footprints
- Choose a safe 0°, 90°, +45°, or -45° orientation
- Hide MountingHole and LOGO values by default
- Move references to F.Fab/B.Fab and hide them

Building a silkscreen plan overlays proposed values separately from existing `F.SilkS` and `B.SilkS`. Footprints without a safe candidate are skipped rather than forced into collision.

Before applying, verify polarity, pin-1 markers, warnings, certification marks, and rework access. Explicitly enable the JLCPCB 1.0 mm text / 0.15 mm stroke profile when that readability baseline is required.

## 15. Board-outline optimization

### 15.1 Default strategy

- Mode: diagonal edges allowed
- Strategy: `convex_preserve_existing_concavities`
- Target vertices: 8
- Allowed target range: 4–64
- Vertex grid: 0.5 mm
- Fillet radius: 1.0 mm
- Destructive replacement: disabled

The proposal starts from a convex support polygon around protected footprints, pads, vias, tracks, and mounting holes. A concave source vertex is reinserted only when it already existed in Edge.Cuts and passes protection and safety tests. New concavities are not created by default.

### 15.2 Target polygon side count

Set `target_vertex_count` to the desired target. The actual count may differ because of the safe hull, grid, protected geometry, original concavities, and orthogonal constraints. The proposal reports requested and actual values.

More sides can follow the board content more closely but increase mechanical and manufacturing review complexity. Six to twelve is a practical starting range for many boards.

When a vertex grid is enabled, the optimizer inserts only lattice points that lie **exactly on an existing edge**. It never rounds an arbitrary midpoint inward. If the requested count cannot be reached safely, the proposal uses fewer vertices and emits a warning instead of violating the protected envelope.

If grid processing creates an unintended reflex vertex, the default strategy returns to a convex hull. Only concavities explicitly preserved from the source outline may remain.

### 15.3 Orthogonal mode

Choose `orthogonal` for horizontal and vertical edges only. Choose `diagonal` and enable `allow_diagonal_edges` when sloped edges are acceptable.

### 15.4 Ground perimeter and application gates

The plugin samples the proposed perimeter and blocks automatic replacement unless the requested ground band can be demonstrated. It also checks area-reduction limits, component and copper margins, mounting-hole protection, and post-fillet area. In addition to the sharp polygon, it verifies that the **actual rounded contour, including every fillet arc**, contains all protected geometry; the contour is expanded outward when needed and proposal generation fails closed if safety cannot be established.

The outline view exposes the vertex grid directly and provides separate **Optimize**, **Smooth current outline**, and **Fillet current outline** operations. Existing board layers are overlaid in the outline preview.

Application requires destructive replacement to be enabled, a backup, the exact board name, and explicit confirmation. Enclosure, connector, panel, fixture, antenna keepout, and creepage requirements remain a human responsibility.

## 16. GND via stitching

**Plan via stitching** verifies same-net ground fill and creates moderate-density perimeter candidates. The defaults are 5.0 mm spacing and 2.5 mm minimum spacing, with candidates near outline vertices prioritized. The full via annulus must remain inside target ground copper and pass other-net, pad, existing-via, and edge-clearance checks.

A perimeter rebuild preview shows both removals and additions. If only some additions are selected, deletion of the old ring is automatically disabled. Ordinary stitching additions retain existing vias.

## 17. Schematic-block initial placement

**Plan initial placement** is a dry-run aid for an unrouted board. It groups footprints by schematic sheet path where available, preserves locked parts, biases connectors toward the perimeter, and places likely capacitors near candidate pads carrying matching power nets. Larger core parts are placed first to make block structure easier to route.

The preview now draws each destination footprint body, translated pad geometry, reference/value fields, schematic-group box, identity label, and an arrow from the current position. Selected and unselected moves are visually distinct, so the proposed component and destination can be identified without relying on a center dot.

This is not complete autorouting or circuit-intent inference. Review thermal, isolation, RF, mechanical, and usability constraints, then select only the moves to adopt.

## 18. JLCPCB manufacturing profiles

### 16.1 Economy default

| Item | Value |
|---|---:|
| Layers | 2 |
| Thickness | 1.6 mm |
| Solder mask | Green |
| Silkscreen | White |
| Copper | 1 oz |
| Finish | Leaded HASL |
| Track/clearance baseline | 0.20/0.20 mm |
| Automatic-fix via | 0.60/0.30 mm |
| Routed-edge copper distance | 0.30 mm |

### 16.2 Capability limit

| Item | Value |
|---|---:|
| Track/clearance | 0.10/0.10 mm |
| Via diameter/drill | 0.25/0.15 mm |
| Annular ring | 0.05 mm |
| Routed-edge copper distance | 0.20 mm |

Process limits are not recommended board-wide defaults. Fine tracks, small drills, colors, thicknesses, and finishes may affect price, lead time, and yield.

### 16.3 Thickness and color

Available thicknesses are 0.4, 0.6, 0.8, 1.0, 1.2, 1.6, and 2.0 mm. Mask colors are green, purple, red, yellow, blue, white, and black. White mask automatically selects black silkscreen; other masks select white silkscreen.

Board thickness and color cannot always be safely written through the KiCad 10 public IPC. The plugin stores the order assumption, compares any readable KiCad data, and exports it in JSON and order notes. Set the same values in KiCad Board Setup and the JLCPCB quote.

### 16.4 Multiple track-width presets

Available track widths are:

`0.1, 0.2, 0.3, 0.4, 0.5, 0.8, 1.0, 1.5, 2.0, 3.0, 5.0 mm`

Multi-selection defines the routing catalogue for the project. One safe automatic-repair width is chosen using this order:

1. Use the active profile default when it is selected
2. Otherwise use the smallest selected width that satisfies the active profile
3. If no selection satisfies the profile, fall back to the profile default

Selecting both 0.1 and 0.2 mm under the economy profile therefore keeps 0.20 mm for automatic repairs. The 0.1 mm catalogue entry remains available for local routing and is reported by DFM when used outside the active baseline.

### 16.5 Multiple via presets

- JLCPCB capability limit: 0.25 / 0.15 mm
- KiCad 10 default / JLCPCB economy: 0.60 / 0.30 mm

Both may be selected. Automatic repairs use 0.60/0.30 mm under the economy profile and prefer 0.25/0.15 mm under the capability profile. The complete selection is retained in routing exports.

### 16.6 DFM and exports

The DFM checker covers track width, different-net clearance, via diameter/drill/annular ring, hole spacing, edge clearance, thickness/finish combinations, and silkscreen dimensions. Japanese UI displays the issue details and recommendations in Japanese.

Manufacturing bundle:

```text
jlcpcb-dfm-report.json
jlcpcb-order-settings.json
routing-presets.json
emi-guardian-jlcpcb.kicad_dru
JLCPCB-ORDER-NOTES.md
README.txt
```

The `kicad_dru` file is a review template, not an automatic replacement for existing project rules.

## 19. Long-idle connection behavior

The local dashboard remains available by default:

- Idle shutdown: 0 minutes, disabled
- KiCad heartbeat: 20 seconds
- IPC retry count: 2

The browser periodically calls `/api/ping`. If the IPC client is stale, the plugin closes it and attempts a bounded reconnect. Closing KiCad, closing the board, OS sleep, or blocking localhost traffic can still interrupt the session. Reopen the board and run a fresh analysis.

Set `ui.inactivity_timeout_minutes` to a positive value only when automatic shutdown is desired.

## 20. Performance

Connection recovery includes:

- Uniform-grid indexing for pad/via proximity queries
- Spatial deduplication of parallel-route findings
- Connected-component processing for long routes
- Bounded preview payloads and delayed rendering
- Per-stage analysis timing
- A 1,500,000-cell antenna raster cap

Stage timing is included in report statistics. Increase `antenna.raster_step_mm` for faster scans, but understand that coarser rasterization can miss fine copper features. Speed and maximum geometric sensitivity cannot both be optimized without tradeoffs.

## 21. Quantitative estimates

The plugin displays:

- Microstrip and stripline characteristic impedance approximations
- Effective permittivity
- Propagation speed and delay
- Rise-time critical length
- Quarter-wave resonance
- Copper skin depth
- Normalized parallel-coupling proxy

Solver exchange output contains geometry, layers, nets, units, and material assumptions. It does not automatically establish ports, excitation, termination, cables, enclosure, boundary conditions, or mesh convergence, so an export is not a completed EM simulation.

## 22. Configuration summary

### 20.1 General

- `fixes.dry_run`
- `fixes.minimum_apply_confidence`
- `ui.language`: `auto`, `ja`, or `en`
- `ui.inactivity_timeout_minutes`: 0 disables
- `ui.heartbeat_seconds`
- `ui.ipc_retry_count`

### 20.2 Antenna

Ground-net regular expression, raster step and cell cap, neck width, required connection width `t`, pad/via/explicit-track protection margins, protected perimeter-GND width, appendage length, anchor distance, resonance target, effective permittivity, and aggressor distance.

### 20.3 Noise

Parallel-angle/spacing/overlap, acute threshold and pad exclusion, route length, rise time, critical-length fraction, long-route mode, two-layer reference-gap minimum length/fraction and endpoint exclusion, GND-detour minimum ratio/excess, edge clearance, and differential naming/mismatch.

### 20.4 Outline

- `mode`: `orthogonal` or `diagonal`
- `outline_strategy`: default `convex_preserve_existing_concavities`
- `target_vertex_count`: 4–64
- Grid, fillet radius, component/copper margins, ground band, and maximum reduction

Advanced JSON exposes every setting. Invalid values are rejected. The configuration schema is version 5.

## 23. Reports and retained data

HTML, JSON, and Markdown reports contain scores, bilingual finding presentation, evidence, plans, outline data, quantitative estimates, DFM, assumptions, and timing. Review net and board names before committing reports to a public repository.

Normal uninstall preserves settings and reports. Use the explicit removal options only when a complete local cleanup is intended.

## 24. Troubleshooting

### Corner score is unexpectedly low

Inspect included angles. The default threshold is 75 degrees and does not flag ordinary 90-degree bends. If the displayed behavior differs, recreate the managed environment and refresh cached web assets.

### A real acute corner is missed

Check whether it is inside the pad/via exclusion area, a branch point, a short segment, or an arc approximation. Reduce pad clearance or minimum segment length only after reviewing false-positive impact.

### Too many long-route findings

Enter the real driver rise time, inspect `long_net_trigger_mode`, power-net exclusion, and the 50 mm threshold. Confirm the displayed route is the estimated maximum endpoint path, not total branch copper.

### KiCad selection works but zoom does not

The internal KiCad action name may be unavailable. Use manual zoom-to-selection. If zero items are selected, the board may have changed since analysis; rerun the scan.

### Connection fails after a long pause

Confirm KiCad and a board remain open, the browser tab belongs to the same session, and the OS has resumed from sleep. Check heartbeat and retry settings, then run a new analysis.

### Presets are still single-select

The current interface uses checkboxes. Recreate the managed environment and force-refresh the browser if old assets still show a single-select control.

### Fix or silk overlay is missing

Build the corresponding plan first, then enable the **Fix Preview** or **Silk Preview** layer.

### DFM is too strict

The economy profile is intentionally more conservative than process limits. Use capability geometry locally rather than changing every automatic repair to a process-limit dimension.

## 25. Pre-order checklist

1. Save the board and create a backup or Git commit.
2. Match layer count, thickness, color, copper, and finish in KiCad, the plugin, and the quote.
3. Resolve DFM errors and review every warning.
4. Inspect EMI findings in KiCad.
5. Verify automatic proposals against design intent.
6. Refill zones.
7. Run KiCad DRC.
8. Inspect Gerbers, drills, Edge.Cuts, mask, and silkscreen.
9. Check connectors, mounting holes, enclosure, panelization, and V-cuts.
10. Review JLCPCB's uploaded-file DFM and live quote.
11. Prepare any required SI/EMC measurement plan.

## 26. Limitations

- Static PCB geometry cannot prove that every physical radiator has been found.
- Ground-pour detection depends on filled geometry and raster resolution.
- Selection plus zoom is not a persistent DRC marker.
- KiCad action identifiers are not stable API contracts, so automatic zoom may require future adaptation.
- Thickness, color, and project-rule writing are handled through validation/export when the public IPC does not provide a safe write path.
- The outline optimizer cannot understand enclosure intent.
- JLCPCB capability and price rules can change.
- Automated tests cannot replace live KiCad GUI acceptance, EMC measurement, or manufacturer acceptance.

## 27. References

- JLCPCB PCB Capabilities: https://jlcpcb.com/capabilities/pcb-capabilities
- JLCPCB Quote: https://cart.jlcpcb.com/quote
- KiCad 10 PCB Editor Manual: https://docs.kicad.org/10.0/en/pcbnew/pcbnew.html
- KiCad IPC API: https://dev-docs.kicad.org/en/apis-and-binding/ipc-api/
- kicad-python: https://docs.kicad.org/kicad-python-main/

---

This manual and the bundled JLCPCB values are based on public information verified on 2026-08-13. Recheck official information immediately before fabrication.
