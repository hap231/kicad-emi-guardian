# User workflow

## 1. Launch

Open the target board in PCB Editor and choose **Tools → External Plugins → Open EMI Guardian**. Keep Dry-run enabled for the initial pass.

## 2. JLCPCB settings

1. Open JLCPCB Manufacturing.
2. Select the two-layer economy profile unless there is a specific need for capability-limit geometry.
3. Choose thickness, solder-mask color, copper, finish, and separation method.
4. Select at least one track width and one via preset. Multiple selections are supported.
5. Apply the profile and run DFM.

Multi-selection defines a routing catalogue. Automatic repairs still use a safe geometry compatible with the active profile.

## 3. Analyze

Run the analysis to refresh the board snapshot and screen ground antennas, parallel routing, acute corners, long routes, return paths, edge proximity, differential mismatch, and DFM.

Japanese UI localizes finding titles, descriptions, recommendations, and measurement labels. Click a finding for details.

## 4. Board preview

Use fit, zoom buttons, wheel/trackpad zoom, and drag-to-pan. Toggle `F.Cu`, `B.Cu`, `F.SilkS`, `B.SilkS`, pads, vias, footprints, and finding overlays. Click a marker to open it.

## 5. Locate in KiCad

**Show location in KiCad** selects evidence objects, activates the layer when supported, and requests zoom-to-selection. This is not a persistent DRC marker. If automatic zoom fails but selection succeeds, use KiCad's manual command.

## 6. Corner and route-length checks

The default acute threshold is 75 degrees, so 90-degree routing is not flagged. Pad/via regions, branch points, short segments, and arc approximation joints are excluded.

Long-net screening uses the longest endpoint route in each connected net component rather than total branch copper. Enter the actual driver rise time.

## 7. Antenna repair

Build a plan, inspect proposed tracks/vias/rule areas in the fix preview, use layers and zoom to review conflicts, then apply only after disabling Dry-run and confirming. Refill zones and run DRC.

## 8. Silkscreen cleanup

Build a plan, compare current silk with proposed values, review skipped footprints and required polarity/pin-1 marks, apply after confirmation, and inspect Gerbers.

## 9. Outline optimization

The default is a diagonal-capable, convex-first outline with eight target vertices. Only safe concavities already present in the source may be retained. Configure target count, grid, fillet, margins, and ground band before review.

Automatic replacement remains gated by ground-band and safety evidence plus explicit destructive-operation permission.

## 10. Connection and long sessions

Default behavior is no idle shutdown, a 20-second heartbeat, and two reconnect attempts. Reopen the board and rescan after KiCad shutdown or operating-system sleep.

## 11. Reports

Export HTML, JSON, Markdown, and the JLCPCB bundle. Reports include stage timing, bilingual presentation, evidence identifiers, and assumptions.

See the [user manual](user-manual.md) for the complete workflow.
