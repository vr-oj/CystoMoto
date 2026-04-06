# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller build specification for CystoMoto - macOS.

Produces a .app bundle for local packaging into a .dmg by build_macos.sh.
Run from the repository root: pyinstaller CystoMoto_macos.spec --noconfirm
"""

import os

source_script = os.path.join("cysto_app", "cysto_app.py")
icon_file = os.path.join("cysto_app", "ui", "icons", "CystoMoto.icns")

app_version = os.environ.get("CYSTOMOTO_VERSION", "1.0.0")
bundle_identifier = os.environ.get("CYSTOMOTO_BUNDLE_ID", "com.cystomoto.app")
minimum_macos = os.environ.get("CYSTOMOTO_MIN_MACOS", "10.14")

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
    upx=False,  # UPX can corrupt Qt dylibs on macOS
    upx_exclude=[],
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=True,  # Enables drag-and-drop onto Dock icon
    target_arch=None,  # None = current python arch
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
    bundle_identifier=bundle_identifier,
    version=app_version,
    info_plist={
        "CFBundleName": "CystoMoto",
        "CFBundleDisplayName": "CystoMoto",
        "CFBundleVersion": app_version,
        "CFBundleShortVersionString": app_version,
        "CFBundleIdentifier": bundle_identifier,
        "NSHighResolutionCapable": True,
        "NSHumanReadableCopyright": "CC BY-NC-SA 4.0",
        "LSMinimumSystemVersion": minimum_macos,
        "NSPrincipalClass": "NSApplication",
        "NSRequiresAquaSystemAppearance": False,
    },
)
