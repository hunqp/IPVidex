"""Pan / tilt / zoom pad, speed and presets, beside the live view."""

from PyQt6.QtCore import QPointF, QRectF, QSize, Qt
from PyQt6.QtGui import QColor, QIcon, QPainter, QPixmap, QPolygonF
from PyQt6.QtWidgets import QComboBox, QGridLayout, QHBoxLayout, QInputDialog, QPushButton, QSizePolicy
from gui.pages.DevicePage import DevicePage
from gui.pages.Forms import button, fieldLabel, settingsAndVideo, sliderRow
from gui.pages.PreviewPanel import PreviewPanel

PAD_CELL_HEIGHT = 84
ZOOM_BUTTON_HEIGHT = 36
GLYPH_COLOR = "#2F6FB5"
STOP_COLOR = "#B5544E"
SPEED_RANGE = (10, 100)
DEFAULT_SPEED = 50
# 3×3 pad: (arrow angle or None for stop, pan, tilt, tooltip).
PAD = (
    (315, -1, 1, "Up-left"),
    (0, 0, 1, "Up"),
    (45, 1, 1, "Up-right"),
    (270, -1, 0, "Left"),
    (None, 0, 0, "Stop"),
    (90, 1, 0, "Right"),
    (225, -1, -1, "Down-left"),
    (180, 0, -1, "Down"),
    (135, 1, -1, "Down-right"),
)


def glyph(draw, color):
    pixmap = QPixmap(20, 20)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor(color))
    draw(painter)
    painter.end()
    return QIcon(pixmap)


def arrowIcon(angle):
    """A filled triangle pointing `angle` degrees clockwise (0 = up)."""

    def draw(painter):
        painter.translate(10, 10)
        painter.rotate(angle)
        painter.drawPolygon(QPolygonF([QPointF(0, -5.2), QPointF(4.4, 3.2), QPointF(-4.4, 3.2)]))

    return glyph(draw, GLYPH_COLOR)


def stopIcon():
    return glyph(lambda painter: painter.drawRoundedRect(QRectF(6, 6, 8, 8), 1.6, 1.6), STOP_COLOR)


def zoomIcon(plus):
    def draw(painter):
        painter.drawRoundedRect(QRectF(3.5, 9, 13, 2), 1, 1)
        if plus:
            painter.drawRoundedRect(QRectF(9, 3.5, 2, 13), 1, 1)

    return glyph(draw, GLYPH_COLOR)


def padButton(icon, tooltip, height=PAD_CELL_HEIGHT):
    widget = QPushButton()
    widget.setIcon(icon)
    widget.setIconSize(QSize(28, 28))
    widget.setFixedHeight(height)
    widget.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
    widget.setToolTip(tooltip)
    return widget


class PtzPage(DevicePage):
    ICON = "ptz"
    TITLE = "PTZ"
    USES_PROFILE = True

    def __init__(self, workspace):
        super().__init__(workspace)
        self.profile = None
        form, settings, video = settingsAndVideo(self)
        self.speed, _ = sliderRow(form, "Speed")
        self.speed.setRange(*SPEED_RANGE)
        self.speed.setValue(DEFAULT_SPEED)
        self.controls = []
        settings.addLayout(self.buildPad())
        settings.addWidget(fieldLabel("Zoom"))
        settings.addLayout(self.buildZoom())
        settings.addWidget(fieldLabel("Preset"))
        self.presets = QComboBox()
        settings.addWidget(self.presets)
        settings.addLayout(self.buildPresetButtons())
        settings.addStretch(1)
        self.panel = PreviewPanel(workspace, self)
        video.addWidget(self.panel, 1)

    def buildPad(self):
        pad = QGridLayout()
        pad.setSpacing(6)
        for column in range(3):
            pad.setColumnStretch(column, 1)
        for index, (angle, pan, tilt, tooltip) in enumerate(PAD):
            if angle is None:
                widget = padButton(stopIcon(), tooltip)
                widget.clicked.connect(self.halt)
                self.controls.append(widget)
            else:
                widget = self.moveButton(arrowIcon(angle), (pan, tilt, 0), tooltip)
            pad.addWidget(widget, index // 3, index % 3)
        return pad

    def buildZoom(self):
        row = QHBoxLayout()
        row.addWidget(self.moveButton(zoomIcon(False), (0, 0, -1), "Zoom out", ZOOM_BUTTON_HEIGHT), 1)
        row.addWidget(self.moveButton(zoomIcon(True), (0, 0, 1), "Zoom in", ZOOM_BUTTON_HEIGHT), 1)
        return row

    def buildPresetButtons(self):
        row = QHBoxLayout()
        for text, handler in (("Go", self.gotoPreset), ("Save", self.savePreset), ("Delete", self.deletePreset)):
            widget = button(text, handler)
            row.addWidget(widget, 1)
            self.controls.append(widget)
        return row

    def moveButton(self, icon, velocity, tooltip, height=PAD_CELL_HEIGHT):
        """Moves while pressed, stops on release."""
        widget = padButton(icon, tooltip, height)
        widget.pressed.connect(lambda: self.move(*velocity))
        widget.released.connect(self.halt)
        self.controls.append(widget)
        return widget

    def load(self, profile):
        self.profile = profile
        supported = self.device.ptzSupported()
        for control in self.controls + [self.presets, self.speed]:
            control.setEnabled(supported)
        self.present()
        if supported:
            self.workspace.setStatus("")
            self.run(lambda: self.device.ptzPresets(profile["token"]), self.showPresets)
        else:
            self.presets.clear()
            self.workspace.setStatus("This device does not advertise PTZ.")
        if not self.panel.running():
            self.panel.play(profile)

    def deactivate(self):
        self.panel.stop()

    def showPresets(self, presets):
        self.presets.clear()
        for preset in presets:
            self.presets.addItem(preset["name"] or preset["token"], preset["token"])
        self.workspace.loaded()

    def command(self, function):
        """Fire a PTZ call without the page-load busy indicator."""
        if self.profile is not None:
            self.workspace.runTask(function, failed=self.commandFailed, quiet=True)

    def commandFailed(self, message):
        self.workspace.setStatus("PTZ error: " + message)

    def move(self, pan, tilt, zoom):
        speed = self.speed.value() / 100.0
        token = self.profile["token"] if self.profile else ""
        self.command(lambda: self.device.ptzMove(token, round(pan * speed, 3), round(tilt * speed, 3), round(zoom * speed, 3)))

    def halt(self):
        token = self.profile["token"] if self.profile else ""
        self.command(lambda: self.device.ptzStop(token))

    def gotoPreset(self):
        preset = self.presets.currentData()
        if preset and self.profile:
            token = self.profile["token"]
            self.command(lambda: self.device.ptzGoto(token, preset))

    def savePreset(self):
        if not self.profile:
            return
        name, accepted = QInputDialog.getText(self, "Save preset", "Preset name")
        name = name.strip()
        if accepted and name:
            profile = self.profile
            self.run(lambda: self.device.ptzSetPreset(profile["token"], name), lambda _: self.load(profile), "Saving…")

    def deletePreset(self):
        preset = self.presets.currentData()
        if not preset or not self.profile:
            return
        if self.workspace.confirm("Delete preset", [self.presets.currentText()]):
            profile = self.profile
            self.run(lambda: self.device.ptzRemovePreset(profile["token"], preset), lambda _: self.load(profile), "Deleting…")
