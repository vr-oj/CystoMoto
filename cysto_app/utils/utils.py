# SPDX-License-Identifier: GPL-3.0-only
# cysto_app/utils/utils.py
import time
import serial.tools.list_ports
import re

VIRTUAL_CYSTOMOTO_PORT = "Virtual CystoMoto"
VIRTUAL_CYSTOMOTO_DESCRIPTION = "Built-in simulator"


def is_virtual_port(port) -> bool:
    return isinstance(port, str) and port == VIRTUAL_CYSTOMOTO_PORT


def list_serial_ports(include_virtual: bool = True):
    """Lists available serial ports and optionally the built-in simulator."""
    ports = [(p.device, p.description) for p in serial.tools.list_ports.comports()]
    if include_virtual:
        ports.append((VIRTUAL_CYSTOMOTO_PORT, VIRTUAL_CYSTOMOTO_DESCRIPTION))
    return ports


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
