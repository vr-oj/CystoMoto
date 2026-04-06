#!/usr/bin/env bash
# build_macos.sh — Build CystoMoto.app and package it as a .dmg (local-first)
#
# Why this script builds in /tmp:
#   Building directly under iCloud-managed folders (like ~/Documents) can attach
#   extended attributes that break strict code-signing verification.
#
# Quick examples:
#   ./build_macos.sh --arch arm64
#   ./build_macos.sh --arch x86_64 --venv .cystomoto_x86
#   ./build_macos.sh --arch all
#
# Optional notarized release (recommended for public distribution):
#   export CYSTOMOTO_CODESIGN_IDENTITY='Developer ID Application: Your Name (TEAMID)'
#   export CYSTOMOTO_NOTARY_APPLE_ID='you@example.com'
#   export CYSTOMOTO_NOTARY_TEAM_ID='TEAMID'
#   export CYSTOMOTO_NOTARY_PASSWORD='app-specific-password'
#   ./build_macos.sh --arch all --notarize

set -euo pipefail

APP_NAME="CystoMoto"
DEFAULT_VERSION="1.0.0"
ICON_DIR="cysto_app/ui/icons"
ICO_FILE="${ICON_DIR}/CystoMoto.ico"
ICNS_FILE="${ICON_DIR}/CystoMoto.icns"
DEFAULT_OUTPUT_DIR="installer_output"

TARGET_ARCH="native"       # native | arm64 | x86_64 | all
VENV_PATH=""               # auto-selected per arch when empty
OUTPUT_DIR="${DEFAULT_OUTPUT_DIR}"
APP_VERSION="${CYSTOMOTO_VERSION:-${DEFAULT_VERSION}}"
SKIP_ICNS=0
NOTARIZE=0
CLEAN_WORKDIR=1

CODESIGN_IDENTITY="${CYSTOMOTO_CODESIGN_IDENTITY:-}"
NOTARY_APPLE_ID="${CYSTOMOTO_NOTARY_APPLE_ID:-}"
NOTARY_TEAM_ID="${CYSTOMOTO_NOTARY_TEAM_ID:-}"
NOTARY_PASSWORD="${CYSTOMOTO_NOTARY_PASSWORD:-}"
NOTARY_KEYCHAIN_PROFILE="${CYSTOMOTO_NOTARY_KEYCHAIN_PROFILE:-}"

# Populated by setup_python_tools
ARCH_PREFIX=()
PYTHON_BIN=""
PYINSTALLER_BIN=""

usage() {
    cat <<USAGE
Usage: ./build_macos.sh [options]

Options:
  --arch <native|arm64|x86_64|all>  Target architecture (default: native)
  --venv <path>                      Virtualenv path to use for selected arch
  --version <x.y.z>                  Version used in DMG filename and Info.plist
  --output-dir <path>                Output folder for final DMG (default: installer_output)
  --skip-icns                        Skip .icns generation
  --signing-identity <name>          Override Developer ID identity (or use env var)
  --notarize                         Submit DMG to Apple notary service and staple ticket
  --keep-workdir                     Keep temporary /tmp build folder for debugging
  -h, --help                         Show this help

Environment variables:
  CYSTOMOTO_VERSION
  CYSTOMOTO_CODESIGN_IDENTITY
  CYSTOMOTO_NOTARY_APPLE_ID
  CYSTOMOTO_NOTARY_TEAM_ID
  CYSTOMOTO_NOTARY_PASSWORD
  CYSTOMOTO_NOTARY_KEYCHAIN_PROFILE
USAGE
}

log_header() {
    local arch="$1"
    echo "============================================================"
    echo " CystoMoto macOS Build Script"
    echo " Version : ${APP_VERSION}"
    echo " Arch    : ${arch}"
    if [[ -n "${CODESIGN_IDENTITY}" ]]; then
        echo " Sign    : Developer ID"
    else
        echo " Sign    : ad-hoc"
    fi
    if [[ "${NOTARIZE}" == "1" ]]; then
        echo " Notary  : enabled"
    else
        echo " Notary  : disabled"
    fi
    echo "============================================================"
    echo
}

require_cmd() {
    local cmd="$1"
    local install_hint="${2:-}"
    if ! command -v "$cmd" >/dev/null 2>&1; then
        echo "ERROR: Required command not found: ${cmd}"
        if [[ -n "${install_hint}" ]]; then
            echo "Hint: ${install_hint}"
        fi
        exit 1
    fi
}

