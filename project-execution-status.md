# Project Execution Status: External SSD LED-OFF Deep Sleep & Hierarchy System

**Date**: September 22, 2026  
**Status**: COMPLETE & FULLY VERIFIED (23/23 Unit Tests PASS &bull; Native Swift Build Exit Code 0 &bull; Live Hardware Verified)  
**Target Hardware Tested**: Transcend StoreJet 480 GB SSD (Bridge: ASMedia ASM1153E, Parent Device: `/dev/disk7`, Partitions: `disk8s1` [`support-external-drive`], `disk9s1` [`Macbook Backup`])

---

## 1. Executive Summary

We have successfully engineered, integrated, and verified the **Dynamic Disk Utility Hierarchy Detection** and **LED-OFF Deep Sleep Mode** for external SSDs without breaking any existing Safe Eject or Eject Now workflows.

### Verified Hardware Behavior & Hierarchy Detection
1. **Dynamic Disk Utility Hierarchy Order**:
   - The UI groups and enumerates drives strictly in Disk Utility serial order:
     - **Disk 1** &rarr; `disk7` (Parent Physical Device)
     - **Disk 2** &rarr; `disk8s1` (Child Partition 1)
     - **Disk 3** &rarr; `disk9s1` (Child Partition 2)
     - Additional devices dynamically extend from Disk 4 through Disk 13 across pages.
   - UI row display uses exact macOS device identifiers (`disk7`, `disk8s1`, `disk9s1`).
2. **Synchronized Parent-Child Checkbox Control**:
   - Toggling the parent checkbox (`disk7`) automatically selects/deselects all its child partitions (`disk8s1`, `disk9s1`).
   - Toggling a child checkbox (`disk8s1`) checks if all siblings are selected and updates the parent state accordingly.
3. **Selective Partition & Full Deep Sleep Controls**:
   - Unmounting parent `disk7` safely flushes, cleanly unmounts all children, and ejects parent `disk7` &rarr; LED turns completely OFF.
   - Unmounting child `disk8s1` unmounts *only* `disk8s1`, leaving `disk9s1` and `disk7` active and mounted.
   - Mounting `disk8s1` wakes the drive (LED ON) and mounts only `disk8s1`.
   - Multi-selection allows mass Wake/Mount across any checked drives.
4. **Buffer Flush (`sync`)**: Filesystem writes are flushed to ensure no pending dirty pages.
5. **Safe Volume Unmount**: All mounted volumes belonging to the target physical parent drive (e.g. `disk8s1` and `disk9s1`) are cleanly unmounted via `diskutil unmount`.
6. **Safety Gate**: If ANY volume fails to unmount (e.g. file in use, locked resource), physical eject is **ABORTED**, preventing data corruption, and the error is reported.
7. **Physical Parent Disk Eject (`diskutil eject disk7`)**: Only after all volumes are confirmed unmounted is the parent physical disk ejected. This causes the USB bridge controller (ASM1153E) to place the SSD into ultra-low-power standby, **turning the hardware LED light completely OFF**.
8. **Physical Connection Maintained**: The USB cable remains plugged in; device identifiers remain registered in macOS kernel.
9. **Selective Auto-Wake / Manual Remount**: 
   - Mounting an individual partition (e.g. `diskutil mount disk8s1`) wakes the hardware bridge, turns the LED ON, and mounts *only* `disk8s1`, keeping `disk9s1` safely unmounted.
   - Mounting `disk9s1` mounts only `disk9s1`.
   - Global auto-wake (`remount-all --only-recorded`) safely wakes and mounts all recorded sleeping partitions.
10. **Strict Separation of Eject Now**: Explicit `Eject Now` is reserved for physical disconnection, cleanly clearing `ejected_state.json` so no automatic remount occurs.

---

## 2. Test Verification Matrix

