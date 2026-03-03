# cysto_app/utils/utils.py
import time
import serial.tools.list_ports
import re


def list_serial_ports():
    """Lists available serial ports."""
    return [(p.device, p.description) for p in serial.tools.list_ports.comports()]


def timestamped_filename(prefix, ext):
    """Generates a timestamped filename."""
    ts = time.strftime("%Y%m%d-%H%M%S")
    return f"{prefix}_{ts}.{ext}"


def to_prop_name(key: str) -> str:
    """
    Convert CamelCase or mixed_Case to UPPER_SNAKE_CASE.
    Example: "ExposureTime" -> "EXPOSURE_TIME"
    """
    if not key:
        return ""
    s1 = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", key)
    s2 = re.sub(r"([A-Z])([A-Z][a-z])", r"\1_\2", s1)
    return s2.upper()
