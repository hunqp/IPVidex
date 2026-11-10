"""RTSP(S) Live tab: native player for a typed URL, with an optional RTSP command console."""

from urllib.parse import urlsplit, urlunsplit
from PyQt6.QtCore import QObject, QSettings, Qt
from PyQt6.QtWidgets import QFileDialog, QMessageBox, QSplitter
from gui.BusySpinner import statusRow
from gui.MediaPreview import MediaPreview
from gui.RtspConsole import RtspConsole
from infrastructure.Media import parseRtsp
from infrastructure.Network import CertificateRequired, readCertificateFile

# Stored under HKEY_CURRENT_USER\Software\IPVidex\IPVidex.
SETTINGS_SCOPE = ("IPVidex", "IPVidex")
# Non-secret fields remembered across restarts; passwords never are.
REMEMBERED = ("mainUrlEdit", "subUrlEdit", "rtspCaEdit", "rtspUsernameEdit")
STREAM_STATES = {
    "idle": "Disconnected",
    "opening": "Connecting to RTSP...",
    "playing": "Live — no recording",
    "error": "Stream unavailable / disconnected. Check URL, authentication, codec and timeout.",
    "stopped": "Disconnected",
}
RTSPS_CERTIFICATE_HINT = (
    "rtsps:// needs the certificate exported from this camera (.pem). Example: openssl s_client -connect <camera>:<port> </dev/null | openssl x509 > camera.pem"
)
CERTIFICATE_FILTER = "Certificate (*.pem *.crt *.cer);;All files (*)"


def withoutUserinfo(url):
    try:
        parts = urlsplit(url)
    except ValueError:
        return ""
    if "@" not in parts.netloc:
        return url
    return urlunsplit(parts._replace(netloc=parts.netloc.rpartition("@")[2]))


