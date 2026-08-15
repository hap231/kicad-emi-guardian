# Configuration reference

Configuration schema version is **5**. The dashboard exposes common settings; Advanced JSON exposes every field. Older schema files are migrated when possible, unknown fields are ignored, and invalid values are rejected before the file is replaced.

## `antenna`

| Field | Default | Purpose |
|---|---:|---|
| `ground_net_regex` | GND-family pattern | Exact-net candidates treated as ground families |
| `raster_step_mm` | 0.20 | Filled-zone raster resolution |
| `max_raster_cells` | 1,500,000 | Maximum raster budget before coarsening |
| `narrow_neck_width_mm` | 0.80 | User neck-width threshold |
| `minimum_appendage_area_mm2` | 0.40 | Minimum residual area |
| `minimum_appendage_length_mm` | 2.00 | Minimum residual geodesic length |
| `connectivity_tolerance_mm` | 0.08 | Exact-net zone/track/pad/via contact tolerance |
| `minimum_unanchored_component_area_mm2` | 0.50 | Minimum floating-component area |
| `required_ground_connection_width_mm` | 1.00 | Mandatory protected GND corridor width `t` |
| `pad_protection_margin_mm` | 0.30 | Additional pad/thermal protection margin |
| `via_protection_margin_mm` | 0.20 | Additional same-net via protection margin |
| `explicit_track_protection_margin_mm` | 0.15 | Additional explicit GND-track protection margin |
| `perimeter_ground_protection_mm` | 1.00 | Existing perimeter-GND protection band |
| `require_safe_removal_connectivity` | true | Require a removal connectivity proof |
| `protect_perimeter_ground` | true | Fail closed without valid Edge.Cuts/perimeter proof |
| `protect_explicit_ground_tracks` | true | Preserve intentional same-net GND tracks |

The effective morphological opening width is the larger of `narrow_neck_width_mm` and `required_ground_connection_width_mm`. A smaller raster step improves fine-feature sensitivity but raises cell count and runtime. Automatic copper removal fails closed when one filled polygon is not a single four-neighbor electrical component at the effective raster resolution.

## `fixes`

| Field | Default | Purpose |
|---|---:|---|
| `dry_run` | true | Block all automatic board writes |
| `minimum_apply_confidence` | 0.75 | Minimum selected-action confidence |
| `track_width_mm` | 0.20 | Manufacturing-profile base repair width |
| `adaptive_track_width` | true | Search for the widest safe configured width |
| `maximum_track_width_mm` | 2.00 | Upper bound for adaptive repair width |
| `maximum_bridge_length_mm` | 6.00 | Maximum new GND bridge length |
| `via_diameter_mm` / `via_drill_mm` | 0.60 / 0.30 | Automatic repair via geometry |
| `via_clearance_mm` | 0.25 | Known-copper clearance for repair vias |
| `maximum_via_search_radius_mm` | 3.00 | Via candidate search radius |
| `rule_area_margin_mm` | 0.00 | No expansion beyond the proven residual |
| `prefer_rule_area_for_appendages` | true | Prefer exact keepouts for removable overhangs |
| `reject_redundant_same_plane_tracks` | true | Reject tracks entirely on existing same-net fill |
| `board_edge_clearance_mm` | 0.10 | Additional copper-to-Edge.Cuts clearance |
| `require_board_outline_for_new_copper` | true | Require valid Edge.Cuts for tracks/vias |
| `require_proven_safe_rule_area` | true | Require current protected-backbone proof |
| `refill_zones_after_apply` | true | Refill after successful mutation |
| `create_single_undo_group` | true | Group compatible edits in one transaction |

Immediately before applying antenna fixes, the active board is read again and the full analysis/planner is rerun. Every selected action must reproduce the same ID, target net/layer, geometry, dimensions, and safety parameters; any mismatch aborts the whole request without mutation.

Applying a JLCPCB profile preserves multi-selected routing presets while ensuring automatic repair geometry satisfies the active profile.

## `noise`

| Field | Default | Purpose |
|---|---:|---|
| `endpoint_snap_mm` | 0.05 | Endpoint graph quantization |
| `dangling_stub_min_length_mm` | 0.80 | Minimum stub length |
| `parallel_angle_tolerance_deg` | 5.0 | Parallel angle tolerance |
| `parallel_spacing_warning_mm` | 0.50 | Coupling-spacing threshold |
| `parallel_overlap_warning_mm` | 5.0 | Coupled-overlap threshold |
| `acute_corner_warning_deg` | 75.0 | Acute threshold; 90 degrees excluded |
| `corner_pad_exclusion` | true | Exclude pad/via regions |
| `corner_pad_clearance_mm` | 0.10 | Pad exclusion margin |
| `corner_min_segment_length_mm` | 0.50 | Micro-segment rejection |
| `corner_skip_complex_junctions` | true | Skip branches with 3+ segments |
| `trace_length_warning_mm` | 50.0 | Geometric route threshold |
| `signal_rise_time_ns` | 1.0 | Driver rise time |
| `critical_length_fraction` | 1/6 | Electrical threshold fraction |
| `long_net_trigger_mode` | `both_or_severe` | Long-route trigger logic |
| `long_net_severe_multiplier` | 1.50 | Clear-overrun multiplier |
| `long_net_diameter_scan_limit` | 32 | Exact/representative graph scan budget |
| `skip_return_via_check_on_two_layer` | true | Disable generic 2-layer transition warning |
| `reference_plane_sample_step_mm` | 0.50 | Opposite-plane sampling step |
| `reference_gap_min_length_mm` | 3.00 | Minimum sustained unsupported length |
| `reference_gap_min_track_length_mm` | 5.00 | Minimum route length for gap screening |
| `reference_gap_min_fraction` | 0.30 | Minimum unsupported route fraction |
| `reference_gap_endpoint_exclusion_mm` | 0.75 | Ignore normal endpoint breakout regions |
| `ground_bottleneck_width_mm` | 1.00 | Narrow GND-component threshold |
| `ground_detour_warning_ratio` | 4.00 | GND-path/signal-path ratio threshold |
| `ground_detour_min_length_mm` | 5.00 | Minimum signal path for detour screening |
| `ground_detour_min_active_length_mm` | 1.00 | Minimum evaluated GND active path |
| `ground_detour_min_excess_mm` | 5.00 | Required absolute detour excess |
| `board_edge_signal_clearance_mm` | 1.0 | Signal-to-board-edge threshold |
| `differential_pair_mismatch_warning_mm` | 1.0 | Pair mismatch threshold |

