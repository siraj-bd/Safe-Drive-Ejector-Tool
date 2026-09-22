"""
Configuration and persistent state manager.
Cross-platform support for macOS (~/.config/safe-eject) and Windows (%APPDATA%/SafeEject).
"""

import json
import os
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List


def get_config_dir() -> Path:
    """Returns the platform-specific directory for SafeEject configuration with graceful fallback."""
    custom_dir = os.environ.get("SAFEEJECT_CONFIG_DIR")
    if custom_dir:
        path = Path(custom_dir)
        path.mkdir(parents=True, exist_ok=True)
        return path

    if sys.platform == "win32":
        appdata = os.environ.get("APPDATA")
        if appdata:
            path = Path(appdata) / "SafeEject"
        else:
            path = Path.home() / ".config" / "safe-eject"
    else:
        # macOS and Linux
        path = Path.home() / ".config" / "safe-eject"

    try:
        path.mkdir(parents=True, exist_ok=True)
        return path
    except PermissionError:
        # In sandboxed environments or restricted users, fallback to workspace .config
        fallback_path = Path.cwd() / ".safe_eject_config"
        fallback_path.mkdir(parents=True, exist_ok=True)
        return fallback_path


SLEEP_TIMER_PRESETS = {
    "2m": 120,
    "5m": 300,
    "10m": 600,
    "15m": 900,
    "30m": 1800,
    "1h": 3600,
    "2h": 7200,
    "never": 0,
}

MAX_MANAGED_DRIVES = 6


