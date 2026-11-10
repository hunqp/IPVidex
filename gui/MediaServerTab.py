"""Managed MediaMTX ingest servers (receive-only): RTMP(S) and WebRTC. No decoding,
preview, transcoding or recording; the tabs only differ in protocol, URLs and API list."""

import base64
import json
import shutil
import tempfile
import time
from pathlib import Path
from PyQt6.QtCore import QEvent, QPointF, QProcess, QRectF, Qt, QTimer, QUrl
from PyQt6.QtGui import QColor, QDesktopServices, QIcon, QPainter, QPen, QPixmap, QPolygonF
from PyQt6.QtNetwork import QNetworkAccessManager, QNetworkRequest
from PyQt6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFormLayout,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)
from gui.Appearance import plainSpinBox
from gui.BusySpinner import statusRow
from infrastructure.LanDiscovery import interfaces
from infrastructure.MediaMtx import API_USER, BINARY, rtmpConfig, webRtcConfig
from infrastructure.Tls import ensureCertificate

LOOPBACK = "127.0.0.1"
POLL_MS = 1000
POLL_TIMEOUT_MS = 1800
STARTUP_WATCHDOG_MS = 8000
FORCE_STOP_MS = 800
KILL_WAIT_MS = 2000
MAX_LOG_LINES = 1500
LOG_HEIGHT = 180
MEBIBYTE = 1048576
COLUMNS = ("Client", "State", "Path", "Received", "Receive rate")
PATH_COLUMN = 2


def icon(draw):
    """16 px monochrome glyph drawn in code, readable on light and dark themes."""
    pixmap = QPixmap(16, 16)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    pen = QPen(QColor("#888888"))
    pen.setWidthF(1.3)
    painter.setPen(pen)
    painter.setBrush(Qt.BrushStyle.NoBrush)
    draw(painter)
    painter.end()
    return QIcon(pixmap)


def lines(painter, *segments):
    for x1, y1, x2, y2 in segments:
        painter.drawLine(QPointF(x1, y1), QPointF(x2, y2))


def copyIcon():
    def draw(painter):
        painter.drawRoundedRect(QRectF(5.5, 2.5, 7.5, 8.5), 1.4, 1.4)
        painter.drawRoundedRect(QRectF(2.5, 5.5, 7.5, 8.5), 1.4, 1.4)

    return icon(draw)


def clearIcon():
    return icon(
        lambda painter: lines(
            painter,
            (3, 4.5, 13, 4.5),
            (6.3, 4.5, 6.8, 3),
            (6.8, 3, 9.2, 3),
            (9.2, 3, 9.7, 4.5),
            (4.5, 5.2, 5.2, 13.2),
            (11.5, 5.2, 10.8, 13.2),
            (5.2, 13.2, 10.8, 13.2),
            (8, 6.3, 8, 12),
        )
    )


def saveIcon():
    return icon(lambda painter: lines(painter, (8, 2.5, 8, 9.5), (5, 6.8, 8, 9.8), (11, 6.8, 8, 9.8), (3.5, 12.5, 12.5, 12.5)))


def filledIcon(color, shape):
    def draw(painter):
        painter.setPen(QPen(QColor(color), 1.0))
        painter.setBrush(QColor(color))
        shape(painter)

    return icon(draw)


def playIcon():
    return filledIcon("#2E9E5B", lambda painter: painter.drawPolygon(QPolygonF([QPointF(5, 3), QPointF(13, 8), QPointF(5, 13)])))


def stopIcon():
    return filledIcon("#C0392B", lambda painter: painter.drawRoundedRect(QRectF(4, 4, 8, 8), 1.2, 1.2))


def iconButton(glyph, parent=None):
    button = QPushButton(parent)
    button.setIcon(glyph)
    button.setFixedSize(28, 24)
    button.setFlat(True)
    return button


def copyButton(field):
    button = iconButton(copyIcon())
    button.setToolTip("Copy")
    button.clicked.connect(lambda: QApplication.clipboard().setText(field.text()))
    return button


def receiveRate(previous, total, now):
    """kbit/s since the previous sample of the same connection."""
    if not previous or now <= previous[1]:
        return 0
    return max(0, total - previous[0]) * 8 / (now - previous[1]) / 1000


