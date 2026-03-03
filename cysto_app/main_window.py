# cysto_app/main_window.py

import os
import sys
import logging
import csv
import subprocess

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
)
import utils.config as config
from utils.config import (
    APP_NAME,
    APP_VERSION,
    set_results_dir,
    ABOUT_TEXT,
)
from utils.path_helpers import resource_path
from ui.control_panels.top_control_panel import TopControlPanel
from ui.control_panels.plot_control_panel import PlotControlPanel
from ui.control_panels.pump_control_panel import PumpControlPanel
from ui.canvas.pressure_plot_widget import PressurePlotWidget

from threads.serial_thread import SerialThread
from utils.utils import list_serial_ports, timestamped_filename
from utils.path_helpers import get_next_fill_folder

log = logging.getLogger(__name__)


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
        self._last_data_time: float = 0.0

        self._init_paths_and_icons()
        self._build_console_log_dock()
        self._build_central_widget_layout()
        self._build_menus()
        self._build_main_toolbar()
        self._build_status_bar()

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
            return QIcon(path) if os.path.exists(path) else QIcon()

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
        pc.clear_plot_requested.connect(pw.clear_plot)
        pc.layout_changed.connect(pw.set_layout)

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
            self.pressure_plot_widget.clear_plot()
            self.statusBar().showMessage("Pressure plot data cleared.", 3000)

    @pyqtSlot()
    def _on_zero_device(self):
        """Send the zeroing command to the CystoMoto device and clear the plot."""
        try:
            if self.pressure_plot_widget and hasattr(
                self.pressure_plot_widget, "clear_plot"
            ):
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

    def _start_recording(self):
        """Open a new CSV file in a new FillN folder and begin recording."""
        try:
            fill_folder = get_next_fill_folder()
            filename = timestamped_filename("pressure_data", "csv")
            filepath = os.path.join(fill_folder, filename)
            self._csv_file = open(filepath, "w", newline="")
            self._csv_writer = csv.writer(self._csv_file)
            self._csv_writer.writerow(
                ["Frame Index", "Time (s)", "Pressure (mmHg)", "Mass (g)", "Pump Running"]
            )
            self._recording_path = filepath
            folder_name = os.path.basename(fill_folder)
            self.statusBar().showMessage(
                f"Recording started: {folder_name}/{filename}", 5000
            )
            log.info(f"Recording started: {filepath}")
        except Exception:
            log.exception("Failed to start recording")
            self._csv_file = None
            self._csv_writer = None
            self._recording_path = None

    def _stop_recording(self):
        """Flush and close the current CSV recording file."""
        if self._csv_file:
            try:
                self._csv_file.flush()
                self._csv_file.close()
                log.info(f"Recording stopped: {self._recording_path}")
            except Exception:
                log.exception("Error closing CSV file")
            finally:
                self._csv_file = None
                self._csv_writer = None
                self._recording_path = None

    # ─── Pump control slots ──────────────────────────────────────────────────

    @pyqtSlot()
    def _on_start_pump(self):
        """Send command to start the syringe pump."""
        try:
            self._pump_running = True
            self.pump_ctrl.update_pump_state(True)
            self.pressure_plot_widget.add_pump_marker(self._last_data_time, running=True)

            if self._serial_thread and self._serial_thread.isRunning():
                self._serial_thread.send_command("L")
            self.statusBar().showMessage("Pump started.", 4000)
        except Exception:
            log.exception("Failed to start pump")

    @pyqtSlot()
    def _on_stop_pump(self):
        """Send command to stop the syringe pump."""
        try:
            self._pump_running = False
            self.pump_ctrl.update_pump_state(False)
            self.pressure_plot_widget.add_pump_marker(self._last_data_time, running=False)

            if self._serial_thread and self._serial_thread.isRunning():
                self._serial_thread.send_command("O")
            self.statusBar().showMessage(
                "Pump stopped. Recording continues (pump marked off)." if self._recording_active
                else "Pump stopped.",
                4000,
            )
        except Exception:
            log.exception("Failed to stop pump")

    @pyqtSlot()
    def _on_start_recording(self):
        """Clear the plot, open a new CSV file, and begin recording."""
        try:
            # Fresh trace for this recording session
            self.pressure_plot_widget.clear_plot()
            self._start_recording()
            self._recording_active = True
            self.pump_ctrl.update_recording_state(True)
        except Exception:
            log.exception("Failed to start recording")

    @pyqtSlot()
    def _on_stop_recording(self):
        """Finalize the CSV recording and stop the pump if it is still running."""
        try:
            # Stop the pump first so the last CSV rows reflect the correct state
            if self._pump_running:
                if self._serial_thread and self._serial_thread.isRunning():
                    self._serial_thread.send_command("O")
                self._pump_running = False

            self._stop_recording()
            self._recording_active = False
            self.pump_ctrl.update_pump_state(False)
            self.pump_ctrl.update_recording_state(False)
            self.statusBar().showMessage("Recording stopped.", 4000)
        except Exception:
            log.exception("Failed to stop recording")

    def _set_initial_control_states(self):
        if hasattr(self, "plot_control_panel"):
            self.plot_control_panel.setEnabled(True)

    # ─── Menu Actions & Dialog Slots ──────────────────────────────────────────
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
                with open(path, "w", newline="") as f:
                    writer = csv.writer(f)
                    writer.writerow(["Time (s)", "Pressure (mmHg)", "Mass (g)"])
                    for t, p, m in zip(data["time"], data["pressure"], data["mass"]):
                        writer.writerow([t, p, m])
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
    def _handle_serial_status_change(self, status: str):
        log.info(f"Serial status: {status}")
        self.statusBar().showMessage(f"CystoMoto Device: {status}", 4000)
        self.serial_status_label.setText(f"Serial: {status}")

        connected_flag = (
            "connected" in status.lower() or "opened serial port" in status.lower()
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
        self._last_data_time = t
        # Always update device status display regardless of recording state
        self.top_ctrl.update_device_data(idx, t, p)

        # Plot and CSV are only active while recording
        if not self._recording_active:
            return

        ax = self.plot_control_panel.auto_x_cb.isChecked()
        ay = self.plot_control_panel.auto_y_cb.isChecked()
        ay_mass = self.plot_control_panel.auto_y_mass_cb.isChecked()

        self.pressure_plot_widget.update_plot(t, p, mass, ax, ay, ay_mass)

        if self._csv_writer:
            self._csv_writer.writerow(
                [idx, f"{t:.4f}", f"{p:.4f}", f"{mass:.4f}", 1 if self._pump_running else 0]
            )

        if self.dock_console.isVisible():
            self.console_out_textedit.append(
                f"Data: Idx={idx}, Time={t:.3f}s, P={p:.2f}, Mass={mass:.2f}g"
            )

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
