# SPDX-License-Identifier: GPL-3.0-only
"""Load previously recorded CystoMoto CSV runs back into plot-ready data."""

import csv
import json
import logging
import os

log = logging.getLogger(__name__)


def load_run_csv(csv_path: str) -> dict:
    """Parse a recorded CSV and return plot-ready data.

    Returns
    -------
    dict with keys:
        times            : list[float]
        pressures        : list[float]
        masses           : list[float]
        pump_markers     : list[tuple[float, bool]]   – (t, running)
        annotation_markers : list[tuple[float, str]]   – (t, label)
    """
    times = []
    pressures = []
    masses = []
    pump_markers = []
    annotation_markers = []

    with open(csv_path, newline="") as f:
        reader = csv.reader(f)
        header = next(reader)

        # Find column indices by header name (tolerant of minor changes)
        col = {name.strip(): idx for idx, name in enumerate(header)}
        i_time = col.get("Time (s)")
        i_pressure = col.get("Pressure (mmHg)")
        i_mass = col.get("Mass (g)")
        i_event = col.get("Event")
        # Legacy format support
        i_pump_event = col.get("Pump Event")
        i_annotation = col.get("Annotation")

        if i_time is None or i_pressure is None:
            raise ValueError(
                f"CSV is missing required columns. Found: {header}"
            )

        for row in reader:
            if not row or not row[i_time].strip():
                continue
            t = float(row[i_time])
            p = float(row[i_pressure])
            m = float(row[i_mass]) if i_mass is not None and row[i_mass].strip() else 0.0
            times.append(t)
            pressures.append(p)
            masses.append(m)

            # Parse events from unified Event column
            if i_event is not None and len(row) > i_event and row[i_event].strip():
                for token in row[i_event].split(";"):
                    token = token.strip()
                    if not token:
                        continue
                    if token == "Pump ON":
                        pump_markers.append((t, True))
                    elif token == "Pump OFF":
                        pump_markers.append((t, False))
                    else:
                        annotation_markers.append((t, token))

            # Legacy: separate Pump Event / Annotation columns
            if i_pump_event is not None and len(row) > i_pump_event and row[i_pump_event].strip():
                for token in row[i_pump_event].split(";"):
                    token = token.strip()
                    if token == "Pump ON":
                        pump_markers.append((t, True))
                    elif token == "Pump OFF":
                        pump_markers.append((t, False))
            if i_annotation is not None and len(row) > i_annotation and row[i_annotation].strip():
                for token in row[i_annotation].split(";"):
                    token = token.strip()
                    if token:
                        annotation_markers.append((t, token))

    return {
        "times": times,
        "pressures": pressures,
        "masses": masses,
        "pump_markers": pump_markers,
        "annotation_markers": annotation_markers,
    }


def load_run_metadata(csv_path: str) -> dict | None:
    """Load the JSON metadata sidecar for a CSV, if it exists."""
    stem, _ = os.path.splitext(csv_path)
    metadata_path = f"{stem}_metadata.json"
    if not os.path.isfile(metadata_path):
        return None
    try:
        with open(metadata_path) as f:
            return json.load(f)
    except Exception:
        log.warning("Failed to load metadata from %s", metadata_path)
        return None
