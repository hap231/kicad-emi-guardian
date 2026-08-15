# Safety, verification, and limitations

## Safety gates

- Dry-run blocks every board write by default.
- Application requires explicit UI confirmation and minimum confidence.
- Existing nets are resolved by exact name; substitute nets are not created.
- Copper and silkscreen mutations require KiCad transactions and one undo unit where supported.
- A rule area is created only when copper-pour-only keepout flags can be set safely.
- Edge.Cuts replacement requires ground-band evidence, a saved board, backup, required API capabilities, destructive-operation permission, and exact board-name confirmation.
- Economy manufacturing remains profile-safe even when fine process-limit presets are included in a multi-selection.
- The local UI binds only to loopback and uses a random token, CSP, request-size limits, and path-traversal protection.

## KiCad navigation safety

Show location in KiCad changes selection and attempts layer activation and zoom, but it does not create or update board items. It is not a custom DRC marker. If an action identifier is unavailable, zoom is skipped and the operation fails closed.

## Connection behavior

Idle shutdown defaults to zero and is disabled. A 20-second heartbeat and two reconnect attempts are used. KiCad exit, board close, OS sleep, or blocked localhost traffic can still interrupt the session. Failed reconnect never authorizes a write.

## Required post-change checks

Refill zones; run KiCad DRC; verify via geometry and spacing; inspect reference-plane continuity; review connectors, intended antennas, RF keepouts, creepage, mounting, enclosure, panelization, and fixtures; inspect Gerbers, polarity and pin-1 silk, mask, and outline; and use measurement or a validated solver for EMC-critical products.

## Principal limitations

- “All antenna candidates” means all sampled filled-zone geometry at the configured raster resolution, not proof of no physical radiator.
- Static geometry cannot determine current, phase, excitation, termination, cable/enclosure resonance, common-mode conversion, or regulatory limits.
- Zone-outline fallback can overestimate copper; refill zones before analysis.
- Arcs are decomposed into analysis chords, although same-arc internal joints are excluded from corner findings.
- Pad geometry uses conservative bounding boxes for proximity and collision checks.
- Long-route analysis estimates an endpoint path and does not infer the true driver and receiver.
- Previews are simplified SVG, not 3D EM or manufacturing results; large boards use display caps.
- Solver exchange is an unsolved model without automatic ports, excitation, boundaries, or convergence.
- Outline optimization cannot understand enclosure, panel, fixture, or intentional antenna constraints.
- JLCPCB capabilities and price rules can change.
- Automated tests do not include a live KiCad GUI, physical EMC, or manufacturer acceptance; execute the [live acceptance test](acceptance-test.md).
