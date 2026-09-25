@echo off
REM ==============================================================================
REM Safe Drive Ejector Tool - Windows Standalone Build & Packaging Script
REM Freezes SafeDriveEjector (System Tray GUI) and safeeject_cli (CLI) using PyInstaller
REM ==============================================================================

setlocal enabledelayedexpansion
set "ROOT_DIR=%~dp0"
cd /d "%ROOT_DIR%"

set "BUILD_DIR=%ROOT_DIR%.build_windows"
set "DIST_DIR=%ROOT_DIR%dist\SafeDriveEjector_Windows"

echo =======================================================
echo    Building Safe Drive Ejector for Windows (Standalone)
echo =======================================================

REM 1. Clean previous build directories
echo [1/5] Cleaning build directories...
if exist "%BUILD_DIR%" rd /s /q "%BUILD_DIR%"
if exist "%DIST_DIR%" rd /s /q "%DIST_DIR%"
mkdir "%BUILD_DIR%" 2>nul
mkdir "%DIST_DIR%" 2>nul

REM 2. Verify or Install Build Dependencies
echo [2/5] Checking PyInstaller and GUI dependencies...
where pyinstaller >nul 2>&1
if errorlevel 1 (
    echo PyInstaller not found. Installing into Python environment...
    python -m pip install --upgrade pip pyinstaller pystray pillow
)

REM 3. Compile Standalone Binaries via Spec
echo [3/5] Compiling SafeDriveEjector Tray & safeeject_cli with PyInstaller...
pyinstaller --clean --noconfirm ^
    --workpath "%BUILD_DIR%\work" ^
    --distpath "%DIST_DIR%" ^
    safeeject_windows.spec

REM Move safeeject_cli.exe inside the SafeDriveEjector directory
if exist "%DIST_DIR%\safeeject_cli.exe" (
    move /Y "%DIST_DIR%\safeeject_cli.exe" "%DIST_DIR%\SafeDriveEjector\" >nul
)

REM 4. Copy Release Helpers and Documentation
echo [4/5] Copying release helpers and documentation...
copy "%ROOT_DIR%install\windows\install_release.bat" "%DIST_DIR%\SafeDriveEjector\install.bat" >nul
copy "%ROOT_DIR%install\windows\uninstall_release.bat" "%DIST_DIR%\SafeDriveEjector\uninstall.bat" >nul
copy "%ROOT_DIR%install\windows\register_task.ps1" "%DIST_DIR%\SafeDriveEjector\register_task.ps1" >nul
copy "%ROOT_DIR%LICENSE" "%DIST_DIR%\SafeDriveEjector\LICENSE" >nul
copy "%ROOT_DIR%README.md" "%DIST_DIR%\SafeDriveEjector\README.md" >nul
if exist "%ROOT_DIR%FIRST_LAUNCH_INSTRUCTIONS.txt" copy "%ROOT_DIR%FIRST_LAUNCH_INSTRUCTIONS.txt" "%DIST_DIR%\SafeDriveEjector\FIRST_LAUNCH_INSTRUCTIONS.txt" >nul

REM 5. Create Standalone ZIP Archive for Distribution
echo [5/5] Creating distribution archive SafeDriveEjector-1.0.0-Windows.zip...
powershell -NoProfile -Command "Compress-Archive -Path '%DIST_DIR%\SafeDriveEjector' -DestinationPath '%ROOT_DIR%dist\SafeDriveEjector-1.0.0-Windows.zip' -Force" 2>nul

echo.
echo =======================================================
echo WINDOWS BUILD COMPLETED SUCCESSFULLY!
echo Release Folder: %DIST_DIR%\SafeDriveEjector
echo ZIP Archive:    %ROOT_DIR%dist\SafeDriveEjector-1.0.0-Windows.zip
echo =======================================================
if not defined CI pause
