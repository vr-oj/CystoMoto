# cysto_app/main_window.py

import os
import sys
import logging
import csv
import json
import subprocess
import time
from datetime import datetime
from collections import deque

from PyQt5.QtWidgets import (
    QApplication,
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QDockWidget,
    QTextEdit,
    QToolBar,
    QAction,
    QFileDialog,
    QComboBox,
    QMessageBox,
    QSizePolicy,
    QHBoxLayout,
    QCheckBox,
    QLabel,
)
from PyQt5.QtCore import (
    Qt,
    pyqtSlot,
    QTimer,
    QVariant,
    QSize,
)
from PyQt5.QtGui import QIcon, QKeySequence, QDesktopServices
from PyQt5.QtCore import QUrl

from utils.app_settings import (
    save_app_setting,
    load_app_setting,
    SETTING_RESULTS_DIR,
    SETTING_OPEN_FOLDER_PROMPT,
    SETTING_RUN_METADATA_DEFAULTS,
)
import utils.config as config
from utils.config import (
    APP_NAME,
    APP_VERSION,
    set_results_dir,
    ABOUT_TEXT,
)
from utils.path_helpers import resource_path
from utils.icon_helpers import load_icon
from ui.control_panels.top_control_panel import TopControlPanel
from ui.control_panels.plot_control_panel import PlotControlPanel
from ui.control_panels.pump_control_panel import PumpControlPanel
from ui.canvas.pressure_plot_widget import PressurePlotWidget
from ui.run_metadata_dialog import RunMetadataDialog

from threads.serial_thread import SerialThread
from utils.utils import list_serial_ports, timestamped_filename
from utils.path_helpers import get_next_fill_folder

log = logging.getLogger(__name__)

