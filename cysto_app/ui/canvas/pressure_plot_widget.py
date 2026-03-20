# pressure_plot_widget.py
import bisect
import logging
import math
import os
import time

from PyQt5.QtWidgets import (
    QWidget,
    QSizePolicy,
    QVBoxLayout,
    QMessageBox,
    QFileDialog,
    QScrollBar,
)
from PyQt5.QtCore import Qt, pyqtSlot

from utils.config import (
    PLOT_DEFAULT_Y_MIN,
    PLOT_DEFAULT_Y_MAX,
    PLOT_DEFAULT_MASS_Y_MIN,
    PLOT_DEFAULT_MASS_Y_MAX,
    PLOT_MAX_POINTS,
)

log = logging.getLogger(__name__)

try:
    import pyqtgraph as pg
except Exception as e:
    pg = None
    _PYQTGRAPH_IMPORT_ERROR = e
else:
    _PYQTGRAPH_IMPORT_ERROR = None


if pg is None:
    log.warning(
        "pyqtgraph import failed (%s). Falling back to matplotlib live plotting.",
        _PYQTGRAPH_IMPORT_ERROR,
    )
    from .pressure_plot_widget_mpl import PressurePlotWidget  # noqa: F401
else:

    class PressurePlotWidget(QWidget):
        """Dual live plot (pressure + mass) rendered with pyqtgraph.

        Matplotlib is kept for high-quality image export only.
        """

        _STACKED_LAYOUT_KW = {
            "left": 0.06,
            "right": 0.995,
            "top": 0.985,
            "bottom": 0.08,
            "hspace": 0.08,
        }
        _SIDE_BY_SIDE_LAYOUT_KW = {
            "left": 0.06,
            "right": 0.995,
            "top": 0.985,
            "bottom": 0.10,
            "wspace": 0.16,
        }
        _STACKED_GRID_MARGINS = (44, 8, 8, 16)  # left, top, right, bottom
        _SIDE_BY_SIDE_GRID_MARGINS = (44, 8, 8, 20)
        _LEFT_AXIS_WIDTH = 54
        _BOTTOM_AXIS_HEIGHT = 36

        def __init__(self, parent=None):
            super().__init__(parent)
            pg.setConfigOptions(antialias=True)

            self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

            outer_layout = QVBoxLayout(self)
            outer_layout.setContentsMargins(0, 0, 0, 0)

            self.graphics = pg.GraphicsLayoutWidget(self)
            self.graphics.setBackground("w")
            outer_layout.addWidget(self.graphics)

            # Scrollbar kept for API compatibility/manual pan mode.
            self.scrollbar = QScrollBar(Qt.Horizontal, self)
            self.scrollbar.hide()
            outer_layout.addWidget(self.scrollbar)
            self.scrollbar.valueChanged.connect(self._on_scroll)

            # Data storage
            self.times = []
            self.pressures = []
            self.masses = []
            self.manual_xlim = None
            self.manual_ylim_pressure = (PLOT_DEFAULT_Y_MIN, PLOT_DEFAULT_Y_MAX)
            self.manual_ylim_mass = (PLOT_DEFAULT_MASS_Y_MIN, PLOT_DEFAULT_MASS_Y_MAX)
            self.window_duration = 60
            self.max_points = max(int(PLOT_MAX_POINTS), 200)
            self._trim_chunk = max(50, self.max_points // 8)

            # Pump markers
            self._pump_marker_data = []  # list[(t: float, running: bool)]
            self._pump_markers = []

            # Layout + autoscale state
            self._layout_mode = "stacked"
            self._auto_x_enabled = False
            self._auto_y_pressure_enabled = False
            self._auto_y_mass_enabled = False

            self._placeholder_text = "Waiting for CystoMoto device data..."

            # Build initial UI
            self._rebuild_axes("stacked")

            self._mouse_proxy = pg.SignalProxy(
                self.graphics.scene().sigMouseMoved,
                rateLimit=60,
                slot=self._on_mouse_moved,
            )

        # ── Axes construction ──────────────────────────────────────────────────

        def _rebuild_axes(self, mode: str):
            self.graphics.clear()
            self._pump_markers = []
            self._configure_graphics_layout(mode)

            if mode == "stacked":
                self.ax_pressure = self.graphics.addPlot(row=0, col=0)
                self.ax_mass = self.graphics.addPlot(row=1, col=0)
                self.ax_mass.setXLink(self.ax_pressure)
            else:  # side_by_side
                self.ax_pressure = self.graphics.addPlot(row=0, col=0)
                self.ax_mass = self.graphics.addPlot(row=0, col=1)
                self.ax_mass.setXLink(self.ax_pressure)

            self._style_axes(mode)

            self.line_pressure = self.ax_pressure.plot(
                [], [], pen=pg.mkPen("#111111", width=2)
            )
            self.line_mass = self.ax_mass.plot([], [], pen=pg.mkPen("#5E81AC", width=2))

            self.placeholder = pg.TextItem(
                self._placeholder_text,
                color=(110, 110, 110),
                anchor=(0.5, 0.5),
                fill=pg.mkBrush(236, 239, 244, 210),
                border=pg.mkPen(95, 95, 95, 180),
            )
            self.placeholder.setZValue(10)
            self.ax_pressure.addItem(self.placeholder, ignoreBounds=True)

            self.hover_pressure = pg.TextItem("", color=(0, 0, 0), anchor=(0, 1))
            self.hover_pressure.setZValue(11)
            self.hover_pressure.hide()
            self.ax_pressure.addItem(self.hover_pressure, ignoreBounds=True)

            self.hover_mass = pg.TextItem("", color=(0, 0, 0), anchor=(0, 1))
            self.hover_mass.setZValue(11)
            self.hover_mass.hide()
            self.ax_mass.addItem(self.hover_mass, ignoreBounds=True)

            self.ax_pressure.sigRangeChanged.connect(self._on_pressure_range_changed)
            self.ax_mass.sigRangeChanged.connect(self._on_mass_range_changed)

            self._apply_view_ranges(
                self._auto_x_enabled,
                self._auto_y_pressure_enabled,
                self._auto_y_mass_enabled,
                force_redraw=True,
            )
            self._redraw_all_markers()
            self._update_placeholder(None if self.times else self._placeholder_text)

        def _configure_graphics_layout(self, mode: str):
            lay = self.graphics.ci.layout
            if mode == "stacked":
                lay.setContentsMargins(*self._STACKED_GRID_MARGINS)
                lay.setHorizontalSpacing(0)
                lay.setVerticalSpacing(8)
                lay.setColumnStretchFactor(0, 1)
                lay.setRowStretchFactor(0, 1)
                lay.setRowStretchFactor(1, 1)
            else:
                lay.setContentsMargins(*self._SIDE_BY_SIDE_GRID_MARGINS)
                lay.setHorizontalSpacing(16)
                lay.setVerticalSpacing(0)
                lay.setRowStretchFactor(0, 1)
                lay.setColumnStretchFactor(0, 1)
                lay.setColumnStretchFactor(1, 1)

        def _style_axes(self, mode: str):
            label_style = {"color": "#111111", "font-size": "12pt", "font-weight": "600"}

            for ax in (self.ax_pressure, self.ax_mass):
                ax.showGrid(x=True, y=True, alpha=0.25)
                ax.getViewBox().setDefaultPadding(0.0)
                ax.getViewBox().enableAutoRange(axis="x", enable=False)
                ax.getViewBox().enableAutoRange(axis="y", enable=False)
                ax.setMenuEnabled(False)
                ax.hideButtons()
                ax.getViewBox().setBorder(pg.mkPen("#D8DEE9", width=1))

                for axis_name in ("left", "bottom"):
                    axis = ax.getAxis(axis_name)
                    axis.setTextPen(pg.mkPen("#333333"))
                    axis.setPen(pg.mkPen("#D8DEE9"))
                    axis.setStyle(tickTextOffset=8, autoExpandTextSpace=False)

            self.ax_pressure.setLabel("left", "Pressure (mmHg)", **label_style)
            self.ax_mass.setLabel("left", "Mass (g)", **label_style)

            if mode == "stacked":
                self.ax_pressure.showAxis("bottom")
                self.ax_mass.showAxis("bottom")
                self.ax_pressure.getAxis("bottom").setStyle(showValues=False)
                self.ax_pressure.setLabel("bottom", " ", **label_style)
                self.ax_mass.setLabel("bottom", "Time (s)", **label_style)
            else:
                self.ax_pressure.showAxis("bottom")
                self.ax_mass.showAxis("bottom")
                self.ax_pressure.getAxis("bottom").setStyle(showValues=True)
                self.ax_mass.getAxis("bottom").setStyle(showValues=True)
                self.ax_pressure.setLabel("bottom", "Time (s)", **label_style)
                self.ax_mass.setLabel("bottom", "Time (s)", **label_style)

            # Lock axis geometry so plot view boxes remain exactly matched.
            for ax in (self.ax_pressure, self.ax_mass):
                ax.getAxis("left").setWidth(self._LEFT_AXIS_WIDTH)
                ax.getAxis("bottom").setHeight(self._BOTTOM_AXIS_HEIGHT)

        def _safe_set_xrange(self, xmin: float, xmax: float):
            if not (math.isfinite(xmin) and math.isfinite(xmax)):
                return
            if xmin >= xmax:
                xmax = xmin + 1.0
            self.ax_pressure.setXRange(xmin, xmax, padding=0.0)

        def _safe_set_yrange(self, ax, ymin: float, ymax: float):
            if not (math.isfinite(ymin) and math.isfinite(ymax)):
                return
            if ymin >= ymax:
                ymax = ymin + 1.0
            ax.setYRange(ymin, ymax, padding=0.0)

        def _sorted_range(self, v0, v1):
            return (v0, v1) if v0 <= v1 else (v1, v0)

        def _apply_view_ranges(self, auto_x, auto_y_pressure, auto_y_mass, force_redraw=False):
            self.line_pressure.setData(self.times, self.pressures)
            self.line_mass.setData(self.times, self.masses)

            # X-range (shared via XLink)
            if auto_x:
                self.manual_xlim = None
                self.scrollbar.hide()
                if len(self.times) > 1:
                    start, end = self.times[0], self.times[-1]
                    pad = max(1.0, (end - start) * 0.05)
                    xmin = start - pad * 0.1
                    xmax = end + pad * 0.9
                    self._safe_set_xrange(xmin, xmax)
                elif self.times:
                    t0 = self.times[-1]
                    self._safe_set_xrange(t0 - 0.5, t0 + 0.5)
            else:
                if self.manual_xlim:
                    xmin, xmax = self.manual_xlim
                elif self.times:
                    t_latest = self.times[-1]
                    xmax = max(t_latest, float(self.window_duration))
                    xmin = max(0.0, xmax - self.window_duration)
                    self.manual_xlim = (xmin, xmax)
                else:
                    xmin, xmax = (0.0, 100.0)
                self._safe_set_xrange(xmin, xmax)
                self.scrollbar.hide()

            # Pressure Y-range
            if auto_y_pressure:
                self.manual_ylim_pressure = None
                if self.pressures:
                    mn, mx = min(self.pressures), max(self.pressures)
                    pad = max(abs(mx - mn) * 0.1, 2.0)
                    self._safe_set_yrange(self.ax_pressure, mn - pad, mx + pad)
                else:
                    self._safe_set_yrange(
                        self.ax_pressure,
                        PLOT_DEFAULT_Y_MIN,
                        PLOT_DEFAULT_Y_MAX,
                    )
            else:
                if self.manual_ylim_pressure:
                    ymin, ymax = self.manual_ylim_pressure
                elif self.pressures:
                    mn, mx = min(self.pressures), max(self.pressures)
                    pad = max(abs(mx - mn) * 0.1, 2.0)
                    ymin, ymax = (mn - pad, mx + pad)
                else:
                    ymin, ymax = (PLOT_DEFAULT_Y_MIN, PLOT_DEFAULT_Y_MAX)
                self._safe_set_yrange(self.ax_pressure, ymin, ymax)

            # Mass Y-range
            if auto_y_mass:
                self.manual_ylim_mass = None
                if self.masses:
                    mn, mx = min(self.masses), max(self.masses)
                    pad = max(abs(mx - mn) * 0.1, 1.0)
                    self._safe_set_yrange(self.ax_mass, mn - pad, mx + pad)
                else:
                    self._safe_set_yrange(
                        self.ax_mass,
                        PLOT_DEFAULT_MASS_Y_MIN,
                        PLOT_DEFAULT_MASS_Y_MAX,
                    )
            else:
                if self.manual_ylim_mass:
                    ymin, ymax = self.manual_ylim_mass
                elif self.masses:
                    mn, mx = min(self.masses), max(self.masses)
                    pad = max(abs(mx - mn) * 0.1, 1.0)
                    ymin, ymax = (mn - pad, mx + pad)
                else:
                    ymin, ymax = (PLOT_DEFAULT_MASS_Y_MIN, PLOT_DEFAULT_MASS_Y_MAX)
                self._safe_set_yrange(self.ax_mass, ymin, ymax)

            if force_redraw:
                self.graphics.viewport().update()

        # ── Layout control ─────────────────────────────────────────────────────

        @pyqtSlot(str)
        def set_layout(self, mode: str):
            if mode != self._layout_mode:
                self._layout_mode = mode
                self._rebuild_axes(mode)

        # ── Placeholder + hover ────────────────────────────────────────────────

        def _on_pressure_range_changed(self, *_):
            self._reposition_placeholder()
            self._reposition_marker_labels(pressure=True)

        def _on_mass_range_changed(self, *_):
            self._reposition_marker_labels(pressure=False)

        def _reposition_placeholder(self):
            if not self.placeholder.isVisible():
                return
            x0, x1 = self.ax_pressure.viewRange()[0]
            y0, y1 = self.ax_pressure.viewRange()[1]
            xc = (x0 + x1) * 0.5
            yc = (y0 + y1) * 0.5
            self.placeholder.setPos(xc, yc)

        def _update_placeholder(self, text=None, redraw=True):
            if text:
                self._placeholder_text = text
                self.placeholder.setText(text)
                self.placeholder.show()
                self._reposition_placeholder()
                self.hover_pressure.hide()
                self.hover_mass.hide()
            else:
                self.placeholder.hide()
            if redraw:
                self.graphics.viewport().update()

        def _find_nearest(self, x_coord):
            if not self.times:
                return None, -1
            idx = bisect.bisect_left(self.times, x_coord)
            if idx == 0:
                best = 0
            elif idx == len(self.times):
                best = len(self.times) - 1
            else:
                left = self.times[idx - 1]
                right = self.times[idx]
                best = idx - 1 if abs(x_coord - left) <= abs(x_coord - right) else idx
            return self.times[best], best

        def _on_mouse_moved(self, evt):
            if not self.times or self.placeholder.isVisible():
                if self.hover_pressure.isVisible():
                    self.hover_pressure.hide()
                if self.hover_mass.isVisible():
                    self.hover_mass.hide()
                return

            pos = evt[0]

            def _update_hover(ax, hover, values, fmt):
                vb = ax.getViewBox()
                if not vb.sceneBoundingRect().contains(pos):
                    hover.hide()
                    return
                mouse_point = vb.mapSceneToView(pos)
                t, idx = self._find_nearest(mouse_point.x())
                if t is None:
                    hover.hide()
                    return
                v = values[idx]
                hover.setText(fmt.format(t=t, v=v))
                hover.setPos(t, v)
                hover.show()

            _update_hover(
                self.ax_pressure,
                self.hover_pressure,
                self.pressures,
                "Time: {t:.2f} s\nPressure: {v:.2f} mmHg",
            )
            _update_hover(
                self.ax_mass,
                self.hover_mass,
                self.masses,
                "Time: {t:.2f} s\nMass: {v:.2f} g",
            )

        # ── Plot update ────────────────────────────────────────────────────────

        def _trim_history_if_needed(self):
            max_allowed = self.max_points + self._trim_chunk
            if len(self.times) <= max_allowed:
                return

            keep_from = len(self.times) - self.max_points
            min_t = self.times[keep_from]

            del self.times[:keep_from]
            del self.pressures[:keep_from]
            del self.masses[:keep_from]

            if self._pump_marker_data:
                kept = [(t, running) for (t, running) in self._pump_marker_data if t >= min_t]
                if len(kept) != len(self._pump_marker_data):
                    self._pump_marker_data = kept
                    self._clear_pump_markers()
                    self._redraw_all_markers()

        def _refresh_plot_view(self, auto_x, auto_y_pressure, auto_y_mass, force_redraw=False):
            self._auto_x_enabled = bool(auto_x)
            self._auto_y_pressure_enabled = bool(auto_y_pressure)
            self._auto_y_mass_enabled = bool(auto_y_mass)
            self._apply_view_ranges(auto_x, auto_y_pressure, auto_y_mass, force_redraw)

        def update_plot_batch(self, samples, auto_x, auto_y_pressure, auto_y_mass):
            if not samples:
                return

            if not self.times and self.placeholder and self.placeholder.isVisible():
                self._update_placeholder(None, redraw=False)

            dropped = 0
            for t, p, mass in samples:
                if self.times and t <= self.times[-1]:
                    dropped += 1
                    continue
                self.times.append(t)
                self.pressures.append(p)
                self.masses.append(mass)

            if dropped:
                log.warning(
                    "[plot] dropped %d non-monotonic packets (last t=%.4f).",
                    dropped,
                    self.times[-1] if self.times else float("nan"),
                )
            if not self.times:
                return

            self._trim_history_if_needed()
            self._refresh_plot_view(auto_x, auto_y_pressure, auto_y_mass)

        @pyqtSlot(float, float, float, bool, bool, bool)
        def update_plot(self, t, p, mass, auto_x, auto_y_pressure, auto_y_mass):
            self.update_plot_batch([(t, p, mass)], auto_x, auto_y_pressure, auto_y_mass)

        # ── Manual axis setters ────────────────────────────────────────────────

        def set_manual_x_limits(self, xmin, xmax):
            if xmin < xmax and math.isfinite(xmin) and math.isfinite(xmax):
                self.manual_xlim = (xmin, xmax)
                self._safe_set_xrange(xmin, xmax)
                self._update_scrollbar()
            else:
                log.warning("X min must be less than X max")

        def set_manual_y_limits(self, ymin, ymax):
            if ymin < ymax and math.isfinite(ymin) and math.isfinite(ymax):
                self.manual_ylim_pressure = (ymin, ymax)
                self._safe_set_yrange(self.ax_pressure, ymin, ymax)
            else:
                log.warning("Pressure Y limits invalid: %s, %s", ymin, ymax)

        def set_manual_y_mass_limits(self, ymin, ymax):
            if ymin < ymax and math.isfinite(ymin) and math.isfinite(ymax):
                self.manual_ylim_mass = (ymin, ymax)
                self._safe_set_yrange(self.ax_mass, ymin, ymax)
            else:
                log.warning("Mass Y limits invalid: %s, %s", ymin, ymax)

        def set_auto_scale_x(self, enabled: bool):
            self._auto_x_enabled = bool(enabled)
            if self.times:
                self._refresh_plot_view(
                    self._auto_x_enabled,
                    self._auto_y_pressure_enabled,
                    self._auto_y_mass_enabled,
                    force_redraw=True,
                )

        def set_auto_scale_y(self, enabled: bool):
            self._auto_y_pressure_enabled = bool(enabled)
            if enabled:
                self.manual_ylim_pressure = None
            else:
                self.manual_ylim_pressure = (PLOT_DEFAULT_Y_MIN, PLOT_DEFAULT_Y_MAX)
                self._safe_set_yrange(self.ax_pressure, *self.manual_ylim_pressure)
            if self.times:
                self._refresh_plot_view(
                    self._auto_x_enabled,
                    self._auto_y_pressure_enabled,
                    self._auto_y_mass_enabled,
                    force_redraw=True,
                )

        def set_auto_scale_y_mass(self, enabled: bool):
            self._auto_y_mass_enabled = bool(enabled)
            if enabled:
                self.manual_ylim_mass = None
            else:
                self.manual_ylim_mass = (
                    PLOT_DEFAULT_MASS_Y_MIN,
                    PLOT_DEFAULT_MASS_Y_MAX,
                )
                self._safe_set_yrange(self.ax_mass, *self.manual_ylim_mass)
            if self.times:
                self._refresh_plot_view(
                    self._auto_x_enabled,
                    self._auto_y_pressure_enabled,
                    self._auto_y_mass_enabled,
                    force_redraw=True,
                )

        def reset_zoom(self, auto_x, auto_y_pressure, auto_y_mass):
            self.manual_xlim = None
            if auto_x:
                self.scrollbar.hide()

            if not auto_y_pressure:
                self.manual_ylim_pressure = (PLOT_DEFAULT_Y_MIN, PLOT_DEFAULT_Y_MAX)
                self._safe_set_yrange(self.ax_pressure, *self.manual_ylim_pressure)
            else:
                self.manual_ylim_pressure = None

            if not auto_y_mass:
                self.manual_ylim_mass = (PLOT_DEFAULT_MASS_Y_MIN, PLOT_DEFAULT_MASS_Y_MAX)
                self._safe_set_yrange(self.ax_mass, *self.manual_ylim_mass)
            else:
                self.manual_ylim_mass = None

            if self.times:
                self._update_placeholder(None, redraw=False)
                self._refresh_plot_view(auto_x, auto_y_pressure, auto_y_mass, force_redraw=True)
            else:
                self._safe_set_xrange(0.0, 100.0)
                if not auto_y_pressure:
                    self._safe_set_yrange(self.ax_pressure, PLOT_DEFAULT_Y_MIN, PLOT_DEFAULT_Y_MAX)
                if not auto_y_mass:
                    self._safe_set_yrange(
                        self.ax_mass,
                        PLOT_DEFAULT_MASS_Y_MIN,
                        PLOT_DEFAULT_MASS_Y_MAX,
                    )
                self._update_placeholder("Plot cleared or waiting for data.")

        # ── Scrollbar ──────────────────────────────────────────────────────────

        def _update_scrollbar(self):
            # Hidden by default in live mode; retained for compatibility.
            self.scrollbar.hide()

        @pyqtSlot(int)
        def _on_scroll(self, _pos):
            # Manual scroll support intentionally disabled in current UX.
            return

        def set_window_duration(self, seconds: int):
            self.window_duration = seconds

        # ── Pump markers ───────────────────────────────────────────────────────

        def add_pump_marker(self, t: float, running: bool, redraw: bool = True):
            self._pump_marker_data.append((t, running))
            self._draw_pump_marker(t, running)
            if redraw:
                self._reposition_marker_labels(pressure=True)
                self._reposition_marker_labels(pressure=False)

        def _marker_color(self, running: bool):
            return "#2E8B57" if running else "#BF616A"

        def _draw_pump_marker(self, t: float, running: bool):
            color = self._marker_color(running)
            label = "Pump ON" if running else "Pump OFF"
            pen = pg.mkPen(color=color, width=1.5, style=Qt.DashLine)

            line_p = pg.InfiniteLine(pos=t, angle=90, pen=pen, movable=False)
            line_m = pg.InfiniteLine(pos=t, angle=90, pen=pen, movable=False)
            self.ax_pressure.addItem(line_p, ignoreBounds=True)
            self.ax_mass.addItem(line_m, ignoreBounds=True)

            txt_p = pg.TextItem(f" {label}", color=color, anchor=(1, 0))
            txt_m = pg.TextItem(f" {label}", color=color, anchor=(1, 0))
            txt_p.setZValue(9)
            txt_m.setZValue(9)
            self.ax_pressure.addItem(txt_p, ignoreBounds=True)
            self.ax_mass.addItem(txt_m, ignoreBounds=True)

            marker = {
                "t": t,
                "running": running,
                "line_p": line_p,
                "line_m": line_m,
                "txt_p": txt_p,
                "txt_m": txt_m,
            }
            self._pump_markers.append(marker)
            self._position_single_marker_label(marker)

            # Keep current x-window fixed after adding marker.
            x0, x1 = self.ax_pressure.viewRange()[0]
            self._safe_set_xrange(x0, x1)

        def _position_single_marker_label(self, marker):
            t = marker["t"]
            yp0, yp1 = self.ax_pressure.viewRange()[1]
            ym0, ym1 = self.ax_mass.viewRange()[1]
            marker["txt_p"].setPos(t, max(yp0, yp1))
            marker["txt_m"].setPos(t, max(ym0, ym1))

        def _reposition_marker_labels(self, pressure: bool):
            for marker in self._pump_markers:
                t = marker["t"]
                if pressure:
                    y0, y1 = self.ax_pressure.viewRange()[1]
                    marker["txt_p"].setPos(t, max(y0, y1))
                else:
                    y0, y1 = self.ax_mass.viewRange()[1]
                    marker["txt_m"].setPos(t, max(y0, y1))

        def _redraw_all_markers(self):
            for t, running in self._pump_marker_data:
                self._draw_pump_marker(t, running)

        def _clear_pump_markers(self):
            for marker in self._pump_markers:
                for key, ax in (
                    ("line_p", self.ax_pressure),
                    ("txt_p", self.ax_pressure),
                    ("line_m", self.ax_mass),
                    ("txt_m", self.ax_mass),
                ):
                    item = marker.get(key)
                    if item is None:
                        continue
                    try:
                        ax.removeItem(item)
                    except Exception:
                        pass
            self._pump_markers.clear()

        # ── Clear / export ─────────────────────────────────────────────────────

        def clear_plot(self):
            self.times.clear()
            self.pressures.clear()
            self.masses.clear()
            self._clear_pump_markers()
            self._pump_marker_data.clear()

            self.line_pressure.setData([], [])
            self.line_mass.setData([], [])
            self._safe_set_xrange(0.0, 100.0)

            ylim_p = self.manual_ylim_pressure
            if ylim_p and isinstance(ylim_p, tuple) and all(math.isfinite(v) for v in ylim_p):
                self._safe_set_yrange(self.ax_pressure, *ylim_p)
            else:
                self.manual_ylim_pressure = (PLOT_DEFAULT_Y_MIN, PLOT_DEFAULT_Y_MAX)
                self._safe_set_yrange(self.ax_pressure, *self.manual_ylim_pressure)

            ylim_m = self.manual_ylim_mass
            if ylim_m and isinstance(ylim_m, tuple) and all(math.isfinite(v) for v in ylim_m):
                self._safe_set_yrange(self.ax_mass, *ylim_m)
            else:
                self.manual_ylim_mass = (PLOT_DEFAULT_MASS_Y_MIN, PLOT_DEFAULT_MASS_Y_MAX)
                self._safe_set_yrange(self.ax_mass, *self.manual_ylim_mass)

            self.hover_pressure.hide()
            self.hover_mass.hide()
            self._update_placeholder("Plot data cleared.")

        def get_plot_data(self):
            return {
                "time": list(self.times),
                "pressure": list(self.pressures),
                "mass": list(self.masses),
                "pump_markers": list(self._pump_marker_data),
            }

        def _build_export_figure(self):
            from matplotlib.figure import Figure

            fig = Figure(facecolor="white", constrained_layout=False)

            if self._layout_mode == "stacked":
                gs = fig.add_gridspec(2, 1, height_ratios=[1, 1])
                ax_pressure = fig.add_subplot(gs[0])
                ax_mass = fig.add_subplot(gs[1], sharex=ax_pressure)
                fig.subplots_adjust(**self._STACKED_LAYOUT_KW)
            else:
                gs = fig.add_gridspec(1, 2)
                ax_pressure = fig.add_subplot(gs[0])
                ax_mass = fig.add_subplot(gs[1], sharex=ax_pressure)
                fig.subplots_adjust(**self._SIDE_BY_SIDE_LAYOUT_KW)

            for ax in (ax_pressure, ax_mass):
                ax.set_facecolor("white")
                ax.tick_params(labelsize=10, colors="#333333")
                ax.grid(True, linestyle="--", alpha=0.7, color="lightgray")
                for spine in ax.spines.values():
                    spine.set_color("#D8DEE9")

            if self._layout_mode == "stacked":
                for lbl in ax_pressure.get_xticklabels():
                    lbl.set_visible(False)
                ax_mass.set_xlabel("Time (s)", fontsize=13, fontweight="bold")
            else:
                ax_pressure.set_xlabel("Time (s)", fontsize=13, fontweight="bold")
                ax_mass.set_xlabel("Time (s)", fontsize=13, fontweight="bold")

            ax_pressure.set_ylabel("Pressure (mmHg)", fontsize=13, fontweight="bold")
            ax_mass.set_ylabel("Mass (g)", fontsize=13, fontweight="bold")

            ax_pressure.plot(self.times, self.pressures, "-", lw=2, color="black")
            ax_mass.plot(self.times, self.masses, "-", lw=2, color="#5E81AC")

            # Preserve current viewport for export.
            x0, x1 = self._sorted_range(*self.ax_pressure.viewRange()[0])
            yp0, yp1 = self._sorted_range(*self.ax_pressure.viewRange()[1])
            ym0, ym1 = self._sorted_range(*self.ax_mass.viewRange()[1])
            ax_pressure.set_xlim(x0, x1)
            ax_mass.set_xlim(x0, x1)
            ax_pressure.set_ylim(yp0, yp1)
            ax_mass.set_ylim(ym0, ym1)

            for t, running in self._pump_marker_data:
                color = self._marker_color(running)
                label = "Pump ON" if running else "Pump OFF"
                for ax in (ax_pressure, ax_mass):
                    ax.axvline(
                        x=t,
                        color=color,
                        linestyle="--",
                        linewidth=1.5,
                        alpha=0.85,
                        zorder=3,
                    )
                    txt = ax.text(
                        t,
                        0.98,
                        f" {label}",
                        color=color,
                        fontsize=8,
                        fontweight="bold",
                        rotation=90,
                        va="top",
                        ha="right",
                        transform=ax.get_xaxis_transform(),
                        zorder=4,
                    )
                    txt.set_clip_on(True)
                    txt.set_clip_path(ax.patch)

            if not self.times:
                ax_pressure.text(
                    0.5,
                    0.5,
                    self._placeholder_text,
                    transform=ax_pressure.transAxes,
                    ha="center",
                    va="center",
                    fontsize=12,
                    color="gray",
                    bbox=dict(boxstyle="round,pad=0.5", fc="#ECEFF4", alpha=0.8),
                )

            return fig

        def export_as_image(self):
            if not self.times and not self.placeholder.isVisible():
                QMessageBox.warning(self, "Empty Plot", "Plot has no data to export.")
                return

            default_name = f"plot_export_{time.strftime('%Y%m%d-%H%M%S')}.png"
            path, _ = QFileDialog.getSaveFileName(
                self,
                "Save Plot Image",
                default_name,
                "PNG (*.png);;JPEG (*.jpg);;SVG (*.svg);;PDF (*.pdf)",
            )
            if not path:
                return

            try:
                fig = self._build_export_figure()
                fig.savefig(path, dpi=300, facecolor=fig.get_facecolor())
                sb = self.window().statusBar() if self.window() else None
                if sb:
                    sb.showMessage(f"Plot exported to {os.path.basename(path)}", 3000)
            except Exception as e:
                log.exception("Error exporting plot image: %s", e)
                QMessageBox.critical(self, "Export Error", f"Could not save plot image: {e}")
