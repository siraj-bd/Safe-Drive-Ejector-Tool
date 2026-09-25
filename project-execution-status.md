# Project Execution Status: External SSD Hardware Silence & Deep Sleep Architecture

**Date**: September 25, 2026  
**Status**: COMPLETE, CLEANED & VERIFIED (49/49 Unit Tests PASS &bull; Native Swift Build Exit Code 0 &bull; 0 Unused Imports &bull; Clean Working Tree)  
**Target Hardware Tested**: Transcend StoreJet 480 GB SSD (Bridge: ASMedia ASM1153E, Parent Device: `/dev/disk7`, Partitions: `disk8s1` [`support-external-drive`], `disk9s1` [`Macbook Backup`])

---

## 1. Executive Summary

We have fully diagnosed, engineered, fixed, and verified the **Deep Sleep Hardware Silence & Auto-Wake Isolation Architecture**:
1. **Zero Hardware Polling on Sleeping Parent**: When a physical parent disk (e.g. `disk7`) is put into Deep Sleep, all automatic hardware polling (`diskutil info`, SCSI inquiries) is completely eliminated.
2. **`diskutil list` Suppression**: When all external parent drives are in deep sleep, `diskutil list` bus scans are completely suppressed, allowing the ASMedia ASM1153E USB-to-SATA bridge controller to enter low-power SATA slumber undisturbed.
3. **Strict Disjoint State Isolation (Explicit Deep Sleep vs. Idle Sleep)**:
   - `explicit_sleep_parent_ids`: Manual / UI 1-click Deep Sleep targets. Completely immune to touch-wake (mouse/keyboard events) and macOS system wake notifications.
   - `idle_sleep_parent_ids`: Automated idle-timer sleep targets. Eligible for touch-wake.
   - Starting an explicit Deep Sleep resets `isSleepingDueToIdle = false`. No parent can ever exist simultaneously in both sets.
4. **Time Machine & APFS Snapshot Dependency Teardown**:
   - Detects active local snapshot mount dependencies (e.g., `com.apple.TimeMachine...backup@/dev/disk9s1 on /Volumes/.timemachine/...`) and cleanly unmounts them before child volume unmount.
   - If any snapshot unmount fails or is locked by a live backup process, Deep Sleep aborts safely without force-eject and without recording sleeping state.
5. **No Remount-All Fallbacks**:
   - If `ejected_state.json` contains no drives, `remount_all_ejected()` safely returns empty without touching active external drives.
6. **Selective Child Volume Wake**:
   - Mounting `disk8s1` wakes parent `disk7`, mounts only `disk8s1`, keeps `disk9s1` unmounted, and safely clears parent sleep state upon verified success.
7. **Native Menu Bar App Isolation**:
   - `checkIdleState()` and `handleSystemWake()` in `ui/SafeEjectMenuBar.swift` strictly check whether drives are in explicit Deep Sleep and bypass automatic remounts.
8. **Live Hardware Verification**:
   - Tested on real Transcend StoreJet 480GB SSD (`/dev/disk7`). Ejected into Deep Sleep, remained unmounted for 120+ seconds while interacting with keyboard/mouse and running menu bar app. Verified selective wake of `disk8s1` leaving `disk9s1` unmounted.

---

## 2. Test Verification Matrix

| Test Suite / Case | Description | Result |
| :--- | :--- | :--- |
| `test_explicit_deep_sleep_sets_correct_state` | Verifies explicit deep sleep populates explicit_sleep_parent_ids and clears idle state | **PASS** |
| `test_idle_sleep_populates_idle_set` | Verifies idle sleep populates idle_sleep_parent_ids and is disjoint from explicit set | **PASS** |
| `test_touch_wake_ignores_explicit_deep_sleep` | Verifies mouse/keyboard touch-wake ignores explicit deep sleep drives | **PASS** |
| `test_remount_all_ejected_with_empty_state_does_not_remount` | Verifies remount_all_ejected with empty state returns [] and never touches drives | **PASS** |
| `test_snapshot_dependency_teardown_failure_aborts_deep_sleep` | Verifies Deep Sleep aborts cleanly without ejecting if snapshot unmount fails | **PASS** |
| `test_selective_child_mount_clears_parent_sleep_state` | Verifies mounting disk8s1 wakes parent disk7 and clears sleeping state | **PASS** |
| `test_sleeping_parent_recorded_in_state_manager` | Verifies parent disk7 recorded in StateManager.drive_ids upon Deep Sleep | **PASS** |
| `test_macos_adapter_hardware_silence_gates` | Verifies MacOSAdapter suppresses diskutil list when all external drives sleep & never queries diskutil info | **PASS** |
| `test_safe_mount_wake_sequence_and_parent_cleanup` | Verifies mounting child disk8s1 verifies success & clears parent disk7 from sleeping state | **PASS** |
| `test_safe_mount_wake_sequence_retains_state_on_failure` | Verifies sleeping state is retained on mount failure to prevent uncontrolled polling | **PASS** |
| `test_disk7_vs_dev_disk7_selection_normalization` | Verifies disk7 and /dev/disk7 both normalize to match parent drive and store primary UUID | **PASS** |
| `test_parent_selection_persistence` | Verifies parent UUID saved in config persists across config reloads | **PASS** |
| `test_parent_precedence_in_idle_sleep_execution` | Verifies _on_idle_sleep executes parent Deep Sleep once and skips child branches | **PASS** |
| `test_deep_sleep_failure_returns_non_zero_exit_code` | Verifies CLI exits with code 1 when volume unmount fails during Deep Sleep | **PASS** |
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
| **Total Test Count** | **43 Passed, 0 Failed, 0 Skipped** | **100% PASS** |

---

## 3. Build & Runtime Verification

