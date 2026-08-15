#!/usr/bin/env python3
"""KiCad action entry point for the EMI Guardian dashboard."""

from __future__ import annotations

import logging
import sys
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parent
if str(PLUGIN_ROOT) not in sys.path:
    sys.path.insert(0, str(PLUGIN_ROOT))

from emi_guardian.controller import GuardianController  # noqa: E402
from emi_guardian.kicad_adapter import KicadIpcAdapter  # noqa: E402
from emi_guardian.server import DashboardServer  # noqa: E402


def main() -> int:
    """Connect to KiCad and run the local dashboard."""

    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    adapter = KicadIpcAdapter(timeout_ms=10_000)
    controller = GuardianController(adapter)
    DashboardServer(controller).run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
