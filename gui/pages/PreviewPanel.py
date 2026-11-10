"""Live video of one media profile with stream facts (resolution, codec, fps, audio) and its URI."""

from PyQt6.QtCore import QSize, Qt
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import QApplication, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget
from core.Paths import ICONS
from gui.MediaPreview import MediaPreview
from infrastructure.Media import parseRtsp

AUDIO_NAMES = {"pcm_alaw": "G.711 A-law", "pcm_mulaw": "G.711 µ-law", "aac": "AAC", "adpcm_g726": "G.726"}
CHIP_COUNT = 4
MIN_PREVIEW_TIMEOUT = 5.0


def streamFacts(data):
    audio = ", ".join(f"{AUDIO_NAMES.get(a.get('codec'), a.get('codec'))} {int(a.get('sampleRate') or 0) // 1000} kHz" for a in data.get("audio", []))
    fps = data.get("measuredFps")
    return [
        f"{data.get('width', 0)}×{data.get('height', 0)}",
        str(data.get("codec", "?")).upper(),
        f"{fps:.1f} fps" if fps else "",
        audio,
    ]


class PreviewPanel(QWidget):
    def __init__(self, workspace, parent):
        super().__init__(parent)
        self.workspace = workspace
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        self.video = QLabel()
        self.video.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.video.setMinimumSize(320, 180)
        self.video.setObjectName("discoveryVideo")
        layout.addWidget(self.video, 1)
        layout.addLayout(self.buildInfoRow())
        self.preview = MediaPreview(self.video, self)
        layout.addWidget(self.preview.controls())
        self.preview.metadataChanged.connect(self.showFacts)
        workspace.registerPreview(self.preview)

    def buildInfoRow(self):
        row = QHBoxLayout()
        row.setSpacing(6)
        self.chips = []
        for _ in range(CHIP_COUNT):
            chip = QLabel()
            chip.setObjectName("discoveryChip")
            chip.hide()
            row.addWidget(chip)
            self.chips.append(chip)
        row.addStretch(1)
        self.uri = QLabel()
        self.uri.setObjectName("discoveryUri")
        self.uri.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        copy = QPushButton()
        copy.setObjectName("discoveryCopy")
        copy.setIcon(QIcon(str(ICONS / "copy.svg")))
        copy.setIconSize(QSize(16, 16))
        copy.setFixedSize(26, 26)
        copy.setToolTip("Copy stream URI")
        copy.clicked.connect(lambda: QApplication.clipboard().setText(self.uri.text()))
        row.addWidget(self.uri)
        row.addWidget(copy)
        return row

    def play(self, profile):
        for chip in self.chips:
            chip.hide()
        self.uri.clear()
        self.workspace.runTask(lambda: self.workspace.device.streamUri(profile["token"]), self.start)

    def start(self, uri):
        self.uri.setText(uri)
        session = self.workspace.device.session
        config = session.config
        try:
            data = parseRtsp(uri, config.username, config.password, config.host)
        except ValueError as exc:
            self.workspace.deviceError(str(exc))
            return
        data.update(timeout=max(config.timeout, MIN_PREVIEW_TIMEOUT))
        if data["secure"]:
            data["certificatePem"] = session.certificatePem
        self.preview.start(data)

    def stop(self):
        self.preview.stop()

    def running(self):
        return self.preview.running()

    def showFacts(self, data):
        for chip, value in zip(self.chips, streamFacts(data), strict=True):
            chip.setText(value)
            chip.setVisible(bool(value))
