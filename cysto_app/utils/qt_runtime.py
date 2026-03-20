"""Qt runtime diagnostics and self-healing helpers for macOS/PyQt5."""

from __future__ import annotations

import os
import platform
import re
import site
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Tuple

PINNED_QT_STACK: Dict[str, str] = {
    "PyQt5": "5.15.11",
    "PyQt5-Qt5": "5.15.18",
    "PyQt5_sip": "12.18.0",
}

_STALE_NAME_RE = re.compile(r"(^~)|(~$)|( 2($|\.))")
_DIST_INFO_RE = re.compile(r"^(?P<name>.+)-(?P<version>[^-]+)\.dist-info$")


@dataclass(frozen=True)
class QtRuntimeInfo:
    pyqt_version: str
    qt_version: str
    prefix_path: Path
    plugins_path: Path
    platforms_path: Path
    cocoa_plugin_path: Path
    site_packages_path: Path


def normalize_dist_name(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def qt_stack_normalized_names() -> Dict[str, str]:
    return {
        normalize_dist_name(name): name
        for name in PINNED_QT_STACK
    }


def site_packages_path() -> Path:
    candidates = [Path(p) for p in site.getsitepackages() if Path(p).exists()]
    if candidates:
        return candidates[0]
    # Fallback for unusual virtualenv layouts.
    return Path(site.getusersitepackages())


def resolve_qt_runtime_info() -> QtRuntimeInfo:
    # Import QtCore only; do not construct QApplication here.
    from PyQt5.QtCore import QLibraryInfo, PYQT_VERSION_STR, QT_VERSION_STR

    prefix = Path(QLibraryInfo.location(QLibraryInfo.PrefixPath)).resolve()
    plugins = Path(QLibraryInfo.location(QLibraryInfo.PluginsPath)).resolve()
    if not plugins.exists():
        candidate = prefix / "plugins"
        if candidate.exists():
            plugins = candidate
    platforms = plugins / "platforms"
    cocoa_plugin = platforms / "libqcocoa.dylib"
    return QtRuntimeInfo(
        pyqt_version=PYQT_VERSION_STR,
        qt_version=QT_VERSION_STR,
        prefix_path=prefix,
        plugins_path=plugins,
        platforms_path=platforms,
        cocoa_plugin_path=cocoa_plugin,
        site_packages_path=site_packages_path(),
    )


def run_stat_flags(path: Path) -> str:
    proc = subprocess.run(
        ["stat", "-f", "%Sf %N", str(path)],
        capture_output=True,
        text=True,
        check=False,
    )
    return proc.stdout.strip() if proc.returncode == 0 else ""


def path_has_hidden_flag(path: Path) -> bool:
    out = run_stat_flags(path)
    if not out:
        return False
    flags = out.split(" ", 1)[0].lower()
    return "hidden" in flags


def find_hidden_paths(root: Path) -> List[Path]:
    if sys.platform != "darwin" or not root.exists():
        return []
    try:
        import stat as statmod
        hidden_mask = getattr(statmod, "UF_HIDDEN", 0)
    except Exception:
        hidden_mask = 0
    if hidden_mask == 0:
        return []

    hidden_paths: List[Path] = []

    def _check_path(path: Path):
        try:
            st = os.stat(path, follow_symlinks=False)
            if st.st_flags & hidden_mask:
                hidden_paths.append(path)
        except Exception:
            pass

    _check_path(root)
    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        for name in dirnames:
            _check_path(Path(dirpath) / name)
        for name in filenames:
            _check_path(Path(dirpath) / name)
    return hidden_paths


def clear_hidden_flags(root: Path, recursive: bool = True) -> Tuple[int, int]:
    if sys.platform != "darwin" or not root.exists():
        return (0, 0)
    before = find_hidden_paths(root)
    if not before:
        return (0, 0)
    try:
        import stat as statmod
        hidden_mask = getattr(statmod, "UF_HIDDEN", 0)
    except Exception:
        hidden_mask = 0
    if hidden_mask == 0:
        return (0, len(before))

    for path in before:
        try:
            st = os.stat(path, follow_symlinks=False)
            new_flags = st.st_flags & ~hidden_mask
            os.chflags(path, new_flags, follow_symlinks=False)
            continue
        except Exception:
            pass
        # Fallback if os.chflags fails on this path.
        cmd = ["chflags"]
        if path.is_symlink():
            cmd.append("-h")
        cmd.extend(["nohidden", str(path)])
        subprocess.run(cmd, capture_output=True, text=True, check=False)
    if recursive:
        subprocess.run(["chflags", "-R", "nohidden", str(root)], capture_output=True, text=True, check=False)

    after = find_hidden_paths(root)
    return (max(0, len(before) - len(after)), len(after))


def find_stale_site_packages_entries(site_pkgs: Path) -> List[Path]:
    if not site_pkgs.exists():
        return []
    stale: List[Path] = []
    for entry in site_pkgs.iterdir():
        if _STALE_NAME_RE.search(entry.name):
            stale.append(entry)
    return sorted(stale)


def find_duplicate_dist_info(site_pkgs: Path) -> Dict[str, List[Path]]:
    grouped: Dict[str, List[Path]] = {}
    if not site_pkgs.exists():
        return grouped
    for entry in site_pkgs.iterdir():
        if not entry.name.endswith(".dist-info"):
            continue
        m = _DIST_INFO_RE.match(entry.name)
        if not m:
            continue
        norm_name = normalize_dist_name(m.group("name"))
        grouped.setdefault(norm_name, []).append(entry)
    return {
        name: sorted(paths)
        for name, paths in grouped.items()
        if len(paths) > 1
    }


def is_qt_related_entry(path: Path) -> bool:
    n = path.name.lower()
    return any(token in n for token in ("pyqt", "qt", "sip"))


def file_description(path: Path) -> str:
    proc = subprocess.run(
        ["file", str(path)],
        capture_output=True,
        text=True,
        check=False,
    )
    return proc.stdout.strip()


def architecture_compatible(binary_description: str, machine: str | None = None) -> bool:
    if not binary_description:
        return False
    machine = machine or platform.machine()
    desc = binary_description.lower()
    machine = machine.lower()
    return machine in desc or "universal binary" in desc


def configure_qt_runtime_environment(repair_hidden: bool = True) -> QtRuntimeInfo:
    """Set Qt plugin env vars and self-heal hidden flags on macOS."""
    info = resolve_qt_runtime_info()
    os.environ["QT_PLUGIN_PATH"] = str(info.plugins_path)
    os.environ["QT_QPA_PLATFORM_PLUGIN_PATH"] = str(info.platforms_path)
    if sys.platform == "darwin" and repair_hidden:
        clear_hidden_flags(info.prefix_path, recursive=True)
    return info


def pinned_stack_mismatches(installed_versions: Dict[str, str]) -> Dict[str, Tuple[str, str]]:
    mismatches: Dict[str, Tuple[str, str]] = {}
    for name, expected in PINNED_QT_STACK.items():
        found = installed_versions.get(name, "")
        if found != expected:
            mismatches[name] = (expected, found)
    return mismatches


def read_installed_versions(names: Iterable[str]) -> Dict[str, str]:
    try:
        import importlib.metadata as md
    except ImportError:
        import importlib_metadata as md  # type: ignore

    versions: Dict[str, str] = {}
    for name in names:
        try:
            versions[name] = md.version(name)
        except md.PackageNotFoundError:
            versions[name] = ""
    return versions
