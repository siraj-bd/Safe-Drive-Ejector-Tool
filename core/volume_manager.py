"""
SSD Volume Manager & Drive Controller.
Coordinates volume mounting/unmounting, up-to-6 managed drives selection,
Eject Now logic, and drive state refreshing.
"""

import logging
from typing import Dict, List, Optional, Tuple

from core.config import MAX_MANAGED_DRIVES, SafeEjectConfig, StateManager
from core.models import DriveInfo, EjectResult, RemountResult, VolumeInfo
from platform_adapters.base import PlatformAdapter

logger = logging.getLogger("SafeEject.VolumeManager")


class SSDVolumeManager:
    """Manages volume-level operations and tracks up to 6 managed external SSDs/HDDs."""

    def __init__(self, adapter: PlatformAdapter, config: SafeEjectConfig):
        self.adapter = adapter
        self.config = config

    def get_all_external_drives(self) -> List[DriveInfo]:
        """Fetch all physical external drives, annotating whether they are managed and sleep-selected."""
        all_drives = self.adapter.get_drives()
        external_drives: List[DriveInfo] = []

        for d in all_drives:
            if d.is_external and not d.is_virtual:
                # Check if managed
                d.is_managed = self.config.is_drive_managed(d.primary_uuid, drive_id=d.id)
                # Check if individually selected for sleep
                d.is_sleep_selected = self.config.is_drive_sleep_selected(d.primary_uuid, drive_id=d.id)

                for v in d.volumes:
                    v.is_managed = self.config.is_drive_managed(v.uuid or v.device_id, drive_id=d.id)
                    v.is_sleep_selected = self.config.is_drive_sleep_selected(v.uuid or v.device_id, drive_id=d.id)

                external_drives.append(d)

        # Enforce maximum of 6 managed drives
        managed_count = 0
        for d in external_drives:
            if d.is_managed:
                managed_count += 1
                if managed_count > MAX_MANAGED_DRIVES:
                    d.is_managed = False

        return external_drives

    def play_sound(self, sound_name: str):
        """Play a macOS system sound if sounds are enabled."""
        if not self.config.play_sounds:
            return
        sound_file = f"/System/Library/Sounds/{sound_name}.aiff"
        try:
            import subprocess
            subprocess.Popen(["afplay", sound_file], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except Exception:
            pass

    def get_managed_drives(self) -> List[DriveInfo]:
        """Return only the managed external drives (up to 6)."""
        drives = self.get_all_external_drives()
        return [d for d in drives if d.is_managed]

    def eject_now(self, targets: Optional[List[str]] = None) -> List[EjectResult]:
        """
        'Eject Now' Logic:
        If specific targets are provided, immediately safely unmounts/ejects ONLY those targets.
        If no targets are provided, ejects all managed external drives.
        """
        results: List[EjectResult] = []
        ejected_ids: List[str] = []
        ejected_vols: List[str] = []

        if targets:
            logger.info(f"Executing 'Eject Now' for {len(targets)} selected target(s): {targets}")
            for t in targets:
                res = self.unmount_target(t)
                results.append(res)
                if res.success:
                    if "s" in t.lower():
                        ejected_vols.append(t)
                    else:
                        ejected_ids.append(t)
            if ejected_ids or ejected_vols:
                StateManager.save_ejected_drives(ejected_ids, ejected_vols)
                if self.config.show_notifications:
                    self.adapter.show_notification(
                        "SafeEject",
                        f"Safely unmounted/ejected {len(results)} target(s).",
                    )
            return results

        logger.info("Executing 'Eject Now' for all managed drives...")
        managed = self.get_managed_drives()

        for drive in managed:
            # Check exclusions (volume name, volume UUID, or drive ID)
            is_excluded = False
            for v in drive.volumes:
                if self.config.is_excluded(volume_name=v.name, volume_uuid=v.uuid, drive_id=drive.id):
                    is_excluded = True
                    break
            if is_excluded or self.config.is_excluded("", drive_id=drive.id):
                continue

            res = self.adapter.eject_drive(drive.id)
            results.append(res)
            if res.success:
                ejected_ids.append(drive.id)
                for v in drive.volumes:
                    ejected_vols.append(v.device_id)

        if ejected_ids or ejected_vols:
            StateManager.save_ejected_drives(ejected_ids, ejected_vols)
            if self.config.show_notifications:
                count = len(ejected_ids) + len(ejected_vols)
                self.adapter.show_notification(
                    "SafeEject",
                    f"Safely unmounted/ejected {count} item(s) successfully.",
                )

        return results

    def mount_target(self, target_id: str) -> RemountResult:
        """Mount a specific volume or drive by ID, UUID, or name."""
        logger.info(f"Manual Mount requested for: {target_id}")
        clean_target = target_id.strip()
        drives = self.get_all_external_drives()

        # 1. Prioritize volume match so mounting disk8s1 targets only that volume
        for d in drives:
            for v in d.volumes:
                if (
                    v.device_id.lower() == clean_target.lower()
                    or (v.device_id.replace("/dev/", "").lower() == clean_target.replace("/dev/", "").lower())
                    or (v.uuid and v.uuid.lower() == clean_target.lower())
                    or (v.name and v.name.lower() == clean_target.lower())
                ):
                    res = self.adapter.mount_volume(v.device_id)
                    if res.success:
                        StateManager.remove_ejected_target(v.device_id)
                    return res

        # 2. Check if target matches drive ID or primary UUID
        for d in drives:
            if (
                d.id.lower() == clean_target.lower()
                or (d.id.replace("/dev/", "").lower() == clean_target.replace("/dev/", "").lower())
                or (d.primary_uuid and d.primary_uuid.lower() == clean_target.lower())
            ):
                res = self.adapter.mount_drive(d.id)
                if res.success:
                    StateManager.remove_ejected_target(d.id)
                    for v in d.volumes:
                        StateManager.remove_ejected_target(v.device_id)
                return res

        # Direct fallback
        import re
        if re.search(r"disk\d+s\d+", clean_target.lower()):
            return self.adapter.mount_volume(clean_target)
        return self.adapter.mount_drive(clean_target)

    def unmount_target(self, target_id: str) -> EjectResult:
        """Unmount a specific volume or drive by ID, UUID, or name."""
        logger.info(f"Manual Unmount requested for: {target_id}")
        clean_target = target_id.strip()
        drives = self.get_all_external_drives()

        # 1. Prioritize volume match so unmounting disk8s1 unmounts ONLY that volume partition
        for d in drives:
            for v in d.volumes:
                if (
                    v.device_id.lower() == clean_target.lower()
                    or (v.device_id.replace("/dev/", "").lower() == clean_target.replace("/dev/", "").lower())
                    or (v.uuid and v.uuid.lower() == clean_target.lower())
                    or (v.name and v.name.lower() == clean_target.lower())
                ):
                    logger.info(f"Matched volume {v.device_id} ({v.name}). Unmounting volume only (parent remains awake, LED ON).")
                    res = self.adapter.unmount_volume(v.device_id)
                    if res.success:
                        StateManager.save_ejected_drives([], [v.device_id], append=True)
                    # NOTE: Do NOT automatically eject parent drive. Partition unmount must leave parent awake and LED ON.
                    return res

        # 2. Match parent physical drive
        for d in drives:
            if (
                d.id.lower() == clean_target.lower()
                or (d.id.replace("/dev/", "").lower() == clean_target.replace("/dev/", "").lower())
                or (d.primary_uuid and d.primary_uuid.lower() == clean_target.lower())
            ):
                return self.deep_sleep_drive(d.id)

        # 3. Direct fallback: if target looks like a volume partition (e.g. disk8s1)
        import re
        if re.search(r"disk\d+s\d+", clean_target.lower()):
            return self.adapter.unmount_volume(clean_target)

        return self.adapter.eject_drive(clean_target)

    def deep_sleep_drive(self, drive_id: str) -> EjectResult:
        """
        Deep Sleep / LED-OFF Sleep workflow:
        1. Flush filesystem buffers (sync).
        2. Safely unmount all mounted child volumes of target physical drive.
        3. If ANY required unmount fails, ABORT immediately and report error (NEVER force-eject).
        4. On macOS, cleanly teardown synthesized APFS container dependencies (diskutil unmountDisk).
           If ANY container teardown fails, ABORT immediately.
        5. Only after all unmounts and teardowns succeed, eject physical parent disk (diskutil eject <parentId>).
        6. Record sleeping relevant volumes for selective Auto-Wake.
        """
        import subprocess, sys
        clean_id = drive_id.strip().replace("/dev/", "")
        drives = self.get_all_external_drives()

        target_drive = None
        for d in drives:
            d_id = d.id.replace("/dev/", "")
            if d_id.lower() == clean_id.lower():
                target_drive = d
                break
            for v in d.volumes:
                v_id = v.device_id.replace("/dev/", "")
                if v_id.lower() == clean_id.lower():
                    target_drive = d
                    break
            if target_drive:
                break

        if not target_drive:
            return self.adapter.eject_drive(clean_id)

        # 1. Flush filesystem buffers
        try:
            if sys.platform == "darwin":
                subprocess.run(["sync"], check=False)
        except Exception:
            pass

        # 2. Safely unmount all mounted child volumes
        vols_to_unmount = [v for v in target_drive.volumes if v.is_mounted]
        unmounted_vols: List[str] = []

        for v in vols_to_unmount:
            res = self.adapter.unmount_volume(v.device_id)
            if not res.success:
                logger.error(f"Deep Sleep aborted: volume {v.device_id} ({v.name}) failed to unmount: {res.message}")
                return EjectResult(
                    target=target_drive.id,
                    success=False,
                    message=f"Deep Sleep aborted: {v.name or v.device_id} in use ({res.message})",
                    blocking_processes=res.blocking_processes,
                )
            unmounted_vols.append(v.device_id)

        # 3. Teardown associated synthesized APFS container disks (e.g. disk8, disk9)
        if hasattr(self.adapter, "get_apfs_containers_for_disk"):
            containers = self.adapter.get_apfs_containers_for_disk(target_drive.id)
            for c_id in containers:
                c_res = self.adapter.unmount_disk(c_id)
                if not c_res.success:
                    logger.error(f"Deep Sleep aborted: APFS container {c_id} teardown failed: {c_res.message}")
                    return EjectResult(
                        target=target_drive.id,
                        success=False,
                        message=f"Deep Sleep aborted: Container {c_id} in use ({c_res.message})",
                    )

        # 4. Only after all successful unmounts & container teardowns, eject physical parent disk
        eject_res = self.adapter.eject_drive(target_drive.id)
        if eject_res.success:
            if unmounted_vols:
                StateManager.save_ejected_drives([], unmounted_vols, append=True)
            return EjectResult(
                target=target_drive.id,
                success=True,
                message=f"Drive {target_drive.id} in Deep Sleep (LED OFF). {len(unmounted_vols)} volume(s) safely unmounted.",
            )
        else:
            logger.warning(f"Parent eject for {target_drive.id} failed after unmounting volumes: {eject_res.message}")
            return eject_res

    def toggle_managed(self, target_id: str) -> Tuple[bool, str]:
        """
        Toggle managed state for a drive or volume UUID.
        Returns (is_now_managed, message).
        """
        drives = self.get_all_external_drives()
        target_uuid = target_id

        for d in drives:
            if d.id.lower() == target_id.lower():
                target_uuid = d.primary_uuid
                break
            for v in d.volumes:
                if v.device_id.lower() == target_id.lower() or v.name.lower() == target_id.lower():
                    target_uuid = v.uuid or v.device_id
                    break

        is_managed = self.config.toggle_managed_drive(target_uuid)
        status_msg = f"Drive '{target_id}' is now {'Managed' if is_managed else 'Unmanaged'}."
        logger.info(status_msg)
        return is_managed, status_msg
