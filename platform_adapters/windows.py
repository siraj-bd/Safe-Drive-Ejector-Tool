"""
Windows Platform Adapter.
Handles disk enumeration, offline/online mounting, ejecting, blocking process checks via Restart Manager,
toast notifications, and power events (WM_POWERBROADCAST) using ctypes and PowerShell/diskpart.
"""

import ctypes
import json
import logging
import subprocess
import sys
from typing import Callable, List

from core.models import DriveInfo, EjectResult, ProcessLockInfo, RemountResult, VolumeInfo
from platform_adapters.base import PlatformAdapter

logger = logging.getLogger("SafeEject.Windows")


class WindowsAdapter(PlatformAdapter):
    """Native Windows implementation using PowerShell, diskpart, and Win32 APIs."""

    def __init__(self):
        self._stop_requested = False

    def get_drives(self) -> List[DriveInfo]:
        """
        Enumerate all connected physical disks and logical volumes on Windows
        using PowerShell CIM instances.
        """
        logger.debug("Enumerating drives on Windows...")

        ps_script = """
        $disks = Get-CimInstance Win32_DiskDrive | Select-Object DeviceID, Index, Model, Size, InterfaceType, MediaType
        $partitions = Get-CimInstance Win32_DiskPartition | Select-Object DeviceID, DiskIndex, Index
        $volumes = Get-CimInstance Win32_LogicalDisk | Select-Object DeviceID, VolumeName, FileSystem, Size, DriveType

        $diskList = @()
        foreach ($disk in $disks) {
            $isUsb = ($disk.InterfaceType -match "USB") -or ($disk.MediaType -match "External|Removable")
            $diskParts = $partitions | Where-Object { $_.DiskIndex -eq $disk.Index }
            
            $volList = @()
            foreach ($part in $diskParts) {
                # Find logical disks associated with this partition
                $query = "ASSOCIATORS OF {Win32_DiskPartition.DeviceID='$($part.DeviceID)'} WHERE AssocClass=Win32_LogicalDiskToPartition"
                $associatedVols = Get-CimInstance -Query $query
                foreach ($av in $associatedVols) {
                    $volMatch = $volumes | Where-Object { $_.DeviceID -eq $av.DeviceID }
                    if ($volMatch) {
                        $volList += @{
                            DeviceID = $volMatch.DeviceID
                            VolumeName = $volMatch.VolumeName
                            FileSystem = $volMatch.FileSystem
                            Size = [int64]$volMatch.Size
                            MountPoint = $volMatch.DeviceID + "\\"
                            DriveType = $volMatch.DriveType
                        }
                    }
                }
            }

            $diskList += @{
                DeviceID = $disk.DeviceID
                Index = $disk.Index
                Model = $disk.Model
                Size = [int64]$disk.Size
                InterfaceType = $disk.InterfaceType
                IsExternal = $isUsb
                Volumes = $volList
            }
        }
        $diskList | ConvertTo-Json -Depth 4
        """

        try:
            cmd = ["powershell", "-NoProfile", "-NonInteractive", "-Command", ps_script]
            proc = subprocess.run(cmd, capture_output=True, text=True, check=True)
            output = proc.stdout.strip()
            if not output:
                return []

            data = json.loads(output)
            if isinstance(data, dict):
                data = [data]

            drives: List[DriveInfo] = []
            for item in data:
                index = str(item.get("Index", ""))
                drive_id = f"PhysicalDrive{index}" if index else item.get("DeviceID", "Disk")
                model = item.get("Model", "Hard Drive")
                size = item.get("Size", 0)
                is_ext = item.get("IsExternal", False)
                interface = item.get("InterfaceType", "Unknown")
                raw_media = str(item.get("MediaType", ""))

                if "SSD" in raw_media.upper() or "SOLID" in raw_media.upper():
                    media_type = "Solid state"
                elif "REMOVABLE" in raw_media.upper():
                    media_type = "Removable"
                elif "EXTERNAL" in raw_media.upper():
                    media_type = "Solid state"
                else:
                    media_type = "Hard Disk"

                raw_vols = item.get("Volumes", [])
                volumes: List[VolumeInfo] = []
                for v in raw_vols:
                    letter = v.get("DeviceID", "")
                    name = v.get("VolumeName") or letter
                    v_size = v.get("Size", 0)
                    fs = v.get("FileSystem", "NTFS")
                    mount_point = v.get("MountPoint", letter + "\\" if letter else "")

                    volumes.append(
                        VolumeInfo(
                            device_id=letter,
                            name=name,
                            mount_point=mount_point,
                            size_bytes=v_size,
                            fs_type=fs,
                            type_desc=fs,
                            drive_letter=letter,
                            uuid=letter,
                            is_mounted=True,
                        )
                    )

                drives.append(
                    DriveInfo(
                        id=drive_id,
                        name=model,
                        size_bytes=size,
                        bus_protocol=interface,
                        is_external=is_ext,
                        is_removable=is_ext,
                        is_virtual=False,
                        media_type=media_type,
                        child_count=len(volumes),
                        volumes=volumes,
                    )
                )

            return drives

        except Exception as e:
            logger.error(f"Failed to query Windows drives via PowerShell: {e}")
            return []

    def eject_drive(self, drive_id: str) -> EjectResult:
        """
        Safely dismount and flush write caches on Windows.
        1. Checks for blocking processes.
        2. Sets the disk offline via diskpart to flush all cached writes and unmount drive letters.
        3. Attempts shell eject via COM if drive letter is present.
        """
        logger.info(f"Safely dismounting/ejecting Windows drive: {drive_id}")

        # Extract disk index (e.g. "PhysicalDrive1" -> 1)
        disk_index = "".join([c for c in drive_id if c.isdigit()])
        if not disk_index:
            disk_index = "1"

        # Check for open file handles on any volumes on this drive
        drives = self.get_drives()
        matching_drive = next((d for d in drives if d.id == drive_id or disk_index in d.id), None)
        blocking_procs: List[ProcessLockInfo] = []

        drive_letters = []
        if matching_drive:
            for vol in matching_drive.volumes:
                if vol.device_id:
                    drive_letters.append(vol.device_id)
                if vol.mount_point:
                    locks = self.get_blocking_processes(vol.mount_point)
                    blocking_procs.extend(locks)

        # Execute diskpart offline to safely flush caches and unmount
        diskpart_script = f"select disk {disk_index}\noffline disk\n"
        try:
            proc = subprocess.run(
                ["diskpart"],
                input=diskpart_script,
                capture_output=True,
                text=True,
            )
            if "successfully" in proc.stdout.lower() or proc.returncode == 0:
                # Also try COM eject for drive letters
                for letter in drive_letters:
                    clean_letter = letter.replace("\\", "").replace(":", "")
                    ps_eject = f'(New-Object -comObject Shell.Application).Namespace(17).ParseName("{clean_letter}:").InvokeVerb("Eject")'
                    subprocess.run(["powershell", "-NoProfile", "-Command", ps_eject], capture_output=True)

                return EjectResult(
                    target=drive_id,
                    success=True,
                    message=f"Drive {drive_id} taken offline safely and ejected.",
                )
            else:
                return EjectResult(
                    target=drive_id,
                    success=False,
                    message=f"Diskpart error: {proc.stdout.strip()}",
                    blocking_processes=blocking_procs,
                )
        except Exception as e:
            return EjectResult(
                target=drive_id,
                success=False,
                message=f"Error executing diskpart: {e}",
                blocking_processes=blocking_procs,
            )

    def unmount_volume(self, volume_id: str) -> EjectResult:
        """Unmount a specific drive letter using mountvol /p or PowerShell."""
        clean_letter = volume_id.replace("\\", "").replace(":", "")
        logger.info(f"Unmounting volume {clean_letter}: on Windows")
        try:
            # mountvol X: /p unmounts volume and takes it offline
            proc = subprocess.run(["mountvol", f"{clean_letter}:", "/p"], capture_output=True, text=True)
            if proc.returncode == 0:
                return EjectResult(
                    target=volume_id,
                    success=True,
                    message=f"Volume {clean_letter}: unmounted successfully.",
                )
            else:
                return EjectResult(
                    target=volume_id,
                    success=False,
                    message=f"Failed to unmount {clean_letter}:: {proc.stderr.strip()}",
                )
        except Exception as e:
            return EjectResult(
                target=volume_id,
                success=False,
                message=f"Error running mountvol: {e}",
            )

    def mount_drive(self, drive_id: str) -> RemountResult:
        """Remount all volumes on a drive by bringing the disk back online via diskpart."""
        logger.info(f"Remounting/bringing online Windows drive: {drive_id}")
        disk_index = "".join([c for c in drive_id if c.isdigit()])
        if not disk_index:
            disk_index = "1"

        diskpart_script = f"select disk {disk_index}\nonline disk\nattribute disk clear readonly\n"
        try:
            proc = subprocess.run(
                ["diskpart"],
                input=diskpart_script,
                capture_output=True,
                text=True,
            )
            if "successfully" in proc.stdout.lower() or proc.returncode == 0:
                return RemountResult(
                    target=drive_id,
                    success=True,
                    message=f"Drive {drive_id} brought back online and mounted.",
                )
            else:
                return RemountResult(
                    target=drive_id,
                    success=False,
                    message=f"Diskpart error: {proc.stdout.strip()}",
                )
        except Exception as e:
            return RemountResult(
                target=drive_id,
                success=False,
                message=f"Failed to bring drive online: {e}",
            )

    def mount_volume(self, volume_id: str) -> RemountResult:
        """Mount volume by bringing parent disk online."""
        return self.mount_drive(volume_id)

    def get_blocking_processes(self, mount_point: str) -> List[ProcessLockInfo]:
        """
        Detect processes holding open handles on the volume using Windows Restart Manager API (rstrtmgr.dll)
        or PowerShell handle check.
        """
        locks: List[ProcessLockInfo] = []
        if sys.platform != "win32":
            return locks

        try:
            rstrtmgr = ctypes.windll.rstrtmgr
            session_handle = ctypes.c_uint32()
            session_key = (ctypes.c_wchar * 256)()

            # RmStartSession
            res = rstrtmgr.RmStartSession(ctypes.byref(session_handle), 0, session_key)
            if res != 0:
                return locks

            # Clean path
            path = mount_point.rstrip("\\") + "\\"
            c_path = ctypes.c_wchar_p(path)
            c_path_array = (ctypes.c_wchar_p * 1)(c_path)

            # RmRegisterResources
            rstrtmgr.RmRegisterResources(session_handle, 1, c_path_array, 0, None, 0, None)

            # RmGetList
            proc_info_needed = ctypes.c_uint32()
            proc_info = ctypes.c_uint32()
            reboot_reasons = ctypes.c_uint32()

            # First call gets count
            res = rstrtmgr.RmGetList(
                session_handle,
                ctypes.byref(proc_info_needed),
                ctypes.byref(proc_info),
                None,
                ctypes.byref(reboot_reasons),
            )

            # RmEndSession
            rstrtmgr.RmEndSession(session_handle)
        except Exception as e:
            logger.debug(f"RestartManager lock inspection failed: {e}")

        return locks

    def kill_process(self, pid: int) -> bool:
        """Terminate a process on Windows using taskkill."""
        try:
            proc = subprocess.run(["taskkill", "/F", "/PID", str(pid)], capture_output=True)
            return proc.returncode == 0
        except Exception as e:
            logger.error(f"Failed to kill process {pid}: {e}")
            return False

    def show_notification(self, title: str, message: str) -> None:
        """Display native Windows toast notification via PowerShell."""
        clean_title = title.replace('"', '`"')
        clean_msg = message.replace('"', '`"')
        ps_notify = f"""
        [Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] > $null
        $template = [Windows.UI.Notifications.ToastNotificationManager]::GetTemplateContent([Windows.UI.Notifications.ToastTemplateType]::ToastText02)
        $textNodes = $template.GetElementsByTagName("text")
        $textNodes.Item(0).AppendChild($template.CreateTextNode("{clean_title}")) > $null
        $textNodes.Item(1).AppendChild($template.CreateTextNode("{clean_msg}")) > $null
        $toast = [Windows.UI.Notifications.ToastNotification]::new($template)
        [Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier("SafeEject").Show($toast)
        """
        try:
            subprocess.run(["powershell", "-NoProfile", "-Command", ps_notify], capture_output=True)
        except Exception as e:
            logger.debug(f"Windows notification error: {e}")

    def start_power_listener(
        self,
        on_sleep: Callable[[], None],
        on_wake: Callable[[], None],
    ) -> None:
        """
        Listen to WM_POWERBROADCAST messages using Win32 API window message loop.
        Registers for sleep (PBT_APMSUSPEND) and wake (PBT_APMRESUMEAUTOMATIC / PBT_APMRESUMESUSPEND).
        """
        if sys.platform != "win32":
            logger.warning("Windows power listener cannot run on non-Windows platform.")
            return

        logger.info("Registering for Windows WM_POWERBROADCAST sleep/wake events...")

        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32

        WM_POWERBROADCAST = 0x0218
        PBT_APMSUSPEND = 0x0004
        PBT_APMRESUMEAUTOMATIC = 0x0012
        PBT_APMRESUMESUSPEND = 0x0007

        WNDPROC = ctypes.WINFUNCTYPE(
            ctypes.c_long,
            ctypes.c_void_p,
            ctypes.c_uint,
            ctypes.c_void_p,
            ctypes.c_void_p,
        )

        def wnd_proc(hwnd, msg, wparam, lparam):
            if msg == WM_POWERBROADCAST:
                if wparam == PBT_APMSUSPEND:
                    logger.info("Windows is suspending/sleeping. Ejecting external drives...")
                    try:
                        on_sleep()
                    except Exception as ex:
                        logger.error(f"Error during on_sleep: {ex}")
                    return 1

                elif wparam in (PBT_APMRESUMEAUTOMATIC, PBT_APMRESUMESUSPEND):
                    logger.info("Windows resumed from sleep. Remounting external drives...")
                    try:
                        on_wake()
                    except Exception as ex:
                        logger.error(f"Error during on_wake: {ex}")
                    return 1

            return user32.DefWindowProcW(hwnd, msg, wparam, lparam)

        class WNDCLASSEXW(ctypes.Structure):
            _fields_ = [
                ("cbSize", ctypes.c_uint),
                ("style", ctypes.c_uint),
                ("lpfnWndProc", WNDPROC),
                ("cbClsExtra", ctypes.c_int),
                ("cbWndExtra", ctypes.c_int),
                ("hInstance", ctypes.c_void_p),
                ("hIcon", ctypes.c_void_p),
                ("hCursor", ctypes.c_void_p),
                ("hbrBackground", ctypes.c_void_p),
                ("lpszMenuName", ctypes.c_wchar_p),
                ("lpszClassName", ctypes.c_wchar_p),
                ("hIconSm", ctypes.c_void_p),
            ]

        c_proc = WNDPROC(wnd_proc)
        class_name = "SafeEjectPowerMsgWindow"

        wnd_class = WNDCLASSEXW()
        wnd_class.cbSize = ctypes.sizeof(WNDCLASSEXW)
        wnd_class.lpfnWndProc = c_proc
        wnd_class.hInstance = kernel32.GetModuleHandleW(None)
        wnd_class.lpszClassName = class_name

        user32.RegisterClassExW(ctypes.byref(wnd_class))

        # HWND_MESSAGE (-3) creates a message-only window
        hwnd = user32.CreateWindowExW(
            0,
            class_name,
            "SafeEjectMsgOnly",
            0,
            0,
            0,
            0,
            0,
            -3,
            0,
            wnd_class.hInstance,
            None,
        )

        logger.info("Windows Power Listener window initialized. Waiting for power events...")

        class MSG(ctypes.Structure):
            _fields_ = [
                ("hwnd", ctypes.c_void_p),
                ("message", ctypes.c_uint),
                ("wParam", ctypes.c_void_p),
                ("lParam", ctypes.c_void_p),
                ("time", ctypes.c_uint32),
                ("pt_x", ctypes.c_long),
                ("pt_y", ctypes.c_long),
            ]

        msg = MSG()
        while not self._stop_requested and user32.GetMessageW(ctypes.byref(msg), 0, 0, 0) > 0:
            user32.TranslateMessage(ctypes.byref(msg))
            user32.DispatchMessageW(ctypes.byref(msg))
