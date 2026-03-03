# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller build specification for CystoMoto - macOS.

Produces a .app bundle in dist/CystoMoto.app which build_macos.sh
wraps into a .dmg using create-dmg.
Run from the repository root: pyinstaller CystoMoto_macos.spec --noconfirm
"""

import os

source_script = os.path.join("cysto_app", "cysto_app.py")
icon_file = os.path.join("cysto_app", "ui", "icons", "CystoMoto.icns")

data_files = [
    (
        os.path.join("cysto_app", "ui", "icons", "*"),
        os.path.join("cysto_app", "ui", "icons"),
    ),
    (
        os.path.join("cysto_app", "ui", "style.qss"),
        os.path.join("cysto_app", "ui"),
    ),
]

a = Analysis(
    [source_script],
    pathex=[os.path.abspath("cysto_app")],
    binaries=[],
    datas=data_files,
    hiddenimports=[
        "PyQt5.sip",
        "serial.serialutil",
        "serial.serialposix",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["tkinter"],
    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="CystoMoto",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,          # UPX corrupts Qt dylibs on macOS — always leave off
    upx_exclude=[],
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=True,    # Enables drag-and-drop onto Dock icon
    target_arch=None,       # None = build for current arch (arm64 on macos-latest, x86_64 on macos-13)
    codesign_identity=None,
    entitlements_file=None,
    icon=icon_file,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="CystoMoto",
)

app = BUNDLE(
    coll,
    name="CystoMoto.app",
    icon=icon_file,
    bundle_identifier="com.cystomoto.app",
    version="0.0.0",
    info_plist={
        "CFBundleName": "CystoMoto",
        "CFBundleDisplayName": "CystoMoto",
        "CFBundleVersion": "0.0.0",
        "CFBundleShortVersionString": "0.0.0",
        "CFBundleIdentifier": "com.cystomoto.app",
        "NSHighResolutionCapable": True,
        "NSHumanReadableCopyright": "CC BY-NC-SA 4.0",
        "LSMinimumSystemVersion": "10.14",
        "NSPrincipalClass": "NSApplication",
        "NSRequiresAquaSystemAppearance": False,  # Respect system dark mode
    },
)
