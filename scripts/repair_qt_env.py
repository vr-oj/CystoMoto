#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Repair stale Qt/PyQt artifacts and optionally reinstall pinned stack."""

from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "cysto_app"))

from utils.qt_runtime import (  # noqa: E402
    PINNED_QT_STACK,
    clear_hidden_flags,
    find_duplicate_dist_info,
    find_stale_site_packages_entries,
    is_qt_related_entry,
    normalize_dist_name,
    qt_stack_normalized_names,
    resolve_qt_runtime_info,
    site_packages_path,
)

_DIST_INFO_RE = re.compile(r"^(?P<name>.+)-(?P<version>[^-]+)\.dist-info$")


def _remove_path(path: Path, dry_run: bool):
    if dry_run:
        print(f"[dry-run] remove {path}")
        return
    if path.is_dir() and not path.is_symlink():
        shutil.rmtree(path, ignore_errors=True)
    elif path.exists():
        path.unlink(missing_ok=True)
    print(f"removed {path}")


def _pick_dist_info_to_keep(paths: list[Path], expected_version: str) -> Path:
    expected_suffix = f"-{expected_version}.dist-info"
    for path in paths:
        if path.name.endswith(expected_suffix):
            return path
    # Fallback: keep newest by mtime if expected version absent.
    return max(paths, key=lambda p: p.stat().st_mtime)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--reinstall",
        action="store_true",
        help="Force-reinstall pinned PyQt5 stack after cleanup.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print actions only; do not modify files.",
    )
    args = parser.parse_args()

    try:
        info = resolve_qt_runtime_info()
        site_pkgs = info.site_packages_path
        qt_root = info.prefix_path
    except Exception:
        info = None
        site_pkgs = site_packages_path()
        qt_root = site_pkgs / "PyQt5" / "Qt5"

    print(f"site-packages: {site_pkgs}")
    print(f"qt root: {qt_root}")

    removal_targets: list[Path] = []

    stale = find_stale_site_packages_entries(site_pkgs)
    stale_qt = [p for p in stale if is_qt_related_entry(p)]
    if stale_qt:
        print("\nStale Qt/PyQt artifact candidates:")
        for p in stale_qt:
            print(f"- {p}")
        removal_targets.extend(stale_qt)
    else:
        print("\nNo stale Qt/PyQt artifact candidates found.")

    qt_norm_names = qt_stack_normalized_names()
    dupes = find_duplicate_dist_info(site_pkgs)
    qt_dupes = {k: v for k, v in dupes.items() if k in qt_norm_names}
    if qt_dupes:
        print("\nDuplicate Qt/PyQt dist-info directories:")
        for norm_name, paths in qt_dupes.items():
            canonical = qt_norm_names[norm_name]
            expected_version = PINNED_QT_STACK[canonical]
            keep = _pick_dist_info_to_keep(paths, expected_version)
            print(f"- {norm_name}: keeping {keep.name}")
            for p in paths:
                if p != keep:
                    print(f"  - prune {p.name}")
                    removal_targets.append(p)
    else:
        print("\nNo duplicate Qt/PyQt dist-info directories found.")

    # De-duplicate while preserving order.
    unique_targets = list(dict.fromkeys(removal_targets))
    if unique_targets:
        print("\nPruning artifacts:")
        for p in unique_targets:
            _remove_path(p, dry_run=args.dry_run)
    else:
        print("\nNothing to prune.")

    print("\nClearing hidden flags on Qt tree...")
    if args.dry_run:
        print(f"[dry-run] chflags -R nohidden {qt_root}")
    else:
        removed, remaining = clear_hidden_flags(qt_root, recursive=True)
        print(f"hidden flags cleared: {removed}")
        print(f"hidden flags remaining: {remaining}")

    if args.reinstall:
        pkgs = [f"{name}=={version}" for name, version in PINNED_QT_STACK.items()]
        cmd = [
            sys.executable,
            "-m",
            "pip",
            "install",
            "--upgrade",
            "--force-reinstall",
            "--no-cache-dir",
            *pkgs,
        ]
        print("\nReinstalling pinned Qt stack:")
        print(" ".join(cmd))
        if not args.dry_run:
            subprocess.run(cmd, check=True)

    post_check_cmd = [sys.executable, str(REPO_ROOT / "scripts" / "check_qt_runtime.py"), "--strict"]
    print("\nPost-check:")
    print(" ".join(post_check_cmd))
    if not args.dry_run:
        subprocess.run(post_check_cmd, check=True)

    print("\nQt environment repair complete.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