CSV_HEADER = [
    "Frame Index",
    "Time (s)",
    "Pressure (mmHg)",
    "Mass (g)",
    "Pump Running",
    "Pump Event",
    "Marker Time (s)",
]
CSV_PUMP_EVENT_COL = 5
CSV_MARKER_TIME_COL = 6


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()

        # ─── State Variables ─────────────────────────────────────────────────────
        self._serial_thread = None
        self._serial_active = False
        self._open_folder_prompt = load_app_setting(SETTING_OPEN_FOLDER_PROMPT, True)

        self.plot_control_panel = None
        self.top_ctrl = None
        self.pump_ctrl = None
        self.pressure_plot_widget = None

        # Recording state
        self._pump_running = False
        self._recording_active = False
        self._csv_file = None
        self._csv_writer = None
        self._recording_path = None
        self._recording_metadata_path = None
        self._recording_metadata = {}
        self._last_data_time: float = 0.0
        self._recording_time_origin: float | None = None
        self._t_offset: float = 0.0   # accumulated offset from Arduino timer resets
        self._last_raw_t: float = 0.0  # last raw t received from Arduino
        self._pending_csv_events = deque()  # queued tuples[(marker_time, running)]
        self._pending_csv_sample_row = None
        self._pending_plot_samples = []  # list[(t, p, mass)] waiting for batched draw
        self._csv_row_buffer = []  # buffered CSV rows to reduce per-packet file I/O

        self._plot_batch_size = 512
        self._csv_flush_threshold = 256
        self._status_update_interval_s = 0.05
        self._console_update_interval_s = 0.10
        self._last_status_update_s = 0.0
        self._last_console_update_s = 0.0

        self._init_paths_and_icons()
        self._build_console_log_dock()
        self._build_central_widget_layout()
        self._build_menus()
        self._build_main_toolbar()
        self._build_status_bar()
        self._init_background_timers()

        self._set_initial_control_states()

        self.setWindowTitle(f"{APP_NAME} - v{APP_VERSION}")
        log.info("MainWindow initialized.")
        self.showMaximized()

    # ─── UI Builders ────────────────────────────────────────────────────────

    def _init_paths_and_icons(self):
        base = resource_path()
        icon_dir = os.path.join(base, "ui", "icons")
        if not os.path.isdir(icon_dir):
            alt_icon_dir = os.path.join(
                os.path.dirname(base), "cysto_app", "ui", "icons"
            )
            if os.path.isdir(alt_icon_dir):
                icon_dir = alt_icon_dir
            else:
                another_alt_icon_dir = os.path.join(
                    os.path.dirname(base), "ui", "icons"
                )
                if os.path.isdir(another_alt_icon_dir):
                    icon_dir = another_alt_icon_dir
                else:
                    log.warning(
                        f"Icon directory not found. Looked in: {icon_dir}, {alt_icon_dir}, {another_alt_icon_dir}"
                    )

        def get_icon(name):
            path = os.path.join(icon_dir, name)
            return load_icon(path) if os.path.exists(path) else QIcon()

        self.icon_connect = get_icon("plug.svg")
        self.icon_disconnect = get_icon("plug_disconnect.svg")
        self.icon_refresh = get_icon("sync.svg")

    def _build_console_log_dock(self):
        self.dock_console = QDockWidget("Console Log", self)
        self.dock_console.setObjectName("ConsoleLogDock")
        self.dock_console.setAllowedAreas(
            Qt.BottomDockWidgetArea | Qt.TopDockWidgetArea
        )
        console_widget = QWidget()
        layout = QVBoxLayout(console_widget)
        self.console_out_textedit = QTextEdit(readOnly=True)
        self.console_out_textedit.setFontFamily("monospace")
        # Keep console memory bounded during long acquisitions.
        self.console_out_textedit.document().setMaximumBlockCount(5000)
        layout.addWidget(self.console_out_textedit)
        self.dock_console.setWidget(console_widget)
        self.addDockWidget(Qt.BottomDockWidgetArea, self.dock_console)
        self.dock_console.setVisible(False)

    def _build_central_widget_layout(self):
        """
        Top row: CystoMoto Device status | Plot Controls.
        Bottom row: PressurePlotWidget (live plot, full width).
        """
        central = QWidget()
        main_vlay = QVBoxLayout(central)
        main_vlay.setContentsMargins(4, 4, 4, 4)
        main_vlay.setSpacing(6)

        # ─── Top Row (Control Ribbon) ─────────────────────────────────────
        top_row_widget = QWidget()
        top_row_lay = QHBoxLayout(top_row_widget)
        top_row_lay.setContentsMargins(0, 0, 0, 0)
        top_row_lay.setSpacing(10)

        self.top_ctrl = TopControlPanel(self)
        self.top_ctrl.zero_requested.connect(self._on_zero_device)
        top_row_lay.addWidget(self.top_ctrl, stretch=2)

        self.pump_ctrl = PumpControlPanel(self)
        self.pump_ctrl.pump_start_requested.connect(self._on_start_pump)
        self.pump_ctrl.pump_stop_requested.connect(self._on_stop_pump)
        self.pump_ctrl.record_start_requested.connect(self._on_start_recording)
        self.pump_ctrl.record_stop_requested.connect(self._on_stop_recording)
        top_row_lay.addWidget(self.pump_ctrl, stretch=1)

        self.plot_control_panel = PlotControlPanel(self)
        top_row_lay.addWidget(self.plot_control_panel, stretch=2)

        main_vlay.addWidget(top_row_widget, stretch=0)

        # ─── Bottom Row ───────────────────────────────────────────────────
        self.pressure_plot_widget = PressurePlotWidget(self)
        self.pressure_plot_widget.setSizePolicy(
            QSizePolicy.Expanding, QSizePolicy.Expanding
        )
        main_vlay.addWidget(self.pressure_plot_widget, stretch=1)

        # ─── Wire Up PlotControlPanel → PressurePlotWidget ────────────────
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
        pc.clear_plot_requested.connect(self._clear_pressure_plot)
        pc.layout_changed.connect(pw.set_layout)
        pc.window_duration_changed.connect(pw.set_window_duration)
        if hasattr(pw, "manual_x_mode_requested"):
            pw.manual_x_mode_requested.connect(
                lambda: pc.auto_x_cb.isChecked() and pc.auto_x_cb.setChecked(False)
            )

        self.setCentralWidget(central)

    def _refresh_serial_port_list(self):
        ports = list_serial_ports()
        self.serial_port_combobox.clear()
        if ports:
            for p_dev, p_desc in ports:
                self.serial_port_combobox.addItem(
                    f"{os.path.basename(p_dev)} ({p_desc})", QVariant(p_dev)
                )
            self.serial_port_combobox.setEnabled(True)
        else:
            self.serial_port_combobox.addItem("No Serial Ports Found", QVariant())
            self.serial_port_combobox.setEnabled(False)

    @pyqtSlot()
    def _refresh_device_lists(self):
        self._refresh_serial_port_list()
        self.statusBar().showMessage("Device lists refreshed", 3000)

    def _build_menus(self):
        mb = self.menuBar()
        fm = mb.addMenu("&File")
        exp_data_act = QAction(
            "Export Plot &Data (CSV)…", self, triggered=self._export_plot_data_as_csv
        )
        fm.addAction(exp_data_act)
        exp_img_act = QAction("Export Plot &Image…", self)
        exp_img_act.triggered.connect(self.pressure_plot_widget.export_as_image)
        fm.addAction(exp_img_act)
        choose_dir_act = QAction(
            "Set &Results Folder…", self, triggered=self._choose_results_dir
        )
        fm.addAction(choose_dir_act)
        fm.addSeparator()
        exit_act = QAction(
            "&Exit", self, shortcut=QKeySequence.Quit, triggered=self.close
        )
        fm.addAction(exit_act)

        vm = mb.addMenu("&View")
        if hasattr(self, "dock_console") and self.dock_console:
            vm.addAction(self.dock_console.toggleViewAction())

        pm = mb.addMenu("&Plot")
        clear_plot_act = QAction(
            "&Clear Plot Data", self, triggered=self._clear_pressure_plot
        )
        pm.addAction(clear_plot_act)

        def trigger_reset_zoom():
            self.pressure_plot_widget.reset_zoom(
                self.plot_control_panel.is_autoscale_x(),
                self.plot_control_panel.is_autoscale_y(),
                self.plot_control_panel.is_autoscale_y_mass(),
            )

        reset_zoom_act = QAction("&Reset Plot Zoom", self, triggered=trigger_reset_zoom)
        pm.addAction(reset_zoom_act)

        hm = mb.addMenu("&Help")
        welcome_act = QAction("&Show Welcome", self, triggered=self._show_welcome_dialog)
        hm.addAction(welcome_act)
        readme_act = QAction("&Open User Guide", self, triggered=self._open_readme)
        hm.addAction(readme_act)
        about_act = QAction(
            f"&About {APP_NAME}", self, triggered=self._show_about_dialog
        )
        hm.addAction(about_act)
        hm.addAction("About &Qt", QApplication.instance().aboutQt)

    def _build_main_toolbar(self):
        tb = QToolBar("Main Controls")
        tb.setObjectName("MainControlsToolbar")
        tb.setIconSize(QSize(20, 20))
        tb.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self.addToolBar(Qt.TopToolBarArea, tb)

        self.refresh_action = QAction(
            self.icon_refresh,
            "&Refresh Devices",
            self,
            triggered=self._refresh_device_lists,
        )
        tb.addAction(self.refresh_action)

        self.connect_serial_action = QAction(
            self.icon_connect,
            "&Connect CystoMoto Device",
            self,
            triggered=self._toggle_serial_connection,
        )
        tb.addAction(self.connect_serial_action)

        self.serial_port_combobox = QComboBox()
        self.serial_port_combobox.setToolTip("Select Serial Port")
        self.serial_port_combobox.setMinimumWidth(200)
        self._refresh_serial_port_list()
        tb.addWidget(self.serial_port_combobox)

    def _build_status_bar(self):
        sb = self.statusBar()
        self.serial_status_label = QLabel("Serial: Disconnected")
        self.app_session_time_label = QLabel("Session: 00:00:00")
        sb.addPermanentWidget(self.serial_status_label)
        sb.addPermanentWidget(self.app_session_time_label)
        self._app_session_seconds = 0
        self._app_session_timer = QTimer(self)
        self._app_session_timer.setInterval(1000)
        self._app_session_timer.timeout.connect(self._update_app_session_time)
        self._app_session_timer.start()

    def _init_background_timers(self):
        # Plot redraw timer: decouples serial packet rate from UI redraw rate.
        self._plot_update_timer = QTimer(self)
        self._plot_update_timer.setInterval(33)  # ~30 FPS max redraw
        self._plot_update_timer.timeout.connect(self._drain_plot_samples)
        self._plot_update_timer.start()

        # CSV timer: writes buffered rows in chunks while recording.
        self._csv_flush_timer = QTimer(self)
        self._csv_flush_timer.setInterval(200)
        self._csv_flush_timer.timeout.connect(self._flush_csv_rows)

    @pyqtSlot()
    def _update_app_session_time(self):
        self._app_session_seconds += 1
        hours, rem = divmod(self._app_session_seconds, 3600)
        minutes, seconds = divmod(rem, 60)
        self.app_session_time_label.setText(
            f"Session: {hours:02d}:{minutes:02d}:{seconds:02d}"
        )

    @pyqtSlot()
    def _clear_pressure_plot(self):
        if self.pressure_plot_widget and hasattr(
            self.pressure_plot_widget, "clear_plot"
        ):
            self._pending_plot_samples.clear()
            self.pressure_plot_widget.clear_plot()
            self.statusBar().showMessage("Pressure plot data cleared.", 3000)

    @pyqtSlot()
    def _on_zero_device(self):
        """Send the zeroing command to the CystoMoto device and clear the plot."""
        try:
            if self.pressure_plot_widget and hasattr(
                self.pressure_plot_widget, "clear_plot"
            ):
                self._pending_plot_samples.clear()
                self.pressure_plot_widget.clear_plot()

            if self._serial_thread and self._serial_thread.isRunning():
                self._serial_thread.send_command("Z")
                msg = "Zero command sent to device and plot cleared."
            else:
                msg = "CystoMoto device not connected; plot cleared."

            self.statusBar().showMessage(msg, 3000)
        except Exception:
            log.exception("Failed to send zero command to device")

    # ─── Recording helpers ───────────────────────────────────────────────────

    def _default_recording_path(self) -> str:
        fill_folder = get_next_fill_folder(create=False)
        return os.path.join(fill_folder, timestamped_filename("pressure_data", "csv"))

    @staticmethod
    def _metadata_path_for_csv(csv_path: str) -> str:
        stem, _ = os.path.splitext(csv_path)
        return f"{stem}_metadata.json"

    def _current_serial_port_label(self) -> str:
        if self._serial_thread and getattr(self._serial_thread, "port", None):
            return str(self._serial_thread.port)
        data = self.serial_port_combobox.currentData()
        if isinstance(data, QVariant):
            data = data.value()
        return str(data) if data else ""

    def _prompt_run_setup(self):
        defaults = load_app_setting(SETTING_RUN_METADATA_DEFAULTS, {})
        if not isinstance(defaults, dict):
            defaults = {}
        dlg = RunMetadataDialog(self._default_recording_path(), defaults, self)
        if dlg.exec_() != dlg.Accepted:
            return None
        run_setup = dlg.get_run_setup()
        save_app_setting(SETTING_RUN_METADATA_DEFAULTS, run_setup["metadata"])
        return run_setup

    def _build_run_metadata_payload(self, csv_path: str, run_metadata: dict) -> dict:
        return {
            "app_name": APP_NAME,
            "app_version": APP_VERSION,
            "created_at": datetime.now().isoformat(timespec="seconds"),
            "csv_path": csv_path,
            "device_port": self._current_serial_port_label(),
            "metadata": dict(run_metadata),
        }

    def _start_recording(self, csv_path: str, run_metadata: dict):
        """Open the run CSV and companion metadata file and begin recording."""
        csv_file = None
        csv_writer = None
        metadata_path = self._metadata_path_for_csv(csv_path)
        try:
            os.makedirs(os.path.dirname(csv_path), exist_ok=True)

            csv_file = open(csv_path, "w", newline="")
            csv_writer = csv.writer(csv_file)
            csv_writer.writerow(CSV_HEADER)
            csv_file.flush()

            with open(metadata_path, "w") as metadata_file:
                json.dump(
                    self._build_run_metadata_payload(csv_path, run_metadata),
                    metadata_file,
                    indent=2,
                )

            self._csv_file = csv_file
            self._csv_writer = csv_writer
            self._recording_path = csv_path
            self._recording_metadata_path = metadata_path
            self._recording_metadata = dict(run_metadata)
            self.statusBar().showMessage(
                f"Recording started: {os.path.basename(os.path.dirname(csv_path))}/{os.path.basename(csv_path)}",
                5000,
            )
            log.info("Recording started: %s", csv_path)
        except Exception:
            log.exception("Failed to start recording")
            try:
                if csv_file:
                    csv_file.close()
            except Exception:
                pass
            try:
                if os.path.exists(csv_path):
                    os.remove(csv_path)
            except Exception:
                pass
            try:
                if os.path.exists(metadata_path):
                    os.remove(metadata_path)
            except Exception:
                pass
            self._csv_file = None
            self._csv_writer = None
            self._recording_path = None
            self._recording_metadata_path = None
            self._recording_metadata = {}

    def _stop_recording(self):
        """Flush and close the current CSV recording file."""
        if self._csv_file:
            try:
                self._flush_csv_rows()
                self._csv_file.flush()
                self._csv_file.close()
                log.info(f"Recording stopped: {self._recording_path}")
            except Exception:
                log.exception("Error closing CSV file")
            finally:
                self._csv_file = None
                self._csv_writer = None
                self._recording_path = None
                self._recording_metadata_path = None
                self._recording_metadata = {}

    @classmethod
    def _append_events_to_csv_row(cls, row, events):
        if not events:
            return
        labels = ";".join(cls._pump_event_label(bool(running)) for _, running in events)
        marker_times = ";".join(f"{marker_t:.4f}" for marker_t, _ in events)
        if row[CSV_PUMP_EVENT_COL]:
            row[CSV_PUMP_EVENT_COL] = f"{row[CSV_PUMP_EVENT_COL]};{labels}"
        else:
            row[CSV_PUMP_EVENT_COL] = labels
        if row[CSV_MARKER_TIME_COL]:
            row[CSV_MARKER_TIME_COL] = f"{row[CSV_MARKER_TIME_COL]};{marker_times}"
        else:
            row[CSV_MARKER_TIME_COL] = marker_times

    @classmethod
    def _build_csv_sample_row(cls, idx, t_plot, pressure, mass, pump_running, events=None):
        row = [
            "" if idx is None else idx,
            f"{t_plot:.4f}",
            f"{pressure:.4f}",
            f"{mass:.4f}",
            1 if pump_running else 0,
            "",
            "",
        ]
        cls._append_events_to_csv_row(row, events or [])
        return row

    def _finalize_pending_csv_sample_row(self):
        if self._pending_csv_sample_row is None:
            return
        self._queue_csv_row(self._pending_csv_sample_row)
        self._pending_csv_sample_row = None

    def _attach_pending_events_to_pending_row(self):
        if not self._pending_csv_events:
            return
        events = list(self._pending_csv_events)
        self._pending_csv_events.clear()
        if self._pending_csv_sample_row is None:
            log.warning(
                "Dropping %d pending pump events because there is no sample row to attach them to.",
                len(events),
            )
            return
        self._append_events_to_csv_row(self._pending_csv_sample_row, events)

    def _current_recording_marker_time(self) -> float:
        if self._recording_time_origin is None:
            return 0.0
        return max(0.0, self._last_data_time - self._recording_time_origin)

    def _register_pump_event(self, running: bool):
        if not self._recording_active:
            return
        marker_t = self._current_recording_marker_time()
        self._pending_csv_events.append((marker_t, running))
        if self.pressure_plot_widget:
            self.pressure_plot_widget.add_pump_marker(marker_t, running)

    def _queue_csv_row(self, row):
        if not self._csv_writer:
            return
        self._csv_row_buffer.append(row)
        if len(self._csv_row_buffer) >= self._csv_flush_threshold:
            self._flush_csv_rows()

    @pyqtSlot()
    def _flush_csv_rows(self):
        if not self._csv_writer or not self._csv_row_buffer:
            return
        try:
            self._csv_writer.writerows(self._csv_row_buffer)
            self._csv_row_buffer.clear()
            if self._csv_file:
                self._csv_file.flush()
        except Exception:
            log.exception("Failed flushing buffered CSV rows")

    @pyqtSlot()
    def _drain_plot_samples(self):
        if not self._pending_plot_samples:
            return
        if not self.pressure_plot_widget:
            self._pending_plot_samples.clear()
            return

        ax = self.plot_control_panel.auto_x_cb.isChecked()
        ay = self.plot_control_panel.auto_y_cb.isChecked()
        ay_mass = self.plot_control_panel.auto_y_mass_cb.isChecked()

        batch = self._pending_plot_samples
        self._pending_plot_samples = []
        self.pressure_plot_widget.update_plot_batch(batch, ax, ay, ay_mass)

    # ─── Pump control slots ──────────────────────────────────────────────────

    @pyqtSlot()
    def _on_start_pump(self):
        """Send command to start the syringe pump."""
        try:
            self._pump_running = True
            self.pump_ctrl.update_pump_state(True)
            if self._recording_active:
                self._register_pump_event(True)

            if self._serial_thread and self._serial_thread.isRunning():
                self._serial_thread.send_command("G")
            self.statusBar().showMessage("Pump started.", 4000)
        except Exception:
            log.exception("Failed to start pump")

    @pyqtSlot()
    def _on_stop_pump(self):
        """Send command to stop the syringe pump."""
        try:
            self._pump_running = False
            self.pump_ctrl.update_pump_state(False)
            if self._recording_active:
                self._register_pump_event(False)

            if self._serial_thread and self._serial_thread.isRunning():
                self._serial_thread.send_command("S")
            self.statusBar().showMessage("Pump stopped.", 4000)
        except Exception:
            log.exception("Failed to stop pump")

    @pyqtSlot()
    def _on_start_recording(self):
        """Clear the plot, open a new CSV file, and begin recording."""
        try:
            run_setup = self._prompt_run_setup()
            if not run_setup:
                return

            # Fresh trace for this recording session
            self.pressure_plot_widget.clear_plot()
            self._pending_csv_events.clear()
            self._pending_csv_sample_row = None
            self._pending_plot_samples.clear()
            self._csv_row_buffer.clear()
            self._start_recording(
                run_setup["csv_path"],
                run_setup.get("metadata", {}),
            )
            if not self._csv_writer:
                self.statusBar().showMessage("Failed to start recording.", 4000)
                self._recording_active = False
                self._csv_flush_timer.stop()
                return
            self._t_offset = 0.0
            self._last_raw_t = 0.0
            self._recording_time_origin = None
            self._last_status_update_s = 0.0
            self._last_console_update_s = 0.0
            self._recording_active = True
            self._csv_flush_timer.start()
            self.pump_ctrl.update_recording_state(True)
        except Exception:
            log.exception("Failed to start recording")

    @pyqtSlot()
    def _on_stop_recording(self):
        """Finalize the CSV recording."""
        try:
            self._drain_plot_samples()
            self._attach_pending_events_to_pending_row()
            self._finalize_pending_csv_sample_row()
            self._flush_csv_rows()
            self._csv_flush_timer.stop()
            self._stop_recording()
            self._recording_active = False
            self._recording_time_origin = None
            self._pending_csv_events.clear()
            self._pending_csv_sample_row = None
            self._pending_plot_samples.clear()
            self._csv_row_buffer.clear()
            self.pump_ctrl.update_recording_state(False)
            self.statusBar().showMessage("Recording stopped.", 4000)
        except Exception:
            log.exception("Failed to stop recording")

    def _set_initial_control_states(self):
        if hasattr(self, "plot_control_panel"):
            self.plot_control_panel.setEnabled(True)

    # ─── Menu Actions & Dialog Slots ──────────────────────────────────────────
    @staticmethod
    def _pump_event_label(running: bool) -> str:
        return "Pump ON" if running else "Pump OFF"

    @classmethod
    def _build_plot_export_rows(cls, times, pressures, masses, pump_markers):
        """Build CSV rows with marker metadata folded into sample rows."""
        rows = []
        sorted_markers = (
            sorted(pump_markers, key=lambda pair: pair[0]) if pump_markers else []
        )
        marker_idx = 0
        running = False
        eps = 1e-9
        pending_row = None

        for t, p, m in zip(times, pressures, masses):
            if pending_row is not None:
                rows.append(pending_row)

            events_here = []
            while (
                marker_idx < len(sorted_markers)
                and sorted_markers[marker_idx][0] <= t + eps
            ):
                marker_t, marker_running = sorted_markers[marker_idx]
                running = bool(marker_running)
                events_here.append((marker_t, running))
                marker_idx += 1

            pending_row = cls._build_csv_sample_row(
                idx=None,
                t_plot=t,
                pressure=p,
                mass=m,
                pump_running=running,
                events=events_here,
            )

        if pending_row is not None:
            if marker_idx < len(sorted_markers):
                cls._append_events_to_csv_row(
                    pending_row,
                    sorted_markers[marker_idx:],
                )
            rows.append(pending_row)

        return rows

    def _export_plot_data_as_csv(self):
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Export Plot Data as CSV",
            config.CYSTO_RESULTS_DIR,
            "CSV Files (*.csv)",
        )
        if path:
            try:
                data = self.pressure_plot_widget.get_plot_data()
                export_rows = self._build_plot_export_rows(
                    data["time"],
                    data["pressure"],
                    data["mass"],
                    data.get("pump_markers", []),
                )
                with open(path, "w", newline="") as f:
                    writer = csv.writer(f)
                    writer.writerow(CSV_HEADER)
                    writer.writerows(export_rows)
                self.statusBar().showMessage(f"Plot data exported to {path}", 3000)
            except Exception as e:
                log.error(f"Error exporting CSV: {e}")
                QMessageBox.critical(
                    self, "Export Error", f"Failed to export CSV:\n{e}"
                )

    def _choose_results_dir(self):
        new_dir = QFileDialog.getExistingDirectory(
            self, "Select Results Folder", config.CYSTO_RESULTS_DIR
        )
        if new_dir:
            results_dir = os.path.join(new_dir, "CystoMoto Results")
            set_results_dir(results_dir)
            save_app_setting(SETTING_RESULTS_DIR, results_dir)
            self.statusBar().showMessage(f"Results folder set to {results_dir}", 5000)

    def _show_error_dialog(self, title: str, message: str, details: str = None):
        dlg = QMessageBox(
            QMessageBox.Critical,
            title,
            message,
            QMessageBox.Ok,
            self,
        )
        if details:
            dlg.setDetailedText(details)
        dlg.exec_()

    def _show_about_dialog(self):
        QMessageBox.information(self, f"About {APP_NAME}", ABOUT_TEXT)

    def _show_welcome_dialog(self):
        from ui.welcome_dialog import WelcomeDialog
        dlg = WelcomeDialog(parent=self, force_show=True)
        dlg.exec_()

    def _open_readme(self):
        path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "README.md"))
        QDesktopServices.openUrl(QUrl.fromLocalFile(path))

    # ─── Toggle Serial Connection ────────────────────────────────────────────
    def _toggle_serial_connection(self):
        if self._serial_thread is None or not self._serial_thread.isRunning():
            data = self.serial_port_combobox.currentData()
            port = data.value() if isinstance(data, QVariant) else data

            if port is None:
                QMessageBox.warning(self, "Serial Connection", "Please select a port.")
                return

            log.info(f"Starting SerialThread on port: {port}")
            try:
                if self._serial_thread:
                    if self._serial_thread.isRunning():
                        self._serial_thread.stop()
                        if not self._serial_thread.wait(1000):
                            self._serial_thread.terminate()
                            self._serial_thread.wait(500)
                    self._serial_thread.deleteLater()
                    self._serial_thread = None

                self._serial_thread = SerialThread(port=port, parent=self)
                self._serial_thread.data_ready.connect(self._handle_new_serial_data)
                self._serial_thread.error_occurred.connect(self._handle_serial_error)
                self._serial_thread.status_changed.connect(
                    self._handle_serial_status_change
                )
                self._serial_thread.device_event.connect(
                    self._handle_device_event
                )
                self._serial_thread.finished.connect(
                    self._handle_serial_thread_finished
                )
                self._serial_thread.start()

                self.connect_serial_action.setIcon(self.icon_disconnect)
                self.connect_serial_action.setText("Disconnect CystoMoto Device")
                self.serial_port_combobox.setEnabled(False)

            except Exception as e:
                log.exception("Failed to start SerialThread.")
                QMessageBox.critical(self, "Serial Error", str(e))
                if self._serial_thread:
                    self._serial_thread.deleteLater()
                self._serial_thread = None
                self.serial_port_combobox.setEnabled(True)

        else:
            log.info("Stopping SerialThread on user request...")
            try:
                self._serial_thread.stop()
            except Exception as e:
                log.error(f"Error while stopping SerialThread: {e}")
            try:
                if self._serial_thread is not None:
                    self._serial_thread.finished.disconnect(
                        self._handle_serial_thread_finished
                    )
            except TypeError:
                pass

            self.connect_serial_action.setIcon(self.icon_connect)
            self.connect_serial_action.setText("Connect CystoMoto Device")
            self.serial_port_combobox.setEnabled(True)
            self._serial_thread = None

            self._on_stop_recording()
            self._pump_running = False
            self.pump_ctrl.update_pump_state(False)
            self.pump_ctrl.update_connection_status(False)

    @pyqtSlot(str)
    @pyqtSlot(str)
    def _handle_device_event(self, event: str):
        """Handle status messages sent by the Arduino (e.g. physical button press)."""
        log.info(f"Device event: {event}")
        if event.strip().upper() == "STARTED" and not self._recording_active:
            log.info("Arduino-initiated start detected — auto-starting recording.")
            self._on_start_recording()

    def _handle_serial_status_change(self, status: str):
        log.info(f"Serial status: {status}")
        self.statusBar().showMessage(f"CystoMoto Device: {status}", 4000)
        self.serial_status_label.setText(f"Serial: {status}")

        status_lower = status.lower()
        connected_flag = (
            status_lower == "connected"
            or status_lower.startswith("connected to ")
            or status_lower.startswith("reconnected to ")
            or "opened serial port" in status_lower
        )
        self.top_ctrl.update_connection_status(status, connected_flag)
        self.pump_ctrl.update_connection_status(connected_flag)

    @pyqtSlot(str)
    def _handle_serial_error(self, msg: str):
        log.error(f"Serial error: {msg}")
        hint = "Check the cable and selected port, then try reconnecting."
        self.statusBar().showMessage(f"Serial Error: {msg} — {hint}", 8000)
        self.serial_status_label.setText("Serial: Error")
        self._show_error_dialog("Serial Connection Error", f"{msg}\n\n{hint}")

    @pyqtSlot()
    def _handle_serial_thread_finished(self):
        log.info("SerialThread finished signal received.")
        sender = self.sender()

        if self._serial_thread is not None and sender == self._serial_thread:
            self._serial_thread.deleteLater()
            self._serial_thread = None

            self.connect_serial_action.setIcon(self.icon_connect)
            self.connect_serial_action.setText("Connect CystoMoto Device")
            self.serial_port_combobox.setEnabled(True)

            self._on_stop_recording()
            self._pump_running = False
            self.pump_ctrl.update_pump_state(False)
            self.pump_ctrl.update_connection_status(False)

            log.info("SerialThread instance cleaned up.")
        else:
            log.warning(
                "Received 'finished' from an unknown/old SerialThread instance."
            )

    @pyqtSlot(int, float, float, float)
    def _handle_new_serial_data(self, idx: int, t: float, p: float, mass: float):
        """Called whenever SerialThread emits data_ready(idx, t, p, mass)."""
        # Detect Arduino timer reset and accumulate offset to keep time continuous
        if t < self._last_raw_t:
            self._t_offset += self._last_raw_t
            log.warning(f"Arduino timer reset detected (t={t:.4f} < last={self._last_raw_t:.4f}); offset now {self._t_offset:.4f}s")
        self._last_raw_t = t
        t_adj = t + self._t_offset

        self._last_data_time = t_adj
        now_s = time.monotonic()
        # Throttle device status repaint to keep UI smooth at high packet rates.
        if (now_s - self._last_status_update_s) >= self._status_update_interval_s:
            self.top_ctrl.update_device_data(p, mass)
            self._last_status_update_s = now_s

        # Plot and CSV are only active while recording
        if not self._recording_active:
            return

        if self._recording_time_origin is None:
            self._recording_time_origin = t_adj
        t_plot = max(0.0, t_adj - self._recording_time_origin)

        self._pending_plot_samples.append((t_plot, p, mass))
        if len(self._pending_plot_samples) >= self._plot_batch_size:
            self._drain_plot_samples()

        if self._csv_writer:
            self._finalize_pending_csv_sample_row()
            pending_events = list(self._pending_csv_events)
            self._pending_csv_events.clear()
            self._pending_csv_sample_row = self._build_csv_sample_row(
                idx=idx,
                t_plot=t_plot,
                pressure=p,
                mass=mass,
                pump_running=self._pump_running,
                events=pending_events,
            )

        if self.dock_console.isVisible() and (
            now_s - self._last_console_update_s
        ) >= self._console_update_interval_s:
            self.console_out_textedit.append(
                f"Data: Idx={idx}, Time={t_plot:.3f}s, P={p:.2f}, Mass={mass:.2f}g"
            )
            self._last_console_update_s = now_s

    # ─── Window Close Cleanup ──────────────────────────────────────────────────
    def closeEvent(self, event):
        log.info("MainWindow closeEvent triggered.")

        if self._serial_thread:
            try:
                if self._serial_thread.isRunning():
                    log.info("Stopping SerialThread...")
                    self._serial_thread.stop()
                    if not self._serial_thread.wait(1500):
                        log.warning(
                            "SerialThread did not stop gracefully; forcing terminate."
                        )
                        try:
                            self._serial_thread.terminate()
                        except Exception:
                            pass
                        self._serial_thread.wait(500)

                try:
                    self._serial_thread.finished.disconnect(
                        self._handle_serial_thread_finished
                    )
                except TypeError:
                    pass

            except RuntimeError:
                pass
            finally:
                try:
                    self._serial_thread.deleteLater()
                except Exception:
                    pass
                self._serial_thread = None

        self._on_stop_recording()
        QApplication.processEvents()
        log.info("All threads cleaned up. Proceeding with close.")
        super().closeEvent(event)
