@echo off
REM ==============================================================================
REM Safe Drive Ejector Tool - Windows Installer
REM Supports both Standalone Executable Release (Zero Python required)
REM and Source/Developer Installation.
REM ==============================================================================

echo =======================================================
echo   Safe Drive Ejector Tool - Windows Installer
echo =======================================================

set "ROOT_DIR=%~dp0"
cd /d "%ROOT_DIR%"

set "STANDALONE_EXE="
if exist "%ROOT_DIR%SafeDriveEjector.exe" set "STANDALONE_EXE=%ROOT_DIR%SafeDriveEjector.exe"
if exist "%ROOT_DIR%dist\SafeDriveEjector_Windows\SafeDriveEjector\SafeDriveEjector.exe" set "STANDALONE_EXE=%ROOT_DIR%dist\SafeDriveEjector_Windows\SafeDriveEjector\SafeDriveEjector.exe"

if defined STANDALONE_EXE (
    echo [Mode: Standalone Release detected]
    set "INSTALL_DIR=%LOCALAPPDATA%\Programs\SafeDriveEjector"
    echo [1/3] Installing application to: %INSTALL_DIR%
    if not exist "%INSTALL_DIR%" mkdir "%INSTALL_DIR%" 2>nul
    
    REM Copy binaries and assets
    for %%F in ("%STANDALONE_EXE%") do set "SRC_DIR=%%~dpF"
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
    
    echo [3/3] Registering Scheduled Tasks (Kernel-Power Sleep/Wake hooks)...
    powershell -NoProfile -ExecutionPolicy Bypass -Command "& '%INSTALL_DIR%\register_task.ps1'" 2>nul
    
    echo.
    echo =======================================================
    echo SUCCESS! Safe Drive Ejector Tool is now installed!
    echo Launching Safe Drive Ejector in System Tray...
    echo =======================================================
    start "" "%INSTALL_DIR%\SafeDriveEjector.exe"
) else (
    echo [Mode: Source Developer installation]
    echo [1/2] Checking Python dependencies...
    python -m pip install -r requirements.txt
    
    echo [2/2] Registering in Windows Startup folder...
    call "%ROOT_DIR%install\windows\install_startup.bat"
    
    echo.
    echo =======================================================
    echo SUCCESS! Safe Drive Ejector Tool is now installed!
    echo Look for the Eject icon in your Windows System Tray (bottom right).
    echo =======================================================
)
pause
