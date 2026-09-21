"""
Cross-platform System Tray (Windows) / Menu Bar (macOS) application.
Uses pystray when available, with background daemon thread.
"""

import logging
import os
import sys
import threading
import time
from typing import Optional

from core.config import SafeEjectConfig
from core.engine import SafeEjectEngine

logger = logging.getLogger("SafeEject.Tray")


def create_default_icon_image():
    """Generates an in-memory tray icon (eject symbol on circle) using PIL."""
    from PIL import Image, ImageDraw

    width = 64
    height = 64
    image = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)

    # Draw dark circle background
    draw.ellipse((4, 4, width - 4, height - 4), fill=(30, 30, 30, 240), outline=(200, 200, 200, 255), width=2)

    # Draw eject triangle: pointing up
    # Coordinates: top, bottom-left, bottom-right
    top = (width // 2, 16)
    bl = (18, 36)
    br = (width - 18, 36)
    draw.polygon([top, bl, br], fill=(255, 255, 255, 255))

    # Draw eject horizontal bar below triangle
    draw.rectangle([18, 42, width - 18, 47], fill=(255, 255, 255, 255))

    return image


class SafeEjectTrayApp:
    """Manages the system tray icon and interactive menu."""

    def __init__(self, engine: Optional[SafeEjectEngine] = None):
        self.engine = engine or SafeEjectEngine()
        self.icon = None
        self.daemon_thread = None

    def start(self):
        """Start the system tray and background power listener."""
        try:
            import pystray
            from PIL import Image
        except ImportError:
            print("\n[SafeEject] 'pystray' and 'Pillow' are required for the GUI system tray.")
            print("Install them via:")
            print("    pip install pystray pillow\n")
            print("Or run SafeEject in background daemon mode:")
            print("    python3 main.py daemon\n")
            if sys.platform == "darwin":
                print("For macOS, you can also launch the native Menu Bar app:")
                print("    ./run_menubar_mac.sh\n")
            sys.exit(1)

        logger.info("Initializing System Tray / Menu Bar app...")

        # Start power listener daemon in a background daemon thread
        self.daemon_thread = threading.Thread(target=self.engine.run_daemon, daemon=True)
        self.daemon_thread.start()

        image = create_default_icon_image()
        self.icon = pystray.Icon(
            "SafeEject",
            image,
            "SafeEject: External Disk Protector",
            menu=self._build_menu,
        )

        logger.info("Running System Tray event loop...")
        self.icon.run()

    def _build_menu(self):
        """Dynamically build the tray menu based on current drives and settings."""
        import pystray

        items = []

        # Header / Status
        items.append(pystray.MenuItem("SafeEject (Monitoring: Active)", None, enabled=False))
        items.append(pystray.Menu.SEPARATOR)

        # Quick actions
        items.append(pystray.MenuItem("⏏ Eject All External Disks", self._on_eject_all))
        items.append(pystray.MenuItem("🔄 Remount Disks", self._on_remount_all))
        items.append(pystray.Menu.SEPARATOR)

        # List connected external drives
        ext_drives = self.engine.get_external_drives()
        if ext_drives:
            items.append(pystray.MenuItem("Connected External Drives:", None, enabled=False))
            for drive in ext_drives:
                vols = [v.name for v in drive.volumes if v.is_mounted]
                vol_str = f" ({', '.join(vols)})" if vols else ""
                label = f"   • {drive.name}{vol_str}"

                # Individual eject submenu
                drive_menu = pystray.Menu(
                    pystray.MenuItem(f"Eject '{drive.name}'", self._make_eject_handler(drive.id)),
                    pystray.MenuItem(f"Remount '{drive.name}'", self._make_remount_handler(drive.id)),
                )
                items.append(pystray.MenuItem(label, drive_menu))
        else:
            items.append(pystray.MenuItem("No external drives connected", None, enabled=False))

        items.append(pystray.Menu.SEPARATOR)

        # Settings toggles
        items.append(
            pystray.MenuItem(
                "Eject on Sleep",
                self._toggle_eject_on_sleep,
                checked=lambda item: self.engine.config.eject_on_sleep,
            )
        )
        items.append(
            pystray.MenuItem(
                "Remount on Wake",
                self._toggle_remount_on_wake,
                checked=lambda item: self.engine.config.remount_on_wake,
            )
        )
        items.append(
            pystray.MenuItem(
                "Show Notifications",
                self._toggle_notifications,
                checked=lambda item: self.engine.config.show_notifications,
            )
        )

        items.append(pystray.Menu.SEPARATOR)
        items.append(pystray.MenuItem("Quit SafeEject", self._on_quit))

        return pystray.Menu(*items)

    def _on_eject_all(self, icon, item):
        self.engine.eject_all_external(manual=True)

    def _on_remount_all(self, icon, item):
        self.engine.remount_all_ejected()

    def _make_eject_handler(self, drive_id: str):
        return lambda icon, item: self.engine.eject_single(drive_id)

    def _make_remount_handler(self, drive_id: str):
        return lambda icon, item: self.engine.remount_single(drive_id)

    def _toggle_eject_on_sleep(self, icon, item):
        self.engine.config.eject_on_sleep = not self.engine.config.eject_on_sleep
        self.engine.config.save()

    def _toggle_remount_on_wake(self, icon, item):
        self.engine.config.remount_on_wake = not self.engine.config.remount_on_wake
        self.engine.config.save()

    def _toggle_notifications(self, icon, item):
        self.engine.config.show_notifications = not self.engine.config.show_notifications
        self.engine.config.save()

    def _on_quit(self, icon, item):
        logger.info("Quitting SafeEject Tray...")
        icon.stop()


def run_tray():
    app = SafeEjectTrayApp()
    app.start()
