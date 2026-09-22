# Project Execution Status: External SSD LED-OFF Deep Sleep, Hierarchy & OS Hover Details

**Date**: September 23, 2026  
**Status**: COMPLETE & FULLY VERIFIED (29/29 Unit Tests PASS &bull; Native Swift Build Exit Code 0 &bull; Live Hardware Verified)  
**Target Hardware Tested**: Transcend StoreJet 480 GB SSD (Bridge: ASMedia ASM1153E, Parent Device: `/dev/disk7`, Partitions: `disk8s1` [`support-external-drive`], `disk9s1` [`Macbook Backup`])

---

## 1. Executive Summary

We have successfully engineered, integrated, and verified the **Final Deep Sleep (SSD LED-OFF) Architecture with Parent Precedence & Partition Isolation**:
1. **Physical Parent Target (`disk7`)**: When the physical parent disk is selected, it is the Deep Sleep target. Triggering unmount or timer executes the complete Deep Sleep workflow:
   $$\text{flush (sync)} \longrightarrow \text{child partitions clean unmount} \longrightarrow \text{APFS container teardown} \longrightarrow \text{parent disk eject} \longrightarrow \mathbf{SSD\ LED\ OFF}$$
2. **Strict Gatekeeping (No Force Eject Fallback)**: If any child volume or APFS container unmount fails, Deep Sleep is aborted immediately with a clear error report. Automatic force-eject is strictly avoided.
3. **Partition-Level Unmount Isolation**: When only child partitions (`disk8s1`, `disk9s1`) are unmounted, parent disk is never ejected and the SSD LED stays ON.
4. **Parent Precedence Rule**: When both parent disk and child partitions are selected, Deep Sleep executes once for the parent disk, subsuming child partitions without duplicate sequential operations.
5. **No Skipping in Idle Sleep**: Physical parent disk is never skipped in `_on_idle_sleep` even if child volumes were already unmounted earlier.
6. **Dedicated CLI & Menu Bar Routing**: Added `safe-eject deep-sleep` command and verified all timers (2m, 5m, 10m, 15m, 30m, 1h, 2h), Before Sleep, and Before Logout triggers.

---

## 2. Test Verification Matrix

| Test Suite / Case | Description | Result |
| :--- | :--- | :--- |
| `test_parent_precedence_in_eject_targets` | Verifies parent precedence rule: single Deep Sleep run when parent and child targets are combined | **PASS** |
| `test_child_only_unmount_never_ejects_parent` | Verifies partition isolation: unmounting child partition never ejects parent SSD | **PASS** |
| `test_deep_sleep_aborts_on_volume_unmount_failure_no_force` | Verifies Deep Sleep aborts on volume unmount error without using force | **PASS** |
| `test_idle_sleep_parent_precedence_and_no_skipping` | Verifies `_on_idle_sleep` does not skip parent even if child volumes are unmounted | **PASS** |
| `test_deep_sleep_teardown_apfs_containers` | Verifies clean synthesized APFS container teardown before parent physical eject | **PASS** |
| `test_drive_and_volume_hover_metadata` | Verifies 100% dynamic OS metadata generation for macOS and Windows hover details | **PASS** |
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
| **Total Test Count** | **29 Passed, 0 Failed, 0 Skipped** | **100% PASS** |

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

---

### Drive Hover Details — Fixed Anchor Positioning (1X to 4X Responsive)

1. **Elimination of Duplicate Tooltips**:
   - Stripped all native browser/WebKit `title` attributes on driver labels.
   - Enforced a single, unified, custom HTML hover details popup (`#driveHoverPopup`).
2. **Fixed Anchor Position Below Drivers List**:
   - Fixed popup top anchor to start directly below `.drivers-section` (overlaying the Sleep/Awake and lower controls section).
   - Whichever disk is hovered (`disk7`, `disk8s1`, `disk9s1`), the popup opens at the exact same anchored position.
   - The hovered disk row, disk identifier, checkboxes, and buttons remain 100% visible and un-obscured at all times.
   - Zero occlusion of cursor or hovered row.
3. **Responsive Scaling & Boundaries**:
   - Bounded strictly within `.card` borders (`left: 6px; right: 6px; width: calc(100% - 12px)`).
   - Scales and reflows seamlessly across **1X, 1.25X, 1.5X, 2X, 3X, and 4X** modes.
   - Clean vertical wrapping (`.popup-row.vertical-wrap` with `.val-path`) prevents path truncation or clipping for long mount paths.
   - Preserves 100% OS-system-derived live metadata (Title, Location, Mount Point, Capacity, Child Count, Media Type).

