# cysto_app/ui/control_panels/plot_control_panel.py

import logging
from PyQt5.QtWidgets import (
    QGroupBox,
    QFormLayout,
    QVBoxLayout,
    QHBoxLayout,
    QCheckBox,
    QDoubleSpinBox,
    QSpinBox,
    QLabel,
    QPushButton,
)
from PyQt5.QtCore import pyqtSignal

from utils.config import (
    PLOT_DEFAULT_Y_MIN,
    PLOT_DEFAULT_Y_MAX,
    PLOT_DEFAULT_MASS_Y_MIN,
    PLOT_DEFAULT_MASS_Y_MAX,
)

log = logging.getLogger(__name__)


class PlotControlPanel(QGroupBox):
    """Controls for the dual live plot (Pressure + Mass vs. Time)."""

    autoscale_x_changed = pyqtSignal(bool)
    window_duration_changed = pyqtSignal(int)
    autoscale_y_changed = pyqtSignal(bool)           # pressure
    autoscale_y_mass_changed = pyqtSignal(bool)      # mass
    x_axis_limits_changed = pyqtSignal(float, float)
    y_axis_limits_changed = pyqtSignal(float, float)          # pressure
    y_mass_axis_limits_changed = pyqtSignal(float, float)     # mass
    reset_zoom_requested = pyqtSignal()
    export_plot_image_requested = pyqtSignal()
    clear_plot_requested = pyqtSignal()
    layout_changed = pyqtSignal(str)                 # "stacked" or "side_by_side"

    def __init__(self, parent=None):
        super().__init__("Plot Controls", parent)

        # Outer: axis controls (left) | action buttons (right)
        outer = QHBoxLayout(self)
        outer.setContentsMargins(3, 6, 3, 3)
        outer.setSpacing(8)

        # ── Left: axis controls ───────────────────────────────────────────────
        form = QFormLayout()
        form.setSpacing(4)
        outer.addLayout(form)

        # X-axis
        self.auto_x_cb = QCheckBox("Auto-scale X")
        self.auto_x_cb.setChecked(False)
        form.addRow(self.auto_x_cb)

        self.window_duration_spin = QSpinBox()
        self.window_duration_spin.setRange(10, 600)
        self.window_duration_spin.setValue(60)
        self.window_duration_spin.setSuffix(" s")
        self.window_duration_spin.setMaximumWidth(80)
        form.addRow("Window:", self.window_duration_spin)

        self.x_min = QDoubleSpinBox()
        self.x_max = QDoubleSpinBox()
        for spin in (self.x_min, self.x_max):
            spin.setDecimals(1)
            spin.setRange(-1e6, 1e6)
            spin.setEnabled(False)
            spin.setMaximumWidth(75)

        x_layout = QHBoxLayout()
        x_layout.addWidget(QLabel("Min:"))
        x_layout.addWidget(self.x_min)
        x_layout.addWidget(QLabel("Max:"))
        x_layout.addWidget(self.x_max)
        form.addRow("X-Limits:", x_layout)

        # Pressure Y-axis
        self.auto_y_cb = QCheckBox("Auto-scale Pressure Y")
        self.auto_y_cb.setChecked(False)
        form.addRow(self.auto_y_cb)

        self.y_min = QDoubleSpinBox()
        self.y_max = QDoubleSpinBox()
        for spin in (self.y_min, self.y_max):
            spin.setDecimals(1)
            spin.setRange(-1e6, 1e6)
            spin.setMaximumWidth(75)
        self.y_min.setValue(PLOT_DEFAULT_Y_MIN)
        self.y_max.setValue(PLOT_DEFAULT_Y_MAX)

        y_layout = QHBoxLayout()
        y_layout.addWidget(QLabel("Min:"))
        y_layout.addWidget(self.y_min)
        y_layout.addWidget(QLabel("Max:"))
        y_layout.addWidget(self.y_max)
        form.addRow("Pressure Y:", y_layout)

        # Mass Y-axis
        self.auto_y_mass_cb = QCheckBox("Auto-scale Mass Y")
        self.auto_y_mass_cb.setChecked(False)
        form.addRow(self.auto_y_mass_cb)

        self.y_mass_min = QDoubleSpinBox()
        self.y_mass_max = QDoubleSpinBox()
        for spin in (self.y_mass_min, self.y_mass_max):
            spin.setDecimals(1)
            spin.setRange(-1e6, 1e6)
            spin.setMaximumWidth(75)
        self.y_mass_min.setValue(PLOT_DEFAULT_MASS_Y_MIN)
        self.y_mass_max.setValue(PLOT_DEFAULT_MASS_Y_MAX)

        y_mass_layout = QHBoxLayout()
        y_mass_layout.addWidget(QLabel("Min:"))
        y_mass_layout.addWidget(self.y_mass_min)
        y_mass_layout.addWidget(QLabel("Max:"))
        y_mass_layout.addWidget(self.y_mass_max)
        form.addRow("Mass Y (g):", y_mass_layout)

        # ── Right: action buttons ─────────────────────────────────────────────
        self.reset_btn = QPushButton("↺ Reset Zoom/View")
        self.clear_plot_btn = QPushButton("Clear Plot Data")
        self.export_img_btn = QPushButton("Export Plot Image")

        self._current_layout = "stacked"
        self.layout_btn = QPushButton("⇔ Side by Side")
        self.layout_btn.clicked.connect(self._toggle_layout)

        btn_col = QVBoxLayout()
        btn_col.setSpacing(4)
        btn_col.addWidget(self.reset_btn)
        btn_col.addWidget(self.clear_plot_btn)
        btn_col.addWidget(self.export_img_btn)
        btn_col.addWidget(self.layout_btn)
        btn_col.addStretch()
        outer.addLayout(btn_col)

        # ── Connections ───────────────────────────────────────────────────────
        self.auto_x_cb.toggled.connect(self._on_auto_x_toggled)
        self.auto_x_cb.toggled.connect(self.autoscale_x_changed.emit)
        self.window_duration_spin.valueChanged.connect(self.window_duration_changed.emit)

        self.auto_y_cb.toggled.connect(self._on_auto_y_toggled)
        self.auto_y_cb.toggled.connect(self.autoscale_y_changed.emit)

        self.auto_y_mass_cb.toggled.connect(self._on_auto_y_mass_toggled)
        self.auto_y_mass_cb.toggled.connect(self.autoscale_y_mass_changed.emit)

        self.x_min.valueChanged.connect(self._emit_x_limits)
        self.x_max.valueChanged.connect(self._emit_x_limits)

        self.y_min.valueChanged.connect(self._emit_y_limits)
        self.y_max.valueChanged.connect(self._emit_y_limits)

        self.y_mass_min.valueChanged.connect(self._emit_y_mass_limits)
        self.y_mass_max.valueChanged.connect(self._emit_y_mass_limits)

        self.reset_btn.clicked.connect(self.reset_zoom_requested.emit)
        self.clear_plot_btn.clicked.connect(self.clear_plot_requested.emit)
        self.export_img_btn.clicked.connect(self.export_plot_image_requested.emit)

    # ── Toggle handlers ───────────────────────────────────────────────────────

    def _toggle_layout(self):
        if self._current_layout == "stacked":
            self._current_layout = "side_by_side"
            self.layout_btn.setText("⬍ Stacked")
        else:
            self._current_layout = "stacked"
            self.layout_btn.setText("⇔ Side by Side")
        self.layout_changed.emit(self._current_layout)

    def _on_auto_x_toggled(self, checked: bool):
        self.window_duration_spin.setEnabled(not checked)
        self.x_min.setEnabled(not checked)
        self.x_max.setEnabled(not checked)

    def _on_auto_y_toggled(self, checked: bool):
        self.y_min.setEnabled(not checked)
        self.y_max.setEnabled(not checked)

    def _on_auto_y_mass_toggled(self, checked: bool):
        self.y_mass_min.setEnabled(not checked)
        self.y_mass_max.setEnabled(not checked)

    # ── Emit helpers ──────────────────────────────────────────────────────────

    def _emit_x_limits(self):
        if not self.auto_x_cb.isChecked():
            self.x_axis_limits_changed.emit(self.x_min.value(), self.x_max.value())

    def _emit_y_limits(self):
        if not self.auto_y_cb.isChecked():
            self.y_axis_limits_changed.emit(self.y_min.value(), self.y_max.value())

    def _emit_y_mass_limits(self):
        if not self.auto_y_mass_cb.isChecked():
            self.y_mass_axis_limits_changed.emit(
                self.y_mass_min.value(), self.y_mass_max.value()
            )

    # ── Query helpers ─────────────────────────────────────────────────────────

    def is_autoscale_x(self) -> bool:
        return self.auto_x_cb.isChecked()

    def is_autoscale_y(self) -> bool:
        return self.auto_y_cb.isChecked()

    def is_autoscale_y_mass(self) -> bool:
        return self.auto_y_mass_cb.isChecked()

    def setEnabled(self, enabled: bool):
        super().setEnabled(enabled)
        self.auto_x_cb.setEnabled(enabled)
        self.auto_y_cb.setEnabled(enabled)
        self.auto_y_mass_cb.setEnabled(enabled)
        self.window_duration_spin.setEnabled(enabled and not self.auto_x_cb.isChecked())
        self.x_min.setEnabled(enabled and not self.auto_x_cb.isChecked())
        self.x_max.setEnabled(enabled and not self.auto_x_cb.isChecked())
        self.y_min.setEnabled(enabled and not self.auto_y_cb.isChecked())
        self.y_max.setEnabled(enabled and not self.auto_y_cb.isChecked())
        self.y_mass_min.setEnabled(enabled and not self.auto_y_mass_cb.isChecked())
        self.y_mass_max.setEnabled(enabled and not self.auto_y_mass_cb.isChecked())
        self.reset_btn.setEnabled(enabled)
        self.clear_plot_btn.setEnabled(enabled)
        self.export_img_btn.setEnabled(enabled)
        self.layout_btn.setEnabled(enabled)
