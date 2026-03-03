import logging

from PyQt5.QtWidgets import (
    QGroupBox,
    QFormLayout,
    QHBoxLayout,
    QPushButton,
)
from PyQt5.QtCore import pyqtSignal

log = logging.getLogger(__name__)


class PumpControlPanel(QGroupBox):
    """UI panel for syringe pump and recording controls.

    Button workflow enforced by state:
      1. Connect         → only "Start Recording" is enabled.
      2. Start Recording → CSV + plot begin; "Start Fill" becomes available.
      3. Start Fill      → Arduino receives start command; "Stop Pump" active.
      4. Stop Pump       → Arduino receives stop command; "Start Fill" active.
      5. Stop Recording  → CSV + plot stop; all pump buttons disabled.
    """

    pump_start_requested = pyqtSignal()
    pump_stop_requested = pyqtSignal()
    record_start_requested = pyqtSignal()
    record_stop_requested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__("Pump & Recording", parent)

        self._recording_active = False

        layout = QFormLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(6)

        # ── Recording row (first step) ────────────────────────────────────────
        self.rec_start_btn = QPushButton("⏺ Start Recording")
        self.rec_start_btn.setEnabled(False)
        self.rec_start_btn.clicked.connect(self.record_start_requested.emit)

        self.rec_stop_btn = QPushButton("⏹ Stop Recording")
        self.rec_stop_btn.setEnabled(False)
        self.rec_stop_btn.clicked.connect(self.record_stop_requested.emit)

        rec_row = QHBoxLayout()
        rec_row.addWidget(self.rec_start_btn)
        rec_row.addWidget(self.rec_stop_btn)
        layout.addRow("Recording:", rec_row)

        # ── Pump row (available only while recording is active) ───────────────
        self.start_btn = QPushButton("Start Fill")
        self.start_btn.setEnabled(False)
        self.start_btn.clicked.connect(self.pump_start_requested.emit)

        self.stop_btn = QPushButton("Stop Pump")
        self.stop_btn.setEnabled(False)
        self.stop_btn.clicked.connect(self.pump_stop_requested.emit)

        pump_row = QHBoxLayout()
        pump_row.addWidget(self.start_btn)
        pump_row.addWidget(self.stop_btn)
        layout.addRow("Pump:", pump_row)

    def update_connection_status(self, connected: bool):
        """Enable/disable controls on device connect or disconnect."""
        self._recording_active = False
        if not connected:
            self.rec_start_btn.setEnabled(False)
            self.rec_stop_btn.setEnabled(False)
            self.start_btn.setEnabled(False)
            self.stop_btn.setEnabled(False)
        else:
            # Only recording can be started at connect time
            self.rec_start_btn.setEnabled(True)
            self.rec_stop_btn.setEnabled(False)
            self.start_btn.setEnabled(False)
            self.stop_btn.setEnabled(False)

    def update_pump_state(self, running: bool):
        """Toggle pump buttons (only effective while recording is active)."""
        if self._recording_active:
            self.start_btn.setEnabled(not running)
            self.stop_btn.setEnabled(running)
        else:
            self.start_btn.setEnabled(False)
            self.stop_btn.setEnabled(False)

    def update_recording_state(self, recording: bool):
        """Toggle recording buttons and gate pump access on recording state."""
        self._recording_active = recording
        self.rec_start_btn.setEnabled(not recording)
        self.rec_stop_btn.setEnabled(recording)
        if recording:
            # Recording started — enable Start Fill, pump not yet running
            self.start_btn.setEnabled(True)
            self.stop_btn.setEnabled(False)
        else:
            # Recording stopped — disable all pump buttons
            self.start_btn.setEnabled(False)
            self.stop_btn.setEnabled(False)
