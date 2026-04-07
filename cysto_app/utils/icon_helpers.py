# SPDX-License-Identifier: GPL-3.0-only
import os

from PyQt5.QtCore import QRectF, Qt
from PyQt5.QtGui import QColor, QIcon, QPainter, QPixmap
from PyQt5.QtSvg import QSvgRenderer


DEFAULT_ICON_SIZES = (16, 20, 24, 32, 40, 48, 64)
DEFAULT_DEVICE_PIXEL_RATIOS = (1.0, 2.0, 3.0)


def render_icon_pixmap(
    icon_path: str,
    logical_size: int,
    *,
    device_pixel_ratio: float = 1.0,
    tint: str | QColor | None = None,
) -> QPixmap:
    """Render a crisp pixmap from an icon asset, with optional monochrome tint."""
    if not icon_path or not os.path.exists(icon_path) or logical_size <= 0:
        return QPixmap()

    dpr = max(float(device_pixel_ratio), 1.0)
    pixel_size = max(int(round(logical_size * dpr)), logical_size)

    if icon_path.lower().endswith(".svg"):
        renderer = QSvgRenderer(icon_path)
        if not renderer.isValid():
            return QPixmap()
        pixmap = QPixmap(pixel_size, pixel_size)
        pixmap.fill(Qt.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHints(
            QPainter.Antialiasing
            | QPainter.TextAntialiasing
            | QPainter.SmoothPixmapTransform,
            True,
        )
        renderer.render(painter, QRectF(0, 0, pixel_size, pixel_size))
        if tint is not None:
            painter.setCompositionMode(QPainter.CompositionMode_SourceIn)
            painter.fillRect(pixmap.rect(), QColor(tint))
        painter.end()
        pixmap.setDevicePixelRatio(dpr)
        return pixmap

    source = QPixmap(icon_path)
    if source.isNull():
        return QPixmap()
    pixmap = source.scaled(
        pixel_size,
        pixel_size,
        Qt.KeepAspectRatio,
        Qt.SmoothTransformation,
    )
    if tint is not None:
        painter = QPainter(pixmap)
        painter.setCompositionMode(QPainter.CompositionMode_SourceIn)
        painter.fillRect(pixmap.rect(), QColor(tint))
        painter.end()
    pixmap.setDevicePixelRatio(dpr)
    return pixmap


def load_icon(
    icon_path: str,
    *,
    tint: str | QColor | None = None,
    sizes=DEFAULT_ICON_SIZES,
    device_pixel_ratios=DEFAULT_DEVICE_PIXEL_RATIOS,
) -> QIcon:
    """Build a QIcon with multiple crisp raster sizes for use across the app."""
    if not icon_path or not os.path.exists(icon_path):
        return QIcon()

    if not icon_path.lower().endswith(".svg") and tint is None:
        return QIcon(icon_path)

    icon = QIcon()
    for size in sizes:
        for dpr in device_pixel_ratios:
            pixmap = render_icon_pixmap(
                icon_path,
                size,
                device_pixel_ratio=dpr,
                tint=tint,
            )
            if not pixmap.isNull():
                icon.addPixmap(pixmap)
    return icon
