import logging

from PyQt5.QtWidgets import (
    QGroupBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
)
from PyQt5.QtCore import pyqtSignal

log = logging.getLogger(__name__)


class PumpControlPanel(QGroupBox):
    """UI panel for syringe pump and recording controls.

    Recording and pump are independent:
      - Connect         → "Start Recording" and "Start Fill" become available.
      - Start Recording → creates a new file, opens the run setup dialog, then starts CSV + plot capture.
      - Stop Recording  → CSV + plot stop; does not affect pump state.
      - Start Fill      → sends start command to Arduino only.
      - Stop Pump       → sends stop command to Arduino only.
    """

    pump_start_requested = pyqtSignal()
    pump_stop_requested = pyqtSignal()
    record_start_requested = pyqtSignal()
    record_stop_requested = pyqtSignal()
    annotation_requested = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__("Pump & Recording", parent)

        layout = QFormLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(6)

        # ── Recording row (first step) ────────────────────────────────────────
        self.rec_start_btn = QPushButton("⏺ Start Recording")
        self.rec_start_btn.setEnabled(False)
        self.rec_start_btn.setToolTip(
            "Start a new recording. This creates a new file and opens the run setup dialog for save location and metadata."
        )
        self.rec_start_btn.clicked.connect(self.record_start_requested.emit)

        self.rec_stop_btn = QPushButton("⏹ Stop Recording")
        self.rec_stop_btn.setEnabled(False)
        self.rec_stop_btn.setToolTip("Stop the current recording and close its CSV file.")
        self.rec_stop_btn.clicked.connect(self.record_stop_requested.emit)

        rec_row = QHBoxLayout()
        rec_row.addWidget(self.rec_start_btn)
        rec_row.addWidget(self.rec_stop_btn)
        layout.addRow("Recording:", rec_row)

        self.rec_hint_lbl = QLabel(
            "Starting a recording creates a new file and opens the run setup dialog."
        )
        self.rec_hint_lbl.setWordWrap(True)
        self.rec_hint_lbl.setStyleSheet("color:#9AA3AE;font-size:10px;")
        layout.addRow("", self.rec_hint_lbl)

        # ── Pump row (available only while recording is active) ───────────────
        self.start_btn = QPushButton("Start Pump")
        self.start_btn.setEnabled(False)
        self.start_btn.clicked.connect(self.pump_start_requested.emit)

        self.stop_btn = QPushButton("Stop Pump")
        self.stop_btn.setEnabled(False)
        self.stop_btn.clicked.connect(self.pump_stop_requested.emit)

        pump_row = QHBoxLayout()
        pump_row.addWidget(self.start_btn)
        pump_row.addWidget(self.stop_btn)
        layout.addRow("Pump:", pump_row)

        # ── Annotation row ───────────────────────────────────────────────────
        self.annotation_input = QLineEdit()
        self.annotation_input.setPlaceholderText("Type annotation…")
        self.annotation_input.setEnabled(False)
        self.annotation_input.returnPressed.connect(self._submit_annotation)

        self.annotation_btn = QPushButton("Add")
        self.annotation_btn.setEnabled(False)
        self.annotation_btn.setToolTip("Add a manual annotation marker to the trace.")
        self.annotation_btn.clicked.connect(self._submit_annotation)

        ann_row = QHBoxLayout()
        ann_row.addWidget(self.annotation_input, 1)
        ann_row.addWidget(self.annotation_btn)
        layout.addRow("Annotate:", ann_row)

    def _submit_annotation(self):
        text = self.annotation_input.text().strip()
        if text:
            self.annotation_requested.emit(text)
            self.annotation_input.clear()

    def update_connection_status(self, connected: bool):
        """Enable/disable controls on device connect or disconnect."""
        if not connected:
            self.rec_start_btn.setEnabled(False)
            self.rec_stop_btn.setEnabled(False)
            self.start_btn.setEnabled(False)
            self.stop_btn.setEnabled(False)
        else:
            self.rec_start_btn.setEnabled(True)
            self.rec_stop_btn.setEnabled(False)
            self.start_btn.setEnabled(True)
            self.stop_btn.setEnabled(False)

    def update_pump_state(self, running: bool):
        """Toggle pump buttons based on pump running state."""
        self.start_btn.setEnabled(not running)
        self.stop_btn.setEnabled(running)

    def update_recording_state(self, recording: bool):
        """Toggle recording buttons."""
        self.rec_start_btn.setEnabled(not recording)
        self.rec_stop_btn.setEnabled(recording)
        self.annotation_input.setEnabled(recording)
        self.annotation_btn.setEnabled(recording)
        if not recording:
            self.annotation_input.clear()
