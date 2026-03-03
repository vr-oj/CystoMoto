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
    """UI panel for syringe pump and recording controls (independent)."""

    pump_start_requested = pyqtSignal()
    pump_stop_requested = pyqtSignal()
    record_start_requested = pyqtSignal()
    record_stop_requested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__("Pump & Recording", parent)

        layout = QFormLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(6)

        # ── Pump row ──────────────────────────────────────────────────────────
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

        # ── Recording row ─────────────────────────────────────────────────────
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

    def update_connection_status(self, connected: bool):
        """Enable or disable controls based on device connection."""
        if not connected:
            self.start_btn.setEnabled(False)
            self.stop_btn.setEnabled(False)
            self.rec_start_btn.setEnabled(False)
            self.rec_stop_btn.setEnabled(False)
        else:
            self.start_btn.setEnabled(True)
            self.stop_btn.setEnabled(False)
            self.rec_start_btn.setEnabled(True)
            self.rec_stop_btn.setEnabled(False)

    def update_pump_state(self, running: bool):
        """Flip pump button availability based on whether the pump is running."""
        self.start_btn.setEnabled(not running)
        self.stop_btn.setEnabled(running)

    def update_recording_state(self, recording: bool):
        """Flip recording button availability based on whether recording is active."""
        self.rec_start_btn.setEnabled(not recording)
        self.rec_stop_btn.setEnabled(recording)
