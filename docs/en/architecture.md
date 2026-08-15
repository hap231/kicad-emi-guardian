# Architecture

```text
KiCad 10+ PCB Editor
        │ public IPC API / kicad-python
        ▼
KicadIpcAdapter
  snapshot / selection / layer / ping / reconnect / transactions
        │ KiCad-independent millimetre snapshot
        ▼
Analysis and planning core
  raster + antenna + noise + quantitative
  fixes + silkscreen + edge_optimizer + manufacturing
        │ JSON results, evidence IDs, stage timing
        ▼
GuardianController
  cache, configuration, locking, safety gates, preview payload
        │
        ├── token-protected localhost HTTP API
        ├── blue bilingual HTML/CSS/JavaScript UI
        ├── board/fix/silkscreen SVG previews
        ├── HTML / JSON / Markdown / JLCPCB bundle
        └── external-solver exchange manifest
```

## Compatibility boundary

Only `kicad_adapter.py` imports `kipy`. Canonical KiCad 10 layer names and capability detection are preferred; the legacy SWIG `pcbnew.ActionPlugin` API is not used. Selection or ping failure can recreate the client for a bounded retry count.

## Domain model

KiCad objects are converted into millimetre dataclasses. Tracks retain their source KiCad identifier and arc-approximation metadata. Findings retain evidence identifiers so the dashboard can navigate back to KiCad selection.

## Preview model

The controller returns bounded tracks, vias, pads, footprints, existing silk, zones, edges, and finding positions. The browser overlays fix and silkscreen plans, then performs layer filtering, zoom, and pan client-side.

## Mutation boundary

Only the controller mediates writes. The adapter requires exact-net matching, transactions, Dry-run release, confidence, and explicit confirmation. Outline replacement adds backup and destructive-operation gates.

## Local UI

The server uses loopback, an ephemeral port, a random token, request limits, and CSP. Idle shutdown is configurable but disabled by default in 0.0.2. Browser heartbeat drives KiCad ping and bounded reconnect.