run_with_arch() {
    if [[ ${#ARCH_PREFIX[@]} -gt 0 ]]; then
        "${ARCH_PREFIX[@]}" "$@"
    else
        "$@"
    fi
}

parse_args() {
    while [[ $# -gt 0 ]]; do
        case "$1" in
            --arch)
                TARGET_ARCH="${2:-}"
                shift 2
                ;;
            --venv)
                VENV_PATH="${2:-}"
                shift 2
                ;;
            --version)
                APP_VERSION="${2:-}"
                shift 2
                ;;
            --output-dir)
                OUTPUT_DIR="${2:-}"
                shift 2
                ;;
            --skip-icns)
                SKIP_ICNS=1
                shift
                ;;
            --signing-identity)
                CODESIGN_IDENTITY="${2:-}"
                shift 2
                ;;
            --notarize)
                NOTARIZE=1
                shift
                ;;
            --keep-workdir)
                CLEAN_WORKDIR=0
                shift
                ;;
            -h|--help)
                usage
                exit 0
                ;;
            *)
                echo "ERROR: Unknown argument: $1"
                echo
                usage
                exit 1
                ;;
        esac
    done

    case "${TARGET_ARCH}" in
        native|arm64|x86_64|all)
            ;;
        *)
            echo "ERROR: --arch must be one of: native, arm64, x86_64, all"
            exit 1
            ;;
    esac
}

resolve_target_arch() {
    local requested="$1"
    local host
    host="$(uname -m)"

    if [[ "${requested}" == "native" ]]; then
        echo "${host}"
        return
    fi
    echo "${requested}"
}

resolve_venv_for_arch() {
    local arch="$1"
    if [[ -n "${VENV_PATH}" ]]; then
        echo "${VENV_PATH}"
        return
    fi

    if [[ "${arch}" == "x86_64" && -d ".cystomoto_x86" ]]; then
        echo ".cystomoto_x86"
        return
    fi

    echo ".cystomoto"
}

setup_python_tools() {
    local arch="$1"
    local selected_venv
    selected_venv="$(resolve_venv_for_arch "${arch}")"

    local python_bin="${selected_venv}/bin/python"
    local pyinstaller_bin="${selected_venv}/bin/pyinstaller"

    if [[ ! -x "${python_bin}" ]]; then
        echo "ERROR: Python not found at ${python_bin}"
        exit 1
    fi
    if [[ ! -x "${pyinstaller_bin}" ]]; then
        echo "ERROR: PyInstaller not found at ${pyinstaller_bin}"
        exit 1
    fi

    local host_arch
    host_arch="$(uname -m)"

    ARCH_PREFIX=()
    if [[ "${arch}" == "x86_64" && "${host_arch}" == "arm64" ]]; then
        ARCH_PREFIX=(arch -x86_64)
    elif [[ "${arch}" == "arm64" && "${host_arch}" == "x86_64" ]]; then
        echo "ERROR: arm64 build requested on Intel host without an arm64 runtime."
        echo "Build arm64 on an Apple Silicon Mac."
        exit 1
    fi

    PYTHON_BIN="${python_bin}"
    PYINSTALLER_BIN="${pyinstaller_bin}"
}

