"""
SafeEject Engine.
Orchestrates:
- Individual SSD selection for sleep
- Mac user inactivity detection (2m default)
- Auto-Active on Mac touch vs. Manual Stay Asleep modes
- Sleep Timer Presets (2m, 5m, 10m, 15m, 30m, 1h, 2h, Never)
- Audio feedback (Pop, Basso, Bubble, etc.)
- System sleep/wake and state persistence.
"""

import logging
import time
from typing import List, Optional, Tuple

from core.config import SafeEjectConfig, StateManager
from core.idle_monitor import IdleMonitor
from core.models import DriveInfo, EjectResult, RemountResult, VolumeInfo
from core.volume_manager import SSDVolumeManager
from platform_adapters import get_platform_adapter
from platform_adapters.base import PlatformAdapter

logger = logging.getLogger("SafeEject.Engine")


class SafeEjectEngine:
    """Core controller coordinating volume management, idle monitoring, and power events."""

    def __init__(self, config: SafeEjectConfig = None, adapter: PlatformAdapter = None):
        self.config = config or SafeEjectConfig.load()
        self.adapter = adapter or get_platform_adapter()

        self.volume_manager = SSDVolumeManager(self.adapter, self.config)
        self.idle_monitor = IdleMonitor(
            self.config,
            on_idle_sleep=self._on_idle_sleep,
            on_touch_wake=self._on_touch_wake,
        )

        self.status_message: str = "Ready"

    def get_external_drives(self) -> List[DriveInfo]:
        """Returns physical external drives annotated with managed state, sleep selection, and idle seconds."""
        drives = self.volume_manager.get_all_external_drives()
        for d in drives:
            d.idle_seconds = self.idle_monitor.last_user_idle_seconds
        return drives

    def get_managed_drives(self) -> List[DriveInfo]:
        """Returns up to 6 managed external drives."""
        return [d for d in self.get_external_drives() if d.is_managed]

    def get_sleep_selected_drives(self) -> List[DriveInfo]:
        """Returns only the drives individually selected to sleep."""
        return [d for d in self.get_external_drives() if d.is_sleep_selected]

    def get_bottom_status(self) -> str:
        """Returns real-time status message formatted for the bottom area."""
        managed = self.get_managed_drives()
        return self.idle_monitor.get_status_summary(managed)

    def eject_now(self, targets: Optional[List[str]] = None) -> List[EjectResult]:
        """Immediate 1-click safe ejection of managed drives or selected targets."""
        results = self.volume_manager.eject_now(targets=targets)
        success = any(r.success for r in results)
        if success:
            self.volume_manager.play_sound(self.config.success_sound)
        else:
            self.volume_manager.play_sound(self.config.failure_sound)
        self.status_message = f"Ejected {len(results)} drive(s)"
        return results

    def eject_all_external(self, manual: bool = False) -> List[EjectResult]:
        """Eject all managed external drives."""
        return self.eject_now()

    def remount_all_ejected(self) -> List[RemountResult]:
        """Remount drives that were previously safely ejected by SafeEject."""
        state = StateManager.load_ejected_drives()
        drive_ids = state.get("drive_ids", [])
        results: List[RemountResult] = []

        if not drive_ids:
            logger.info("No recorded ejected drives in state. Mounting managed drives...")
            managed = self.get_managed_drives()
            for d in managed:
                res = self.adapter.mount_drive(d.id)
                results.append(res)
                self.idle_monitor.mark_drive_awake(d.id)
            self.status_message = f"Remounted {len(results)} drive(s)"
            if results and any(r.success for r in results):
                self.volume_manager.play_sound(self.config.success_sound)
            return results

        logger.info(f"Remounting {len(drive_ids)} previously ejected drives...")
        success_count = 0

        for drive_id in drive_ids:
            res = self.adapter.mount_drive(drive_id)
            results.append(res)
            if res.success:
                success_count += 1
                self.idle_monitor.mark_drive_awake(drive_id)
            else:
                logger.warning(f"Could not remount {drive_id}: {res.message}")

        StateManager.clear_ejected_drives()

        if success_count > 0:
            self.volume_manager.play_sound(self.config.success_sound)
            if self.config.show_notifications:
                self.adapter.show_notification(
                    "SafeEject",
                    f"{success_count} external drive(s) remounted successfully.",
                )
        else:
            self.volume_manager.play_sound(self.config.failure_sound)

        self.status_message = f"Remounted {success_count} drive(s)"
        return results

    def eject_single(self, target: str) -> EjectResult:
        """Manual unmount/eject of a single drive or volume."""
        res = self.volume_manager.unmount_target(target)
        if res.success:
            self.idle_monitor.mark_drive_asleep(target)
            self.volume_manager.play_sound(self.config.success_sound)
        else:
            self.volume_manager.play_sound(self.config.failure_sound)
        return res

    def remount_single(self, target: str) -> RemountResult:
        """Manual mount of a single drive or volume."""
        res = self.volume_manager.mount_target(target)
        if res.success:
            self.idle_monitor.mark_drive_awake(target)
            self.volume_manager.play_sound(self.config.success_sound)
        else:
            self.volume_manager.play_sound(self.config.failure_sound)
        return res

    def sleep_system(self) -> bool:
        """Puts the host computer to sleep."""
        logger.info("Triggering system sleep...")
        try:
            if sys.platform == "darwin":
                subprocess.run(["osascript", "-e", 'tell application "System Events" to sleep'], check=False)
                return True
            elif sys.platform == "win32":
                subprocess.run(["rundll32.exe", "powrprof.dll,SetSuspendState", "0,1,0"], check=False)
                return True
        except Exception as e:
            logger.error(f"Failed to sleep system: {e}")
        return False

    def eject_and_sleep(self) -> bool:
        """Ejects all selected external SSDs and immediately sleeps the system."""
        self.eject_now()
        time.sleep(1.0)
        return self.sleep_system()

    def open_volume(self, target: str) -> bool:
        """Opens a mounted volume in Finder or Explorer."""
        mount_point = ""
        drives = self.get_external_drives()
        for d in drives:
            for v in d.volumes:
                if (
                    v.name.lower() == target.lower()
                    or v.device_id.lower() == target.lower()
                    or (v.mount_point and v.mount_point.lower() == target.lower())
                ):
                    if v.is_mounted and v.mount_point:
                        mount_point = v.mount_point
                        break
            if mount_point:
                break

        if not mount_point and os.path.exists(target):
            mount_point = target

        if mount_point and os.path.exists(mount_point):
            if sys.platform == "darwin":
                subprocess.run(["open", mount_point])
            elif sys.platform == "win32":
                subprocess.run(["explorer.exe", mount_point])
            return True
        return False

    def mount_and_open(self, target: str) -> bool:
        """Mounts an unmounted volume and opens it in Finder/Explorer."""
        res = self.remount_single(target)
        time.sleep(0.8)
        return self.open_volume(target)

    def mount_and_open_all(self) -> int:
        """Mounts all external drives and opens each mounted volume in Finder/Explorer."""
        self.remount_all_ejected()
        time.sleep(1.0)
        opened = 0
        drives = self.get_external_drives()
        for d in drives:
            for v in d.volumes:
                if v.is_mounted and v.mount_point:
                    if sys.platform == "darwin":
                        subprocess.run(["open", v.mount_point])
                    elif sys.platform == "win32":
                        subprocess.run(["explorer.exe", v.mount_point])
                    opened += 1
        return opened

    def set_timer_preset(self, preset_key: str) -> bool:
        """Sets sleep timer preset (2m, 5m, 10m, 15m, 30m, 1h, 2h, never)."""
        ok = self.config.set_timer_preset(preset_key)
        if ok:
            self.status_message = f"Timer set to {self.config.sleep_timer_label}"
        return ok

    def set_wake_mode(self, mode: str) -> bool:
        """Sets wake mode: 'touch' (auto-active on Mac touch) or 'manual' (stay asleep until manual mount)."""
        clean_mode = mode.lower().strip()
        if clean_mode in ("touch", "manual"):
            self.config.wake_mode = clean_mode
            self.config.save()
            self.status_message = f"Wake mode: {'Auto-Active on Touch' if clean_mode == 'touch' else 'Stay Asleep until Manual Mount'}"
            return True
        return False

    def toggle_sleep_selection(self, target: str) -> Tuple[bool, str]:
        """Toggle individual SSD selection for auto-sleep."""
        drives = self.get_external_drives()
        target_uuid = target
        for d in drives:
            if d.id.lower() == target.lower():
                target_uuid = d.primary_uuid
                break
            for v in d.volumes:
                if v.device_id.lower() == target.lower() or v.name.lower() == target.lower():
                    target_uuid = v.uuid or v.device_id
                    break

        is_sel = self.config.toggle_sleep_drive_selection(target_uuid)
        msg = f"Drive '{target}' auto-sleep: {'Enabled' if is_sel else 'Disabled'}."
        return is_sel, msg

    def toggle_manage_drive(self, target: str) -> Tuple[bool, str]:
        """Toggle managed state for a drive (up to 6 max)."""
        return self.volume_manager.toggle_managed(target)

    def _on_idle_sleep(self, _targets: List[str]):
        """Triggered when Mac is idle beyond the sleep timer (default 2 mins)."""
        # Only put the individually chosen SSDs to sleep!
        sleep_targets = self.get_sleep_selected_drives()
        if not sleep_targets:
            return

        logger.info(f"Mac idle threshold reached. Putting {len(sleep_targets)} selected SSD(s) to sleep...")
        ejected_count = 0
        for d in sleep_targets:
            if d.has_mounted_volumes:
                res = self.adapter.eject_drive(d.id)
                if res.success:
                    ejected_count += 1
                    self.idle_monitor.mark_drive_asleep(d.id)

        if ejected_count > 0:
            self.volume_manager.play_sound(self.config.success_sound)
            if self.config.show_notifications:
                self.adapter.show_notification(
                    "SafeEject - SSD Sleep",
                    f"{ejected_count} SSD(s) safely put to sleep after {self.config.sleep_timer_label} of Mac inactivity.",
                )

    def _on_touch_wake(self, sleeping_ids: List[str]):
        """Triggered when user touches the Mac and wake_mode == 'touch'."""
        if self.config.wake_mode != "touch":
            logger.debug("Mac touched, but wake_mode is manual. Keeping SSDs asleep.")
            return

        logger.info(f"User touched Mac. Auto-activating {len(sleeping_ids)} sleeping SSD(s)...")
        wake_count = 0
        for drive_id in sleeping_ids:
            res = self.adapter.mount_drive(drive_id)
            if res.success:
                wake_count += 1
                self.idle_monitor.mark_drive_awake(drive_id)

        if wake_count > 0:
            self.volume_manager.play_sound(self.config.success_sound)
            if self.config.show_notifications:
                self.adapter.show_notification(
                    "SafeEject - Auto-Active",
                    f"Mac active! {wake_count} SSD(s) remounted automatically.",
                )

    def run_daemon(self) -> None:
        """Run the sleep/wake watcher daemon and idle monitor."""
        logger.info("Starting SafeEject power listener and idle monitor...")

        self.idle_monitor.start()

        def on_sleep():
            logger.info("Power event: PRE-SLEEP triggered.")
            if self.config.eject_on_sleep:
                self.eject_all_external(manual=False)

        def on_wake():
            logger.info("Power event: WAKE triggered (Auto Awake).")
            if self.config.auto_awake and self.config.remount_on_wake:
                time.sleep(1.5)
                self.remount_all_ejected()

        try:
            self.adapter.start_power_listener(on_sleep, on_wake)
        finally:
            self.idle_monitor.stop()
