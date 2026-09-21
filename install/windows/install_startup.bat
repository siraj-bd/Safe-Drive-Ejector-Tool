@echo off
REM SafeEject Windows Installer
REM Sets up SafeEject to automatically launch in the system tray upon user logon.

echo ===================================================
echo   SafeEject Windows Startup Installer
echo ===================================================

set "SCRIPT_DIR=%~dp0..\.."
cd /d "%SCRIPT_DIR%"

echo [1/2] Checking Python dependencies...
python -m pip install -r requirements.txt

echo [2/2] Creating Startup shortcut...
set "VBS_PATH=%TEMP%\create_safeeject_shortcut.vbs"
set "STARTUP_FOLDER=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup"
set "TARGET_BAT=%SCRIPT_DIR%\run_tray_windows.bat"

REM Create launcher batch file that runs pythonw (no black console window)
(
echo @echo off
echo cd /d "%SCRIPT_DIR%"
echo start pythonw main.py tray
) > "%TARGET_BAT%"

REM Create shortcut in Startup directory
(
echo Set oWS = WScript.CreateObject^("WScript.Shell"^)
echo sLinkFile = "%STARTUP_FOLDER%\SafeEject.lnk"
echo Set oLink = oWS.CreateShortcut^(sLinkFile^)
echo oLink.TargetPath = "%TARGET_BAT%"
echo oLink.WorkingDirectory = "%SCRIPT_DIR%"
echo oLink.Description = "SafeEject External Disk Protector"
echo oLink.WindowStyle = 7
echo oLink.Save
) > "%VBS_PATH%"

cscript //nologo "%VBS_PATH%"
del "%VBS_PATH%"

echo.
echo SafeEject configured successfully!
echo SafeEject will now start automatically in the Windows System Tray on startup.
echo To start it right now, double-click: run_tray_windows.bat
echo ===================================================
pause
