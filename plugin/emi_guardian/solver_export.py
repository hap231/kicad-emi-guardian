"""External electromagnetic-solver interchange export.

The exporter writes explicit geometry and assumptions without pretending that
a first-order conversion is a validated full-wave model.  A downstream adapter
can convert the manifest to openEMS, Elmer, or another solver and return result
files to the report pipeline.
"""

from __future__ import annotations

import json
from pathlib import Path

from .config import QuantitativeConfig
from .models import BoardSnapshot


def export_solver_manifest(
    snapshot: BoardSnapshot,
    output_directory: Path,
    config: QuantitativeConfig,
) -> dict[str, Path]:
    """Export board geometry and solver assumptions to a portable bundle."""

    output_directory.mkdir(parents=True, exist_ok=True)
    manifest = {
        "schema": "com.openai.emi-guardian.solver-manifest/v1",
        "units": "mm",
        "board": {
            "name": snapshot.board_name,
            "path": snapshot.board_path,
            "kicad_version": snapshot.kicad_version,
        },
        "stackup": {
            "dielectric_constant": snapshot.stackup.dielectric_constant,
            "loss_tangent": snapshot.stackup.loss_tangent,
            "signal_to_reference_height": snapshot.stackup.signal_to_reference_height,
            "copper_thickness": snapshot.stackup.copper_thickness,
        },
        "mesh": {
            "target_cell_mm": config.openems_mesh_mm,
            "maximum_cells": config.openems_max_cells,
        },
        "tracks": [
            {
                "id": track.item_id,
                "start": track.start.to_dict(),
                "end": track.end.to_dict(),
                "width": track.width,
                "layer": track.layer,
                "net": track.net,
            }
            for track in snapshot.tracks
        ],
        "vias": [
            {
                "id": via.item_id,
                "position": via.position.to_dict(),
                "diameter": via.diameter,
                "drill": via.drill,
                "net": via.net,
            }
            for via in snapshot.vias
        ],
        "zones": [
            {
                "id": zone.item_id,
                "net": zone.net,
                "layers": list(zone.layers),
                "outline": zone.outline.to_dict(),
                "filled": {
                    layer: [polygon.to_dict() for polygon in polygons]
                    for layer, polygons in zone.filled.items()
                },
            }
            for zone in snapshot.zones
            if not zone.is_rule_area
        ],
        "edge_cuts": [
            {
                "id": edge.item_id,
                "kind": edge.kind,
                "start": edge.start.to_dict(),
                "mid": edge.mid.to_dict() if edge.mid else None,
                "end": edge.end.to_dict(),
            }
            for edge in snapshot.edges
        ],
        "ports": [],
        "solver": {
            "requested": config.external_solver,
            "executable": config.openems_executable,
            "status": "ports and excitations must be defined before solver execution",
        },
    }
    manifest_path = output_directory / "solver-manifest.json"
    readme_path = output_directory / "README.txt"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    readme_path.write_text(
        "EMI Guardian solver interchange bundle\n"
        "======================================\n\n"
        "This bundle contains PCB geometry and material assumptions. It is not a solved model.\n"
        "Define excitations, ports, boundary conditions, enclosure geometry, and frequency sweep\n"
        "in a validated solver workflow before interpreting electromagnetic results.\n",
        encoding="utf-8",
    )
    return {"manifest": manifest_path, "readme": readme_path}
