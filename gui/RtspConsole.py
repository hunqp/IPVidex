"""RTSP command console: real requests on a separate test connection, shown as a transcript."""

import json
from html import escape
from PyQt6.QtCore import QProcess, Qt, QTimer
from PyQt6.QtWidgets import QGroupBox, QLabel, QPlainTextEdit, QPushButton, QTextBrowser, QToolButton, QVBoxLayout, QWidget
from core.Paths import ROOT
from core.Runtime import detachWorker, workerCommand
from gui.BusySpinner import statusRow
from gui.FlowLayout import FlowLayout

# Method: (accent color, background) of its button and transcript card.
COMMAND_COLORS = {
    "OPTIONS": ("#2467A8", "#EFF6FD"),
    "DESCRIBE": ("#6B52A3", "#F4F0FA"),
    "GET_PARAMETER": ("#187D83", "#EDF8F8"),
    "SET_PARAMETER": ("#A3671D", "#FCF5EA"),
    "SETUP": ("#456A40", "#F0F6EE"),
    "PLAY": ("#287F60", "#EDF8F2"),
    "PAUSE": ("#9A7540", "#FAF6EE"),
    "TEARDOWN": ("#A04F64", "#FBF0F3"),
}
DEFAULT_COLORS = ("#2467A8", "#F4F8FD")
MAX_TRANSCRIPT_BLOCKS = 4000
COMMAND_BUTTON_HEIGHT = 26


def responseDeadlineMs(timeout):
    """Room for a 401 challenge plus retry, track discovery and SETUP before PLAY."""
    return int((4 * float(timeout) + 10) * 1000)


def card(title, content, color, background):
    head, _, body = content.partition("\r\n\r\n")
    lines = head.splitlines()
    first = lines[0] if lines else ""
    headers = "\n".join(lines[1:])
    details = f'<pre style="white-space:pre-wrap;color:#586575;margin:6px 0">{escape(headers)}</pre>' if headers else ""
    if body:
        details += f'<pre style="white-space:pre-wrap;margin:8px 0">{escape(body)}</pre>'
    return (
        f'<table width="100%" cellspacing="0" cellpadding="8" style="background:{background};border:1px solid #DEE5ED">'
        f'<tr><td><span style="color:{color};font-family:Tahoma"><b>{title}</b></span>'
        f'<p style="margin:6px 0;color:{color}">{escape(first)}</p>{details}</td></tr></table>'
    )


def commandButton(method):
    button = QPushButton(method)
    button.setObjectName("rtspCommandTag")
    color, background = COMMAND_COLORS[method]
    button.setStyleSheet(
        f"QPushButton#rtspCommandTag {{color:{color};border-color:{color};background:{background};}}"
        "QPushButton#rtspCommandTag:hover {background:#FFFFFF;}"
        "QPushButton#rtspCommandTag:disabled {color:#91A7BC;border-color:#C6D6E5;background:#F7F9FB;}"
    )
    button.setFixedHeight(COMMAND_BUTTON_HEIGHT)
    button.setMinimumWidth(button.fontMetrics().horizontalAdvance(method) + 28)
    return button


