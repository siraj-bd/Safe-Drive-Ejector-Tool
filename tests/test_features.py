"""
Unit tests for Safe-Drive-Ejector-Tool functional features:
- Drive Controller & SSD Volume Manager
- Sleep Timer Presets (2m, 5m, 10m, 15m, 30m, 1h, 2h, Never)
- Up to 6 Managed Drives limit
- Idle Monitor countdown & auto safe-eject trigger
- Eject Now logic
- Auto Awake
- Bottom status message display
"""

import time
import unittest

from core.config import MAX_MANAGED_DRIVES, SLEEP_TIMER_PRESETS, SafeEjectConfig
from core.idle_monitor import IdleMonitor
from core.models import DriveInfo, EjectResult, RemountResult, VolumeInfo
from core.volume_manager import SSDVolumeManager
from platform_adapters.base import PlatformAdapter


class FeatureMockAdapter(PlatformAdapter):
    def __init__(self, drives=None):
        self.drives = drives or []
        self.ejected = []
        self.mounted = []

    def get_drives(self):
        return self.drives

    def eject_drive(self, drive_id: str):
        self.ejected.append(drive_id)
        return EjectResult(target=drive_id, success=True, message=f"Ejected {drive_id}")

    def unmount_volume(self, volume_id: str):
        self.ejected.append(volume_id)
        return EjectResult(target=volume_id, success=True, message=f"Unmounted {volume_id}")

    def mount_drive(self, drive_id: str):
        self.mounted.append(drive_id)
        return RemountResult(target=drive_id, success=True, message=f"Mounted {drive_id}")

    def mount_volume(self, volume_id: str):
        self.mounted.append(volume_id)
        return RemountResult(target=volume_id, success=True, message=f"Mounted {volume_id}")

    def get_blocking_processes(self, mount_point: str):
        return []

    def kill_process(self, pid: int):
        return True

    def show_notification(self, title: str, message: str):
        pass

    def start_power_listener(self, on_sleep, on_wake):
        pass


class TestFunctionalFeatures(unittest.TestCase):

    def test_sleep_timer_presets(self):
        config = SafeEjectConfig()
        
        # Test all required presets
        presets = ["2m", "5m", "10m", "15m", "30m", "1h", "2h", "never"]
        expected_seconds = [120, 300, 600, 900, 1800, 3600, 7200, 0]

        for p, s in zip(presets, expected_seconds):
            self.assertTrue(config.set_timer_preset(p))
            self.assertEqual(config.sleep_timer_seconds, s)

        # Invalid preset
        self.assertFalse(config.set_timer_preset("invalid_preset"))

    def test_max_6_managed_drives(self):
        config = SafeEjectConfig(managed_drive_uuids=[])

        # Add up to 6 drives
        for i in range(MAX_MANAGED_DRIVES):
            uuid = f"UUID-{i}"
            res = config.toggle_managed_drive(uuid)
            self.assertTrue(res)

        self.assertEqual(len(config.managed_drive_uuids), 6)

        # Adding 7th should be rejected by limit
        res_7th = config.toggle_managed_drive("UUID-7")
        self.assertFalse(res_7th)
        self.assertEqual(len(config.managed_drive_uuids), 6)

        # Toggling an existing one removes it
        res_remove = config.toggle_managed_drive("UUID-0")
        self.assertFalse(res_remove)
        self.assertEqual(len(config.managed_drive_uuids), 5)

    def test_eject_now_logic(self):
        vol = VolumeInfo(device_id="disk7s1", name="Backup", mount_point="/Volumes/Backup", is_mounted=True)
        drive = DriveInfo(id="disk7", name="Samsung T7", is_external=True, volumes=[vol])

        adapter = FeatureMockAdapter(drives=[drive])
        config = SafeEjectConfig(show_notifications=False)
        vol_mgr = SSDVolumeManager(adapter=adapter, config=config)

        results = vol_mgr.eject_now()
        self.assertEqual(len(results), 1)
        self.assertTrue(results[0].success)
        self.assertIn("disk7", adapter.ejected)

    def test_eject_now_with_specific_targets(self):
        vol1 = VolumeInfo(device_id="disk8s1", name="support-external-drive", mount_point="/Volumes/support-external-drive", is_mounted=True)
        vol2 = VolumeInfo(device_id="disk9s1", name="Macbook Backup", mount_point="/Volumes/Macbook Backup", is_mounted=True)
        drive = DriveInfo(id="disk7", name="Transcend SSD", is_external=True, volumes=[vol1, vol2])

        adapter = FeatureMockAdapter(drives=[drive])
        config = SafeEjectConfig(show_notifications=False)
        vol_mgr = SSDVolumeManager(adapter=adapter, config=config)

        # Eject ONLY disk8s1
        results = vol_mgr.eject_now(targets=["disk8s1"])
        self.assertEqual(len(results), 1)
        self.assertTrue(results[0].success)
        self.assertIn("disk8s1", adapter.ejected)
        self.assertNotIn("disk9s1", adapter.ejected)
        self.assertNotIn("disk7", adapter.ejected)

    def test_idle_monitor_timeout_trigger(self):
        timed_out_drives = []

        def on_sleep(drives):
            timed_out_drives.extend(drives)

        def on_wake(drives):
            pass

        config = SafeEjectConfig(sleep_timer_seconds=2)
        monitor = IdleMonitor(config=config, on_idle_sleep=on_sleep, on_touch_wake=on_wake, check_interval_seconds=0.1)

        # Simulate user idle exceeding timeout limit
        monitor.get_mac_user_idle_seconds = lambda: 3.0
        monitor._check_state()

        self.assertTrue(monitor.is_user_currently_idle)

    def test_bottom_status_summary(self):
        config = SafeEjectConfig(sleep_timer_seconds=600, wake_mode="touch")  # 10m
        monitor = IdleMonitor(config=config, on_idle_sleep=lambda d: None, on_touch_wake=lambda d: None)

        vol = VolumeInfo(device_id="disk7s1", name="DriveOne", mount_point="/Volumes/DriveOne", is_mounted=True)
        drive = DriveInfo(id="disk7", name="DriveOne", is_external=True, volumes=[vol])

        summary = monitor.get_status_summary([drive])
        self.assertIn("10 Minutes", summary)
        self.assertIn("Auto-Wake on Touch", summary)

        # Test with sleeping drive
        monitor.mark_drive_asleep("disk7")
        sleeping_summary = monitor.get_status_summary([drive])
        self.assertIn("1 SSD(s) in Sleep", sleeping_summary)

    def test_config_update_settings(self):
        config = SafeEjectConfig()
        config.update_settings({
            "start_at_login": True,
            "show_disks_count_badge": True,
            "success_sound": "Bubble",
            "failure_sound": "Gong",
            "unmount_instead_of_eject": True
        })
        self.assertTrue(config.start_at_login)
        self.assertTrue(config.show_disks_count_badge)
        self.assertEqual(config.success_sound, "Bubble")
        self.assertEqual(config.failure_sound, "Gong")
        self.assertTrue(config.unmount_instead_of_eject)


if __name__ == "__main__":
    unittest.main()