`long_net_trigger_mode` accepts `either`, `both`, and `both_or_severe`. `long_net_ignore_regex` and `reference_gap_ignore_regex` exclude common ground and power names by default. The two-layer return checks intentionally require sustained evidence rather than a single missing sample.

Default category weights are antenna 0.30, parallel 0.20, corner 0.10, length 0.15, return path 0.15, and other 0.10.

## `silkscreen`

Defaults are 0.8 × 0.8 mm text with a 0.10 mm stroke, 0.20 mm pad/via clearance, 0.30 mm edge clearance, and 0.15 mm text clearance. Allowed angles are 0°, 90°, +45°, and -45°. Values stay within 2.50 mm of the owner footprint when possible; otherwise an on-footprint manual-review fallback may be generated. MountingHole/LOGO values are hidden by default, references are moved to F.Fab/B.Fab and hidden, and locked footprints are skipped.

## `edge`

| Field | Default |
|---|---:|
| `mode` | `diagonal` |
| `grid_mm` | 0.50 |
| `component_margin_mm` | 1.50 |
| `copper_margin_mm` | 0.50 |
| `minimum_ground_band_mm` | 1.00 |
| `fillet_radius_mm` | 1.00 |
| `outline_strategy` | `convex_preserve_existing_concavities` |
| `target_vertex_count` | 8 |
| `preserve_existing_concavities` | true |
| `allow_concave_outline` | false |
| `allow_diagonal_edges` | true |
| `maximum_area_reduction_percent` | 35.0 |
| `reject_area_increase` | true |
| `maximum_area_increase_percent` | 0.0 |
| `preserve_existing_outline_when_smaller` | true |
| `allow_destructive_edge_replacement` | false |
| `perimeter_via_rebuild_default` | false |

Target vertex count accepts 4–64. Safety geometry can produce a different actual count. The default strategy creates no new concavity and retains only safe original reflex vertices. `mode=diagonal` automatically normalizes `allow_diagonal_edges=true`.

`require_explicit_backup` applies only to destructive `.kicad_pcb` Edge.Cuts replacement and is unrelated to installers. Installers never make a copy of the previous plugin.

## `stitching`

Defaults are 5.00 mm perimeter spacing, 1.00 mm edge offset, 1.20 mm vertex offset, 2.50 mm minimum candidate spacing, 0.60/0.30 mm via geometry, 0.25 mm clearance, both-layer GND support, and a maximum of 1000 proposals. Rebuilding the existing perimeter ring is off by default; partial adoption cannot delete the old ring.

## `placement`

Defaults are 8.00 mm group spacing, 1.50 mm component spacing, 45.00 mm block width, schematic-sheet grouping, locked-part preservation, connector perimeter bias, capacitor reference/value inference, and `dry_run_only=true`.

## `manufacturing`

Default `jlcpcb_2l_economy` uses two layers, 1.60 mm, green mask, white silk, 1 oz, leaded HASL, routed separation, a 0.20 mm track/clearance baseline, and a 0.60/0.30 mm automatic-fix via.

Track presets:

`0.1, 0.2, 0.3, 0.4, 0.5, 0.8, 1.0, 1.5, 2.0, 3.0, 5.0 mm`

Via presets:

- `jlcpcb_capability_limit`: 0.25/0.15 mm
- `kicad_default`: 0.60/0.30 mm

`selected_track_widths_mm` and `selected_via_preset_ids` retain multiple catalogue values. The singular fields hold the profile-compatible automatic-repair defaults. `apply_profile_to_silkscreen` remains false so the requested 0.8 mm/0.10 mm silk default is preserved unless JLCPCB readability dimensions are explicitly adopted.

## `ui`

| Field | Default | Purpose |
|---|---:|---|
| `language` | `auto` | Also `ja` or `en` |
| `open_browser` | true | Open dashboard |
| `bind_address` | `127.0.0.1` | Loopback only |
| `inactivity_timeout_minutes` | 0 | Idle shutdown disabled |
| `heartbeat_seconds` | 20 | KiCad connection check |
| `ipc_retry_count` | 2 | Reconnect attempts |
| `report_directory` | empty | Use default location |

Non-loopback bind addresses are rejected. Set a positive inactivity timeout only when automatic shutdown is desired.