class RtspTab(QObject):
    """Drives the RTSP widgets that main.ui places on `window.viewerTab`."""

    def __init__(self, window):
        super().__init__(window)
        self.ui = window
        self.state, self.errorCode, self.metadata = "idle", "", {}
        self.debugVisible = False
        layout = window.viewerTab.layout()
        position = layout.indexOf(window.streamStatusLabel)
        layout.removeWidget(window.streamStatusLabel)
        layout.insertWidget(position, statusRow(window.streamStatusLabel))
        self.console = RtspConsole(lambda: (window.rtspUsernameEdit.text(), window.rtspPasswordEdit.text()))
        self.split = self.buildSplit(layout)
        self.player = MediaPreview(window.videoLabel, window)
        self.player.enableDebug()
        self.player.debugToggled.connect(self.toggleDebug)
        layout.addWidget(self.player.controls())
        self.player.stateChanged.connect(self.playerState)
        self.player.metadataChanged.connect(self.playerMetadata)
        window.playButton.clicked.connect(self.play)
        window.stopStreamButton.clicked.connect(self.stop)
        window.stopStreamButton.setEnabled(False)
        window.rtspCaButton.clicked.connect(self.chooseCertificate)
        window.rtspAutoTrustCheck.toggled.connect(self.updateControls)
        self.render()

    def buildSplit(self, layout):
        """Video and command console side by side; the console only shows while debugging."""
        position = layout.indexOf(self.ui.videoLabel)
        layout.removeWidget(self.ui.videoLabel)
        split = QSplitter(Qt.Orientation.Horizontal)
        split.addWidget(self.ui.videoLabel)
        split.addWidget(self.console)
        split.setStretchFactor(0, 1)
        split.setStretchFactor(1, 1)
        split.setChildrenCollapsible(False)
        layout.insertWidget(position, split, 1)
        self.console.hide()
        return split

    # ---- settings -----------------------------------------------------------------
    def restoreSettings(self):
        settings = QSettings(*SETTINGS_SCOPE)
        for name in REMEMBERED:
            getattr(self.ui, name).setText(str(settings.value(name, "") or ""))

    def saveSettings(self):
        settings = QSettings(*SETTINGS_SCOPE)
        for name in REMEMBERED:
            value = getattr(self.ui, name).text().strip()
            settings.setValue(name, withoutUserinfo(value) if name.endswith("UrlEdit") else value)

    # ---- player -------------------------------------------------------------------
    def running(self):
        return self.player.running()

    def streamData(self):
        ui = self.ui
        url = ui.mainUrlEdit.text() if ui.streamCombo.currentIndex() == 0 else ui.subUrlEdit.text()
        data = parseRtsp(url, ui.rtspUsernameEdit.text(), ui.rtspPasswordEdit.text())
        data.update(timeout=ui.timeoutSpin.value(), autoTrust=ui.rtspAutoTrustCheck.isChecked())
        if data["secure"] and not data["autoTrust"]:
            data["certificatePem"] = readCertificateFile(ui.rtspCaEdit.text().strip())
        return data

    def play(self):
        if self.running():
            return
        try:
            data = self.streamData()
        except CertificateRequired:
            self.warn(RTSPS_CERTIFICATE_HINT)
            return
        except (ValueError, OSError) as exc:
            self.warn(str(exc))
            return
        self.metadata, self.errorCode = {}, ""
        self.console.setTarget(data)
        self.player.start(data)
        self.ui.stopStreamButton.setEnabled(True)
        self.updateControls()

    def stop(self):
        self.console.setTarget(None)
        self.player.stop()

    def tabChanged(self):
        if self.ui.tabs.currentWidget() is not self.ui.viewerTab and self.running():
            self.stop()

    def playerState(self, state, error):
        self.ui.streamStatusLabel.busySpinner.setBusy(state == "opening")
        if state == "playing" and self.debugVisible:
            self.showConsole()
        else:
            self.hideConsole()
        self.state, self.errorCode = state, error
        self.renderState()
        self.ui.stopStreamButton.setEnabled(self.running())
        self.updateControls()

    def playerMetadata(self, metadata):
        self.metadata = metadata
        self.renderMetadata()

    # ---- console --------------------------------------------------------------------
    def toggleDebug(self, enabled):
        self.debugVisible = enabled
        if enabled and self.state == "playing":
            self.showConsole()
        else:
            self.hideConsole()

    def showConsole(self):
        self.console.show()
        self.split.setSizes([self.split.width() // 2] * 2)

    def hideConsole(self):
        self.console.closeConnection()
        self.console.hide()

    # ---- presentation -----------------------------------------------------------------
    def updateControls(self, *args):
        ui = self.ui
        editable = not self.running()
        for widget in (ui.playButton, ui.mainUrlEdit, ui.subUrlEdit, ui.rtspUsernameEdit, ui.rtspPasswordEdit, ui.streamCombo, ui.rtspAutoTrustCheck):
            widget.setEnabled(editable)
        for widget in (ui.rtspCaEdit, ui.rtspCaButton):
            widget.setEnabled(editable and not ui.rtspAutoTrustCheck.isChecked())

    def render(self):
        self.renderState()
        self.renderMetadata()

    def renderState(self):
        suffix = f" [{self.errorCode}]" if self.state == "error" and self.errorCode else ""
        self.ui.streamStatusLabel.setText(STREAM_STATES[self.state] + suffix)

    def renderMetadata(self):
        facts = self.metadata
        self.ui.metadataLabel.setWordWrap(True)
        if not facts:
            self.ui.metadataLabel.clear()
            return
        audio = ", ".join(f"{a.get('codec')} {a.get('sampleRate')}Hz" for a in facts.get("audio", []))
        self.ui.metadataLabel.setText(
            f"{facts.get('width', 0)} × {facts.get('height', 0)} | Codec: {facts.get('codec', '?')} | "
            f"{'Displayed FPS'}: {facts.get('measuredFps') or '—'} | "
            f"{'Window'}: {facts.get('wallSampleSeconds', 0)}s | "
            f"{'Latency: not measured'} | Audio: {audio}"
        )

    def chooseCertificate(self):
        path, _ = QFileDialog.getOpenFileName(self.ui, "RTSPS certificate", self.ui.rtspCaEdit.text(), CERTIFICATE_FILTER)
        if path:
            self.ui.rtspCaEdit.setText(path)

    def warn(self, message):
        QMessageBox.warning(self.ui, "Configuration / operation", message)
