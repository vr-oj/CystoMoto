# pressure_plot_widget.py
import os
import time
import bisect
import logging
import math

from PyQt5.QtWidgets import (
    QWidget,
    QSizePolicy,
    QVBoxLayout,
    QMessageBox,
    QFileDialog,
    QScrollBar,
)
from PyQt5.QtCore import Qt, pyqtSlot
from matplotlib.figure import Figure
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
import matplotlib as mpl

from utils.config import (
    PLOT_DEFAULT_Y_MIN,
    PLOT_DEFAULT_Y_MAX,
    PLOT_DEFAULT_MASS_Y_MIN,
    PLOT_DEFAULT_MASS_Y_MAX,
)

log = logging.getLogger(__name__)

_HOVER_KW = dict(
    xy=(0, 0),
    xytext=(15, 15),
    textcoords="offset points",
    bbox=dict(boxstyle="round,pad=0.4", fc="wheat", alpha=0.85),
    arrowprops=dict(arrowstyle="->", connectionstyle="arc3,rad=.2", color="black"),
)


class PressurePlotWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        mpl.rcParams.update(
            {
                "font.size": 11,
                "axes.edgecolor": "#333333",
                "axes.labelweight": "bold",
                "axes.labelsize": 12,
                "axes.linewidth": 1.5,
                "xtick.color": "#333333",
                "ytick.color": "#333333",
                "figure.facecolor": "#ffffff",
                "savefig.facecolor": "#ffffff",
            }
        )
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        outer_layout = QVBoxLayout(self)
        outer_layout.setContentsMargins(0, 0, 0, 0)

        # Figure + canvas
        self.fig = Figure(facecolor="white")
        self.fig.set_constrained_layout(True)
        self.canvas = FigureCanvas(self.fig)
        outer_layout.addWidget(self.canvas)

        # Scrollbar for manual X panning
        self.scrollbar = QScrollBar(Qt.Horizontal, self)
        self.scrollbar.hide()
        outer_layout.addWidget(self.scrollbar)
        self.scrollbar.valueChanged.connect(self._on_scroll)
        self.scrollbar.setStyleSheet(
            """
            QScrollBar:horizontal {
                border: 1px solid #C0C0C0;
                background: #F0F0F0;
                height: 15px;
                margin: 0px 20px 0 20px;
            }
            QScrollBar::handle:horizontal {
                background: #A0A0A0;
                min-width: 20px;
                border-radius: 5px;
                border: 1px solid #808080;
            }
            QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {
                width: 0px; height: 0px; background: none; border: none;
            }
            QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {
                background: none;
            }
        """
        )

        # ── Data storage ───────────────────────────────────────────────────────
        self.times = []
        self.pressures = []
        self.masses = []
        self.manual_xlim = None
        self.manual_ylim_pressure = (PLOT_DEFAULT_Y_MIN, PLOT_DEFAULT_Y_MAX)
        self.manual_ylim_mass = (PLOT_DEFAULT_MASS_Y_MIN, PLOT_DEFAULT_MASS_Y_MAX)
        self.window_duration = 100

        # Pump markers: persistent data survives layout rebuilds; artists do not
        self._pump_marker_data = []  # list of (t: float, running: bool)
        self._pump_markers = []      # list of artist tuples — rebuilt on layout change

        # Layout mode
        self._layout_mode = "stacked"

        # Build initial axes
        self._rebuild_axes("stacked")

        self.canvas.mpl_connect("motion_notify_event", self._on_hover)

    # ── Axes construction ──────────────────────────────────────────────────────

    def _rebuild_axes(self, mode: str):
        """Clear the figure and recreate both axes for the given layout mode."""
        self.fig.clear()
        self._pump_markers = []  # artists are gone after fig.clear()

        if mode == "stacked":
            gs = self.fig.add_gridspec(2, 1, height_ratios=[1, 1])
            self.ax_pressure = self.fig.add_subplot(gs[0])
            self.ax_mass = self.fig.add_subplot(gs[1], sharex=self.ax_pressure)
        else:  # side_by_side
            gs = self.fig.add_gridspec(1, 2)
            self.ax_pressure = self.fig.add_subplot(gs[0])
            self.ax_mass = self.fig.add_subplot(gs[1], sharex=self.ax_pressure)

        self._style_axes(mode)
        self._restore_plot_state()

    def _style_axes(self, mode: str):
        for ax in (self.ax_pressure, self.ax_mass):
            ax.set_facecolor("white")
            ax.tick_params(labelsize=10)
            ax.grid(True, linestyle="--", alpha=0.7, color="lightgray")
            for spine in ax.spines.values():
                spine.set_color("#D8DEE9")

        if mode == "stacked":
            # X labels only on the bottom subplot
            for lbl in self.ax_pressure.get_xticklabels():
                lbl.set_visible(False)
            self.ax_mass.set_xlabel("Time (s)", fontsize=13, fontweight="bold")
        else:
            # Both subplots show their own X label
            self.ax_pressure.set_xlabel("Time (s)", fontsize=13, fontweight="bold")
            self.ax_mass.set_xlabel("Time (s)", fontsize=13, fontweight="bold")

        self.ax_pressure.set_ylabel("Pressure (mmHg)", fontsize=13, fontweight="bold")
        self.ax_mass.set_ylabel("Mass (g)", fontsize=13, fontweight="bold")

    def _restore_plot_state(self):
        """Recreate lines, limits, annotations and markers after an axes rebuild."""
        # Lines with current data
        (self.line_pressure,) = self.ax_pressure.plot(
            self.times, self.pressures, "-", lw=2, color="black"
        )
        (self.line_mass,) = self.ax_mass.plot(
            self.times, self.masses, "-", lw=2, color="#5E81AC"
        )

        # Y limits
        if self.manual_ylim_pressure:
            self.ax_pressure.set_ylim(self.manual_ylim_pressure)
        elif self.pressures:
            mn, mx = min(self.pressures), max(self.pressures)
            pad = max(abs(mx - mn) * 0.1, 2.0)
            self.ax_pressure.set_ylim(mn - pad, mx + pad)
        else:
            self.ax_pressure.set_ylim(PLOT_DEFAULT_Y_MIN, PLOT_DEFAULT_Y_MAX)

        if self.manual_ylim_mass:
            self.ax_mass.set_ylim(self.manual_ylim_mass)
        elif self.masses:
            mn, mx = min(self.masses), max(self.masses)
            pad = max(abs(mx - mn) * 0.1, 1.0)
            self.ax_mass.set_ylim(mn - pad, mx + pad)
        else:
            self.ax_mass.set_ylim(PLOT_DEFAULT_MASS_Y_MIN, PLOT_DEFAULT_MASS_Y_MAX)

        # X limits
        if self.manual_xlim:
            self.ax_pressure.set_xlim(self.manual_xlim)
        elif self.times:
            start, end = self.times[0], self.times[-1]
            pad = max(1, (end - start) * 0.05)
            self.ax_pressure.set_xlim(start - pad * 0.1, end + pad * 0.9)

        # Placeholder text
        self.placeholder = self.ax_pressure.text(
            0.5,
            0.5,
            "Waiting for CystoMoto device data...",
            transform=self.ax_pressure.transAxes,
            ha="center",
            va="center",
            fontsize=12,
            color="gray",
            bbox=dict(boxstyle="round,pad=0.5", fc="#ECEFF4", alpha=0.8),
        )
        self.placeholder.set_visible(not bool(self.times))

        # Hover annotations
        self.hover_pressure = self.ax_pressure.annotate("", **_HOVER_KW)
        self.hover_pressure.set_visible(False)
        self.hover_mass = self.ax_mass.annotate("", **_HOVER_KW)
        self.hover_mass.set_visible(False)

        # Re-draw pump markers from stored data
        for t, running in self._pump_marker_data:
            self._draw_pump_marker(t, running)

        self.canvas.draw_idle()

    # ── Public layout control ──────────────────────────────────────────────────

    @pyqtSlot(str)
    def set_layout(self, mode: str):
        if mode != self._layout_mode:
            self._layout_mode = mode
            self._rebuild_axes(mode)

    # ── Internal helpers ───────────────────────────────────────────────────────

    def _update_placeholder(self, text=None):
        if text:
            self.line_pressure.set_data([], [])
            if self.hover_pressure.get_visible():
                self.hover_pressure.set_visible(False)
            if self.placeholder:
                self.placeholder.set_text(text)
                self.placeholder.set_visible(True)
        else:
            if self.placeholder:
                self.placeholder.set_visible(False)
        self.canvas.draw_idle()

    def _find_nearest(self, x_coord):
        if not self.times:
            return None, -1
        idx = bisect.bisect_left(self.times, x_coord)
        if idx == 0:
            best = 0
        elif idx == len(self.times):
            best = len(self.times) - 1
        else:
            best = idx - 1 if abs(x_coord - self.times[idx - 1]) <= abs(x_coord - self.times[idx]) else idx
        return self.times[best], best

    def _on_hover(self, event):
        needs_redraw = False

        def _update(ann, ax, values, fmt):
            nonlocal needs_redraw
            if (
                event.inaxes == ax
                and self.times
                and not (self.placeholder and self.placeholder.get_visible())
                and event.xdata is not None
            ):
                t, best = self._find_nearest(event.xdata)
                if t is not None:
                    val = values[best]
                    ann.xy = (t, val)
                    new_text = fmt.format(t=t, v=val)
                    if ann.get_text() != new_text:
                        ann.set_text(new_text)
                        needs_redraw = True
                    if not ann.get_visible():
                        ann.set_visible(True)
                        needs_redraw = True
                    return
            if ann.get_visible():
                ann.set_visible(False)
                needs_redraw = True

        _update(self.hover_pressure, self.ax_pressure, self.pressures,
                "Time: {t:.2f} s\nPressure: {v:.2f} mmHg")
        _update(self.hover_mass, self.ax_mass, self.masses,
                "Time: {t:.2f} s\nMass: {v:.2f} g")

        if needs_redraw:
            self.canvas.draw_idle()

    # ── Plot update ────────────────────────────────────────────────────────────

    @pyqtSlot(float, float, float, bool, bool, bool)
    def update_plot(self, t, p, mass, auto_x, auto_y_pressure, auto_y_mass):
        if not self.times and self.placeholder and self.placeholder.get_visible():
            self._update_placeholder(None)

        self.times.append(t)
        self.pressures.append(p)
        self.masses.append(mass)

        self.line_pressure.set_data(self.times, self.pressures)
        self.line_mass.set_data(self.times, self.masses)

        prev_xlim = self.ax_pressure.get_xlim()
        prev_ylim_p = self.ax_pressure.get_ylim()
        prev_ylim_m = self.ax_mass.get_ylim()

        # X-axis (setting on ax_pressure propagates to ax_mass via sharex)
        if auto_x:
            self.manual_xlim = None
            self.scrollbar.hide()
            if len(self.times) > 1:
                start, end = self.times[0], self.times[-1]
                pad = max(1, (end - start) * 0.05)
                self.ax_pressure.set_xlim(start - pad * 0.1, end + pad * 0.9)
            elif self.times:
                t0 = self.times[-1]
                self.ax_pressure.set_xlim(t0 - 0.5, t0 + 0.5)
        else:
            t_latest = self.times[-1]
            xmin = max(0.0, t_latest - self.window_duration)
            self.manual_xlim = (xmin, t_latest)
            self.ax_pressure.set_xlim(self.manual_xlim)
            self.scrollbar.hide()

        # Pressure Y
        if auto_y_pressure:
            self.manual_ylim_pressure = None
            if self.pressures:
                mn, mx = min(self.pressures), max(self.pressures)
                pad = max(abs(mx - mn) * 0.1, 2.0)
                self.ax_pressure.set_ylim(mn - pad, mx + pad)
        else:
            if self.manual_ylim_pressure:
                self.ax_pressure.set_ylim(self.manual_ylim_pressure)
            elif not self.pressures:
                self.ax_pressure.set_ylim(PLOT_DEFAULT_Y_MIN, PLOT_DEFAULT_Y_MAX)

        # Mass Y
        if auto_y_mass:
            self.manual_ylim_mass = None
            if self.masses:
                mn, mx = min(self.masses), max(self.masses)
                pad = max(abs(mx - mn) * 0.1, 1.0)
                self.ax_mass.set_ylim(mn - pad, mx + pad)
        else:
            if self.manual_ylim_mass:
                self.ax_mass.set_ylim(self.manual_ylim_mass)
            elif not self.masses:
                self.ax_mass.set_ylim(PLOT_DEFAULT_MASS_Y_MIN, PLOT_DEFAULT_MASS_Y_MAX)

        if (
            prev_xlim != self.ax_pressure.get_xlim()
            or prev_ylim_p != self.ax_pressure.get_ylim()
            or prev_ylim_m != self.ax_mass.get_ylim()
            or self.line_pressure.stale
            or self.line_mass.stale
        ):
            self.canvas.draw_idle()

    # ── Manual axis limit setters ─────────────────────────────────────────────

    def set_manual_x_limits(self, xmin, xmax):
        if xmin < xmax:
            self.manual_xlim = (xmin, xmax)
            self.ax_pressure.set_xlim(self.manual_xlim)
            self._update_scrollbar()
            self.canvas.draw_idle()
        else:
            log.warning("X min must be less than X max")

    def set_manual_y_limits(self, ymin, ymax):
        if ymin < ymax and math.isfinite(ymin) and math.isfinite(ymax):
            self.manual_ylim_pressure = (ymin, ymax)
            self.ax_pressure.set_ylim(self.manual_ylim_pressure)
            self.canvas.draw_idle()
        else:
            log.warning(f"Pressure Y limits invalid: {ymin}, {ymax}")

    def set_manual_y_mass_limits(self, ymin, ymax):
        if ymin < ymax and math.isfinite(ymin) and math.isfinite(ymax):
            self.manual_ylim_mass = (ymin, ymax)
            self.ax_mass.set_ylim(self.manual_ylim_mass)
            self.canvas.draw_idle()
        else:
            log.warning(f"Mass Y limits invalid: {ymin}, {ymax}")

    def set_auto_scale_x(self, enabled: bool):
        pass  # handled inside update_plot

    def set_auto_scale_y(self, enabled: bool):
        if enabled:
            self.manual_ylim_pressure = None
        else:
            self.manual_ylim_pressure = (PLOT_DEFAULT_Y_MIN, PLOT_DEFAULT_Y_MAX)
            self.ax_pressure.set_ylim(self.manual_ylim_pressure)
            self.canvas.draw_idle()

    def set_auto_scale_y_mass(self, enabled: bool):
        if enabled:
            self.manual_ylim_mass = None
        else:
            self.manual_ylim_mass = (PLOT_DEFAULT_MASS_Y_MIN, PLOT_DEFAULT_MASS_Y_MAX)
            self.ax_mass.set_ylim(self.manual_ylim_mass)
            self.canvas.draw_idle()

    def reset_zoom(self, auto_x, auto_y_pressure, auto_y_mass):
        self.manual_xlim = None
        if auto_x:
            self.scrollbar.hide()

        if not auto_y_pressure:
            self.manual_ylim_pressure = (PLOT_DEFAULT_Y_MIN, PLOT_DEFAULT_Y_MAX)
            self.ax_pressure.set_ylim(self.manual_ylim_pressure)
        else:
            self.manual_ylim_pressure = None

        if not auto_y_mass:
            self.manual_ylim_mass = (PLOT_DEFAULT_MASS_Y_MIN, PLOT_DEFAULT_MASS_Y_MAX)
            self.ax_mass.set_ylim(self.manual_ylim_mass)
        else:
            self.manual_ylim_mass = None

        if self.times:
            self.update_plot(
                self.times[-1], self.pressures[-1], self.masses[-1],
                auto_x, auto_y_pressure, auto_y_mass,
            )
        else:
            self.ax_pressure.set_xlim(0, 10)
            if not auto_y_pressure:
                self.ax_pressure.set_ylim(PLOT_DEFAULT_Y_MIN, PLOT_DEFAULT_Y_MAX)
            if not auto_y_mass:
                self.ax_mass.set_ylim(PLOT_DEFAULT_MASS_Y_MIN, PLOT_DEFAULT_MASS_Y_MAX)
            self._update_placeholder("Plot cleared or waiting for data.")
            self.canvas.draw_idle()

    # ── Scrollbar ──────────────────────────────────────────────────────────────

    def _update_scrollbar(self):
        if not self.times or not self.manual_xlim:
            self.scrollbar.hide()
            return
        xmin, xmax = self.manual_xlim
        idx0 = bisect.bisect_left(self.times, xmin)
        idx1 = bisect.bisect_right(self.times, xmax)
        window_size = max(idx1 - idx0, 1)
        full_len = len(self.times)
        if full_len <= window_size:
            self.scrollbar.hide()
            return
        self.scrollbar.setMinimum(0)
        self.scrollbar.setMaximum(max(full_len - window_size, 0))
        self.scrollbar.setPageStep(window_size)
        self.scrollbar.setSingleStep(max(window_size // 10, 1))
        self.scrollbar.setValue(idx0)
        self.scrollbar.show()

    @pyqtSlot(int)
    def _on_scroll(self, pos):
        if not self.manual_xlim or not self.times or len(self.times) <= 1:
            return
        window_indices = self.scrollbar.pageStep()
        start_idx = pos
        end_idx = min(start_idx + window_indices - 1, len(self.times) - 1)
        if start_idx >= end_idx and len(self.times) > 1:
            start_idx = max(0, len(self.times) - 2)
            end_idx = len(self.times) - 1
        if start_idx < 0:
            start_idx = 0
        xmin_new = self.times[start_idx]
        xmax_new = self.times[end_idx]
        if xmin_new == xmax_new and len(self.times) > 1:
            if end_idx + 1 < len(self.times):
                xmax_new = self.times[end_idx + 1]
            elif start_idx - 1 >= 0:
                xmin_new = self.times[start_idx - 1]
            else:
                xmax_new = xmin_new + 1.0
        self.manual_xlim = (xmin_new, xmax_new)
        self.ax_pressure.set_xlim(self.manual_xlim)
        self.canvas.draw_idle()

    # ── Pump markers ──────────────────────────────────────────────────────────

    def add_pump_marker(self, t: float, running: bool):
        self._pump_marker_data.append((t, running))
        self._draw_pump_marker(t, running)
        self.canvas.draw_idle()

    def _draw_pump_marker(self, t: float, running: bool):
        color = "#2E8B57" if running else "#BF616A"
        label = "Pump ON" if running else "Pump OFF"

        def _vline_and_label(ax):
            line = ax.axvline(
                x=t, color=color, linestyle="--", linewidth=1.5, alpha=0.85, zorder=3
            )
            txt = ax.text(
                t, 0.98, f" {label}",
                color=color, fontsize=8, fontweight="bold",
                rotation=90, va="top", ha="right",
                transform=ax.get_xaxis_transform(), zorder=4,
            )
            return line, txt

        lp, tp = _vline_and_label(self.ax_pressure)
        lm, tm = _vline_and_label(self.ax_mass)
        self._pump_markers.append((lp, tp, lm, tm))

    def _clear_pump_markers(self):
        """Remove marker artists. Does NOT clear _pump_marker_data."""
        for lp, tp, lm, tm in self._pump_markers:
            for artist in (lp, tp, lm, tm):
                try:
                    artist.remove()
                except Exception:
                    pass
        self._pump_markers.clear()

    # ── Clear / export ────────────────────────────────────────────────────────

    def clear_plot(self):
        self.times.clear()
        self.pressures.clear()
        self.masses.clear()
        self._clear_pump_markers()
        self._pump_marker_data.clear()

        self.line_pressure.set_data([], [])
        self.line_mass.set_data([], [])
        self.ax_pressure.set_xlim(0, 100)

        ylim_p = self.manual_ylim_pressure
        if ylim_p and isinstance(ylim_p, tuple) and all(math.isfinite(v) for v in ylim_p):
            self.ax_pressure.set_ylim(ylim_p)
        else:
            self.manual_ylim_pressure = (PLOT_DEFAULT_Y_MIN, PLOT_DEFAULT_Y_MAX)
            self.ax_pressure.set_ylim(self.manual_ylim_pressure)

        ylim_m = self.manual_ylim_mass
        if ylim_m and isinstance(ylim_m, tuple) and all(math.isfinite(v) for v in ylim_m):
            self.ax_mass.set_ylim(ylim_m)
        else:
            self.manual_ylim_mass = (PLOT_DEFAULT_MASS_Y_MIN, PLOT_DEFAULT_MASS_Y_MAX)
            self.ax_mass.set_ylim(self.manual_ylim_mass)

        for ann in (self.hover_pressure, self.hover_mass):
            if ann.get_visible():
                ann.set_visible(False)

        self._update_placeholder("Plot data cleared.")

    def get_plot_data(self):
        return {
            "time": list(self.times),
            "pressure": list(self.pressures),
            "mass": list(self.masses),
        }

    def export_as_image(self):
        if not self.times and not (self.placeholder and self.placeholder.get_visible()):
            QMessageBox.warning(self, "Empty Plot", "Plot has no data to export.")
            return
        default_name = f"plot_export_{time.strftime('%Y%m%d-%H%M%S')}.png"
        path, _ = QFileDialog.getSaveFileName(
            self, "Save Plot Image", default_name,
            "PNG (*.png);;JPEG (*.jpg);;SVG (*.svg);;PDF (*.pdf)",
        )
        if not path:
            return
        try:
            anns = [
                (self.hover_pressure, self.hover_pressure.get_visible()),
                (self.hover_mass, self.hover_mass.get_visible()),
                (self.placeholder, self.placeholder and self.placeholder.get_visible()),
            ]
            for ann, vis in anns:
                if ann and vis:
                    ann.set_visible(False)
            self.canvas.draw()
            self.fig.savefig(path, dpi=300, facecolor=self.fig.get_facecolor())
            for ann, vis in anns:
                if ann and vis:
                    ann.set_visible(True)
            self.canvas.draw_idle()
            sb = self.window().statusBar() if self.window() else None
            if sb:
                sb.showMessage(f"Plot exported to {os.path.basename(path)}", 3000)
        except Exception as e:
            log.exception(f"Error exporting plot image: {e}")
            QMessageBox.critical(self, "Export Error", f"Could not save plot image: {e}")