class MediaServerTab(QWidget):
    defaultPort = 1935
    portLabel = "Port"
    tempPrefix = "ipvidex-media-"
    hint = ""
    supportsBrowserPlay = False

    def makeConfig(self, address, port, prefix, debug, tls):
        """(MediaMTX config, apiPort, apiPassword); tls is None or (certPath, keyPath)."""
        raise NotImplementedError

    def scheme(self):
        raise NotImplementedError

    def publishUrl(self, address, port, prefix):
        raise NotImplementedError

    def viewUrl(self, address, port, prefix):
        raise NotImplementedError

    def connectionsEndpoint(self):
        raise NotImplementedError

    def __init__(self, parent=None):
        super().__init__(parent)
        self.process = None
        self.temporary = None
        self.stopping = False
        self.polling = False
        self.apiSeen = False
        self.previous = {}
        self.generation = 0
        self.apiPort, self.apiPassword = 0, ""
        self.net = QNetworkAccessManager(self)
        self.timer = QTimer(self)
        self.timer.setInterval(POLL_MS)
        self.timer.timeout.connect(self.poll)
        layout = QVBoxLayout(self)
        layout.addLayout(self.buildForm())
        layout.addLayout(self.buildActions())
        layout.addLayout(self.buildUrls())
        self.hintLabel = QLabel(self.hint)
        self.hintLabel.setWordWrap(True)
        layout.addWidget(self.hintLabel)
        self.status = QLabel("Stopped")
        layout.addWidget(statusRow(self.status))
        layout.addWidget(self.buildTable(), 1)
        self.debugCheck = QCheckBox("Verbose log")
        self.debugCheck.setToolTip(
            "Log every client connect/disconnect and the exact reason a client is rejected (auth, path, handshake). Applies when the server is (re)started."
        )
        layout.addWidget(self.debugCheck)
        layout.addWidget(self.buildLog())
        self.loadInterfaces()

    # ---- construction --------------------------------------------------------------
    def buildForm(self):
        form = QFormLayout()
        self.address = QComboBox()
        self.address.setMinimumWidth(260)
        self.refresh = QPushButton("Refresh")
        self.refresh.clicked.connect(self.loadInterfaces)
        adapters = QWidget()
        row = QHBoxLayout(adapters)
        row.setContentsMargins(0, 0, 0, 0)
        row.addWidget(self.address, 1)
        row.addWidget(self.refresh)
        form.addRow(QLabel("Listen interface"), adapters)
        self.port = QSpinBox()
        self.port.setRange(1, 65535)
        self.port.setValue(self.defaultPort)
        plainSpinBox(self.port)
        form.addRow(self.portLabel, self.port)
        self.path = QLineEdit("live")
        form.addRow(QLabel("Base path (prefix)"), self.path)
        form.addRow(QLabel("Enable security"), self.buildSecurityRow())
        for signal in (self.address.currentIndexChanged, self.port.valueChanged, self.path.textChanged, self.tlsCheck.toggled):
            signal.connect(self.updateUrls)
        return form

    def buildSecurityRow(self):
        self.tlsCheck = QCheckBox("Enable TLS  —  RTMP → RTMPS, WebRTC → HTTPS")
        self.tlsCheck.setToolTip(
            "Encrypt the endpoint with a self-signed certificate this app generates. Export it and import it into "
            "the camera so the camera trusts the server. Applies when the server is (re)started."
        )
        self.exportCert = QPushButton("  Export certificate")
        self.exportCert.setIcon(saveIcon())
        self.exportCert.setToolTip("Save the TLS certificate (.crt) to import into the camera / device.")
        self.exportCert.setEnabled(False)
        self.exportCert.clicked.connect(self.exportCertificate)
        self.tlsCheck.toggled.connect(self.exportCert.setEnabled)
        field = QWidget()
        row = QHBoxLayout(field)
        row.setContentsMargins(0, 0, 0, 0)
        row.addWidget(self.tlsCheck)
        row.addStretch()
        row.addWidget(self.exportCert)
        return field

    def buildActions(self):
        actions = QHBoxLayout()
        self.startButton = QPushButton()
        self.startButton.setIcon(playIcon())
        self.startButton.setToolTip("Start server")
        self.stopButton = QPushButton()
        self.stopButton.setIcon(stopIcon())
        self.stopButton.setToolTip("Stop server")
        self.stopButton.setEnabled(False)
        for button in (self.startButton, self.stopButton):
            button.setFixedSize(38, 28)
            actions.addWidget(button)
        actions.addStretch()
        self.startButton.clicked.connect(self.start)
        self.stopButton.clicked.connect(self.stop)
        return actions

    def buildUrls(self):
        grid = QGridLayout()
        grid.setHorizontalSpacing(8)
        self.url, self.viewField = QLineEdit(), QLineEdit()
        rows = ((self.url, "Endpoint URL:"), (self.viewField, "View URL:"))
        for index, (field, label) in enumerate(rows):
            field.setReadOnly(True)
            grid.addWidget(QLabel(label), index, 0)
            grid.addWidget(field, index, 1)
            grid.addWidget(copyButton(field), index, 2)
        grid.setColumnStretch(1, 1)
        return grid

    def buildTable(self):
        self.table = QTableWidget(0, len(COLUMNS))
        self.table.setHorizontalHeaderLabels(list(COLUMNS))
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.verticalHeader().hide()
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        if self.supportsBrowserPlay:
            self.table.setToolTip("Double-click a stream to play it in your browser over WebRTC.")
            self.table.itemDoubleClicked.connect(lambda item: self.playRow(item.row()))
        return self.table

    def buildLog(self):
        self.logs = QPlainTextEdit()
        self.logs.setReadOnly(True)
        self.logs.setMaximumBlockCount(MAX_LOG_LINES)
        self.logs.setMaximumHeight(LOG_HEIGHT)
        # Clear / Export overlaid inside the log box, top-right.
        self.clearLog = iconButton(clearIcon(), self.logs)
        self.clearLog.setToolTip("Clear log")
        self.exportLog = iconButton(saveIcon(), self.logs)
        self.exportLog.setToolTip("Export log to .txt")
        for overlay in (self.clearLog, self.exportLog):
            overlay.setStyleSheet(
                "QPushButton{background:rgba(247,249,251,0.88);border:1px solid rgba(0,0,0,0.14);"
                "border-radius:4px;} QPushButton:hover{background:rgba(234,240,246,0.96);}"
            )
        self.clearLog.clicked.connect(self.logs.clear)
        self.exportLog.clicked.connect(self.exportLogToFile)
        self.logs.installEventFilter(self)
        self.positionLogButtons()
        return self.logs

    def loadInterfaces(self):
        selected = self.address.currentData()
        self.address.clear()
        for name, ip in interfaces():
            self.address.addItem(f"{name} — {ip}", ip)
        self.address.addItem(f"Loopback — {LOOPBACK}", LOOPBACK)
        index = self.address.findData(selected)
        if index >= 0:
            self.address.setCurrentIndex(index)
        self.updateUrls()

    def currentAddress(self):
        return self.address.currentData() or LOOPBACK

    def updateUrls(self, *args):
        address, port, prefix = self.currentAddress(), self.port.value(), self.path.text().strip().strip("/")
        self.url.setText(self.publishUrl(address, port, prefix))
        self.viewField.setText(self.viewUrl(address, port, prefix))

    def setRunning(self, running):
        for control in (self.address, self.port, self.path, self.refresh, self.startButton, self.debugCheck, self.tlsCheck):
            control.setEnabled(not running)
        self.stopButton.setEnabled(running)

    # ---- server process ------------------------------------------------------------
    def writeConfig(self):
        """Generate the session config in a temporary folder; returns its path."""
        if not BINARY.is_file():
            raise ValueError(f"MediaMTX runtime missing: {BINARY}")
        tls = ensureCertificate(self.address.currentData()) if self.tlsCheck.isChecked() else None
        config, self.apiPort, self.apiPassword = self.makeConfig(
            self.address.currentData(), self.port.value(), self.path.text().strip(), self.debugCheck.isChecked(), tls
        )
        self.temporary = tempfile.TemporaryDirectory(prefix=self.tempPrefix)
        filename = Path(self.temporary.name) / "mediamtx.yml"
        filename.write_text(json.dumps(config), encoding="utf-8")
        return filename

    def start(self):
        if self.process is not None:
            return
        try:
            filename = self.writeConfig()
        except Exception as exc:
            self.status.setText("Unable to start: " + str(exc))
            return
        self.generation += 1
        self.previous = {}
        self.table.setRowCount(0)
        self.logs.clear()
        self.stopping, self.apiSeen = False, False
        self.setRunning(True)
        self.status.setText("Starting server…")
        self.status.busySpinner.setBusy(True)
        process = self.process = QProcess(self)
        process.setWorkingDirectory(self.temporary.name)
        process.setProcessChannelMode(QProcess.ProcessChannelMode.MergedChannels)
        process.readyReadStandardOutput.connect(self.readLogs)
        process.finished.connect(self.finished)
        process.errorOccurred.connect(self.processError)
        process.started.connect(self.timer.start)
        process.start(str(BINARY), [str(filename)])
        generation = self.generation
        QTimer.singleShot(STARTUP_WATCHDOG_MS, lambda: self.startupCheck(generation))

    def startupCheck(self, generation):
        """If the API never answers, say so instead of showing 'waiting…' forever."""
        if generation == self.generation and self.process is not None and not self.stopping and not self.apiSeen:
            self.status.busySpinner.setBusy(False)
            self.status.setText("Server is not responding — it may have failed to start or the port is in use. See the log.")

    def readLogs(self):
        if self.process:
            text = bytes(self.process.readAllStandardOutput()).decode("utf-8", errors="replace").strip()
            if text:
                self.logs.appendPlainText(text)

    def processError(self, error):
        if error == QProcess.ProcessError.FailedToStart:
            self.status.setText("Unable to launch MediaMTX")
            self.finished(-1)

    def stop(self):
        if self.process is None:
            return
        self.stopping = True
        self.status.setText("Stopping server…")
        self.timer.stop()
        self.status.busySpinner.setBusy(True)
        self.stopButton.setEnabled(False)
        # terminate() posts WM_CLOSE, which a Windows console app like MediaMTX ignores, so ask
        # politely then kill() shortly after; otherwise the orphan keeps holding the port.
        self.process.terminate()
        process = self.process
        QTimer.singleShot(FORCE_STOP_MS, lambda: self.forceStop(process))

    def forceStop(self, process):
        if self.process is process and process.state() != QProcess.ProcessState.NotRunning:
            process.kill()

    def finished(self, exitCode=0, *args):
        self.status.busySpinner.setBusy(False)
        self.timer.stop()
        self.generation += 1
        self.polling = False
        self.readLogs()
        if self.process:
            self.process.deleteLater()
            self.process = None
        if self.temporary:
            self.temporary.cleanup()
            self.temporary = None
        self.setRunning(False)
        self.table.setRowCount(0)
        stopped = self.stopping or exitCode == 0
        self.status.setText("Stopped" if stopped else "Server stopped with error — see log")

    def shutdown(self):
        """App close: kill synchronously so MediaMTX never outlives the app holding the port."""
        if self.process is None:
            return
        self.stopping = True
        self.timer.stop()
        self.process.kill()
        self.process.waitForFinished(KILL_WAIT_MS)

    # ---- statistics ------------------------------------------------------------------
    def poll(self):
        if self.polling or self.process is None or self.stopping:
            return
        self.polling = True
        generation = self.generation
        request = QNetworkRequest(QUrl(f"http://{LOOPBACK}:{self.apiPort}{self.connectionsEndpoint()}"))
        token = base64.b64encode(f"{API_USER}:{self.apiPassword}".encode())
        request.setRawHeader(b"Authorization", b"Basic " + token)
        request.setTransferTimeout(POLL_TIMEOUT_MS)
        reply = self.net.get(request)
        reply.finished.connect(lambda: self.pollFinished(reply, generation))

    def pollFinished(self, reply, generation):
        # Always clear the in-flight flag, even on a stale reply, or polling would freeze.
        try:
            self.polling = False
            if generation != self.generation:
                return
            if reply.error() != reply.NetworkError.NoError:
                if not self.apiSeen:
                    self.status.setText("Starting / waiting for server status…")
                return
            self.apiSeen = True
            self.showConnections(json.loads(bytes(reply.readAll()).decode()).get("items", []))
        except (ValueError, TypeError, KeyError):
            self.status.setText("Unable to read server status — see log")
        finally:
            reply.deleteLater()

    def showConnections(self, items):
        self.status.busySpinner.setBusy(False)
        self.table.setRowCount(len(items))
        now, current, publishers = time.monotonic(), {}, 0
        for row, item in enumerate(items):
            total, key = int(item.get("bytesReceived", 0)), item.get("id", "")
            rate = receiveRate(self.previous.get(key), total, now)
            current[key] = (total, now)
            publishers += item.get("state") == "publish"
            values = (item.get("remoteAddr", ""), item.get("state", ""), item.get("path", ""), f"{total / MEBIBYTE:.2f} MiB", f"{rate:.1f} kbit/s")
            for column, value in enumerate(values):
                self.table.setItem(row, column, QTableWidgetItem(str(value)))
        self.previous = current
        readers = len(items) - publishers
        self.status.setText(f"Running — {publishers} publisher(s), {readers} reader(s)" if items else "Listening — waiting for camera")

    def playRow(self, row):
        item = self.table.item(row, PATH_COLUMN)
        if item and item.text():
            self.playPath(item.text())

    def playPath(self, path):
        """Open a live view of the given stream path; only WebRTC supports it."""

    # ---- files --------------------------------------------------------------------------
    def positionLogButtons(self):
        margin = 5
        scrollbar = self.logs.verticalScrollBar()
        right = self.logs.width() - (scrollbar.width() if scrollbar.isVisible() else 0) - margin
        self.exportLog.move(right - self.exportLog.width(), margin)
        self.clearLog.move(right - self.exportLog.width() - self.clearLog.width() - 3, margin)
        self.clearLog.raise_()
        self.exportLog.raise_()

    def eventFilter(self, watched, event):
        if watched is self.logs and event.type() in (QEvent.Type.Resize, QEvent.Type.Show):
            self.positionLogButtons()
        return super().eventFilter(watched, event)

    def exportCertificate(self):
        address = self.currentAddress()
        try:
            certificate, _ = ensureCertificate(address)
        except Exception as exc:
            self.status.setText("TLS certificate error: " + str(exc))
            return
        default = f"IPVidex-{address}.crt".replace(":", "_")
        path, _ = QFileDialog.getSaveFileName(self, "Export TLS certificate", default, "Certificate (*.crt *.pem)")
        if path:
            self.copyOut(lambda: shutil.copyfile(certificate, path), path, "Certificate exported: ")

    def exportLogToFile(self):
        text = self.logs.toPlainText()
        if not text:
            self.status.setText("Log is empty — nothing to export.")
            return
        default = f"{self.tempPrefix}log-{time.strftime('%Y%m%d-%H%M%S')}.txt"
        path, _ = QFileDialog.getSaveFileName(self, "Export log", default, "Text files (*.txt)")
        if path:
            self.copyOut(lambda: Path(path).write_text(text, encoding="utf-8"), path, "Log exported: ")

    def copyOut(self, write, path, done):
        try:
            write()
            self.status.setText(done + path)
        except OSError as exc:
            self.status.setText("Export failed: " + str(exc))


