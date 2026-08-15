# Algorithms and scoring

## Ground-pour antenna detection

1. Select nets matching `ground_net_regex`.
2. Use filled-zone polygons per layer, falling back to outlines only when fill geometry is unavailable.
3. Rasterize at `raster_step_mm`, coarsening only when `max_raster_cells` would be exceeded. A filled polygon that is not one four-neighbor electrical component at that resolution fails closed.
4. Apply a morphological opening whose effective width is `max(narrow_neck_width_mm, required_ground_connection_width_mm)`. This identifies broad GND regions and the copper residual outside a width-`t` interpretation of the plane.
5. Choose one largest broad region as the primary GND core. Every other broad region is a mandatory connectivity group, so the only narrow bridge between two large plane regions cannot be classified as disposable.
6. Exclude every physical pad area plus a conservative pad-launch/thermal capture margin from removal candidates. Treat same-net GND pads, vias, explicit GND tracks, and each existing perimeter-GND component as mandatory terminals.
7. Build a shortest-path tree through occupied copper from the primary core. Protect every secondary core and terminal together with its shortest existing-copper route, dilated to the configured required connection width `t`.
8. Subtract the protected backbone from the narrow residual. For each four-connected remainder, remove it virtually and flood-fill the rest; report it only when every secondary core and mandatory terminal still reaches the primary core and the component overlaps neither pad geometry nor protected perimeter GND.
9. Compute component area, geodesic length, effective width, slenderness, tip, gate, centroid, and isolation state.
10. Independently classify actual ground islands using the combined exact-net zone/track/pad/via connectivity graph. An unanchored component is not also analyzed as a removable appendage.
11. Normalize slenderness, physical length, ground-anchor distance, quarter-wave estimate, and same-layer aggressor distance into severity.

The sampled filled geometry is exhaustively traversed at the effective raster resolution. Automatic appendage removal fails closed when a closed Edge.Cuts loop, broad core, or mandatory-terminal connection cannot be proven. This is not proof that every physical radiator is absent; excitation, current distribution, enclosure, cables, and three-dimensional structures are outside the static geometry model.

## Remediation planning

The planner prefers an exact copper-pour-only keepout reconstructed from a connectivity-proven residual. It does not expand that polygon. Before ranking, it recomputes the protected-backbone model from the current snapshot and requires an exact polygon fingerprint match, so stale findings fail closed after any relevant board edit. A keepout is rejected when it touches any pad, protected width-`t` corridor, explicit same-net GND track, protected perimeter band, or leaves Edge.Cuts. A bridge is considered only when it crosses genuinely uncovered copper, and a via only when it creates a verified new connection to same-net copper on another layer. New copper must remain fully inside Edge.Cuts, including concavities and internal cutouts, and clear other-net tracks, vias, pads, and filled zones. Different net names such as GND and AGND are never joined.

Planning-time validation is not the final write gate. Immediately before applying selected actions, the controller reads the active board again, reruns the complete analysis and fix planner, and compares the target, net, layer, geometry, dimensions, and safety-proof parameters of each selected action with the previewed action. A missing or changed action aborts the whole request without mutation and requires a new preview. This closes the normal dashboard-edit interval; a live KiCad transaction still cannot prevent an external edit in the extremely small interval after the final snapshot and before KiCad accepts the transaction.

When routing presets are multi-selected, automatic repair geometry still uses the active manufacturing profile's default or a compatible selected value.

## Parallel routing

Different-net segments on the same layer are filtered by angle tolerance, line distance, and projected overlap. Spatial keys suppress nearby duplicate findings so one physical coupled region is not repeatedly penalized because of segmentation.

## Sharp trace corner

Endpoints are quantized by `endpoint_snap_mm`, then same-net/same-layer attached segments are collected. Included angle is evaluated only at two-segment junctions. The default threshold is below 75 degrees.

Default exclusions:

- Inside a pad bounding box plus clearance
- On a via
- Three-or-more-segment branch points
- Adjacent segments shorter than `corner_min_segment_length_mm`
- Segments from the same source item
- Internal chord joints used to approximate one arc

Sharpness is normalized as `(threshold - angle) / threshold` and combined with a bounded minimum penalty. Ordinary 90-degree corners are not reported by default.

## Electrically long routed net

Segments are converted into an endpoint graph and split into connected components. Components up to `long_net_diameter_scan_limit` nodes are solved by scanning every graph node. Larger tree-like components scan terminal and junction nodes within the same budget; dense cyclic components use deterministic spatial sampling. Total branch copper remains evidence but is not blindly added to the electrical path. The effective-permittivity estimate is calculated from the widths in each component rather than from a board-wide median.

