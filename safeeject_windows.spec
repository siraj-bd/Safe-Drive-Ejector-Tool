# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller specification for Safe Drive Ejector Windows Standalone Release.
Builds:
  1. SafeDriveEjector (Windowed System Tray App, zero console popup)
  2. safeeject_cli.exe (Single-file Console CLI for Task Scheduler hooks & commands)
"""

import sys
from PyInstaller.utils.hooks import collect_submodules

block_cipher = None

core_submodules = collect_submodules('core')
adapter_submodules = collect_submodules('platform_adapters')
ui_submodules = collect_submodules('ui')

all_hidden = list(set(
    core_submodules +
    adapter_submodules +
    ui_submodules +
    ['pystray', 'PIL', 'PIL.Image', 'PIL.ImageDraw', 'ctypes', 'json', 'subprocess']
))

# 1. Analysis for System Tray GUI
a_tray = Analysis(
    ['main.py'],
    pathex=['.'],
    binaries=[],
    datas=[],
    hiddenimports=all_hidden,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['tests'],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz_tray = PYZ(a_tray.pure, a_tray.zipped_data, cipher=block_cipher)

exe_tray = EXE(
    pyz_tray,
    a_tray.scripts,
    [],
    exclude_binaries=True,
    name='SafeDriveEjector',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,   # Windowed (No console window)
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll_tray = COLLECT(
    exe_tray,
    a_tray.binaries,
    a_tray.zipfiles,
    a_tray.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='SafeDriveEjector',
)

# 2. Analysis for CLI & Scheduled Task Runner
a_cli = Analysis(
    ['main.py'],
    pathex=['.'],
    binaries=[],
    datas=[],
    hiddenimports=list(set(core_submodules + adapter_submodules)),
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['tests', 'pystray', 'PIL'],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz_cli = PYZ(a_cli.pure, a_cli.zipped_data, cipher=block_cipher)

exe_cli = EXE(
    pyz_cli,
    a_cli.scripts,
    a_cli.binaries,
    a_cli.zipfiles,
    a_cli.datas,
    [],
    name='safeeject_cli',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,    # Console mode for terminal output
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