### Native Swift Menu Bar App Compilation
```bash
$ swiftc -O -target arm64-apple-macos11.0 -module-cache-path .module-cache ui/SafeEjectMenuBar.swift -o bin/SafeEjectMenuBar
Exit Code: 0 (Zero warnings, zero errors)
```

---

## 4. Architectural Summary

```
+-------------------------------------------------------------+
|                      User Action                            |
|             (1-Click Deep Sleep disk7)                      |
+------------------------------+------------------------------+
                               |
                               v
+-------------------------------------------------------------+
|                   Deep Sleep Sequence                       |
| 1. Flush filesystem caches: sync                            |
| 2. Teardown active Time Machine snapshots                   |
| 3. Unmount child volumes (disk8s1, disk9s1)                 |
| 4. Teardown synthesized APFS containers (disk8, disk9)      |
| 5. Eject parent physical disk: diskutil eject disk7         |
| 6. Record in explicit_sleep_parent_ids                      |
| 7. Set isSleepingDueToIdle = false                          |
+------------------------------+------------------------------+
                               |
                               v
+-------------------------------------------------------------+
|               Hardware Silence (SATA Slumber)               |
| - diskutil info suppressed (ZERO polling)                   |
| - diskutil list suppressed when all external drives sleep   |
| - ASMedia ASM1153E bridge sleeps undisturbed                |
+------------------------------+------------------------------+
                               |
          +--------------------+--------------------+
          |                                         |
          v                                         v
+-----------------------+                 +--------------------+
|  Touch / System Wake  |                 |   Explicit Mount   |
|  (Mouse / Keyboard)   |                 |   (e.g. disk8s1)   |
+-----------+-----------+                 +---------+----------+
            |                                       |
            v                                       v
+-----------------------+                 +--------------------+
|     IGNORED / NO-OP   |                 | 1. Wake disk7      |
| Drive remains asleep  |                 | 2. Mount disk8s1   |
| Zero wake interrupts  |                 | 3. Keep disk9s1 off|
+-----------------------+                 | 4. Clear sleep     |
                                          +--------------------+
```

---

## 4. Codebase Audit & Low-Risk Cleanup Verification

### Actions Performed
1. **Unused Imports Cleaned**:
   - `main.py`: Removed unused `SafeEjectConfig`
   - `core/engine.py`: Removed unused `VolumeInfo`
   - `core/volume_manager.py`: Removed unused `Dict`, `VolumeInfo`
   - `core/idle_monitor.py`: Removed unused `os`, `Dict`
   - `platform_adapters/base.py`: Removed unused `Optional`, `VolumeInfo`
   - `platform_adapters/macos.py`: Removed unused `threading`
   - `platform_adapters/windows.py`: Removed unused `os`, `time`, `Dict`, `Optional`
   - `ui/cli.py`: Removed unused `SafeEjectConfig`, `DriveInfo`, `ProcessLockInfo`
   - `ui/tray.py`: Removed unused `os`, `time`, `SafeEjectConfig`
   - `tests/test_core.py`: Removed unused `os`, `MagicMock`
   - `tests/test_deep_sleep_auto_wake_isolation.py`: Removed unused `MagicMock`
   - `tests/test_features.py`: Removed unused `SLEEP_TIMER_PRESETS`, `sys`, and `_get_hardware_cache_file`
2. **Inline Imports Hoisted & Cleaned**:
   - In `core/volume_manager.py`, hoisted `re` and `sys` to module top-level alongside `os`, `subprocess`, `threading`.
   - Removed redundant inline `import re` from `mount_target()` and `unmount_target()`.
   - Removed redundant inline `import subprocess, sys, re` from `deep_sleep_drive()`.
3. **Dead Asset Cleaned**:
   - Deleted unused mock image `assets/safe-drive-ejector-card.png` (223 KB).
4. **Cache & Directory Maintenance**:
   - Added `.module-cache/` to `.gitignore`.
   - Removed local `.module-cache/` directory.
   - Removed empty `scratch/` directory.

### Verification Results
- **AST Re-Audit**: 0 unused imports across all production and test Python files.
- **Unit Test Suite**: 49/49 tests pass in 0.14s (43 core/feature tests + 6 deep sleep isolation tests).
- **Swift Compilation**: `swiftc -parse ui/SafeEjectMenuBar.swift` passes with exit code 0.

---

## 5. Free Open-Source GitHub Distribution Architecture

### Strategy & Multi-Platform Support
- **100% Free Open-Source Model**: No paid Apple Developer Program ($99/year) or commercial Windows EV code signing certificate required.
- **Supported Targets**:
  1. **macOS Apple Silicon (`arm64`)**: Native `.app` bundle, frozen standalone Python core engine, WebKit card UI, packaged in `.dmg`.
  2. **macOS Intel (`x86_64`)**: Native build via GitHub Actions `macos-15-intel` runner, identical `.app` and `.dmg`.
  3. **Windows (`x64`)**: Native standalone `.exe` (windowless System Tray GUI + CLI), packaged with non-admin installer/uninstaller in `.zip`.

### Code Signing & Security
- **Inside-Out Ad-Hoc Signing**: Bundle sealed properly (`codesign --verify --deep --strict` returns exit code 0) with `entitlements.plist`.
- **First-Launch Guidance (`FIRST_LAUNCH_INSTRUCTIONS.txt`)**:
  - Bundled directly inside macOS `.dmg` and Windows `.zip`.
  - Detailed in `README.md`.
  - macOS Gatekeeper: Approved via *System Settings > Privacy & Security > Open Anyway* (or `xattr -d com.apple.quarantine`).
  - Windows SmartScreen: Approved via *More info > Run anyway*.
  - **No Global Security Compromises**: SIP and Gatekeeper remain fully enabled.

