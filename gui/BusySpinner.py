"""Small animated busy indicator shared by desktop status rows."""

from PyQt6.QtCore import Qt, QTimer, QRectF
from PyQt6.QtGui import QPainter, QPen, QColor
from PyQt6.QtWidgets import QWidget, QHBoxLayout


class BusySpinner(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(18, 18)
        self.angle = 0
        self.timer = QTimer(self)
        self.timer.setInterval(70)
        self.timer.timeout.connect(self.advance)
        self.hide()
        self.setAccessibleName("Loading")

    def setBusy(self, busy):
        self.setVisible(bool(busy))
        if busy and self.isVisible():
            self.timer.start()
        else:
            self.timer.stop()

    def showEvent(self, event):
        self.timer.start()
        super().showEvent(event)

    def hideEvent(self, event):
        self.timer.stop()
        super().hideEvent(event)

    def advance(self):
        self.angle = (self.angle + 30) % 360
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = QRectF(3, 3, 12, 12)
        painter.setPen(QPen(QColor("#D8E2EC"), 2))
        painter.drawEllipse(rect)
        painter.setPen(QPen(QColor("#347FC5"), 2, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        painter.drawArc(rect, -self.angle * 16, 260 * 16)


def statusRow(label):
    row = QWidget()
    layout = QHBoxLayout(row)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(6)
    spinner = BusySpinner(row)
    layout.addWidget(spinner)
    layout.addWidget(label, 1)
    label.busySpinner = spinner
    return row