The electrical threshold is derived from rise time, effective permittivity, and `critical_length_fraction`. Default `both_or_severe` triggers when both geometric and electrical thresholds are exceeded or when the route exceeds the smaller threshold by `long_net_severe_multiplier`. `either` and `both` are also available.

Ground and common power nets are excluded by `long_net_ignore_regex` by default.

## Other qualitative checks

The analyzer checks unanchored endpoints, missing return vias around layer transitions, edge-proximate signals, and differential-pair mismatch. A uniform spatial index accelerates pad/via proximity tests.

## Scoring

Each finding carries a category, severity, confidence, and penalty. Version 0.0.2 replaces an unbounded linear sum with diminishing category impact. Repeated low-priority findings therefore do not pin a category to exactly zero; the score floor is 1.0.

The overall score is a normalized weighted mean of category scores and is not a compliance decision.

## Quantitative estimates

The fast path computes Hammerstad-style microstrip effective permittivity/impedance, a bounded symmetric-stripline approximation, propagation delay, rise-time critical length, quarter-wave resonance, skin depth, and normalized coupling. KiCad stackup data is used when available; missing values use explicit configuration defaults.

## Silkscreen placement

Candidate positions are generated in rings around each footprint. Text bounds are scored against pads, vias, board edges, existing text, and other footprints. The lowest-cost collision-free candidate is selected; otherwise the footprint is unchanged. Existing and proposed silk are exposed as separate preview layers.

## Outline optimization

The default strategy is `convex_preserve_existing_concavities`:

1. Build protection boxes for footprints, pads, vias, tracks, and mounting holes.
2. Compute a convex hull around protected points.
3. Simplify or interpolate toward the target vertex count and snap to the grid.
4. Consider only reflex vertices already present in Edge.Cuts and reinsert those that remain safe.
5. Convert each corner into tangent line and arc primitives.
6. Resample the filleted outline and verify area-reduction and ground-band constraints.

Safety constraints can make the actual vertex count differ from the target. `legacy_concave` remains only for compatibility.

## Performance

The implementation uses raster cell caps, spatial indexing, per-net connected components, bounded previews, and per-stage timing stored in reports.

## Ground connectivity and island classification

Exact-net connectivity is built with Union-Find across per-layer filled zones, finite-width tracks, pads, and vias. Padstacks using `*.Cu`, `*.Copper`, or `All.Cu` are treated as through-hole connections to every copper layer. A via is an interlayer conductor but is not by itself considered an external circuit anchor. Components containing ground pads are anchored, preventing a polygon that is actually connected through tracks or vias from being reported as an island.

## Two-layer return-path screening

On a two-layer board, the generic “missing ground via near a layer transition” rule is disabled by default. Instead, the opposite-side reference copper is sampled only on routes long enough to be meaningful. Endpoint breakout regions are excluded, common ground/power names are ignored, and a reference gap is emitted only when both its absolute length and route fraction exceed their thresholds. Ground-return detour requires both a high path ratio and a minimum absolute excess length; narrow ground-component bottlenecks are evaluated separately. These are static resistance/path proxies, not a direct frequency-domain current solution.

## Rule-area-first antenna remediation

For a ground appendage connected through a narrow neck, the exact residual cell boundary outside the protected GND backbone is reconstructed into a polygon and a copper-pour-only keepout rule area is preferred. The keepout is accepted only when the current-board recomputation produces the same safe residual and independent planner checks pass for pads, explicit GND traces, protected perimeter copper, same-net fill, and Edge.Cuts. A segment entirely contained in existing same-net fill is rejected as redundant. Only a real copper gap can receive a bridge, and the planner selects the widest configured width whose full copper envelope stays on-board and passes known other-net clearance checks.

## Via stitching

Candidates near every outline vertex are generated first, followed by spaced samples along the perimeter. The annulus circumference is sampled to require same-net ground fill on every requested layer, and candidates must pass other-net, pad, existing-via, edge-clearance, and inter-candidate spacing checks. Partial adoption disables deletion of an old perimeter ring so the board is not left with an incomplete replacement.

## Schematic-block initial placement

Schematic sheet path is used as the primary block identifier, with reference-prefix fallback. Locked footprints are preserved, larger core parts are placed first, and connectors are biased toward perimeter positions. Likely capacitors are inferred from reference/value patterns and placed near candidate pads on matching nets. The preview translates the full footprint bounds, pads, reference/value fields, group box, and identity label to the proposed destination and draws a movement vector. The result is a dry-run starting proposal; thermal, isolation, RF, mechanical, and usability constraints remain human-reviewed.
