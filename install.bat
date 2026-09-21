@echo off
REM Safe Drive Ejector Tool - Windows Installer
REM Sets up Safe Drive Ejector Tool to automatically launch in Windows System Tray upon user logon.

echo =======================================================
echo   Safe Drive Ejector Tool - Windows Installer
echo =======================================================

set "SCRIPT_DIR=%~dp0"
cd /d "%SCRIPT_DIR%"

echo [1/2] Installing dependencies...
python -m pip install -r requirements.txt

echo [2/2] Registering in Windows Startup folder...
call "%SCRIPT_DIR%install\windows\install_startup.bat"

echo.
echo =======================================================
echo SUCCESS! Safe Drive Ejector Tool is now installed!
echo Look for the Eject icon in your Windows System Tray (bottom right).
echo =======================================================
pause
