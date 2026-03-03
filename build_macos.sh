#!/usr/bin/env bash
# build_macos.sh — Build CystoMoto.app and package it as a .dmg
#
# Usage:
#   ./build_macos.sh              # Full build (generates .icns, runs PyInstaller, creates DMG)
#   ./build_macos.sh --skip-icns  # Skip icon generation (use if CystoMoto.icns is already committed)
#
# Prerequisites:
#   pip install pyinstaller
#   brew install create-dmg

set -euo pipefail

APP_NAME="CystoMoto"
APP_VERSION="0.0.0"
ICON_DIR="cysto_app/ui/icons"
ICO_FILE="${ICON_DIR}/CystoMoto.ico"
ICNS_FILE="${ICON_DIR}/CystoMoto.icns"
DIST_DIR="dist"
APP_BUNDLE="${DIST_DIR}/${APP_NAME}.app"
OUTPUT_DIR="installer_output"

# Detect arch for DMG filename
ARCH=$(uname -m)
if [[ "$ARCH" == "arm64" ]]; then
    DMG_ARCH="arm64"
else
    DMG_ARCH="x86_64"
fi
DMG_NAME="${APP_NAME}_${APP_VERSION}_macOS_${DMG_ARCH}.dmg"

echo "============================================================"
echo " CystoMoto macOS Build Script"
echo " Version : ${APP_VERSION}"
echo " Arch    : ${DMG_ARCH}"
echo "============================================================"
echo

# ── Step 0: Generate .icns ────────────────────────────────────────────────────
SKIP_ICNS=0
for arg in "${@:-}"; do
    [[ "$arg" == "--skip-icns" ]] && SKIP_ICNS=1
done

if [[ $SKIP_ICNS -eq 0 ]]; then
    echo "[0/4] Generating CystoMoto.icns from CystoMoto.ico..."
    # sips cannot read .ico files — use Python/PIL to do the initial conversion
    if ! python3 -c "from PIL import Image" &>/dev/null; then
        echo "  Installing Pillow for icon conversion..."
        pip3 install pillow -q
    fi

    TMPDIR_ICON=$(mktemp -d)
    ICONSET_DIR="${TMPDIR_ICON}/CystoMoto.iconset"
    TMP_PNG="${TMPDIR_ICON}/icon_1024.png"
    mkdir -p "$ICONSET_DIR"

    python3 - << PYEOF
from PIL import Image
img = Image.open("${ICO_FILE}")
sizes = list(img.ico.sizes())
largest = max(sizes, key=lambda s: s[0] * s[1])
img.size = largest
img = img.convert("RGBA").resize((1024, 1024), Image.LANCZOS)
img.save("${TMP_PNG}", "PNG")
PYEOF

    sips -z 16   16   "$TMP_PNG" --out "${ICONSET_DIR}/icon_16x16.png"      &>/dev/null
    sips -z 32   32   "$TMP_PNG" --out "${ICONSET_DIR}/icon_16x16@2x.png"   &>/dev/null
    sips -z 32   32   "$TMP_PNG" --out "${ICONSET_DIR}/icon_32x32.png"      &>/dev/null
    sips -z 64   64   "$TMP_PNG" --out "${ICONSET_DIR}/icon_32x32@2x.png"   &>/dev/null
    sips -z 128  128  "$TMP_PNG" --out "${ICONSET_DIR}/icon_128x128.png"    &>/dev/null
    sips -z 256  256  "$TMP_PNG" --out "${ICONSET_DIR}/icon_128x128@2x.png" &>/dev/null
    sips -z 256  256  "$TMP_PNG" --out "${ICONSET_DIR}/icon_256x256.png"    &>/dev/null
    sips -z 512  512  "$TMP_PNG" --out "${ICONSET_DIR}/icon_256x256@2x.png" &>/dev/null
    sips -z 512  512  "$TMP_PNG" --out "${ICONSET_DIR}/icon_512x512.png"    &>/dev/null
    sips -z 1024 1024 "$TMP_PNG" --out "${ICONSET_DIR}/icon_512x512@2x.png" &>/dev/null

    iconutil -c icns "$ICONSET_DIR" -o "${ICNS_FILE}"
    rm -rf "$TMPDIR_ICON"
    echo "  Generated: ${ICNS_FILE}"
    echo
fi

# Confirm .icns exists
if [[ ! -f "${ICNS_FILE}" ]]; then
    echo "ERROR: ${ICNS_FILE} not found."
    echo "Run without --skip-icns, or generate it manually with sips + iconutil."
    exit 1
fi

# ── Step 1: Clean previous build ──────────────────────────────────────────────
echo "[1/4] Cleaning previous build artifacts..."
rm -rf "${DIST_DIR}/${APP_NAME}" "${APP_BUNDLE}" "build/${APP_NAME}"
echo "  Done."
echo

# ── Step 2: Run PyInstaller ───────────────────────────────────────────────────
echo "[2/4] Running PyInstaller (macOS spec)..."
pyinstaller CystoMoto_macos.spec --noconfirm
echo "  Done."
echo

# ── Step 3: Verify .app bundle ────────────────────────────────────────────────
if [[ ! -d "${APP_BUNDLE}" ]]; then
    echo "ERROR: PyInstaller did not produce ${APP_BUNDLE}"
    exit 1
fi

# ── Step 4: Create .dmg ───────────────────────────────────────────────────────
echo "[3/4] Creating .dmg with create-dmg..."
if ! command -v create-dmg &>/dev/null; then
    echo "ERROR: create-dmg not found. Install with: brew install create-dmg"
    exit 1
fi

mkdir -p "${OUTPUT_DIR}"

create-dmg \
    --volname "${APP_NAME} ${APP_VERSION}" \
    --volicon "${ICNS_FILE}" \
    --window-pos 200 120 \
    --window-size 600 400 \
    --icon-size 100 \
    --icon "${APP_NAME}.app" 175 190 \
    --hide-extension "${APP_NAME}.app" \
    --app-drop-link 425 190 \
    "${OUTPUT_DIR}/${DMG_NAME}" \
    "${DIST_DIR}/"

echo "  Done."
echo

echo "============================================================"
echo " BUILD COMPLETE"
echo " DMG: ${OUTPUT_DIR}/${DMG_NAME}"
echo "============================================================"
