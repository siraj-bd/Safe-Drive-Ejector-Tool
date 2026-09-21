"""
Data models for disks, volumes, process locks, and operation results.
Cross-platform support for macOS and Windows.
"""

from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class ProcessLockInfo:
    pid: int
    process_name: str
    file_path: str

    def __str__(self) -> str:
        return f"{self.process_name} (PID: {self.pid}) -> {self.file_path}"


@dataclass
class VolumeInfo:
    device_id: str                      # e.g. "disk8s1" or "E:"
    name: str                           # e.g. "support-external-drive" or "Data"
    mount_point: Optional[str] = None   # e.g. "/Volumes/support-external-drive" or "E:\\"
    size_bytes: int = 0
    fs_type: str = ""                   # e.g. "APFS", "NTFS", "FAT32", "ExFAT"
    uuid: str = ""
    is_mounted: bool = False
    is_managed: bool = False
    is_sleep_selected: bool = False

    @property
    def human_size(self) -> str:
        return format_size(self.size_bytes)

    def to_dict(self) -> dict:
        return {
            "device_id": self.device_id,
            "name": self.name,
            "mount_point": self.mount_point,
            "size_bytes": self.size_bytes,
            "human_size": self.human_size,
            "fs_type": self.fs_type,
            "uuid": self.uuid,
            "is_mounted": self.is_mounted,
            "is_managed": self.is_managed,
            "is_sleep_selected": self.is_sleep_selected,
        }


@dataclass
class DriveInfo:
    id: str                             # e.g. "disk7" or "PhysicalDrive1"
    name: str                           # e.g. "StoreJet Transcend Media"
    size_bytes: int = 0
    bus_protocol: str = "Unknown"       # e.g. "USB", "Thunderbolt", "SD", "SATA"
    is_external: bool = False
    is_removable: bool = False
    is_virtual: bool = False            # e.g. disk images (.dmg, .iso)
    is_managed: bool = False
    is_sleep_selected: bool = False
    idle_seconds: float = 0.0
    volumes: List[VolumeInfo] = field(default_factory=list)

    @property
    def primary_uuid(self) -> str:
        """Returns the first non-empty volume UUID, or drive ID as fallback."""
        for v in self.volumes:
            if v.uuid:
                return v.uuid
        return self.id

    @property
    def human_size(self) -> str:
        return format_size(self.size_bytes)

    @property
    def has_mounted_volumes(self) -> bool:
        return any(v.is_mounted for v in self.volumes)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "size_bytes": self.size_bytes,
            "human_size": self.human_size,
            "bus_protocol": self.bus_protocol,
            "is_external": self.is_external,
            "is_removable": self.is_removable,
            "is_virtual": self.is_virtual,
            "is_managed": self.is_managed,
            "is_sleep_selected": self.is_sleep_selected,
            "primary_uuid": self.primary_uuid,
            "idle_seconds": self.idle_seconds,
            "volumes": [v.to_dict() for v in self.volumes],
        }


@dataclass
class EjectResult:
    target: str                         # Drive ID or Volume ID / MountPoint
    success: bool
    message: str
    blocking_processes: List[ProcessLockInfo] = field(default_factory=list)


@dataclass
class RemountResult:
    target: str                         # Drive ID or Volume ID
    success: bool
    message: str
    mounted_path: Optional[str] = None


def format_size(bytes_num: int) -> str:
    """Format bytes into human-readable string (KB, MB, GB, TB)."""
    if bytes_num <= 0:
        return "0 B"
    units = ["B", "KB", "MB", "GB", "TB", "PB"]
    i = 0
    val = float(bytes_num)
    while val >= 1024.0 and i < len(units) - 1:
        val /= 1024.0
        i += 1
    return f"{val:.1f} {units[i]}"
