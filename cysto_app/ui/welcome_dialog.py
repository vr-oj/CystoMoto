# SPDX-License-Identifier: GPL-3.0-only
# cysto_app/ui/welcome_dialog.py

import os

from PyQt5.QtCore import Qt, QSettings, QUrl
from PyQt5.QtGui import QDesktopServices, QPixmap
from PyQt5.QtWidgets import (
    QCheckBox,
    QDesktopWidget,
    QDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from utils.path_helpers import resource_path
from utils.icon_helpers import render_icon_pixmap


class WelcomeDialog(QDialog):
    """Startup guide shown on launch unless the user hides it."""

    _STEP_ICON_SIZE = 26

    def __init__(self, parent=None, force_show: bool = False):
        super().__init__(parent)

        self.settings = QSettings("YourCompany", "CystoMotoApp")
        self._skip = False
        if not force_show and not self.settings.value(
            "CystoMotoApp/ShowWelcome", True, type=bool
        ):
            self._skip = True
            self.close()
            return

        self.setWindowTitle("Welcome to CystoMoto")
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)
        self.setMinimumSize(760, 520)
        self.setStyleSheet(
            """
            QDialog {
                background-color: #1E232B;
                color: #ECEFF4;
                border-radius: 14px;
            }
            QLabel {
                color: #ECEFF4;
            }
            QLabel#Title {
                font-size: 22pt;
                font-weight: 700;
                color: #F8FAFC;
            }
            QLabel#Subtitle {
                font-size: 11pt;
                color: #C8D0DA;
            }
            QFrame#Banner {
                background-color: #2A313B;
                border: 1px solid #3C4654;
                border-radius: 14px;
            }
            QFrame#Card {
                background-color: #262C35;
                border: 1px solid #3B4552;
                border-radius: 12px;
            }
            QLabel#CardTitle {
                font-size: 11pt;
                font-weight: 700;
                color: #F8FAFC;
            }
            QLabel#CardBody {
                font-size: 10pt;
                color: #C8D0DA;
            }
            QFrame#Tips {
                background-color: #20262E;
                border: 1px solid #3B4552;
                border-radius: 12px;
            }
            QLabel#TipsTitle {
                font-size: 11pt;
                font-weight: 700;
                color: #A3BE8C;
            }
            QLabel#TipsBody {
                font-size: 10pt;
                color: #D8DEE9;
            }
            QCheckBox {
                color: #C8D0DA;
                spacing: 8px;
            }
            QCheckBox::indicator {
                width: 16px;
                height: 16px;
            }
            QPushButton {
                background-color: #A3BE8C;
                color: #1B1F24;
                border: none;
                border-radius: 8px;
                padding: 8px 14px;
                font-weight: 700;
            }
            QPushButton:hover {
                background-color: #B4CC9F;
            }
            QPushButton#Secondary {
                background-color: #4C566A;
                color: #F8FAFC;
            }
            QPushButton#Secondary:hover {
                background-color: #5E6A80;
            }
            """
        )

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(18, 18, 18, 18)
        main_layout.setSpacing(14)

        main_layout.addWidget(self._build_banner())
        main_layout.addWidget(self._build_steps_grid())
        main_layout.addWidget(self._build_tips_box())
        main_layout.addLayout(self._build_footer())

        self._center_on_screen()

    def _build_banner(self):
        banner = QFrame(self)
        banner.setObjectName("Banner")
        layout = QVBoxLayout(banner)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(6)

        title = QLabel("Welcome to CystoMoto", banner)
        title.setObjectName("Title")
        layout.addWidget(title)

        subtitle = QLabel(
            "CystoMoto records synchronized pressure and mass traces for cystometry. "
            "The normal workflow is connect, zero, start recording, then control the pump as needed.",
            banner,
        )
        subtitle.setObjectName("Subtitle")
        subtitle.setWordWrap(True)
        layout.addWidget(subtitle)

        return banner

    def _build_steps_grid(self):
        container = QWidget(self)
        grid = QGridLayout(container)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(12)

        cards = [
            (
                "plug.svg",
                "1. Connect a device",
                "Choose the Arduino port from the toolbar, or select Virtual CystoMoto to practice without hardware.",
            ),
            (
                "sync.svg",
                "2. Zero before the run",
                "Use Zero Device? before filling so the baseline pressure starts clean.",
            ),
            (
                "record.svg",
                "3. Start Recording creates a new file",
                "Click Start Recording to open the run setup dialog. That dialog asks where to save the CSV and lets you enter experiment metadata.",
            ),
            (
                "pump-on.svg",
                "4. Run the fill",
                "Use Start Pump and Stop Pump during the recording. Pump events are marked on the plots and saved into the CSV columns.",
            ),
        ]

        for idx, (icon_name, title, body) in enumerate(cards):
            row = idx // 2
            col = idx % 2
            grid.addWidget(self._build_step_card(icon_name, title, body), row, col)

        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)
        return container

    def _build_step_card(self, icon_name: str, title_text: str, body_text: str):
        card = QFrame(self)
        card.setObjectName("Card")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(8)

        header = QHBoxLayout()
        header.setSpacing(8)

        icon_label = QLabel(card)
        icon_label.setFixedSize(self._STEP_ICON_SIZE, self._STEP_ICON_SIZE)
        icon_label.setPixmap(self._render_step_icon(icon_name))
        icon_label.setAlignment(Qt.AlignLeft | Qt.AlignTop)
        header.addWidget(icon_label, 0, Qt.AlignTop)

        title = QLabel(title_text, card)
        title.setObjectName("CardTitle")
        title.setWordWrap(True)
        header.addWidget(title, 1)

        layout.addLayout(header)

        body = QLabel(body_text, card)
        body.setObjectName("CardBody")
        body.setWordWrap(True)
        layout.addWidget(body)

        layout.addStretch()
        return card

    def _render_step_icon(self, icon_name: str) -> QPixmap:
        icon_path = resource_path("ui", "icons", icon_name)
        tint = "#A3BE8C" if icon_name == "pump-on.svg" else "#F8FAFC"
        return render_icon_pixmap(
            icon_path,
            self._STEP_ICON_SIZE,
            device_pixel_ratio=self.devicePixelRatioF(),
            tint=tint,
        )

    def _build_tips_box(self):
        tips = QFrame(self)
        tips.setObjectName("Tips")
        layout = QVBoxLayout(tips)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(8)

        title = QLabel("Good To Know", tips)
        title.setObjectName("TipsTitle")
        layout.addWidget(title)

        items = [
            "Each recording saves a CSV plus a companion metadata JSON file in the same folder.",
            "The CSV is one row per sample, so pump events stay in columns instead of creating extra rows.",
            "You can start recording before the pump starts. Recording and pump control are independent.",
            "Use File -> Export Plot Data (CSV) or Export Plot Image later if you want a separate export.",
        ]
        for item in items:
            lbl = QLabel(f"- {item}", tips)
            lbl.setObjectName("TipsBody")
            lbl.setWordWrap(True)
            layout.addWidget(lbl)

        return tips

    def _build_footer(self):
        footer = QHBoxLayout()
        footer.setContentsMargins(0, 2, 0, 0)

        self.checkbox = QCheckBox("Don't show this again", self)
        show_welcome = self.settings.value("CystoMotoApp/ShowWelcome", True, type=bool)
        self.checkbox.setChecked(not show_welcome)
        self.checkbox.stateChanged.connect(self._toggle_show)
        footer.addWidget(self.checkbox)
        footer.addStretch()

        guide_btn = QPushButton("Open User Guide", self)
        guide_btn.setObjectName("Secondary")
        guide_btn.clicked.connect(self._open_readme)
        footer.addWidget(guide_btn)

        start_btn = QPushButton("Start Using CystoMoto", self)
        start_btn.clicked.connect(self.accept)
        footer.addWidget(start_btn)
        return footer

    def _open_readme(self):
        path = os.path.abspath(
            os.path.join(os.path.dirname(__file__), "..", "..", "README.md")
        )
        QDesktopServices.openUrl(QUrl.fromLocalFile(path))

    def _center_on_screen(self):
        qr = self.frameGeometry()
        cp = QDesktopWidget().availableGeometry().center()
        qr.moveCenter(cp)
        self.move(qr.topLeft())

    def _toggle_show(self, state):
        self.settings.setValue("CystoMotoApp/ShowWelcome", state != Qt.Checked)
