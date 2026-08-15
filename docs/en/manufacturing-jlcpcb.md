# JLCPCB two-layer manufacturing profiles

## 1. Purpose

This feature checks the open KiCad board against JLCPCB's published manufacturing information and EMI Guardian's cost-conscious engineering baseline. It exports order settings, routing presets, a KiCad custom-rule template, and a DFM report from one versioned configuration.

The bundled profiles target **two-layer FR-4 boards with KiCad 10 or later**. Price depends on the live quote, dimensions, quantity, copper weight, finish, lead time, shipping, coupons, and other options. Therefore, the plugin never guarantees price. “Economy” means that the defaults are designed to avoid known fine-feature surcharge conditions visible in the published information.

## 2. Profiles

### JLCPCB two-layer economy

A conservative board-wide baseline.

| Item | Default |
|---|---:|
| Copper layers | 2 |
| Board thickness | 1.6 mm |
| Solder mask | Green |
| Silkscreen | White |
| Outer copper | 1 oz |
| Surface finish | Leaded HASL |
| Track/clearance engineering baseline | 0.20 / 0.20 mm |
| Automatic-fix via | 0.60 / 0.30 mm diameter/drill |
| Copper to routed edge | 0.30 mm minimum |

The 0.20 mm routing baseline is not JLCPCB's absolute process limit. It is an EMI Guardian engineering choice that avoids using fine geometry everywhere and improves process margin and reviewability.

### JLCPCB two-layer capability limit

Values close to the published minimum process capability.

| Item | Value |
|---|---:|
| Track width / clearance | 0.10 / 0.10 mm |
| Via diameter / drill | 0.25 / 0.15 mm |
| Via annular ring | 0.05 mm |
| Copper to routed edge | 0.20 mm minimum |

Use this profile for localized high-density escape routing. JLCPCB's published capability table identifies every 0.15 mm via drill as a paid option. It also identifies 0.20 mm or 0.25 mm drills with a via diameter below 0.45 mm as paid options. Manual review and reduced process margin remain possible, so this is not the recommended board-wide default.

## 3. Selectable order settings

- Thickness: 0.4, 0.6, 0.8, 1.0, 1.2, 1.6, and 2.0 mm
- Solder mask: green, purple, red, yellow, blue, white, and black
- Outer copper: 1, 2, 2.5, 3.5, and 4.5 oz
- Finish: leaded HASL, lead-free HASL, and ENIG
- Separation: routing or V-cut

The plugin selects black silkscreen for white solder mask and white silkscreen for the other listed mask colors. Its DFM checks require ENIG and routed single-board delivery for a selected 0.4 mm board, rejecting V-cut. They reject leaded HASL and enforce the 100 × 100 mm quote limit for a selected 0.6 mm two-layer board. A selected 0.8 mm or 1.0 mm board is checked against the 300 × 300 mm normal quote limit.

## 4. Track-width presets

The following eleven presets are bundled:

`0.1, 0.2, 0.3, 0.4, 0.5, 0.8, 1.0, 1.5, 2.0, 3.0, 5.0 mm`

The selected value is recorded in the order bundle and is also used for GND tracks added by automatic antenna remediation. Current capacity, temperature rise, impedance, voltage drop, and copper weight remain separate design calculations.

## 5. Via presets

| Preset | Diameter / drill | Intended use |
|---|---:|---|
| JLCPCB capability limit | 0.25 / 0.15 mm | Local dense routing; the 0.15 mm drill is a paid option |
| KiCad 10 default / JLCPCB economy | 0.60 / 0.30 mm | KiCad's built-in default; also the plugin's low-cost standard and outside the published small-drill surcharge condition |

KiCad's current source defines the default through-via as 0.60 mm diameter with a 0.30 mm drill. The DFM checker warns for every 0.15 mm drill and for a 0.20 mm or 0.25 mm drill when the via diameter is below 0.45 mm. The 0.30 mm KiCad-default/economy drill does not match those published conditions. Always confirm the final price in the current quote.

## 6. DFM checks

The current geometric checks cover:

- Layer count, thickness, mask, silkscreen, copper weight, finish, and option compatibility
- Minimum/maximum board dimensions and small-board handling-cost information
- Mismatch between detected KiCad stackup data and selected order settings
- Track width
- Different-net track clearance
- Via diameter, drill, and annular ring
- Hole-to-hole spacing
- Via-to-track clearance
- Track, via, and pad distance to Edge.Cuts
- Height and stroke of available visible footprint reference/value fields

Pad drills, slots, arbitrary graphics, mask apertures, and complex zone details may not be completely available through the KiCad 10 IPC snapshot. JLCPCB's final DFM parser and a Gerber review remain mandatory.

## 7. KiCad 10 integration policy

KiCad 10's public IPC API can read stackup data, but public writes for all stackup fields, colors, and complete board rules are limited. EMI Guardian therefore uses this explicit workflow:

1. Select and persist order assumptions in the plugin.
2. Compare them with values that KiCad exposes.
3. Export `emi-guardian-jlcpcb.kicad_dru`.
4. Export `jlcpcb-order-settings.json` and bilingual order notes.
5. Review Board Setup and merge project rules explicitly.

The plugin does not text-edit an open `.kicad_pcb` file behind KiCad. This avoids corrupting unsaved changes or bypassing the application's Undo model.

## 8. Exported files

“Export JLCPCB bundle” writes:

- `jlcpcb-dfm-report.json`: issues, measured values, limits, and recommendations
- `jlcpcb-order-settings.json`: selected order options and the complete profile
- `routing-presets.json`: track-width and via presets
- `emi-guardian-jlcpcb.kicad_dru`: KiCad 10 custom-rule template
- `JLCPCB-ORDER-NOTES.md`: bilingual order/review notes
- `README.txt`: application and safety instructions

Do not overwrite an existing `<board-name>.kicad_dru`. Compare and merge the required rules, then run KiCad DRC.

## 9. References

Published information verified: **2026-08-13**

- JLCPCB PCB Capabilities: https://jlcpcb.com/jp/capabilities/PCB
- JLCPCB Quote: https://cart.jlcpcb.com/jp/quote
- JLCPCB Trace Spacing Guide: https://jlcpcb.com/jp/blog/optimize-pcb-trace-spacing
- KiCad Custom Rules: https://docs.kicad.org/10.0/en/pcbnew/pcbnew.html#custom_design_rules

Capabilities, quote restrictions, and surcharge conditions can change. Recheck the official pages and the DFM result produced after upload immediately before ordering.