@dataclass
class SafeEjectConfig:
    eject_on_sleep: bool = True
    remount_on_wake: bool = True
    show_notifications: bool = True
    check_blocking_processes: bool = True
    auto_kill_blocking: bool = False
    excluded_volumes: List[str] = field(default_factory=list)
    excluded_drives: List[str] = field(default_factory=list)
    dev_github_url: str = "https://github.com/siraj-bd"
    repo_github_url: str = "https://github.com/siraj-bd/Safe-Drive-Ejector-Tool"
    github_stars: int = 11
    retry_count: int = 2
    retry_delay_seconds: float = 1.0
    log_level: str = "INFO"

    # System & Automation Settings
    start_at_login: bool = True
    show_menubar_icon: bool = True
    show_disks_count_badge: bool = True
    eject_before_sleep: bool = True
    eject_after_display_off: bool = False
    eject_before_logout: bool = False

    # What to Eject
    eject_hard_disks_ssds: bool = True
    eject_dvds_cds: bool = False
    eject_disk_images: bool = False
    eject_network_drives: bool = False
    eject_sd_cards: bool = False
    unmount_instead_of_eject: bool = True

    # Notification & Sounds
    progress_window_eject: bool = True
    progress_window_remount: bool = True
    notify_after_eject_remount: bool = True
    sound_on_success: bool = True
    sound_on_failure: bool = True
    success_sound: str = "Bubble"
    failure_sound: str = "Gong"

    # Hotkeys
    hotkey_eject: str = "^⌘E"
    hotkey_eject_and_sleep: str = ""
    hotkey_remount: str = "^⌘R"

    # Options
    remount_delay_seconds: int = 5
    also_eject_disks: List[str] = field(default_factory=list)
    dont_eject_disks: List[str] = field(default_factory=list)
    dont_remount_disks: List[str] = field(default_factory=list)

    # Custom Functional Features (Individual SSD Selection & Mac Touch Wake)
    sleep_timer_seconds: int = 120       # Default: 2 minutes
    managed_drive_uuids: List[str] = field(default_factory=list) # Up to 6 managed drives
    selected_sleep_drive_uuids: List[str] = field(default_factory=list) # Individually selected SSDs to sleep
    auto_awake: bool = True              # Automatically remount on wake or reconnect
    wake_mode: str = "touch"             # "touch" = auto active on Mac touch; "manual" = stay asleep until manual mount
    play_sounds: bool = True             # Audio feedback

    @property
    def sleep_timer_label(self) -> str:
        sec = self.sleep_timer_seconds
        if sec <= 0:
            return "Never"
        elif sec < 60:
            return f"{sec} Seconds"
        elif sec < 3600:
            return f"{sec // 60} Minute{'s' if sec // 60 > 1 else ''}"
        else:
            hours = sec // 3600
            return f"{hours} Hour{'s' if hours > 1 else ''}"

    def is_drive_sleep_selected(self, uuid: str, drive_id: str = "") -> bool:
        """Check if an individual SSD is selected for sleep."""
        if not self.selected_sleep_drive_uuids:
            # If none explicitly selected, select all managed drives
            return self.is_drive_managed(uuid, drive_id)
        for s in self.selected_sleep_drive_uuids:
            if s.lower() == uuid.lower() or (drive_id and s.lower() == drive_id.lower()):
                return True
        return False

    def toggle_sleep_drive_selection(self, uuid: str) -> bool:
        """Toggle individual SSD selection for auto-sleep."""
        clean_uuid = uuid.strip()
        if not clean_uuid:
            return False
        for idx, s in enumerate(self.selected_sleep_drive_uuids):
            if s.lower() == clean_uuid.lower():
                self.selected_sleep_drive_uuids.pop(idx)
                self.save()
                return False
        self.selected_sleep_drive_uuids.append(clean_uuid)
        self.save()
        return True

    def set_timer_preset(self, preset_key: str) -> bool:
        clean_key = preset_key.lower().strip()
        if clean_key in SLEEP_TIMER_PRESETS:
            self.sleep_timer_seconds = SLEEP_TIMER_PRESETS[clean_key]
            self.save()
            return True
        return False

    def is_drive_managed(self, uuid: str, drive_id: str = "") -> bool:
        """If no managed drives are explicitly defined, manage all connected external drives (up to 6)."""
        if not self.managed_drive_uuids:
            return True
        for m in self.managed_drive_uuids:
            if m.lower() == uuid.lower() or (drive_id and m.lower() == drive_id.lower()):
                return True
        return False

    def toggle_managed_drive(self, uuid: str) -> bool:
        """Add or remove drive from up-to-6 managed drives list. Returns True if now managed."""
        clean_uuid = uuid.strip()
        if not clean_uuid:
            return False

        # If present, remove
        for idx, m in enumerate(self.managed_drive_uuids):
            if m.lower() == clean_uuid.lower():
                self.managed_drive_uuids.pop(idx)
                self.save()
                return False

        # If not present, add up to limit
        if len(self.managed_drive_uuids) < MAX_MANAGED_DRIVES:
            self.managed_drive_uuids.append(clean_uuid)
            self.save()
            return True
        return False

    def update_settings(self, updates: Dict[str, Any]) -> None:
        """Update multiple configuration settings at once and save."""
        for k, v in updates.items():
            if hasattr(self, k):
                field_val = getattr(self, k)
                if isinstance(field_val, bool) and isinstance(v, str):
                    v = v.lower() in ("true", "1", "yes")
                elif isinstance(field_val, int) and isinstance(v, (str, float)):
                    v = int(v)
                setattr(self, k, v)
        self.save()

    @classmethod
    def load(cls) -> "SafeEjectConfig":
        config_path = get_config_dir() / "config.json"
        if not config_path.exists():
            default_config = cls()
            default_config.save()
            return default_config

        try:
            with open(config_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})
        except Exception:
            return cls()

    def save(self) -> None:
        config_path = get_config_dir() / "config.json"
        with open(config_path, "w", encoding="utf-8") as f:
            json.dump(asdict(self), f, indent=4)

    def is_excluded(self, volume_name: str, volume_uuid: str = "", drive_id: str = "") -> bool:
        """Check if a volume or drive is excluded from unmounting/ejecting."""
        for excl in self.excluded_volumes:
            if excl and (excl.lower() == volume_name.lower() or (volume_uuid and excl.lower() == volume_uuid.lower())):
                return True
        for excl in self.excluded_drives:
            if excl and excl.lower() == drive_id.lower():
                return True
        return False


class StateManager:
    """Tracks state such as drives ejected prior to sleep, for remounting on wake."""

    @staticmethod
    def get_state_file() -> Path:
        return get_config_dir() / "ejected_state.json"

    @classmethod
    def save_ejected_drives(cls, drive_ids: List[str], volume_identifiers: List[str]) -> None:
        try:
            state_path = cls.get_state_file()
            data = {
                "drive_ids": drive_ids,
                "volume_identifiers": volume_identifiers,
            }
            with open(state_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=4)
        except Exception:
            pass

    @classmethod
    def load_ejected_drives(cls) -> Dict[str, List[str]]:
        state_path = cls.get_state_file()
        if not state_path.exists():
            return {"drive_ids": [], "volume_identifiers": []}
        try:
            with open(state_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {"drive_ids": [], "volume_identifiers": []}

    @classmethod
    def clear_ejected_drives(cls) -> None:
        state_path = cls.get_state_file()
        if state_path.exists():
            try:
                state_path.unlink()
            except OSError:
                pass
