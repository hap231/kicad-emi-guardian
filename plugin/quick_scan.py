#!/usr/bin/env python3
"""KiCad action entry point for a read-only EMI scan and report export."""

from __future__ import annotations

import logging
import sys
import webbrowser
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parent
if str(PLUGIN_ROOT) not in sys.path:
    sys.path.insert(0, str(PLUGIN_ROOT))

from emi_guardian.controller import GuardianController  # noqa: E402
from emi_guardian.kicad_adapter import KicadIpcAdapter  # noqa: E402


def main() -> int:
    """Run a read-only scan, export the report, and open its HTML file."""

    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    adapter = KicadIpcAdapter(timeout_ms=10_000)
    controller = GuardianController(adapter)
    try:
        controller.analyze(refresh=True)
        paths = controller.export_report()
        html_path = Path(paths["html"]).resolve()
        webbrowser.open(html_path.as_uri(), new=1, autoraise=True)
        print(f"EMI Guardian report: {html_path}")
    finally:
        controller.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
