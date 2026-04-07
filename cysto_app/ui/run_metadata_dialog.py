# SPDX-License-Identifier: GPL-3.0-only
import os

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QPlainTextEdit,
    QVBoxLayout,
    QWidget,
)


class RunMetadataDialog(QDialog):
    """Collect per-run save path and experiment metadata before recording."""

    def __init__(self, default_csv_path: str, metadata_defaults=None, parent=None):
        super().__init__(parent)
        defaults = metadata_defaults or {}

        self.setWindowTitle("Start Recording")
        self.setModal(True)
        self.resize(760, 420)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(10)

        intro = QLabel(
            "Starting a recording creates a new file. Choose the CSV destination for this run and capture any experiment metadata you want saved with it."
        )
        intro.setWordWrap(True)
        layout.addWidget(intro)

        path_row = QWidget(self)
        path_layout = QHBoxLayout(path_row)
        path_layout.setContentsMargins(0, 0, 0, 0)
        path_layout.setSpacing(6)
        self.csv_path_edit = QLineEdit(default_csv_path, self)
        self.csv_path_edit.setClearButtonEnabled(True)
        browse_btn = QPushButton("Browse…", self)
        browse_btn.clicked.connect(self._browse_for_csv_path)
        path_layout.addWidget(self.csv_path_edit, 1)
        path_layout.addWidget(browse_btn)
        layout.addWidget(path_row)

        grid = QGridLayout()
        grid.setHorizontalSpacing(14)
        grid.setVerticalSpacing(8)
        layout.addLayout(grid)

        left_form = QFormLayout()
        left_form.setSpacing(6)
        right_form = QFormLayout()
        right_form.setSpacing(6)
        grid.addLayout(left_form, 0, 0)
        grid.addLayout(right_form, 0, 1)

        self.experiment_name_edit = QLineEdit(defaults.get("experiment_name", ""), self)
        self.subject_id_edit = QLineEdit(defaults.get("subject_id", ""), self)
        self.condition_edit = QLineEdit(defaults.get("condition_group", ""), self)
        self.protocol_edit = QLineEdit(defaults.get("protocol", ""), self)
        self.infusion_rate_edit = QLineEdit(defaults.get("infusion_rate", ""), self)
        self.operator_edit = QLineEdit(defaults.get("operator", ""), self)
        self.notes_edit = QPlainTextEdit(self)
        self.notes_edit.setPlainText(defaults.get("notes", ""))
        self.notes_edit.setPlaceholderText("Optional notes for this run")
        self.notes_edit.setMinimumHeight(100)

        left_form.addRow("Experiment Name:", self.experiment_name_edit)
        left_form.addRow("Subject ID:", self.subject_id_edit)
        left_form.addRow("Condition / Group:", self.condition_edit)
        right_form.addRow("Protocol:", self.protocol_edit)
        right_form.addRow("Infusion Rate:", self.infusion_rate_edit)
        right_form.addRow("Operator:", self.operator_edit)

        notes_label = QLabel("Notes:")
        notes_label.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        grid.addWidget(notes_label, 1, 0, alignment=Qt.AlignTop)
        grid.addWidget(self.notes_edit, 1, 1)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel, self)
        buttons.button(QDialogButtonBox.Ok).setText("Start Recording")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _browse_for_csv_path(self):
        current_path = self.csv_path_edit.text().strip()
        if not current_path:
            current_path = os.path.expanduser("~")
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Choose Recording CSV",
            current_path,
            "CSV Files (*.csv)",
        )
        if path:
            if not path.lower().endswith(".csv"):
                path = f"{path}.csv"
            self.csv_path_edit.setText(path)

    def get_run_setup(self):
        return {
            "csv_path": self.csv_path_edit.text().strip(),
            "metadata": {
                "experiment_name": self.experiment_name_edit.text().strip(),
                "subject_id": self.subject_id_edit.text().strip(),
                "condition_group": self.condition_edit.text().strip(),
                "protocol": self.protocol_edit.text().strip(),
                "infusion_rate": self.infusion_rate_edit.text().strip(),
                "operator": self.operator_edit.text().strip(),
                "notes": self.notes_edit.toPlainText().strip(),
            },
        }

    def accept(self):
        csv_path = self.csv_path_edit.text().strip()
        if not csv_path:
            QMessageBox.warning(self, "Missing CSV Path", "Choose where to save the recording CSV.")
            return
        if not csv_path.lower().endswith(".csv"):
            csv_path = f"{csv_path}.csv"
            self.csv_path_edit.setText(csv_path)

        parent_dir = os.path.dirname(csv_path)
        if not parent_dir:
            QMessageBox.warning(self, "Invalid CSV Path", "Choose a valid CSV file path.")
            return

        if os.path.exists(csv_path):
            choice = QMessageBox.question(
                self,
                "Overwrite Recording?",
                f"The file already exists:\n{csv_path}\n\nOverwrite it?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            if choice != QMessageBox.Yes:
                return

        super().accept()
