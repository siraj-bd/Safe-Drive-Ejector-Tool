@echo off
REM Safe Drive Ejector Tool - Standalone Windows Installer
REM No Python or pip required.

setlocal enabledelayedexpansion
set "SRC_DIR=%~dp0"
set "INSTALL_DIR=%LOCALAPPDATA%\Programs\SafeDriveEjector"

echo =======================================================
echo   Safe Drive Ejector Tool - Windows Installer
echo =======================================================
echo [1/3] Installing application to: %INSTALL_DIR%
if not exist "%INSTALL_DIR%" mkdir "%INSTALL_DIR%" 2>nul
xcopy /E /I /Y "%SRC_DIR%*" "%INSTALL_DIR%\" >nul

echo [2/3] Creating Windows Startup shortcut...
set "STARTUP_FOLDER=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup"
set "VBS_PATH=%TEMP%\create_safeeject_shortcut.vbs"

(
    echo Set oWS = WScript.CreateObject^("WScript.Shell"^)
    echo sLinkFile = "%STARTUP_FOLDER%\SafeDriveEjector.lnk"
    echo Set oLink = oWS.CreateShortcut^(sLinkFile^)
    echo oLink.TargetPath = "%INSTALL_DIR%\SafeDriveEjector.exe"
    echo oLink.WorkingDirectory = "%INSTALL_DIR%"
    echo oLink.Description = "Safe Drive Ejector Tool"
    echo oLink.Save
) > "%VBS_PATH%"
cscript //nologo "%VBS_PATH%" 2>nul
del "%VBS_PATH%" 2>nul

echo [3/3] Registering Sleep & Wake scheduled tasks...
powershell -NoProfile -ExecutionPolicy Bypass -Command "& '%INSTALL_DIR%\register_task.ps1'" 2>nul

echo.
echo =======================================================
echo SUCCESS! Safe Drive Ejector Tool is now installed!
echo Starting Safe Drive Ejector in System Tray...
echo =======================================================
start "" "%INSTALL_DIR%\SafeDriveEjector.exe"
pause
