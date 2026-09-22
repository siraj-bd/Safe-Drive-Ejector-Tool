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

from core.config import MAX_MANAGED_DRIVES, SLEEP_TIMER_PRESETS, SafeEjectConfig, StateManager
from core.engine import SafeEjectEngine
from core.idle_monitor import IdleMonitor
from core.models import DriveInfo, EjectResult, RemountResult, VolumeInfo
from core.volume_manager import SSDVolumeManager
from platform_adapters.base import PlatformAdapter


class FeatureMockAdapter(PlatformAdapter):
    def __init__(self, drives=None):
        self.drives = drives or []
        self.ejected = []
        self.mounted = []
        self.unmounted_volumes = []
        self.mounted_volumes = []

    def get_drives(self):
        return self.drives

    def eject_drive(self, drive_id: str):
        self.ejected.append(drive_id)
        return EjectResult(target=drive_id, success=True, message=f"Ejected {drive_id}")

    def unmount_volume(self, volume_id: str):
        self.ejected.append(volume_id)
        self.unmounted_volumes.append(volume_id)
        return EjectResult(target=volume_id, success=True, message=f"Unmounted {volume_id}")

    def mount_drive(self, drive_id: str):
        self.mounted.append(drive_id)
        return RemountResult(target=drive_id, success=True, message=f"Mounted {drive_id}")

    def mount_volume(self, volume_id: str):
        self.mounted.append(volume_id)
        self.mounted_volumes.append(volume_id)
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

    def test_config_aliases_and_to_dict(self):
        config = SafeEjectConfig()
        # Direct property setter/getter tests
        config.eject_before_sleep = False
        self.assertFalse(config.eject_on_sleep)
        config.eject_on_sleep = True
        self.assertTrue(config.eject_before_sleep)

        config.auto_awake = False
        self.assertFalse(config.remount_on_wake)
        config.remount_on_wake = True
        self.assertTrue(config.auto_awake)

        config.notify_after_eject_remount = False
        self.assertFalse(config.show_notifications)
        config.show_notifications = True
        self.assertTrue(config.notify_after_eject_remount)

        # update_settings with legacy alias keys
        config.update_settings({
            "eject_before_sleep": False,
            "auto_awake": False,
            "notify_after_eject_remount": False,
        })
        self.assertFalse(config.eject_on_sleep)
        self.assertFalse(config.remount_on_wake)
        self.assertFalse(config.show_notifications)

        # to_dict contains both primary and alias keys
        d = config.to_dict()
        self.assertIn("eject_on_sleep", d)
        self.assertIn("eject_before_sleep", d)
        self.assertIn("remount_on_wake", d)
        self.assertIn("auto_awake", d)
        self.assertIn("show_notifications", d)
        self.assertIn("notify_after_eject_remount", d)

    def test_idle_sleep_unmounts_volumes_and_ejects_parent_for_led_off(self):
        adapter = FeatureMockAdapter()
        vol = VolumeInfo(device_id="disk8s1", name="SupportDrive", mount_point="/Volumes/SupportDrive", is_mounted=True)
        drive = DriveInfo(id="disk7", name="Samsung T7", is_external=True, volumes=[vol])
        adapter.drives = [drive]

        config = SafeEjectConfig(
            show_notifications=False,
            unmount_instead_of_eject=True,
            managed_drive_uuids=["disk7"],
            selected_sleep_drive_uuids=["disk7"],
        )
        engine = SafeEjectEngine(config=config, adapter=adapter)

        # Trigger idle sleep
        engine._on_idle_sleep([])

        # Volume must be safely unmounted first, then parent disk7 ejected for LED-OFF deep sleep
        self.assertIn("disk8s1", adapter.unmounted_volumes)
        self.assertIn("disk7", adapter.ejected)
        self.assertIn("disk8s1", engine.idle_monitor.sleeping_drive_ids)

        # State must record the volume identifier
        state = StateManager.load_ejected_drives()
        self.assertIn("disk8s1", state.get("volume_identifiers", []))

        # Touch wake should remount the volume
        engine._on_touch_wake(["disk8s1"])
        self.assertIn("disk8s1", adapter.mounted_volumes)
        self.assertNotIn("disk8s1", engine.idle_monitor.sleeping_drive_ids)

    def test_remount_all_ejected_volume_identifiers(self):
        adapter = FeatureMockAdapter()
        vol = VolumeInfo(device_id="disk9s1", name="WorkBackup", mount_point="/Volumes/WorkBackup", is_mounted=False)
        drive = DriveInfo(id="disk9", name="BackupSSD", is_external=True, volumes=[vol])
        adapter.drives = [drive]

        config = SafeEjectConfig(show_notifications=False)
        engine = SafeEjectEngine(config=config, adapter=adapter)

        # Save only volume identifier in state
        StateManager.save_ejected_drives([], ["disk9s1"], append=False)

        results = engine.remount_all_ejected()
        self.assertEqual(len(results), 1)
        self.assertTrue(results[0].success)
        self.assertIn("disk9s1", adapter.mounted_volumes)

        # State should be cleared
        cleared_state = StateManager.load_ejected_drives()
        self.assertEqual(cleared_state.get("volume_identifiers", []), [])

    def test_open_volume_and_sleep_system(self):
        from unittest.mock import patch
        adapter = FeatureMockAdapter()
        vol = VolumeInfo(device_id="disk8s1", name="SanDisk", mount_point="/Volumes/SanDisk", is_mounted=True)
        drive = DriveInfo(id="disk8", name="SanDisk Ultra", is_external=True, volumes=[vol])
        adapter.drives = [drive]
        engine = SafeEjectEngine(adapter=adapter)

        with patch("subprocess.run") as mock_subproc, patch("os.path.exists", return_value=True):
            # Test open_volume does not raise NameError
            opened = engine.open_volume("SanDisk")
            self.assertTrue(opened)
            mock_subproc.assert_called()

            # Test sleep_system does not raise NameError
            slept = engine.sleep_system()
            self.assertTrue(slept)

    def test_auto_wake_only_recorded_drives(self):
        adapter = FeatureMockAdapter()
        vol1 = VolumeInfo(device_id="disk8s1", name="DriveOne", mount_point="/Volumes/DriveOne", is_mounted=False)
        drive1 = DriveInfo(id="disk8", name="SSDOne", is_external=True, volumes=[vol1])
        vol2 = VolumeInfo(device_id="disk9s1", name="UnrelatedDrive", mount_point="/Volumes/UnrelatedDrive", is_mounted=False)
        drive2 = DriveInfo(id="disk9", name="SSDTwo", is_external=True, volumes=[vol2])
        adapter.drives = [drive1, drive2]

        config = SafeEjectConfig(show_notifications=False)
        engine = SafeEjectEngine(config=config, adapter=adapter)

        # 1. When state is empty, auto-wake (only_if_recorded=True) must NOT remount any drives
        StateManager.clear_ejected_drives()
        res_empty = engine.remount_all_ejected(only_if_recorded=True)
        self.assertEqual(len(res_empty), 0)
        self.assertEqual(len(adapter.mounted_volumes), 0)

        # 2. When only disk8s1 was put to sleep, only disk8s1 must be remounted
        StateManager.save_ejected_drives([], ["disk8s1"], append=False)
        res_recorded = engine.remount_all_ejected(only_if_recorded=True)
        self.assertEqual(len(res_recorded), 1)
        self.assertIn("disk8s1", adapter.mounted_volumes)
        self.assertNotIn("disk9s1", adapter.mounted_volumes)

    def test_legacy_daemon_sleep_uses_safe_unmount(self):
        adapter = FeatureMockAdapter()
        vol = VolumeInfo(device_id="disk8s1", name="DriveOne", mount_point="/Volumes/DriveOne", is_mounted=True)
        drive = DriveInfo(id="disk8", name="SSDOne", is_external=True, volumes=[vol])
        adapter.drives = [drive]

        config = SafeEjectConfig(show_notifications=False, eject_on_sleep=True, remount_on_wake=True)
        engine = SafeEjectEngine(config=config, adapter=adapter)

        captured_callbacks = {}
        def mock_power_listener(on_sleep, on_wake):
            captured_callbacks["sleep"] = on_sleep
            captured_callbacks["wake"] = on_wake

        adapter.start_power_listener = mock_power_listener

        import threading
        t = threading.Thread(target=engine.run_daemon, daemon=True)
        t.start()
        time.sleep(0.05)

        # Trigger sleep callback from power listener
        captured_callbacks["sleep"]()

        # Volume must be safely unmounted first, then physical parent disk ejected for LED-OFF sleep
        self.assertIn("disk8s1", adapter.unmounted_volumes)
        self.assertIn("disk8", adapter.ejected)

        # State must record the sleeping volume
        state = StateManager.load_ejected_drives()
        self.assertIn("disk8s1", state.get("volume_identifiers", []))

        # Stop idle monitor
        engine.idle_monitor.stop()

    def test_deep_sleep_all_mounted_volumes_unmounted_before_parent_eject(self):
        adapter = FeatureMockAdapter()
        vol1 = VolumeInfo(device_id="disk8s1", name="Part1", mount_point="/Volumes/Part1", is_mounted=True)
        vol2 = VolumeInfo(device_id="disk9s1", name="Part2", mount_point="/Volumes/Part2", is_mounted=True)
        drive = DriveInfo(id="disk7", name="Transcend", is_external=True, volumes=[vol1, vol2])
        adapter.drives = [drive]

        config = SafeEjectConfig(show_notifications=False)
        volume_mgr = SSDVolumeManager(config=config, adapter=adapter)

        res = volume_mgr.deep_sleep_drive("disk7")
        self.assertTrue(res.success)
        # Verify both volumes were safely unmounted before parent disk7 was ejected
        self.assertIn("disk8s1", adapter.unmounted_volumes)
        self.assertIn("disk9s1", adapter.unmounted_volumes)
        self.assertIn("disk7", adapter.ejected)

        # State must record both unmounted volume partitions for Auto-Wake
        state = StateManager.load_ejected_drives()
        self.assertIn("disk8s1", state.get("volume_identifiers", []))
        self.assertIn("disk9s1", state.get("volume_identifiers", []))

    def test_deep_sleep_aborted_when_unmount_fails(self):
        adapter = FeatureMockAdapter()
        vol1 = VolumeInfo(device_id="disk8s1", name="Part1", mount_point="/Volumes/Part1", is_mounted=True)
        drive = DriveInfo(id="disk7", name="Transcend", is_external=True, volumes=[vol1])
        adapter.drives = [drive]

        # Simulate unmount failure (e.g. file in use)
        def fail_unmount(vid):
            return EjectResult(target=vid, success=False, message="Resource busy")
        adapter.unmount_volume = fail_unmount

        config = SafeEjectConfig(show_notifications=False)
        volume_mgr = SSDVolumeManager(config=config, adapter=adapter)

        res = volume_mgr.deep_sleep_drive("disk7")
        self.assertFalse(res.success)
        self.assertIn("Resource busy", res.message)
        # Parent disk7 MUST NOT be ejected when unmount fails
        self.assertNotIn("disk7", adapter.ejected)

    def test_deep_sleep_selective_wake_drive1_and_drive2(self):
        adapter = FeatureMockAdapter()
        vol1 = VolumeInfo(device_id="disk8s1", name="Part1", mount_point="/Volumes/Part1", is_mounted=False)
        vol2 = VolumeInfo(device_id="disk9s1", name="Part2", mount_point="/Volumes/Part2", is_mounted=False)
        drive = DriveInfo(id="disk7", name="Transcend", is_external=True, volumes=[vol1, vol2])
        adapter.drives = [drive]

        config = SafeEjectConfig(show_notifications=False)
        engine = SafeEjectEngine(config=config, adapter=adapter)

        # 1. Wake Drive 1 (disk8s1) only
        res1 = engine.remount_single("disk8s1")
        self.assertTrue(res1.success)
        self.assertIn("disk8s1", adapter.mounted_volumes)
        self.assertNotIn("disk9s1", adapter.mounted_volumes)

        # 2. Wake Drive 2 (disk9s1) only
        adapter.mounted_volumes = []
        res2 = engine.remount_single("disk9s1")
        self.assertTrue(res2.success)
        self.assertIn("disk9s1", adapter.mounted_volumes)
        self.assertNotIn("disk8s1", adapter.mounted_volumes)

    def test_eject_now_clears_auto_wake_state(self):
        adapter = FeatureMockAdapter()
        vol1 = VolumeInfo(device_id="disk8s1", name="Part1", mount_point="/Volumes/Part1", is_mounted=True)
        drive = DriveInfo(id="disk7", name="Transcend", is_external=True, volumes=[vol1], is_managed=True)
        adapter.drives = [drive]

        config = SafeEjectConfig(show_notifications=False)
        engine = SafeEjectEngine(config=config, adapter=adapter)

        # Populate sleep state
        StateManager.save_ejected_drives([], ["disk8s1"], append=False)
        self.assertTrue(len(StateManager.load_ejected_drives().get("volume_identifiers", [])) > 0)

        # Execute Eject Now (explicit physical removal workflow)
        res = engine.eject_now()
        self.assertTrue(any(r.success for r in res))
        self.assertIn("disk7", adapter.ejected)

        # Auto-Wake state must be completely cleared so unplugged drive is not woken
        state = StateManager.load_ejected_drives()
        self.assertEqual(len(state.get("volume_identifiers", [])), 0)
        self.assertEqual(len(state.get("drive_ids", [])), 0)

    def test_parent_and_child_hierarchy_control(self):
        adapter = FeatureMockAdapter()
        vol1 = VolumeInfo(device_id="disk8s1", name="support-external-drive", mount_point="/Volumes/support-external-drive", is_mounted=True)
        vol2 = VolumeInfo(device_id="disk9s1", name="Macbook Backup", mount_point="/Volumes/Macbook Backup", is_mounted=True)
        drive = DriveInfo(id="disk7", name="StoreJet Transcend Media", is_external=True, volumes=[vol1, vol2])
        adapter.drives = [drive]

        config = SafeEjectConfig(show_notifications=False)
        volume_mgr = SSDVolumeManager(config=config, adapter=adapter)

        # 1. Unmounting child disk8s1 unmounts ONLY disk8s1 while disk9s1 is still mounted
        res_child = volume_mgr.unmount_target("disk8s1")
        self.assertTrue(res_child.success)
        self.assertIn("disk8s1", adapter.unmounted_volumes)
        # Parent disk7 MUST NOT be ejected yet because disk9s1 is still mounted
        self.assertNotIn("disk7", adapter.ejected)

        # 2. Mounting child disk8s1 mounts only disk8s1
        res_mount_child = volume_mgr.mount_target("disk8s1")
        self.assertTrue(res_mount_child.success)
        self.assertIn("disk8s1", adapter.mounted_volumes)

        # 3. Unmounting parent disk7 triggers Deep Sleep: unmounts all children and ejects parent disk7
        res_parent = volume_mgr.unmount_target("disk7")
        self.assertTrue(res_parent.success)
        self.assertIn("disk7", adapter.ejected)

        # 4. Mounting parent disk7 mounts the whole physical drive
        res_mount_parent = volume_mgr.mount_target("disk7")
        self.assertTrue(res_mount_parent.success)
        self.assertIn("disk7", adapter.mounted)


if __name__ == "__main__":
    unittest.main()