| Test Suite / Case | Description | Result |
| :--- | :--- | :--- |
| `test_parent_and_child_hierarchy_control` | Verifies parent-child hierarchy, target unmount, and parent deep sleep | **PASS** |
| `test_deep_sleep_all_mounted_volumes_unmounted_before_parent_eject` | Verifies clean volume unmount before parent eject | **PASS** |
| `test_deep_sleep_aborted_when_unmount_fails` | Verifies parent eject is aborted if unmount fails | **PASS** |
| `test_deep_sleep_selective_wake_drive1_and_drive2` | Verifies mounting one partition wakes drive without mounting other partitions | **PASS** |
| `test_eject_now_clears_auto_wake_state` | Verifies explicit eject clears state and isolates from wake | **PASS** |
| `test_idle_sleep_unmounts_volumes_and_ejects_parent_for_led_off` | Verifies idle sleep triggers deep sleep sequence | **PASS** |
| `test_legacy_daemon_sleep_uses_safe_unmount` | Verifies daemon sleep hooks follow deep sleep sequence | **PASS** |
| `test_auto_wake_only_recorded_drives` | Verifies auto-wake only targets recorded sleeping drives | **PASS** |
| `test_max_6_managed_drives` | Enforces 6 drive management cap | **PASS** |
| `test_sleep_timer_presets` | Verifies timer presets (2m, 5m, 10m, 15m, 30m, 1h, 2h, never) | **PASS** |
| `test_bottom_status_summary` | Verifies status bar string formatting | **PASS** |
| `test_open_volume_and_sleep_system` | Verifies volume opening and sleep actions | **PASS** |
| **All Other Core & Feature Tests (11 cases)** | Drive models, size formatting, exclusions, UI states | **PASS** |
| **Total Test Count** | **23 Passed, 0 Failed, 0 Skipped** | **100% PASS** |

---

## 3. Build & Runtime Verification

### Native Swift Menu Bar App Compilation
```bash
$ swiftc -module-cache-path .build/cache -O ui/SafeEjectMenuBar.swift -o bin/SafeEjectMenuBar
Exit Code: 0 (Zero warnings, zero errors)
```

### Live Hardware Testing Log (Transcend StoreJet 480GB)
1. **Initial Mount**:
   `disk8s1` (`support-external-drive`) and `disk9s1` (`Macbook Backup`) both mounted and recognized.
2. **Deep Sleep Execution (`python3 main.py idle-sleep`)**:
   - `Attempting to unmount volume: disk8s1` &rarr; Success
   - `Attempting to unmount volume: disk9s1` &rarr; Success
   - `Attempting to eject drive: disk7` &rarr; Success
   - **Hardware Result**: SSD LED turned completely OFF. Cable remained plugged in.
   - `ejected_state.json` recorded: `["disk8s1", "disk9s1"]`.
3. **Selective Wake Execution (`python3 main.py remount disk8s1`)**:
   - Hardware LED turned ON.
   - `disk8s1` mounted on `/Volumes/support-external-drive`.
   - `disk9s1` remained unmounted.
   - `ejected_state.json` updated to: `["disk9s1"]`.
4. **Selective Wake Execution (`python3 main.py remount disk9s1`)**:
   - `disk9s1` mounted on `/Volumes/Macbook Backup`.
   - Both volumes mounted cleanly.
   - `ejected_state.json` cleared.

---

- `core/config.py`: Added `StateManager.remove_ejected_target` for selective wake tracking.
- `core/volume_manager.py`:
  - Implemented `deep_sleep_drive(drive_id)` with `sync`, clean unmount of all volumes, abort gate, and parent eject.
  - Enhanced `mount_target(target_id)` to handle volume partition selective wake and whole parent disk mount.
  - Enhanced `unmount_target(target_id)` to trigger deep sleep when targeting physical parent disk (`disk7`) or cleanly unmount individual child volume (`disk8s1`).
- `core/engine.py`:
  - Integrated `deep_sleep_drive` into `_on_idle_sleep`.
  - Updated `eject_now` to clear `StateManager`.
  - Updated `remount_all_ejected` to remount recorded volumes for selective wake.
- `platform_adapters/macos.py`:
  - Added hardware info caching (`_info_cache`) to prevent excessive USB inquiry polling that previously caused drive LEDs to pulse while UI was open.
- `ui/components/SafeDriveEjectorCard.html`:
  - Implemented dynamic Disk Utility hierarchy sorting and serial numbering (Disk 1: `disk7`, Disk 2: `disk8s1`, Disk 3: `disk9s1`...).
  - Rendered clean system device identifiers directly on rows.
  - Added synchronized parent-child checkbox selection logic.
  - Updated status labels to `"Deep Sleep (LED OFF Mode)"` and `"LED OFF Sleep"`.
- `ui/SafeEjectMenuBar.swift`:
  - Added message handler for `driveSelection` routing to `select-sleep`.
- `tests/test_features.py`:
  - Added full test coverage for LED-off deep sleep, abort-on-failure, selective wake, state cleanup, and parent/child hierarchy controls (`test_parent_and_child_hierarchy_control`).