ensure_icns() {
    if [[ "${SKIP_ICNS}" == "1" ]]; then
        if [[ ! -f "${ICNS_FILE}" ]]; then
            echo "ERROR: ${ICNS_FILE} not found but --skip-icns was used."
            exit 1
        fi
        return
    fi

    echo "[0/6] Generating ${APP_NAME}.icns from CystoMoto.ico..."

    if ! run_with_arch "${PYTHON_BIN}" -c "from PIL import Image" >/dev/null 2>&1; then
        echo "  Installing Pillow in selected venv..."
        run_with_arch "${PYTHON_BIN}" -m pip install pillow
    fi

    local tmpdir_icon
    tmpdir_icon="$(mktemp -d "${TMPDIR:-/tmp}/cystomoto-icon-XXXXXX")"
    local iconset_dir="${tmpdir_icon}/CystoMoto.iconset"
    local tmp_png="${tmpdir_icon}/icon_1024.png"

    mkdir -p "${iconset_dir}"

    run_with_arch "${PYTHON_BIN}" - <<PYEOF
from PIL import Image
img = Image.open("${ICO_FILE}")
sizes = list(img.ico.sizes())
largest = max(sizes, key=lambda s: s[0] * s[1])
img.size = largest
img = img.convert("RGBA").resize((1024, 1024), Image.LANCZOS)
img.save("${tmp_png}", "PNG")
PYEOF

    sips -z 16   16   "${tmp_png}" --out "${iconset_dir}/icon_16x16.png"      >/dev/null
    sips -z 32   32   "${tmp_png}" --out "${iconset_dir}/icon_16x16@2x.png"   >/dev/null
    sips -z 32   32   "${tmp_png}" --out "${iconset_dir}/icon_32x32.png"      >/dev/null
    sips -z 64   64   "${tmp_png}" --out "${iconset_dir}/icon_32x32@2x.png"   >/dev/null
    sips -z 128  128  "${tmp_png}" --out "${iconset_dir}/icon_128x128.png"    >/dev/null
    sips -z 256  256  "${tmp_png}" --out "${iconset_dir}/icon_128x128@2x.png" >/dev/null
    sips -z 256  256  "${tmp_png}" --out "${iconset_dir}/icon_256x256.png"    >/dev/null
    sips -z 512  512  "${tmp_png}" --out "${iconset_dir}/icon_256x256@2x.png" >/dev/null
    sips -z 512  512  "${tmp_png}" --out "${iconset_dir}/icon_512x512.png"    >/dev/null
    sips -z 1024 1024 "${tmp_png}" --out "${iconset_dir}/icon_512x512@2x.png" >/dev/null

    iconutil -c icns "${iconset_dir}" -o "${ICNS_FILE}"
    rm -rf "${tmpdir_icon}"

    echo "  Generated: ${ICNS_FILE}"
    echo
}

notarize_dmg() {
    local dmg_path="$1"

    if [[ "${NOTARIZE}" != "1" ]]; then
        return
    fi

    echo "[6/6] Notarizing DMG with Apple..."

    if [[ -n "${NOTARY_KEYCHAIN_PROFILE}" ]]; then
        xcrun notarytool submit "${dmg_path}" --keychain-profile "${NOTARY_KEYCHAIN_PROFILE}" --wait
    else
        if [[ -z "${NOTARY_APPLE_ID}" || -z "${NOTARY_TEAM_ID}" || -z "${NOTARY_PASSWORD}" ]]; then
            echo "ERROR: Notarization requested but credentials are missing."
            echo "Set CYSTOMOTO_NOTARY_APPLE_ID, CYSTOMOTO_NOTARY_TEAM_ID, and CYSTOMOTO_NOTARY_PASSWORD,"
            echo "or set CYSTOMOTO_NOTARY_KEYCHAIN_PROFILE."
            exit 1
        fi
        xcrun notarytool submit "${dmg_path}" \
            --apple-id "${NOTARY_APPLE_ID}" \
            --team-id "${NOTARY_TEAM_ID}" \
            --password "${NOTARY_PASSWORD}" \
            --wait
    fi

    xcrun stapler staple -v "${dmg_path}"
    xcrun stapler validate -v "${dmg_path}"
    echo "  Notarization complete."
    echo
}

