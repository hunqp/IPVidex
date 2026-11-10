"""About dialog: company identity, description and contact details.
Styled to match the app's light theme."""

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QPixmap
from PyQt6.QtWidgets import QDialog, QHBoxLayout, QVBoxLayout, QGridLayout, QLabel, QPushButton, QFrame
from core.Paths import ROOT

WEBSITE = "vivooeye.com"
EMAIL = "contact@vivooeye.com"

ADDRESS = "3rd Floor, Hpcon Building, 2/13A Bach Dang Street,\nTan Son Hoa Ward, Ho Chi Minh City, Vietnam"
DESCRIPTION = "Vivoo delivers AI camera solutions, intelligent monitoring systems and centralized management platforms for businesses."
HOURS = "Mon – Sat, 08:00 – 17:30"
LINK = '<a href="{0}" style="color:#087ED5;text-decoration:none;">{1}</a>'


class AboutDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("About")
        self.setModal(True)
        self.setStyleSheet("QDialog{background:#FFFFFF;}")

        outer = QVBoxLayout(self)
        outer.setContentsMargins(22, 20, 22, 16)
        outer.setSpacing(12)

        # Company logo (wordmark), left-aligned.
        logo = QLabel()
        mark = QPixmap(str(ROOT / "assets" / "company" / "vivoo-logo.png"))
        logo.setPixmap(mark.scaledToHeight(46, Qt.TransformationMode.SmoothTransformation))
        outer.addWidget(logo, 0, Qt.AlignmentFlag.AlignLeft)

        desc = QLabel(DESCRIPTION)
        desc.setWordWrap(True)
        desc.setStyleSheet("font-size:9pt;color:#2A3340;")
        outer.addWidget(desc)

        separator = QFrame()
        separator.setFrameShape(QFrame.Shape.HLine)
        separator.setStyleSheet("color:#E2E6EB;")
        outer.addWidget(separator)

        contactTitle = QLabel("Contact")
        contactTitle.setStyleSheet("font-size:9pt;font-weight:700;color:#1A222C;")
        outer.addWidget(contactTitle)

        grid = QGridLayout()
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(5)
        grid.setColumnStretch(1, 1)
        rows = [
            ("Address", ADDRESS, False),
            ("Email", LINK.format(f"mailto:{EMAIL}", EMAIL), True),
            ("Website", LINK.format(f"https://{WEBSITE}", WEBSITE), True),
            ("Hours", HOURS, False),
        ]
        for rowIndex, (label, value, isLink) in enumerate(rows):
            name = QLabel(label)
            name.setStyleSheet("font-size:9pt;color:#8A94A2;")
            name.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
            field = QLabel(value)
            field.setStyleSheet("font-size:9pt;color:#2A3340;")
            field.setWordWrap(True)
            if isLink:
                field.setOpenExternalLinks(True)
            grid.addWidget(name, rowIndex, 0)
            grid.addWidget(field, rowIndex, 1)
        outer.addLayout(grid)

        footer = QHBoxLayout()
        footer.addStretch()
        close = QPushButton("Close")
        close.setFixedSize(84, 26)
        close.clicked.connect(self.accept)
        footer.addWidget(close)
        outer.addSpacing(4)
        outer.addLayout(footer)

        self.setFixedWidth(430)