class RtspConsole(QGroupBox):
    """credentials() returns the (username, password) currently typed in the RTSP form."""

    def __init__(self, credentials, parent=None):
        super().__init__(parent)
        self.credentials = credentials
        self.process = None
        self.buffer = bytearray()
        self.target = None
        self.pending = False
        self.timeout = QTimer(self)
        self.timeout.setSingleShot(True)
        self.timeout.timeout.connect(self.timedOut)
        self.setObjectName("rtspCommandPanel")
        panel = QVBoxLayout(self)
        panel.setContentsMargins(12, 14, 12, 10)
        panel.setSpacing(8)
        panel.addWidget(self.buildCommandButtons())
        self.buildRequestOptions(panel)
        self.progress = QLabel("Ready")
        self.progress.setObjectName("rtspCommandProgress")
        panel.addWidget(statusRow(self.progress))
        self.transcript = QTextBrowser()
        self.transcript.setOpenLinks(False)
        self.transcript.setPlaceholderText("RTSP response")
        self.transcript.document().setMaximumBlockCount(MAX_TRANSCRIPT_BLOCKS)
        self.transcript.setStyleSheet("font-family:Consolas;font-size:9pt;")
        self.transcript.setMinimumHeight(100)
        panel.addWidget(self.transcript, 1)
        clear = QPushButton("Clear")
        clear.clicked.connect(self.transcript.clear)
        panel.addWidget(clear, alignment=Qt.AlignmentFlag.AlignRight)

    def buildCommandButtons(self):
        tags = QWidget()
        row = FlowLayout(tags, spacing=6)
        self.buttons = []
        for method in COMMAND_COLORS:
            button = commandButton(method)
            button.clicked.connect(lambda checked=False, name=method: self.send(name))
            self.buttons.append(button)
            row.addWidget(button)
        return tags

    def buildRequestOptions(self, panel):
        toggle = QToolButton()
        toggle.setText("Request options")
        toggle.setObjectName("rtspRequestOptions")
        toggle.setCheckable(True)
        toggle.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        toggle.setArrowType(Qt.ArrowType.RightArrow)
        options = QWidget()
        layout = QVBoxLayout(options)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        self.headers = QPlainTextEdit()
        self.headers.setFixedHeight(44)
        self.headers.setPlaceholderText("Headers, e.g. Range: npt=0-")
        self.body = QPlainTextEdit()
        self.body.setFixedHeight(40)
        self.body.setPlaceholderText("Request body (optional)")
        layout.addWidget(self.headers)
        layout.addWidget(self.body)
        options.hide()

        def expand(expanded):
            options.setVisible(expanded)
            toggle.setArrowType(Qt.ArrowType.DownArrow if expanded else Qt.ArrowType.RightArrow)

        toggle.toggled.connect(expand)
        panel.addWidget(toggle)
        panel.addWidget(options)

    # ---- connection ---------------------------------------------------------------
    def setTarget(self, data):
        """Stream the console talks to (the player's stream data), or None when disconnected."""
        self.closeConnection()
        self.target = dict(data) if data else None
        self.transcript.clear()

    def closeConnection(self):
        self.progress.busySpinner.setBusy(False)
        self.timeout.stop()
        if self.process:
            process, self.process = self.process, None
            detachWorker(process)
            process.kill()
            process.waitForFinished(2000)
            process.deleteLater()
        self.buffer.clear()
        self.setPending(False)

    def setPending(self, pending):
        self.pending = pending
        self.progress.busySpinner.setBusy(pending)
        for button in self.buttons:
            button.setEnabled(not pending)

    def accountChanged(self):
        """Use the account typed in the RTSP form now; a changed account needs a new connection."""
        username, password = self.credentials()
        if not username and not password:
            return True
        if not username or not password:
            self.message("Account", "Enter both RTSP username and password.")
            return False
        if (username, password) != (self.target.get("username"), self.target.get("password")):
            self.closeConnection()
            self.target.update(username=username, password=password)
        return True

    def send(self, method):
        if self.target is None:
            self.progress.setText("Connect the stream first.")
            return
        if self.pending or not self.accountChanged():
            return
        command = dict(method=method, path=self.target["path"], headers=self.headers.toPlainText(), body=self.body.toPlainText())
        self.setPending(True)
        self.progress.setText(f"Sending {method}…")
        self.timeout.start(responseDeadlineMs(self.target.get("timeout", 2)))
        line = json.dumps(command).encode() + b"\n"
        if self.process is None:
            self.startProcess(json.dumps(self.target).encode() + b"\n" + line)
        else:
            self.process.write(line)

    def startProcess(self, firstInput):
        process = self.process = QProcess(self)
        process.setWorkingDirectory(str(ROOT))
        process.started.connect(lambda: process.write(firstInput))
        process.readyReadStandardOutput.connect(lambda: self.readResponses(process))
        process.readyReadStandardError.connect(process.readAllStandardError)
        process.finished.connect(lambda *args: self.exited(process))
        process.errorOccurred.connect(lambda error: self.exited(process) if error == QProcess.ProcessError.FailedToStart else None)
        process.start(*workerCommand("infrastructure.RtspCommands"))

    def readResponses(self, source):
        if source is not self.process:
            return
        self.buffer.extend(bytes(source.readAllStandardOutput()))
        while b"\n" in self.buffer:
            line, _, rest = self.buffer.partition(b"\n")
            self.buffer = bytearray(rest)
            try:
                result = json.loads(line)
            except ValueError:
                continue
            self.showResult(result)

    def showResult(self, result):
        if "error" in result:
            self.message("Error", result["error"])
        # A 401 challenge followed by a retry is normal Digest login: show only the final exchange.
        final = [] if "error" in result else result.get("exchanges", [])[-1:]
        for exchange in final:
            self.showExchange(exchange)
            if exchange.get("status") == 401:
                account = self.target.get("username") or "(anonymous)"
                self.message(
                    "Authentication rejected",
                    f"Camera rejected RTSP account: {account}. This is the final response after authentication retry.",
                )
        self.timeout.stop()
        self.setPending(False)
        self.progress.setText("Error: " + result["error"] if "error" in result else "Response received")

    def exited(self, source):
        if source is not self.process:
            return
        self.readResponses(source)
        self.process.deleteLater()
        self.process = None
        self.timeout.stop()
        if self.pending:
            self.message("Connection closed", "The RTSP test connection has closed.")
            self.progress.setText("Connection closed")
        self.setPending(False)

    def timedOut(self):
        self.message("Timeout", "The device did not return a complete RTSP response.")
        self.closeConnection()
        self.progress.setText("Timeout")

    # ---- transcript ------------------------------------------------------------------
    def message(self, title, text):
        self.transcript.append(f'<p style="color:#A04438"><b>{escape(title)}</b><br>{escape(text)}</p>')

    def showExchange(self, exchange):
        method = exchange["request"].split(" ", 1)[0]
        color, background = COMMAND_COLORS.get(method, DEFAULT_COLORS)
        html = card(f"{escape(method)} · REQUEST", exchange["request"], color, background)
        html += '<p style="margin:3px"> </p>'
        html += card(f"{escape(method)} · RESPONSE", exchange["response"], color, background)
        self.transcript.append(html + '<hr style="color:#E4E9EF">')
