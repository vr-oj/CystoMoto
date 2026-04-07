# SPDX-License-Identifier: GPL-3.0-only
# cysto_app/utils/path_helpers.py

import os
import sys
from datetime import date
from pathlib import Path

import utils.config as config


BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def resource_path(*parts: str) -> str:
    """Return absolute path to a bundled resource."""
    base = (
        os.path.join(sys._MEIPASS, "cysto_app")
        if getattr(sys, "_MEIPASS", None)
        else BASE_DIR
    )
    return os.path.join(base, *parts)


def get_next_fill_folder(create: bool = True) -> str:
    """
    Create (if needed) a folder at:
       CYSTO_ROOT/YYYY-MM-DD/FillN
    where YYYY-MM-DD = today's date,
    and N = smallest positive integer so that "FillN" does not yet exist.
    Returns the full path to the next "FillN" folder. When ``create`` is false,
    the path is returned without touching the filesystem.
    """
    today = date.today().isoformat()
    date_folder = os.path.join(config.CYSTO_ROOT, today)
    if create:
        Path(date_folder).mkdir(parents=True, exist_ok=True)

    existing = []
    if os.path.isdir(date_folder):
        for entry in os.listdir(date_folder):
            if entry.startswith("Fill"):
                suffix = entry[4:]
                if suffix.isdigit():
                    existing.append(int(suffix))

    n = 1
    while n in existing:
        n += 1

    new_fill_name = f"Fill{n}"
    new_fill_path = os.path.join(date_folder, new_fill_name)
    if create:
        Path(new_fill_path).mkdir(parents=True, exist_ok=True)

    return new_fill_path
