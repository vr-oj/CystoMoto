#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Validate PyQt5/Qt runtime integrity without creating QApplication."""

from __future__ import annotations

import argparse
import platform
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "cysto_app"))

from utils.qt_runtime import (  # noqa: E402
    PINNED_QT_STACK,
    architecture_compatible,
    clear_hidden_flags,
    file_description,
    find_duplicate_dist_info,
    find_hidden_paths,
    find_stale_site_packages_entries,
    is_qt_related_entry,
    pinned_stack_mismatches,
    qt_stack_normalized_names,
    read_installed_versions,
    resolve_qt_runtime_info,
    run_stat_flags,
)


def _print_header(title: str):
    print(f"\n== {title} ==")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Treat stale artifacts and version mismatches as hard failures.",
    )
    args = parser.parse_args()

    errors = []
    warnings = []

    _print_header("Environment")
    print(f"python: {sys.executable}")
    print(f"machine: {platform.machine()}")
    print(f"platform: {platform.platform()}")

    _print_header("Qt Runtime")
    try:
        info = resolve_qt_runtime_info()
    except Exception as e:
        errors.append(f"Failed to resolve PyQt5 Qt runtime paths: {e}")
        info = None
    else:
        print(f"site-packages: {info.site_packages_path}")
        print(f"PyQt5 Qt prefix: {info.prefix_path}")
        print(f"plugins path: {info.plugins_path}")
        print(f"platforms path: {info.platforms_path}")
        print(f"cocoa plugin: {info.cocoa_plugin_path}")
        print(f"stat prefix: {run_stat_flags(info.prefix_path)}")
        print(f"stat plugins: {run_stat_flags(info.plugins_path)}")
        print(f"stat platforms: {run_stat_flags(info.platforms_path)}")
        print(f"stat libqcocoa: {run_stat_flags(info.cocoa_plugin_path)}")

        if not info.plugins_path.is_dir():
            errors.append(f"Missing plugins directory: {info.plugins_path}")
        if not info.platforms_path.is_dir():
            errors.append(f"Missing platforms directory: {info.platforms_path}")
        if sys.platform == "darwin" and not info.cocoa_plugin_path.is_file():
            errors.append(f"Missing cocoa platform plugin: {info.cocoa_plugin_path}")

    _print_header("Pinned Qt Stack")
    versions = read_installed_versions(PINNED_QT_STACK.keys())
    for name in PINNED_QT_STACK:
        print(f"{name}: {versions.get(name, '') or 'NOT INSTALLED'}")
    mismatches = pinned_stack_mismatches(versions)
    if mismatches:
        for pkg, (expected, found) in mismatches.items():
            msg = f"Version mismatch for {pkg}: expected {expected}, found {found or 'missing'}"
            (errors if args.strict else warnings).append(msg)

    if info is not None:
        _print_header("Stale/Duplicate Artifacts")
        stale_entries = find_stale_site_packages_entries(info.site_packages_path)
        qt_stale = [p for p in stale_entries if is_qt_related_entry(p)]
        if qt_stale:
            for p in qt_stale:
                msg = f"Stale Qt/PyQt artifact candidate: {p}"
                (errors if args.strict else warnings).append(msg)
        else:
            print("No stale Qt/PyQt artifact candidates found.")

        dupes = find_duplicate_dist_info(info.site_packages_path)
        qt_norm_names = set(qt_stack_normalized_names().keys())
        qt_dupes = {k: v for k, v in dupes.items() if k in qt_norm_names}
        if qt_dupes:
            for norm_name, paths in qt_dupes.items():
                msg = f"Duplicate dist-info for {norm_name}: {', '.join(str(p) for p in paths)}"
                (errors if args.strict else warnings).append(msg)
        else:
            print("No duplicate Qt/PyQt dist-info directories found.")

        _print_header("Hidden-Flag Remediation")
        if sys.platform == "darwin":
            key_paths = [
                info.prefix_path,
                info.plugins_path,
                info.platforms_path,
                info.cocoa_plugin_path,
            ]
            hidden_key_before = [p for p in key_paths if "hidden " in run_stat_flags(p)]
            print(f"critical hidden paths before: {len(hidden_key_before)}")
            if hidden_key_before:
                for p in hidden_key_before:
                    print(f"- hidden: {p}")
            removed, remaining = clear_hidden_flags(info.prefix_path, recursive=True)
            print(f"recursive hidden-flag clear removed: {removed}")
            hidden_key_after = [p for p in key_paths if "hidden " in run_stat_flags(p)]
            print(f"critical hidden paths after: {len(hidden_key_after)}")
            if hidden_key_after:
                errors.append(
                    "Critical Qt paths still hidden after remediation: "
                    + ", ".join(str(p) for p in hidden_key_after)
                )
            # Informational only: Qt wheels may carry extra hidden flags in non-critical trees.
            remaining_paths = find_hidden_paths(info.prefix_path)
            if remaining_paths:
                warnings.append(
                    f"Non-critical hidden flags still present under Qt tree ({len(remaining_paths)} entries)."
                )
        else:
            print("Hidden-flag remediation is macOS-only.")

        _print_header("Architecture Compatibility")
        py_desc = file_description(Path(sys.executable))
        print(py_desc)
        if sys.platform == "darwin":
            cocoa_desc = file_description(info.cocoa_plugin_path)
            print(cocoa_desc)
            if not architecture_compatible(cocoa_desc, platform.machine()):
                errors.append(
                    f"Architecture mismatch: plugin does not match machine {platform.machine()}"
                )

    if warnings:
        _print_header("Warnings")
        for w in warnings:
            print(f"- {w}")
    if errors:
        _print_header("Errors")
        for e in errors:
            print(f"- {e}")
        print("\nResult: FAIL")
        return 1

    print("\nResult: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
