# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller build specification for CystoMoto - Windows.

Produces a one-dir output in dist/CystoMoto/ which Inno Setup wraps
into a single installer .exe.
Run from the repository root: pyinstaller CystoMoto.spec --noconfirm
"""

import os

source_script = os.path.join("cysto_app", "cysto_app.py")
icon_file = os.path.join("cysto_app", "ui", "icons", "CystoMoto.ico")

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
        "serial.serialwin32",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["tkinter", "unittest"],
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
    upx=True,
    upx_exclude=[],
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
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
    upx=True,
    upx_exclude=[],
    name="CystoMoto",
)
