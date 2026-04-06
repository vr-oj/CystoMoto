# cysto_app/threads/serial_thread.py

import logging
import math
import queue
import time

import serial
from PyQt5.QtCore import QMutex, QThread, QWaitCondition, pyqtSignal

from utils.utils import is_virtual_port

log = logging.getLogger(__name__)

# How many seconds of silence on the serial port we interpret
# as "Arduino has stopped streaming." You can tune this if needed.
IDLE_TIMEOUT_S = 2.0

# Virtual CystoMoto simulator timing and shape parameters.
VIRTUAL_SAMPLE_INTERVAL_S = 0.05
VIRTUAL_FILL_RATE_G_PER_S = 0.85
VIRTUAL_CONTRACTION_PERIOD_S = 18.0
VIRTUAL_CONTRACTION_DURATION_S = 3.5


class SerialThread(QThread):
    data_ready = pyqtSignal(int, float, float, float)  # (frameIndex, timestamp_s, pressure, secondary_channel)
    error_occurred = pyqtSignal(str)  # For reporting errors back to the GUI
    status_changed = pyqtSignal(str)  # For general status updates
    device_event = pyqtSignal(str)  # Non-CSV status messages from the Arduino (e.g. "STARTED")

    def __init__(self, port=None, baud=115200, test_csv=None, parent=None):
        super().__init__(parent)
        self.port = port
        self.baud = baud
        self.ser = None
        self._virtual_mode = is_virtual_port(port)

        # Control flags
        self.running = False
        self._got_first_packet = False
        self._last_data_time = None
        self._stop_requested = False

        # For sending commands from the GUI thread.
        self.command_queue = queue.Queue()
        self.mutex = QMutex()
        self.wait_condition = QWaitCondition()

        # Virtual device state
        self._virtual_frame_idx = 0
        self._virtual_stream_started_s = 0.0
        self._virtual_last_sample_s = 0.0
        self._virtual_mass_raw_g = 0.0
        self._virtual_mass_zero_g = 0.0
        self._virtual_pressure_zero_mmhg = 0.0
        self._virtual_pump_running = False
        self._fallback_frame_idx = 0
        self._detected_stream_format = None

    def run(self):
        """Main loop for reading from the CystoMoto device."""
        self.running = True
        self._got_first_packet = False
        self._last_data_time = None
        self._stop_requested = False

        if not self.port:
            self.error_occurred.emit("No serial port specified")
            self.running = False
            return

        try:
            if self._virtual_mode:
                self._run_virtual_device()
            else:
                self._run_serial_device()
        finally:
            if self.ser:
                try:
                    self.ser.close()
                    log.info("Closed serial port %s", self.port)
                except Exception as e:
                    log.exception("Error closing serial port %s: %s", self.port, e)

            self.status_changed.emit("Disconnected")
            self.running = False
            log.info("SerialThread finished.")

    def _run_serial_device(self):
        try:
            self.ser = serial.Serial(self.port, self.baud, timeout=1)
            log.info("Opened serial port %s @ %s baud", self.port, self.baud)
            self.status_changed.emit(f"Connected to {self.port}")
        except Exception as e:
            log.warning("Failed to open serial port %s: %s", self.port, e)
            self.error_occurred.emit(f"Error opening serial: {e}")
            self.ser = None

        while self.running and not self._stop_requested:
            self._process_pending_commands()

            if self.ser is None:
                try:
                    self.ser = serial.Serial(self.port, self.baud, timeout=1)
                    log.info("[SerialThread] Reconnected to %s", self.port)
                    self.status_changed.emit(f"Reconnected to {self.port}")
                except Exception as e_op:
                    log.debug("[SerialThread] Reopen failed: %s; retrying in 0.1 s", e_op)
                    self.msleep(100)
                continue

            try:
                if self.ser.in_waiting > 0:
                    raw = self.ser.readline()
                    if raw:
                        line = raw.decode("utf-8", errors="replace").strip()
                        log.debug("Raw serial data: %s", line)
                        self._handle_incoming_line(line)
                else:
                    self.msleep(10)

            except serial.SerialException as se:
                log.error("[SerialThread] SerialException: %s; will attempt reconnect", se)
                self.status_changed.emit("Serial disconnected, retrying...")
                try:
                    self.ser.close()
                except Exception:
                    pass
                self.ser = None
                t0 = time.time()
                while (
                    self.running
                    and not self._stop_requested
                    and (time.time() - t0) < 1.0
                ):
                    self.msleep(50)
                continue

            except Exception as e:
                log.exception("[SerialThread] Unexpected error in read loop: %s", e)
                self.msleep(100)

            if (
                self._got_first_packet
                and self._last_data_time is not None
                and (time.time() - self._last_data_time) > IDLE_TIMEOUT_S
            ):
                msg = f"No data from Arduino for {time.time() - self._last_data_time:.1f}s"
                log.error("[SerialThread] %s", msg)
                self.error_occurred.emit(msg)
                self._stop_requested = True

    def _run_virtual_device(self):
        self._reset_virtual_state()
        self.status_changed.emit("Connected to Virtual CystoMoto (simulated)")

        next_sample_s = time.monotonic()
        while self.running and not self._stop_requested:
            self._process_pending_commands()

            now_s = time.monotonic()
            if now_s >= next_sample_s:
                idx, elapsed_s, pressure_mmhg, mass_g = self._build_virtual_sample(now_s)
                self.data_ready.emit(idx, elapsed_s, pressure_mmhg, mass_g)
                self._got_first_packet = True
                self._last_data_time = time.time()

                next_sample_s += VIRTUAL_SAMPLE_INTERVAL_S
                if now_s - next_sample_s > VIRTUAL_SAMPLE_INTERVAL_S:
                    next_sample_s = now_s + VIRTUAL_SAMPLE_INTERVAL_S
                continue

            sleep_s = min(VIRTUAL_SAMPLE_INTERVAL_S, max(0.001, next_sample_s - now_s))
            self.msleep(max(1, int(sleep_s * 1000)))

    def _process_pending_commands(self):
        while True:
            try:
                cmd = self.command_queue.get_nowait()
            except queue.Empty:
                return

            try:
                if self._virtual_mode:
                    self._handle_virtual_command(cmd)
                elif self.ser and cmd:
                    payload = cmd.encode("utf-8") + b"\n"
                    self.ser.write(payload)
                    log.debug("Sent command over serial: %s", cmd)
            except Exception as e:
                log.error("Error sending serial command: %s", e)
                self.error_occurred.emit(f"Serial send error: {e}")

    def _handle_incoming_line(self, line: str):
        parts = [fld.strip() for fld in line.split(",")]
        if len(parts) < 3:
            log.info("Device event: %s", line)
            self.device_event.emit(line)
            return

        try:
            frame_idx_device, t_device, pressure, mass = self._parse_sample_parts(parts)
        except ValueError as ve:
            log.error("Parse error for line '%s': %s", line, ve)
            return

        self.data_ready.emit(frame_idx_device, t_device, pressure, mass)
        if not self._got_first_packet:
            self._got_first_packet = True
        self._last_data_time = time.time()

    @staticmethod
    def _looks_like_int_token(token: str) -> bool:
        stripped = token.strip()
        if not stripped:
            return False
        if stripped[0] in "+-":
            stripped = stripped[1:]
        return stripped.isdigit()

    def _next_fallback_frame_idx(self) -> int:
        idx = self._fallback_frame_idx
        self._fallback_frame_idx += 1
        return idx

    def _note_stream_format(self, fmt: str):
        if self._detected_stream_format == fmt:
            return
        self._detected_stream_format = fmt
        if fmt == "pressure_tension_time":
            log.info(
                "Detected 3-field serial stream format: avg_pressure,avg_tension,current_time. "
                "Using a synthesized frame index and mapping Avg Tension into the app's "
                "existing second data channel."
            )
        elif fmt == "frame_time_pressure":
            log.info("Detected legacy 3-field serial stream format: frame,time,pressure.")
        elif fmt == "frame_time_pressure_mass":
            log.info("Detected legacy 4-field serial stream format: frame,time,pressure,mass.")

    def _parse_sample_parts(self, parts):
        if self._looks_like_int_token(parts[0]):
            frame_idx_device = int(parts[0])
            t_device = float(parts[1])
            pressure = float(parts[2])
            mass = float(parts[3]) if len(parts) >= 4 else 0.0
            if len(parts) >= 4:
                self._note_stream_format("frame_time_pressure_mass")
            else:
                self._note_stream_format("frame_time_pressure")
            return frame_idx_device, t_device, pressure, mass

        if len(parts) == 3:
            pressure = float(parts[0])
            mass = float(parts[1])
            t_device = float(parts[2])
            self._note_stream_format("pressure_tension_time")
            return self._next_fallback_frame_idx(), t_device, pressure, mass

        raise ValueError("Unsupported serial sample format")

    def _reset_virtual_state(self):
        now_s = time.monotonic()
        self._virtual_frame_idx = 0
        self._virtual_stream_started_s = now_s
        self._virtual_last_sample_s = now_s
        self._virtual_mass_raw_g = 0.0
        self._virtual_mass_zero_g = 0.0
        self._virtual_pressure_zero_mmhg = 0.0
        self._virtual_pump_running = False

    def _advance_virtual_state(self, now_s: float):
        dt = max(0.0, now_s - self._virtual_last_sample_s)
        if self._virtual_pump_running:
            self._virtual_mass_raw_g += VIRTUAL_FILL_RATE_G_PER_S * dt
        self._virtual_last_sample_s = now_s

    def _build_virtual_sample(self, now_s: float):
        self._advance_virtual_state(now_s)
        elapsed_s = max(0.0, now_s - self._virtual_stream_started_s)
        pressure_raw = self._virtual_pressure_raw(elapsed_s)
        pressure_mmhg = pressure_raw - self._virtual_pressure_zero_mmhg
        mass_g = max(0.0, self._virtual_mass_raw_g - self._virtual_mass_zero_g)

        idx = self._virtual_frame_idx
        self._virtual_frame_idx += 1
        return idx, elapsed_s, pressure_mmhg, mass_g

    def _virtual_pressure_raw(self, elapsed_s: float) -> float:
        fill_g = max(0.0, self._virtual_mass_raw_g)
        baseline = (
            1.4
            + 0.30 * math.sin(2.0 * math.pi * 0.18 * elapsed_s)
            + 0.12 * math.sin(2.0 * math.pi * 1.10 * elapsed_s + 0.7)
        )
        filling_load = (0.06 * fill_g) + (0.0015 * fill_g * fill_g)

        phase = elapsed_s % VIRTUAL_CONTRACTION_PERIOD_S
        contraction = 0.0
        if phase < VIRTUAL_CONTRACTION_DURATION_S:
            pulse = math.sin(math.pi * phase / VIRTUAL_CONTRACTION_DURATION_S) ** 2
            contraction = pulse * (1.5 + min(5.0, 0.05 * fill_g))

        return baseline + filling_load + contraction

    def _handle_virtual_command(self, cmd: str):
        command = (cmd or "").strip().upper()
        if not command:
            return

        now_s = time.monotonic()
        self._advance_virtual_state(now_s)

        if command == "G":
            self._virtual_pump_running = True
            log.info("Virtual CystoMoto pump started.")
        elif command == "S":
            self._virtual_pump_running = False
            log.info("Virtual CystoMoto pump stopped.")
        elif command == "Z":
            elapsed_s = max(0.0, now_s - self._virtual_stream_started_s)
            self._virtual_pressure_zero_mmhg = self._virtual_pressure_raw(elapsed_s)
            self._virtual_mass_zero_g = self._virtual_mass_raw_g
            log.info("Virtual CystoMoto zeroed.")
        else:
            log.info("Virtual CystoMoto ignoring unsupported command: %s", command)

    def send_command(self, command_str):
        """
        Queue a command for the Arduino. GUI can call this safely.
        """
        if self.running:
            self.command_queue.put(command_str)
            log.info("Queued command: %s", command_str)
        else:
            log.warning("Serial thread not running; cannot send command.")
            self.error_occurred.emit("Cannot send: Serial disconnected.")

    def stop(self):
        """
        Ask the thread to exit cleanly. If it doesn't within 2 seconds, force-terminate.
        """
        log.info("Stopping SerialThread...")
        self._stop_requested = True
        self.running = False
        self.wait_condition.wakeAll()
        self.quit()
        self.wait(2000)
        if self.isRunning():
            log.warning("SerialThread did not stop gracefully; terminating.")
            self.terminate()
            self.wait(1000)
