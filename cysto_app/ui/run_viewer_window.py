# SPDX-License-Identifier: GPL-3.0-only
"""Non-modal window for viewing a previously recorded CystoMoto run."""

import logging
import os

from PyQt5.QtWidgets import (
    QAction,
    QLabel,
    QMainWindow,
    QVBoxLayout,
    QWidget,
)
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QKeySequence

from ui.canvas.pressure_plot_widget import PressurePlotWidget
from ui.control_panels.plot_control_panel import PlotControlPanel

log = logging.getLogger(__name__)


class RunViewerWindow(QMainWindow):
    """Independent window that displays a previously recorded CSV run."""

    def __init__(self, csv_path: str, run_data: dict, metadata: dict | None = None, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WA_DeleteOnClose)

        filename = os.path.basename(csv_path)
        exp_name = (metadata or {}).get("metadata", {}).get("experiment_name", "")
        if exp_name:
            self.setWindowTitle(f"Run Viewer \u2014 {exp_name} ({filename})")
        else:
            self.setWindowTitle(f"Run Viewer \u2014 {filename}")

        self.resize(1200, 700)

        # ── Central layout ────────────────────────────────────────────────────
        central = QWidget()
        layout = QVBoxLayout(central)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        # Optional metadata header
        if metadata:
            meta = metadata.get("metadata", {})
            parts = []
            for key in ("experiment_name", "subject_id", "condition_group", "protocol"):
                val = meta.get(key, "")
                if val:
                    label = key.replace("_", " ").title()
                    parts.append(f"<b>{label}:</b> {val}")
            if parts:
                header = QLabel("  \u2022  ".join(parts))
                header.setWordWrap(True)
                header.setStyleSheet("color:#4A5568; font-size:11px; padding:2px 4px;")
                layout.addWidget(header)

        # Plot controls (reuse PlotControlPanel, hide "Clear Plot Data")
        self.plot_control_panel = PlotControlPanel(self)
        self.plot_control_panel.clear_plot_btn.hide()
        self.plot_control_panel.auto_x_cb.setChecked(True)
        self.plot_control_panel.auto_y_cb.setChecked(True)
        self.plot_control_panel.auto_y_mass_cb.setChecked(True)
        layout.addWidget(self.plot_control_panel, stretch=0)

        # Plot widget
        self.pressure_plot_widget = PressurePlotWidget(self)
        layout.addWidget(self.pressure_plot_widget, stretch=1)

        self.setCentralWidget(central)

        # ── Wire PlotControlPanel → PressurePlotWidget ────────────────────────
        pw = self.pressure_plot_widget
        pc = self.plot_control_panel

        pc.autoscale_x_changed.connect(pw.set_auto_scale_x)
        pc.autoscale_y_changed.connect(pw.set_auto_scale_y)
        pc.autoscale_y_mass_changed.connect(pw.set_auto_scale_y_mass)
        pc.x_axis_limits_changed.connect(pw.set_manual_x_limits)
        pc.y_axis_limits_changed.connect(pw.set_manual_y_limits)
        pc.y_mass_axis_limits_changed.connect(pw.set_manual_y_mass_limits)
        pc.reset_zoom_requested.connect(
            lambda: pw.reset_zoom(
                pc.is_autoscale_x(),
                pc.is_autoscale_y(),
                pc.is_autoscale_y_mass(),
            )
        )
        pc.export_plot_image_requested.connect(pw.export_as_image)
        pc.layout_changed.connect(pw.set_layout)
        pc.window_duration_changed.connect(pw.set_window_duration)
        if hasattr(pw, "manual_x_mode_requested"):
            pw.manual_x_mode_requested.connect(
                lambda: pc.auto_x_cb.isChecked() and pc.auto_x_cb.setChecked(False)
            )

        # ── Menu bar ─────────────────────────────────────────────────────────
        fm = self.menuBar().addMenu("&File")
        exp_img = QAction("Export Plot &Image\u2026", self, triggered=pw.export_as_image)
        fm.addAction(exp_img)
        fm.addSeparator()
        close_act = QAction("&Close", self, shortcut=QKeySequence.Close, triggered=self.close)
        fm.addAction(close_act)

        # ── Status bar ───────────────────────────────────────────────────────
        self.statusBar().showMessage(csv_path)

        # ── Load data into the plot ──────────────────────────────────────────
        self._load_run_data(run_data)

    def _load_run_data(self, data: dict):
        pw = self.pressure_plot_widget
        # Disable live-streaming downsampling so static traces render smoothly
        for line in (pw.line_pressure, pw.line_mass):
            line.setDownsampling(auto=False)
            line.setClipToView(False)

        samples = list(zip(data["times"], data["pressures"], data["masses"]))
        if samples:
            pw.update_plot_batch(
                samples, auto_x=True, auto_y_pressure=True, auto_y_mass=True,
            )
        for t, running in data.get("pump_markers", []):
            pw.add_pump_marker(t, running, redraw=False)
        for t, label in data.get("annotation_markers", []):
            pw.add_annotation_marker(t, label, redraw=False)
