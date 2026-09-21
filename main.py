#!/usr/bin/env python3
"""
Safe Drive Ejector Tool - Cross-Platform External Disk Safe Ejector & Auto-Remounter
Built for macOS and Windows.
"""

import json
import sys
from pathlib import Path

# Ensure project root is in sys.path
BASE_DIR = Path(__file__).resolve().parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from core.config import SafeEjectConfig, StateManager
from core.engine import SafeEjectEngine


def handle_json_status():
    """Output machine-readable JSON status of connected drives and configuration."""
    engine = SafeEjectEngine()
    ext_drives = engine.get_external_drives()
    managed_drives = engine.get_managed_drives()
    state = StateManager.load_ejected_drives()

    data = {
        "platform": sys.platform,
        "config": engine.config.__dict__,
        "sleep_timer_label": engine.config.sleep_timer_label,
        "bottom_status": engine.get_bottom_status(),
        "ejected_state": state,
        "external_drives": [d.to_dict() for d in ext_drives],
        "managed_drives": [d.to_dict() for d in managed_drives],
    }
    print(json.dumps(data, indent=2))


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "tray":
        from ui.tray import run_tray
        run_tray()
    elif len(sys.argv) > 1 and sys.argv[1] == "json-status":
        handle_json_status()
    else:
        # Default to CLI
        from ui.cli import main as cli_main
        cli_main()


if __name__ == "__main__":
    main()
