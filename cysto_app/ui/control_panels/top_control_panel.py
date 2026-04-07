# SPDX-License-Identifier: GPL-3.0-only
# cysto_app/ui/control_panels/top_control_panel.py
import logging

from PyQt5.QtWidgets import (
    QWidget,
    QGroupBox,
    QHBoxLayout,
    QFormLayout,
    QLabel,
    QPushButton,
)
from PyQt5.QtCore import pyqtSignal


log = logging.getLogger(__name__)


class TopControlPanel(QWidget):
    """CystoMoto device status panel."""

    parameter_changed = pyqtSignal(str, object)
    zero_requested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(3, 1, 3, 1)
        layout.setSpacing(5)

        status_box = QGroupBox("CystoMoto Device Status")
        status_layout = QFormLayout(status_box)
        self.conn_lbl = QLabel("Disconnected")
        self.conn_lbl.setStyleSheet("font-weight:bold;color:#D6C832;")
        status_layout.addRow("Connection:", self.conn_lbl)

        self.pres_lbl = QLabel("N/A")
        self.pres_lbl.setStyleSheet("font-size:12pt;font-weight:bold;")
        status_layout.addRow("Current Pressure:", self.pres_lbl)

        self.mass_lbl = QLabel("N/A")
        self.mass_lbl.setStyleSheet("font-size:12pt;font-weight:bold;")
        status_layout.addRow("Current Mass:", self.mass_lbl)

        self.zero_btn = QPushButton("Zero Device?")
        self.zero_btn.setEnabled(False)
        self.zero_btn.clicked.connect(self.zero_requested.emit)
        status_layout.addRow(self.zero_btn)

        layout.addWidget(status_box, 1)

    def update_connection_status(self, text: str, connected: bool):
        self.conn_lbl.setText(text)
        if connected:
            color = "#A3BE8C"
        elif "error" in text.lower() or "failed" in text.lower():
            color = "#BF616A"
        else:
            color = "#D6C832"
        self.conn_lbl.setStyleSheet(f"font-weight:bold;color:{color};")
        self.zero_btn.setEnabled(connected)
        if not connected:
            self.clear_device_data()

    def clear_device_data(self):
        """Clear live device readouts when no current device data is available."""
        self.pres_lbl.setText("N/A")
        self.mass_lbl.setText("N/A")

    def update_device_data(self, p_dev: float, mass_dev: float):
        """Update the live pressure and mass readouts."""
        self.pres_lbl.setText(f"{p_dev:.2f} mmHg")
        self.mass_lbl.setText(f"{mass_dev:.2f} g")
