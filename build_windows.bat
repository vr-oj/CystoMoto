@echo off
setlocal enabledelayedexpansion

echo ============================================================
echo  CystoMoto Windows Build Script
echo  Version: 0.0.0
echo ============================================================
echo.

:: ── Check Python ─────────────────────────────────────────────────────────────
python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python not found on PATH.
    echo        Install Python 3.10+ from https://python.org and ensure it is on PATH.
    exit /b 1
)

:: ── Check PyInstaller ─────────────────────────────────────────────────────────
pyinstaller --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: PyInstaller not found.
    echo        Run: pip install pyinstaller
    exit /b 1
)

:: ── Clean previous build ──────────────────────────────────────────────────────
echo [1/4] Cleaning previous build artifacts...
if exist dist\CystoMoto  rmdir /s /q dist\CystoMoto
if exist build\CystoMoto rmdir /s /q build\CystoMoto
echo        Done.
echo.

:: ── Run PyInstaller ───────────────────────────────────────────────────────────
echo [2/4] Running PyInstaller...
pyinstaller CystoMoto.spec --noconfirm
if errorlevel 1 (
    echo ERROR: PyInstaller failed. Check output above.
    exit /b 1
)
echo        Done.
echo.

:: ── Locate Inno Setup ────────────────────────────────────────────────────────
echo [3/4] Locating Inno Setup 6 compiler...
set "ISCC_PATH="

if exist "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" (
    set "ISCC_PATH=C:\Program Files (x86)\Inno Setup 6\ISCC.exe"
) else if exist "C:\Program Files\Inno Setup 6\ISCC.exe" (
    set "ISCC_PATH=C:\Program Files\Inno Setup 6\ISCC.exe"
)

if not defined ISCC_PATH (
    echo WARNING: Inno Setup 6 not found in standard Program Files locations.
    echo          Download from: https://jrsoftware.org/isinfo.php
    echo          PyInstaller output is at dist\CystoMoto\ — run Inno Setup manually.
    echo.
    echo Build partially complete: PyInstaller succeeded, installer step skipped.
    exit /b 0
)
echo        Found: !ISCC_PATH!
echo.

:: ── Run Inno Setup ───────────────────────────────────────────────────────────
echo [4/4] Building installer with Inno Setup...
if not exist installer_output mkdir installer_output
"!ISCC_PATH!" installer\windows\CystoMoto.iss
if errorlevel 1 (
    echo ERROR: Inno Setup failed. Check output above.
    exit /b 1
)
echo        Done.
echo.

echo ============================================================
echo  BUILD COMPLETE
echo  Installer: installer_output\CystoMoto_Setup_v0.0.0.exe
echo ============================================================