class RtmpServerTab(MediaServerTab):
    """RTMP(S): the camera publishes and VLC / ffplay read the same URL."""

    defaultPort = 1935
    portLabel = "RTMP port"
    tempPrefix = "ipvidex-rtmp-"
    hint = (
        "Replace ${key} with each camera's own stream key, e.g. rtmp://<ip>:1935/live/0001, rtmp://<ip>:1935/live/0002. "
        "The server accepts any key under the base path, so several cameras can stream at once. The key must be letters, "
        "digits, _ or - only. To watch a stream, open the same rtmp:// URL in VLC or ffplay. No preview or recording in IPVidex."
    )

    def makeConfig(self, address, port, prefix, debug, tls):
        return rtmpConfig(address, port, prefix, debug, tls)

    def scheme(self):
        return "rtmps" if self.tlsCheck.isChecked() else "rtmp"

    def publishUrl(self, address, port, prefix):
        return f"{self.scheme()}://{address}:{port}/{prefix}/${{key}}"

    viewUrl = publishUrl

    def connectionsEndpoint(self):
        # MediaMTX lists RTMPS connections under a separate endpoint from plain RTMP.
        return "/v3/rtmpsconns/list" if self.tlsCheck.isChecked() else "/v3/rtmpconns/list"


class WebRtcServerTab(MediaServerTab):
    """WebRTC: the camera publishes over WHIP, viewers read over WHEP."""

    defaultPort = 8889
    portLabel = "WebRTC (WHIP/WHEP) port"
    tempPrefix = "ipvidex-webrtc-"
    supportsBrowserPlay = True
    hint = (
        "Replace ${key} with each camera's own stream key. A camera PUBLISHES over WHIP, URL ending in /whip, e.g. "
        "http://<ip>:8889/live/C340-0001/whip. The key must be letters, digits, _ or - only; do not append ?token=... or "
        "&codec=... to the path. To watch a stream, double-click its row in the table below — it opens in your browser and "
        "plays live over WebRTC (WHEP). The server accepts any key, so several cameras stream at once. No preview or recording in IPVidex."
    )

    def makeConfig(self, address, port, prefix, debug, tls):
        return webRtcConfig(address, port, prefix, debug, tls)

    def scheme(self):
        return "https" if self.tlsCheck.isChecked() else "http"

    def publishUrl(self, address, port, prefix):
        return f"{self.scheme()}://{address}:{port}/{prefix}/${{key}}/whip"

    def viewUrl(self, address, port, prefix):
        return f"{self.scheme()}://{address}:{port}/{prefix}/${{key}}/whep"

    def connectionsEndpoint(self):
        return "/v3/webrtcsessions/list"

    def playPath(self, path):
        # MediaMTX serves a built-in WebRTC player at http(s)://<host>:<port>/<path>.
        QDesktopServices.openUrl(QUrl(f"{self.scheme()}://{self.currentAddress()}:{self.port.value()}/{path}"))
