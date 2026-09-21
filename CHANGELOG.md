# Changelog

All notable changes to **Safe Drive Ejector Tool** will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [1.0.0] - 2026-09-22

### Added
- **Native macOS Menu Bar App (`SafeEjectMenuBar`)**:
  - Compact, floating, borderless, transparent panel anchored to the macOS status bar.
  - Interactive diamond toggle icon showing dynamic status (red 45° closed, green 135° open).
  - Two-way IPC bridge between native Swift and HTML5/CSS3/JavaScript front-end.
- **Glassmorphic Interactive Control Card**:
  - Rainbow dynamic animated GitHub header banner with real-time star counts and direct links to profile & repository.
  - Centered Status indicator with live activity animation and processing feedback loops.
  - Dynamic Scale selector (1X, 1.25X, 1.5X, 2X, 3X, 4X) with strictly contained background layers and zero visual bleed.
  - Pager navigation button with large, readable quadrant circles (`1st`, `2nd`, `3rd`, `4th`) and dynamic offset grouping.
  - Natural BSD name serial sorting (`disk3s1` < `disk6s1` < `disk8s1` < `disk9s1`) matching macOS Disk Utility.
  - Smooth mouse wheel scroll navigation for rotating through visible drives.
  - Per-drive Mount and Unmount actions with animated action indicators.
  - Global control grid: Sleep timer presets, Auto-Awake toggle, Emergency Eject Now, Start at Login, Update checker, and About dialog.
  - Safe application termination via dedicated Logout action.
- **Cross-Platform Python Core Engine**:
  - Automated detection of external SSDs, NVMe drives, USB drives, SD cards, and disk images.
  - Safe unmount and eject pipelines with busy-process detection, retry logic, and fallback routines.
  - Automated idle monitoring and sleep detection (`eject_before_sleep`).
  - Auto-remount upon system wake or hardware reconnect (`auto_awake`).
  - Cross-platform support for both macOS (`diskutil` / `IOKit`) and Windows (`mountvol` / `powershell` / `WMI`).
  - JSON-RPC and CLI command interfaces (`--json`, `mount`, `unmount`, `eject-all`, `remount-all`, `timer`).
- **Open-Source Infrastructure**:
  - MIT License.
  - Comprehensive unit test suite covering configuration, models, engine, and platform adapters.
  - Continuous integration and contribution guidelines.
