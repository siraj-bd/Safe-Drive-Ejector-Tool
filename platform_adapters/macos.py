"""
macOS Platform Adapter.
Handles disk enumeration, unmounting, ejecting, remounting, blocking process checks,
desktop notifications, and system sleep/wake interception via IOKit.
"""

import ctypes
import ctypes.util
import logging
import os
import plistlib
import re
import subprocess
import threading
import time
from typing import Callable, Dict, List, Optional

from core.models import DriveInfo, EjectResult, ProcessLockInfo, RemountResult, VolumeInfo
from platform_adapters.base import PlatformAdapter

logger = logging.getLogger("SafeEject.MacOS")


class MacOSAdapter(PlatformAdapter):
    """Native macOS implementation for disk management and power events."""

    def __init__(self):
        self._run_loop = None
        self._stop_requested = False
        self._info_cache: Dict[str, dict] = {}

    def get_drives(self) -> List[DriveInfo]:
        """Enumerate all drives using macOS diskutil plist."""
        try:
            cmd = ["diskutil", "list", "-plist"]
            proc = subprocess.run(cmd, capture_output=True, check=True)
            plist_data = plistlib.loads(proc.stdout)
        except Exception as e:
            logger.error(f"Failed to execute diskutil list: {e}")
            return []

        whole_disks = plist_data.get("WholeDisks", [])
        all_partitions = plist_data.get("AllDisksAndPartitions", [])

        # Build map of disk identifier -> partition/volume info from diskutil list
        volume_map = self._parse_all_partitions(all_partitions)

        drives: List[DriveInfo] = []
        for disk_id in whole_disks:
            drive_info = self._get_drive_details(disk_id, volume_map.get(disk_id, []))
            if drive_info:
                # Omit empty virtual synthesized APFS containers whose volumes are on physical parents
                if drive_info.is_virtual and not drive_info.volumes:
                    continue
                drives.append(drive_info)

        return drives

    def _parse_all_partitions(self, all_partitions: List[dict]) -> Dict[str, List[VolumeInfo]]:
        """Extract VolumeInfo objects grouped by parent whole disk identifier."""
        grouped: Dict[str, List[VolumeInfo]] = {}

        for item in all_partitions:
            parent_id = item.get("DeviceIdentifier")
            if not parent_id:
                continue

            volumes: List[VolumeInfo] = []

            # 1. Standard partitions
            for part in item.get("Partitions", []):
                dev_id = part.get("DeviceIdentifier", "")
                vol_name = part.get("VolumeName", "")
                uuid = part.get("DiskUUID", "")
                size = part.get("Size", 0)
                mount_pt = part.get("MountPoint")
                fs = part.get("Content", "")

                if dev_id and fs != "Apple_APFS":
                    volumes.append(
                        VolumeInfo(
                            device_id=dev_id,
                            name=vol_name or dev_id,
                            mount_point=mount_pt,
                            size_bytes=size,
                            fs_type=fs,
                            uuid=uuid,
                            is_mounted=bool(mount_pt),
                        )
                    )

            # 2. APFS Volumes
            for apfs_vol in item.get("APFSVolumes", []):
                dev_id = apfs_vol.get("DeviceIdentifier", "")
                vol_name = apfs_vol.get("VolumeName", "")
                uuid = apfs_vol.get("VolumeUUID", "")
                size = apfs_vol.get("Size", 0)
                mount_pt = apfs_vol.get("MountPoint")

                if dev_id:
                    volumes.append(
                        VolumeInfo(
                            device_id=dev_id,
                            name=vol_name or dev_id,
                            mount_point=mount_pt,
                            size_bytes=size,
                            fs_type="APFS",
                            uuid=uuid,
                            is_mounted=bool(mount_pt),
                        )
                    )

            # Find parent if this item is an APFS Container
            physical_stores = item.get("APFSPhysicalStores", [])
            if physical_stores:
                # Map back to physical parent disk (e.g. disk7s2 -> parent is disk7)
                store_dev = physical_stores[0].get("DeviceIdentifier", "")
                match = re.match(r"^(disk\d+)", store_dev)
                if match:
                    actual_parent = match.group(1)
                    grouped.setdefault(actual_parent, []).extend(volumes)
                    continue

            grouped.setdefault(parent_id, []).extend(volumes)

        return grouped

    def _get_drive_details(self, disk_id: str, volumes: List[VolumeInfo]) -> Optional[DriveInfo]:
        """Fetch detailed hardware info for a whole disk using diskutil info -plist (cached to prevent waking sleeping drives)."""
        info = self._info_cache.get(disk_id)
        if not info:
            try:
                proc = subprocess.run(["diskutil", "info", "-plist", disk_id], capture_output=True, check=True)
                info = plistlib.loads(proc.stdout)
                self._info_cache[disk_id] = info
            except Exception as e:
                logger.warning(f"Could not query diskutil info for {disk_id}: {e}")
                return None

        name = (
            info.get("MediaName")
            or info.get("IORegistryEntryName")
            or info.get("VolumeName")
            or disk_id
        )
        size_bytes = info.get("TotalSize", 0) or info.get("Size", 0)
        bus_protocol = info.get("BusProtocol", "Unknown")
        is_internal = info.get("Internal", True)
        is_ejectable = info.get("Ejectable", False)
        is_removable_media = info.get("RemovableMediaOrExternalDevice", False)
        virtual_or_physical = info.get("VirtualOrPhysical", "Physical")
        is_virtual = (virtual_or_physical.lower() != "physical") or (bus_protocol.lower() == "disk image")

        # External disk logic:
        # A physical drive is external if Internal is False and (RemovableMediaOrExternalDevice or USB/Thunderbolt/etc)
        is_external = (not is_internal) and (is_removable_media or bus_protocol.upper() in ["USB", "THUNDERBOLT", "FIREWIRE", "SD"])

        # If this is a synthesized container that has no direct physical store and volumes are empty,
        # or it's a virtual container whose volumes were already absorbed by the physical parent, skip if empty
        if not volumes and info.get("MountPoint"):
            volumes = [
                VolumeInfo(
                    device_id=disk_id,
                    name=info.get("VolumeName", disk_id),
                    mount_point=info.get("MountPoint"),
                    size_bytes=size_bytes,
                    fs_type=info.get("FilesystemType", ""),
                    uuid=info.get("VolumeUUID", ""),
                    is_mounted=True,
                )
            ]

        return DriveInfo(
            id=disk_id,
            name=name,
            size_bytes=size_bytes,
            bus_protocol=bus_protocol,
            is_external=is_external,
            is_removable=is_ejectable or is_removable_media,
            is_virtual=is_virtual,
            volumes=volumes,
        )

    def eject_drive(self, drive_id: str) -> EjectResult:
        """Eject an entire drive using diskutil eject."""
        logger.info(f"Attempting to eject drive: {drive_id}")

        # Check for any open files first
        drives = self.get_drives()
        matching_drive = next((d for d in drives if d.id == drive_id), None)
        blocking_procs: List[ProcessLockInfo] = []

        if matching_drive:
            for vol in matching_drive.volumes:
                if vol.mount_point:
                    locks = self.get_blocking_processes(vol.mount_point)
                    blocking_procs.extend(locks)

        # Run diskutil eject
        proc = subprocess.run(["diskutil", "eject", drive_id], capture_output=True, text=True)
        if proc.returncode == 0:
            self._info_cache.pop(drive_id, None)
            return EjectResult(
                target=drive_id,
                success=True,
                message=f"Drive {drive_id} ejected successfully.",
            )
        else:
            err_msg = proc.stderr.strip() or proc.stdout.strip()
            # If standard eject failed and there are blocking processes, report them
            return EjectResult(
                target=drive_id,
                success=False,
                message=f"Failed to eject {drive_id}: {err_msg}",
                blocking_processes=blocking_procs,
            )

    def unmount_volume(self, volume_id: str) -> EjectResult:
        """Unmount a specific volume using diskutil unmount."""
        logger.info(f"Attempting to unmount volume: {volume_id}")
        proc = subprocess.run(["diskutil", "unmount", volume_id], capture_output=True, text=True)
        if proc.returncode == 0:
            return EjectResult(
                target=volume_id,
                success=True,
                message=f"Volume {volume_id} unmounted successfully.",
            )
        else:
            err_msg = proc.stderr.strip() or proc.stdout.strip()
            return EjectResult(
                target=volume_id,
                success=False,
                message=f"Failed to unmount {volume_id}: {err_msg}",
            )

    def mount_drive(self, drive_id: str) -> RemountResult:
        """Mount all volumes on a drive using diskutil mountDisk."""
        logger.info(f"Attempting to mount drive: {drive_id}")
        proc = subprocess.run(["diskutil", "mountDisk", drive_id], capture_output=True, text=True)
        output = proc.stdout.strip() + " " + proc.stderr.strip()
        if proc.returncode == 0:
            return RemountResult(
                target=drive_id,
                success=True,
                message=f"Drive {drive_id} mounted successfully.",
            )
        else:
            return RemountResult(
                target=drive_id,
                success=False,
                message=f"Failed to mount {drive_id}: {output.strip()}",
            )

    def mount_volume(self, volume_id: str) -> RemountResult:
        """Mount a specific volume using diskutil mount."""
        logger.info(f"Attempting to mount volume: {volume_id}")
        proc = subprocess.run(["diskutil", "mount", volume_id], capture_output=True, text=True)
        output = proc.stdout.strip()
        if proc.returncode == 0:
            return RemountResult(
                target=volume_id,
                success=True,
                message=f"Volume {volume_id} mounted successfully.",
            )
        else:
            return RemountResult(
                target=volume_id,
                success=False,
                message=f"Failed to mount {volume_id}: {proc.stderr.strip() or output}",
            )

    def get_blocking_processes(self, mount_point: str) -> List[ProcessLockInfo]:
        """Find processes locking files on the mount point via lsof."""
        if not mount_point or not os.path.exists(mount_point):
            return []

        locks: List[ProcessLockInfo] = []
        try:
            # lsof -F pcn +D <mount_point> gives machine readable output:
            # p<pid>, c<command>, n<filename>
            cmd = ["lsof", "-F", "pcn", "+D", mount_point]
            proc = subprocess.run(cmd, capture_output=True, text=True)
            lines = proc.stdout.splitlines()

            current_pid = 0
            current_comm = ""
            for line in lines:
                if not line:
                    continue
                tag = line[0]
                val = line[1:]
                if tag == "p":
                    current_pid = int(val) if val.isdigit() else 0
                elif tag == "c":
                    current_comm = val
                elif tag == "n":
                    if current_pid > 0 and val.startswith(mount_point):
                        locks.append(
                            ProcessLockInfo(
                                pid=current_pid,
                                process_name=current_comm or "Unknown",
                                file_path=val,
                            )
                        )
        except Exception as e:
            logger.debug(f"lsof check failed for {mount_point}: {e}")

        return locks

    def kill_process(self, pid: int) -> bool:
        """Terminate a process gracefully (SIGTERM), then forcefully (SIGKILL) if needed."""
        try:
            os.kill(pid, 15)  # SIGTERM
            time.sleep(0.5)
            # Check if still running
            os.kill(pid, 0)
            # If it didn't throw ESRCH, send SIGKILL
            os.kill(pid, 9)
            return True
        except ProcessLookupError:
            return True
        except Exception as e:
            logger.error(f"Failed to kill process {pid}: {e}")
            return False

    def show_notification(self, title: str, message: str) -> None:
        """Display native macOS notification via AppleScript."""
        clean_title = title.replace('"', '\\"')
        clean_msg = message.replace('"', '\\"')
        script = f'display notification "{clean_msg}" with title "{clean_title}"'
        try:
            subprocess.run(["osascript", "-e", script], capture_output=True)
        except Exception as e:
            logger.debug(f"Notification display error: {e}")

    def start_power_listener(
        self,
        on_sleep: Callable[[], None],
        on_wake: Callable[[], None],
    ) -> None:
        """
        Listen to system sleep/wake notifications using macOS IOKit framework.
        Runs the CoreFoundation RunLoop to process power events synchronously on the thread.
        """
        logger.info("Registering for macOS IOKit power events (Sleep & Wake)...")

        try:
            iokit_path = ctypes.util.find_library("IOKit")
            cf_path = ctypes.util.find_library("CoreFoundation")

            iokit = ctypes.cdll.LoadLibrary(iokit_path)
            cf = ctypes.cdll.LoadLibrary(cf_path)
        except Exception as e:
            logger.error(f"Failed to load IOKit/CoreFoundation: {e}. Falling back to sleep polling.")
            self._fallback_power_listener(on_sleep, on_wake)
            return

        # Core Foundation & IOKit types
        CFRunLoopRef = ctypes.c_void_p
        CFStringRef = ctypes.c_void_p
        io_connect_t = ctypes.c_uint32
        io_service_t = ctypes.c_uint32
        io_object_t = ctypes.c_uint32
        IONotificationPortRef = ctypes.c_void_p

        # Power Message Constants from <IOKit/pwr_mgt/IOPM.h>
        kIOMessageCanSystemSleep = 0xE0000270
        kIOMessageSystemWillSleep = 0xE0000280
        kIOMessageSystemWillPowerOn = 0xE0000320
        kIOMessageSystemHasPoweredOn = 0xE0000300

        # Callback prototype: void (*IOServiceInterestCallback)(void *refcon, io_service_t service, natural_t messageType, void *messageArgument)
        CALLBACK_FUNC = ctypes.CFUNCTYPE(
            None,
            ctypes.c_void_p,
            io_service_t,
            ctypes.c_uint32,
            ctypes.c_void_p,
        )

        root_port = io_connect_t(0)
        notifier = io_object_t(0)
        notify_port = IONotificationPortRef(0)

        def power_callback(refcon, service, message_type, message_arg):
            logger.debug(f"Received IOKit power message: {hex(message_type)}")

            if message_type in (kIOMessageCanSystemSleep, kIOMessageSystemWillSleep):
                logger.info("macOS System is preparing to sleep. Triggering safe disk ejection...")
                try:
                    on_sleep()
                except Exception as ex:
                    logger.error(f"Error during on_sleep callback: {ex}")

                # Acknowledge sleep notification to allow system to sleep
                logger.info("Acknowledging IOKit sleep permission...")
                iokit.IOAllowPowerChange(root_port, message_arg)

            elif message_type in (kIOMessageSystemHasPoweredOn, kIOMessageSystemWillPowerOn):
                logger.info("macOS System has woken up. Triggering disk remount...")
                try:
                    on_wake()
                except Exception as ex:
                    logger.error(f"Error during on_wake callback: {ex}")

        c_callback = CALLBACK_FUNC(power_callback)

        notify_port_ptr = IONotificationPortRef()
        res_root_port = iokit.IORegisterForSystemPower(
            None,
            ctypes.byref(notify_port_ptr),
            c_callback,
            ctypes.byref(notifier),
        )

        if not res_root_port:
            logger.error("IORegisterForSystemPower returned 0. Falling back to log stream watcher.")
            self._fallback_power_listener(on_sleep, on_wake)
            return

        root_port = io_connect_t(res_root_port)
        run_loop_source = iokit.IONotificationPortGetRunLoopSource(notify_port_ptr)

        kCFRunLoopCommonModes = ctypes.c_void_p.in_dll(cf, "kCFRunLoopCommonModes")
        current_run_loop = cf.CFRunLoopGetCurrent()
        self._run_loop = current_run_loop

        cf.CFRunLoopAddSource(current_run_loop, run_loop_source, kCFRunLoopCommonModes)

        logger.info("IOKit Power Listener active. Monitoring sleep/wake events.")
        # CFRunLoopRun enters the event loop
        cf.CFRunLoopRun()

    def _fallback_power_listener(self, on_sleep: Callable[[], None], on_wake: Callable[[], None]) -> None:
        """Fallback watcher that checks sleep/wake events if IOKit ctypes cannot be initialized."""
        logger.info("Running fallback power monitor via system log stream...")
        try:
            cmd = ["log", "stream", "--style", "ndjson", "--predicate", 'eventMessage contains "Sleep" or eventMessage contains "Wake"']
            proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
            for line in proc.stdout:
                if self._stop_requested:
                    break
                if "Entering Sleep" in line or "System is going to sleep" in line:
                    logger.info("Fallback detected sleep event.")
                    on_sleep()
                elif "Wake from" in line or "System has awakened" in line:
                    logger.info("Fallback detected wake event.")
                    on_wake()
        except Exception as e:
            logger.error(f"Fallback power watcher failed: {e}")
