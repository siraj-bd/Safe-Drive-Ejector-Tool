@echo off
REM ==============================================================================
REM Safe Drive Ejector Tool - Windows Uninstaller
REM Completely stops services, removes Startup shortcuts, unregisters Scheduled Tasks,
REM cleans configurations, and removes installed application files.
REM ==============================================================================

echo =======================================================
echo   Safe Drive Ejector Tool - Windows Uninstaller
echo =======================================================

REM 1. Stop running processes
echo [1/4] Stopping running Safe Drive Ejector processes...
taskkill /F /IM SafeDriveEjector.exe 2>nul
taskkill /F /IM safeeject_cli.exe 2>nul
wmic process where "commandline like '%%main.py tray%%'" delete 2>nul
wmic process where "commandline like '%%main.py run%%'" delete 2>nul

REM 2. Unregister Scheduled Tasks
echo [2/4] Unregistering Scheduled Tasks...
powershell -NoProfile -ExecutionPolicy Bypass -Command "& '%~dp0install\windows\register_task.ps1' -Uninstall" 2>nul
schtasks /delete /tn "SafeEject_PreSleep" /f 2>nul
schtasks /delete /tn "SafeEject_PostWake" /f 2>nul

REM 3. Remove Startup shortcut
echo [3/4] Removing Startup shortcut...
set "STARTUP_LNK=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\SafeDriveEjector.lnk"
set "LEGACY_LNK=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\SafeEject.lnk"
if exist "%STARTUP_LNK%" del /f /q "%STARTUP_LNK%" 2>nul
if exist "%LEGACY_LNK%" del /f /q "%LEGACY_LNK%" 2>nul

REM 4. Remove user configurations and application directory
echo [4/4] Removing configuration and cache data...
set "CONFIG_DIR=%APPDATA%\SafeEject"
set "FALLBACK_DIR=%USERPROFILE%\.config\safe-eject"
set "INSTALL_DIR=%LOCALAPPDATA%\Programs\SafeDriveEjector"

if exist "%CONFIG_DIR%" rd /s /q "%CONFIG_DIR%" 2>nul
if exist "%FALLBACK_DIR%" rd /s /q "%FALLBACK_DIR%" 2>nul
if exist "%INSTALL_DIR%" rd /s /q "%INSTALL_DIR%" 2>nul

echo.
echo =======================================================
echo SUCCESS: Safe Drive Ejector Tool has been completely uninstalled!
echo =======================================================
pause
