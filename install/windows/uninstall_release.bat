@echo off
REM Safe Drive Ejector Tool - Standalone Windows Uninstaller

echo =======================================================
echo   Safe Drive Ejector Tool - Windows Uninstaller
echo =======================================================

echo [1/3] Stopping running processes...
taskkill /F /IM SafeDriveEjector.exe 2>nul
taskkill /F /IM safeeject_cli.exe 2>nul

echo [2/3] Removing Startup shortcut & Scheduled Tasks...
del /f /q "%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\SafeDriveEjector.lnk" 2>nul
del /f /q "%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\SafeEject.lnk" 2>nul
powershell -NoProfile -ExecutionPolicy Bypass -Command "& '%~dp0register_task.ps1' -Uninstall" 2>nul
schtasks /delete /tn "SafeEject_PreSleep" /f 2>nul
schtasks /delete /tn "SafeEject_PostWake" /f 2>nul

echo [3/3] Removing configurations & application files...
rd /s /q "%APPDATA%\SafeEject" 2>nul
rd /s /q "%LOCALAPPDATA%\Programs\SafeDriveEjector" 2>nul

echo.
echo =======================================================
echo SUCCESS: Safe Drive Ejector Tool uninstalled cleanly!
echo =======================================================
pause