build_single_arch() {
    local arch="$1"
    setup_python_tools "${arch}"

    require_cmd create-dmg "brew install create-dmg"
    require_cmd iconutil
    require_cmd sips
    require_cmd codesign

    if [[ "${NOTARIZE}" == "1" ]]; then
        require_cmd xcrun
        if [[ -z "${CODESIGN_IDENTITY}" ]]; then
            echo "ERROR: --notarize requires a Developer ID identity."
            echo "Set CYSTOMOTO_CODESIGN_IDENTITY or use --signing-identity."
            exit 1
        fi
    fi

    local dmg_arch="${arch}"
    local dmg_name="${APP_NAME}_${APP_VERSION}_macOS_${dmg_arch}.dmg"

    log_header "${dmg_arch}"

    ensure_icns

    local work_root
    work_root="$(mktemp -d "${TMPDIR:-/tmp}/cystomoto-build-${dmg_arch}-XXXXXX")"
    local dist_dir="${work_root}/dist"
    local build_dir="${work_root}/build"
    local stage_output_dir="${work_root}/installer_output"
    local app_bundle="${dist_dir}/${APP_NAME}.app"
    local staged_dmg="${stage_output_dir}/${dmg_name}"

    cleanup() {
        local dir="${work_root:-}"
        if [[ -z "${dir}" ]]; then
            return
        fi
        if [[ "${CLEAN_WORKDIR}" == "1" ]]; then
            rm -rf "${dir}"
        else
            echo "Keeping workdir: ${dir}"
        fi
    }
    trap cleanup RETURN

    mkdir -p "${stage_output_dir}"

    echo "[1/6] Building app with PyInstaller..."
    CYSTOMOTO_VERSION="${APP_VERSION}" \
        run_with_arch "${PYINSTALLER_BIN}" CystoMoto_macos.spec \
        --noconfirm \
        --clean \
        --distpath "${dist_dir}" \
        --workpath "${build_dir}" \
        >/tmp/cystomoto-pyinstaller-${dmg_arch}.log 2>&1 || {
            echo "ERROR: PyInstaller failed for ${dmg_arch}."
            echo "Log: /tmp/cystomoto-pyinstaller-${dmg_arch}.log"
            tail -n 50 /tmp/cystomoto-pyinstaller-${dmg_arch}.log || true
            exit 1
        }
    echo "  Done."
    echo

    if [[ ! -d "${app_bundle}" ]]; then
        echo "ERROR: PyInstaller did not produce ${app_bundle}"
        exit 1
    fi

    echo "[2/6] Removing extended attributes..."
    xattr -rc "${app_bundle}" || true
    xattr -rcs "${app_bundle}" || true
    echo "  Done."
    echo

    echo "[3/6] Signing ${APP_NAME}.app..."
    if [[ -n "${CODESIGN_IDENTITY}" ]]; then
        codesign --force --deep --options runtime --timestamp --sign "${CODESIGN_IDENTITY}" "${app_bundle}"
    else
        codesign --force --deep --sign - "${app_bundle}"
    fi

    codesign --verify --deep --strict --verbose=2 "${app_bundle}" >/tmp/cystomoto-codesign-verify-${dmg_arch}.log 2>&1 || {
        echo "ERROR: codesign verification failed for ${dmg_arch}."
        echo "Log: /tmp/cystomoto-codesign-verify-${dmg_arch}.log"
        tail -n 50 /tmp/cystomoto-codesign-verify-${dmg_arch}.log || true
        exit 1
    }
    echo "  Done."
    echo

    echo "[4/6] Creating DMG..."
    create-dmg \
        --volname "${APP_NAME} ${APP_VERSION}" \
        --volicon "${ICNS_FILE}" \
        --window-pos 200 120 \
        --window-size 600 400 \
        --icon-size 100 \
        --icon "${APP_NAME}.app" 175 190 \
        --hide-extension "${APP_NAME}.app" \
        --app-drop-link 425 190 \
        "${staged_dmg}" \
        "${dist_dir}/"
    echo "  Done."
    echo

    if [[ -n "${CODESIGN_IDENTITY}" ]]; then
        echo "[5/6] Signing DMG with Developer ID..."
        codesign --force --timestamp --sign "${CODESIGN_IDENTITY}" "${staged_dmg}"
        codesign --verify --verbose=2 "${staged_dmg}" >/tmp/cystomoto-dmg-codesign-verify-${dmg_arch}.log 2>&1 || {
            echo "ERROR: DMG codesign verification failed for ${dmg_arch}."
            echo "Log: /tmp/cystomoto-dmg-codesign-verify-${dmg_arch}.log"
            tail -n 50 /tmp/cystomoto-dmg-codesign-verify-${dmg_arch}.log || true
            exit 1
        }
        echo "  Done."
        echo
    else
        echo "[5/6] Skipping DMG signing (no Developer ID identity provided)."
        echo
    fi

    notarize_dmg "${staged_dmg}"

    mkdir -p "${OUTPUT_DIR}"
    rm -f "${OUTPUT_DIR}/${dmg_name}"
    cp "${staged_dmg}" "${OUTPUT_DIR}/${dmg_name}"
    xattr -c "${OUTPUT_DIR}/${dmg_name}" || true

    echo "============================================================"
    echo " BUILD COMPLETE (${dmg_arch})"
    echo " DMG: ${OUTPUT_DIR}/${dmg_name}"
    echo "============================================================"
    echo

    if [[ -z "${CODESIGN_IDENTITY}" ]]; then
        echo "WARNING: Built with ad-hoc signature."
        echo "For public distribution without Gatekeeper issues, use Developer ID signing + notarization."
        echo
    fi

    trap - RETURN
    cleanup
}

main() {
    parse_args "$@"

    local resolved_arch
    resolved_arch="$(resolve_target_arch "${TARGET_ARCH}")"

    if [[ "${resolved_arch}" == "all" ]]; then
        build_single_arch arm64
        SKIP_ICNS=1
        build_single_arch x86_64
    else
        build_single_arch "${resolved_arch}"
    fi
}

main "$@"
