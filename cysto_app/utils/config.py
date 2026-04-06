# File: cysto_app/utils/config.py

import os
from pathlib import Path
from PyQt5.QtCore import QStandardPaths, QDir

# ─── User's Documents folder ───────────────────────────────────────────────────
DOCUMENTS_DIR = os.path.join(os.path.expanduser("~"), "Documents")

# Allow users to override the default results directory by setting the
# environment variable "CYSTO_RESULTS_DIR" before launching the application.
DEFAULT_RESULTS_DIR = os.path.join(DOCUMENTS_DIR, "CystoMoto Results")
CYSTO_RESULTS_DIR = os.environ.get("CYSTO_RESULTS_DIR", DEFAULT_RESULTS_DIR)
CYSTO_ROOT = CYSTO_RESULTS_DIR
Path(CYSTO_RESULTS_DIR).mkdir(parents=True, exist_ok=True)


def set_results_dir(path: str):
    """Update ``CYSTO_RESULTS_DIR`` and ensure the folder exists."""
    global CYSTO_RESULTS_DIR, CYSTO_ROOT
    CYSTO_RESULTS_DIR = path
    CYSTO_ROOT = path
    os.environ["CYSTO_RESULTS_DIR"] = path
    Path(path).mkdir(parents=True, exist_ok=True)

# ─── Serial communication ────────────────────────────────────────────────────────
DEFAULT_SERIAL_BAUD_RATE = 115200
SERIAL_COMMAND_TERMINATOR = b"\n"  # Arduino uses Serial.println()

# ─── Application info ───────────────────────────────────────────────────────────
APP_NAME = "CystoMoto"
APP_VERSION = "1.0.0"
ABOUT_TEXT = f"""
<strong>{APP_NAME} v{APP_VERSION}</strong>
<p>Passive Data Logger and Viewer for the CystoMoto system.</p>
<p>This application displays live pressure data from the CystoMoto device
and allows exporting of synchronized CSV logs.</p>
<p>Experiment control (start/stop) can be triggered directly from this application.</p>
"""

# ─── Logging ────────────────────────────────────────────────────────────────────
LOG_LEVEL = "DEBUG"  # DEBUG, INFO, WARNING, ERROR

# ─── Plotting ──────────────────────────────────────────────────────────────────
PLOT_MAX_POINTS = 108000  # ~90 min at 20 Hz; covers a full run with margin
PLOT_DEFAULT_Y_MIN = -5
PLOT_DEFAULT_Y_MAX = 30  # Typical pressure range in mmHg
PLOT_DEFAULT_MASS_Y_MIN = 0
PLOT_DEFAULT_MASS_Y_MAX = 500  # Typical mass range in grams

# ─── Application config directory ────────────────────────────────────────────────
APP_CONFIG_DIR = QStandardPaths.writableLocation(QStandardPaths.AppConfigLocation)
QDir().mkpath(APP_CONFIG_DIR)
