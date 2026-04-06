@echo off
setlocal EnableExtensions EnableDelayedExpansion

set "APP_VERSION=%CYSTOMOTO_VERSION%"
if "%APP_VERSION%"=="" set "APP_VERSION=1.0.0"
set "APP_URL=%CYSTOMOTO_APP_URL%"
if "%APP_URL%"=="" set "APP_URL=https://github.com/valdovegarodr/CystoMoto"

echo ============================================================
echo  CystoMoto Windows Build Script
echo  Version: %APP_VERSION%
echo ============================================================
echo.

:: Check Python
python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python not found on PATH.
    echo        Install Python 3.10+ from https://python.org and ensure it is on PATH.
    exit /b 1
)

:: Enforce 64-bit build toolchain
for /f %%i in ('python -c "import ctypes; print(ctypes.sizeof(ctypes.c_void_p) * 8)"') do set "PY_BITS=%%i"
if not "%PY_BITS%"=="64" (
    echo ERROR: Detected %PY_BITS%-bit Python on PATH.
    echo        Use 64-bit Python to produce a 64-bit installer and binaries.
    exit /b 1
)

:: Check PyInstaller
pyinstaller --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: PyInstaller not found.
    echo        Run: pip install pyinstaller
    exit /b 1
)

:: Clean previous build
echo [1/4] Cleaning previous build artifacts...
if exist dist\CystoMoto  rmdir /s /q dist\CystoMoto
if exist build\CystoMoto rmdir /s /q build\CystoMoto
echo        Done.
echo.

:: Run PyInstaller
echo [2/4] Running PyInstaller...
set "CYSTOMOTO_VERSION=%APP_VERSION%"
pyinstaller CystoMoto.spec --noconfirm
if errorlevel 1 (
    echo ERROR: PyInstaller failed. Check output above.
    exit /b 1
)
echo        Done.
echo.

:: Locate Inno Setup
echo [3/4] Locating Inno Setup 6 compiler...
set "ISCC_PATH="

if exist "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" set "ISCC_PATH=C:\Program Files (x86)\Inno Setup 6\ISCC.exe"
if not defined ISCC_PATH if exist "C:\Program Files\Inno Setup 6\ISCC.exe" set "ISCC_PATH=C:\Program Files\Inno Setup 6\ISCC.exe"
if not defined ISCC_PATH (
    for /f "delims=" %%I in ('where ISCC.exe 2^>nul') do (
        set "ISCC_PATH=%%I"
        goto :iscc_found
    )
)
if not defined ISCC_PATH goto :iscc_missing

:iscc_found
echo        Found: %ISCC_PATH%
echo.
goto :run_inno

:iscc_missing
    echo WARNING: Inno Setup 6 compiler (ISCC.exe) not found.
    echo          Download from: https://jrsoftware.org/isinfo.php
    echo          PyInstaller output is at dist\CystoMoto\ - run Inno Setup manually.
    echo.
    echo Build partially complete: PyInstaller succeeded, installer step skipped.
    exit /b 0

:run_inno

:: Run Inno Setup
echo [4/4] Building installer with Inno Setup...
if not exist installer_output mkdir installer_output
"%ISCC_PATH%" /DMyAppVersion="%APP_VERSION%" /DMyAppURL="%APP_URL%" installer\windows\CystoMoto.iss
if errorlevel 1 (
    echo ERROR: Inno Setup failed. Check output above.
    exit /b 1
)
echo        Done.
echo.

echo ============================================================
echo  BUILD COMPLETE
echo  Installer: installer_output\CystoMoto_Setup_v%APP_VERSION%.exe
echo ============================================================
