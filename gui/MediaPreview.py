"""Native VLC video output with isolated playback and bounded reconnection."""

import json
from PyQt6.QtCore import QEvent, QObject, QProcess, QSize, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QIcon, QKeySequence, QShortcut
from PyQt6.QtWidgets import QCheckBox, QHBoxLayout, QSlider, QToolButton, QWidget
from core.Paths import ICONS, ROOT
from core.Runtime import detachWorker, workerCommand

TOOLBAR_HEIGHT = 50
OVERLAY_REFRESH_MS = 500
MAX_RETRIES = 3
STOP_WAIT_MS = 2000
DEFAULT_VOLUME = 80


class MediaPreview(QObject):
    stateChanged = pyqtSignal(str, str)
    metadataChanged = pyqtSignal(object)
    debugToggled = pyqtSignal(bool)

    def __init__(self, label, parent=None):
        super().__init__(parent)
        self.label = label
        label.setAttribute(Qt.WidgetAttribute.WA_NativeWindow)
        # Give VLC its own surface below a small video toolbar. Native video
        # output must not paint into the area occupied by the fullscreen icon.
        self.renderSurface = QWidget(label)
        self.renderSurface.setAttribute(Qt.WidgetAttribute.WA_NativeWindow)
        self.renderSurface.setStyleSheet("background:#101418;")
        self.fullscreenButton = QToolButton(label)
        # VLC creates native child windows; the overlay must also be native
        # so its white icon stays above the renderer on Windows.
        self.fullscreenButton.setAttribute(Qt.WidgetAttribute.WA_NativeWindow)
        self.fullscreenButton.setIcon(QIcon(str(ICONS / "fullscreen.svg")))
        self.fullscreenButton.setIconSize(QSize(22, 22))
        self.fullscreenButton.setFixedSize(34, 34)
        self.fullscreenButton.setToolTip("Fullscreen · Esc to exit")
        self.fullscreenButton.setStyleSheet(
            "QToolButton {background:#202830;color:#FFFFFF;border:1px solid #C0CAD4;border-radius:5px;padding:0;min-width:32px;min-height:32px;} QToolButton:hover {background:#46515D;}"
        )
        self.fullscreenButton.clicked.connect(self.toggleFullscreen)
        self.debugButton = QToolButton(label)
        self.debugButton.setAttribute(Qt.WidgetAttribute.WA_NativeWindow)
        self.debugButton.setIcon(QIcon(str(ICONS / "debug.svg")))
        self.debugButton.setIconSize(QSize(20, 20))
        self.debugButton.setFixedSize(34, 34)
        self.debugButton.setCheckable(True)
        self.debugButton.setToolTip("RTSP debug commands")
        self.debugButton.setStyleSheet(
            "QToolButton {background:#202830;border:1px solid #7E8B98;border-radius:5px;padding:0;min-width:32px;min-height:32px;} QToolButton:hover,QToolButton:checked {background:#395C7A;border-color:#A8C9E8;}"
        )
        self.debugButton.toggled.connect(self.debugToggled)
        self.debugButton.hide()
        self.debugEnabled = False
        label.installEventFilter(self)
        self.process = None
        self.data = None
        self.volume = DEFAULT_VOLUME
        self.muted = False
        self.buffer = bytearray()
        self.attempts = 0
        self.errorCode = ""
        self.fullscreenWindow = None
        self.fullscreenHidden = []
        self.fullscreenEscape = QShortcut(QKeySequence("Esc"), label.window())
        self.fullscreenEscape.setEnabled(False)
        self.fullscreenEscape.activated.connect(self.exitFullscreen)
        self.retry = QTimer(self)
        self.retry.setSingleShot(True)
        self.retry.timeout.connect(self.launch)
        self.overlayTimer = QTimer(self)
        self.overlayTimer.setInterval(OVERLAY_REFRESH_MS)
        self.overlayTimer.timeout.connect(self.raiseOverlay)

    def controls(self):
        widget = QWidget()
        row = QHBoxLayout(widget)
        row.setContentsMargins(0, 0, 0, 0)
        mute = QCheckBox("Mute")
        volume = QSlider(Qt.Orientation.Horizontal)
        volume.setRange(0, 100)
        volume.setValue(self.volume)
        volume.setFixedWidth(100)
        volume.setToolTip("Volume")
        mute.toggled.connect(lambda value: self.audio(muted=value))
        volume.valueChanged.connect(lambda value: self.audio(volume=value))
        row.addWidget(mute)
        row.addWidget(volume)
        row.addStretch()
        return widget

    def eventFilter(self, watched, event):
        if watched is self.label and event.type() in (QEvent.Type.Resize, QEvent.Type.Show):
            self.raiseOverlay()
        return super().eventFilter(watched, event)

    def raiseOverlay(self):
        if self.label.isVisible():
            self.renderSurface.setGeometry(0, TOOLBAR_HEIGHT, self.label.width(), max(1, self.label.height() - TOOLBAR_HEIGHT))
            self.renderSurface.show()
            self.fullscreenButton.move(max(0, self.label.width() - 44), 10)
            self.fullscreenButton.show()
            self.fullscreenButton.raise_()
            if self.debugEnabled:
                self.debugButton.move(max(0, self.label.width() - 84), 10)
                self.debugButton.show()
                self.debugButton.raise_()

    def enableDebug(self):
        self.debugEnabled = True
        self.raiseOverlay()

    def toggleFullscreen(self):
        if self.fullscreenWindow is None:
            self.enterFullscreen()
        else:
            self.exitFullscreen()

    def enterFullscreen(self):
        if self.fullscreenWindow is not None:
            return
        window = self.label.window()
        self.fullscreenWindow = window
        self.fullscreenState = window.windowState()
        self.fullscreenGeometry = window.saveGeometry()
        self.fullscreenHidden = []
        # Keep the native video widget and HWND in place. Reparenting a VLC
        # target can invalidate the renderer's window handle on Windows.
        child = self.label
        while child is not window:
            parent = child.parentWidget()
            if parent is None:
                break
            for sibling in parent.findChildren(QWidget, options=Qt.FindChildOption.FindDirectChildrenOnly):
                if sibling is not child and not sibling.isWindow() and not sibling.isHidden():
                    self.fullscreenHidden.append(sibling)
                    sibling.hide()
            child = parent
        self.fullscreenEscape.setEnabled(True)
        window.showFullScreen()
        self.label.setFocus()

    def exitFullscreen(self):
        window = self.fullscreenWindow
        if window is None:
            return
        self.fullscreenWindow = None
        self.fullscreenEscape.setEnabled(False)
        for widget in reversed(self.fullscreenHidden):
            widget.show()
        self.fullscreenHidden = []
        window.setWindowState(self.fullscreenState)
        window.restoreGeometry(self.fullscreenGeometry)

    def audio(self, volume=None, muted=None):
        if volume is not None:
            self.volume = volume
        if muted is not None:
            self.muted = muted
        if self.process and self.process.state() == QProcess.ProcessState.Running:
            self.process.write(json.dumps(dict(volume=self.volume, muted=self.muted)).encode() + b"\n")

    def running(self):
        return self.data is not None

    def start(self, data):
        self.stop()
        self.data = dict(data)
        self.attempts = 0
        self.launch()

    def launch(self):
        if self.data is None:
            return
        self.overlayTimer.start()
        self.buffer.clear()
        self.errorCode = ""
        process = self.process = QProcess(self)
        process.setWorkingDirectory(str(ROOT))
        payload = dict(self.data, hwnd=int(self.renderSurface.winId()), volume=self.volume, muted=self.muted)
        process.started.connect(lambda: process.write(json.dumps(payload).encode() + b"\n"))
        process.readyReadStandardOutput.connect(lambda: self.read(process))
        process.readyReadStandardError.connect(process.readAllStandardError)
        process.finished.connect(lambda *args: self.finished(process))
        process.errorOccurred.connect(lambda error: self.failedStart(process, error))
        self.stateChanged.emit("opening", "")
        process.start(*workerCommand("infrastructure.VlcProcess"))

    def failedStart(self, process, error):
        if error == QProcess.ProcessError.FailedToStart and process is self.process:
            self.errorCode = "PLAYER_START_FAILED"
            self.finished(process)

    def read(self, source=None):
        if source is not None and source is not self.process:
            return
        if not self.process:
            return
        self.buffer.extend(bytes(self.process.readAllStandardOutput()))
        while b"\n" in self.buffer:
            line, _, rest = self.buffer.partition(b"\n")
            self.buffer = bytearray(rest)
            try:
                packet = json.loads(line)
            except ValueError:
                continue
            if "metadata" in packet:
                self.metadataChanged.emit(packet["metadata"])
            elif "error" in packet:
                self.errorCode = packet["error"]
            elif packet.get("state") == "playing":
                self.stateChanged.emit("playing", "")

    def finished(self, source=None):
        if source is not None and source is not self.process:
            return
        if self.process:
            self.read()
            self.process.deleteLater()
            self.process = None
        if self.data is None:
            return
        error = self.errorCode or "STREAM_ERROR"
        if error in ("STREAM_ERROR", "NO_FRAMES") and self.attempts < MAX_RETRIES:
            # Some HEVC profiles/drivers stall in the hardware decoder. Retry
            # with software decoding before repeating the same failing setup.
            self.data["softwareDecode"] = True
            self.attempts += 1
            self.stateChanged.emit("opening", f"RECONNECT_{self.attempts}")
            self.retry.start(1000 * 2 ** (self.attempts - 1))
        else:
            self.overlayTimer.stop()
            self.data = None
            self.stateChanged.emit("error", error)

    def stop(self):
        self.overlayTimer.stop()
        self.exitFullscreen()
        self.data = None
        self.retry.stop()
        process, self.process = self.process, None
        if process:
            detachWorker(process)
            process.write(b'{"stop":true}\n')
            process.closeWriteChannel()
            # Do not block Qt waiting for network teardown inside libVLC.
            process.kill()
            process.waitForFinished(STOP_WAIT_MS)
            process.deleteLater()
        self.label.clear()
        self.label.update()
        self.stateChanged.emit("stopped", "")
