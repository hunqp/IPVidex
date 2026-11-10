"""Account, endpoint and certificate trust for one device; connects off the GUI thread."""

import threading
from PyQt6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QWidget,
)
from core.Models import Config
from gui.Appearance import plainSpinBox
from gui.BusySpinner import statusRow
from gui.OnvifTask import OnvifTask
from infrastructure.Network import CertificateRequired, Transport, fetchCertificate, readCertificateFile
from infrastructure.Onvif import OnvifSession
from services.OnvifDevice import OnvifDevice

HTTP_PORT, HTTPS_PORT = 80, 443
MIN_LOGIN_TIMEOUT = 4.0
CERTIFICATE_FILTER = "PEM certificate (*.pem *.crt *.cer);;All files (*)"
UNTRUSTED_MARKERS = ("CERTIFICATE_VERIFY_FAILED", "does not match the pinned file")


def connectDevice(config, transport, certificatePem, autoTrust):
    """Blocking: authenticate and read what the workspace needs to open."""
    if autoTrust:
        certificatePem = fetchCertificate(transport, config.onvifPort)
    device = OnvifDevice(OnvifSession(config, transport, certificatePem)).connect()
    state = {"identification": device.identification(), "profiles": device.profiles() if "trt" in device.services else []}
    transport.checkpoint()
    return device, state


class DeviceLoginDialog(QDialog):
    """On acceptance, `connection` holds (device, state)."""

    def __init__(self, parent, address, info, settings):
        super().__init__(parent)
        self.address, self.settings = address, settings
        self.connection = None
        self.task = None
        self.stop = threading.Event()
        self.setWindowTitle("Device login" + f" — {address}")
        form = QFormLayout(self)
        form.addRow("Device", QLabel(address))
        self.username, self.password = QLineEdit(), QLineEdit()
        self.password.setEchoMode(QLineEdit.EchoMode.Password)
        form.addRow("Username", self.username)
        form.addRow("Password", self.password)
        self.buildEndpoint(form, info)
        self.buildTrust(form)
        self.status = QLabel()
        self.status.setWordWrap(True)
        form.addRow(statusRow(self.status))
        self.buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        self.buttons.accepted.connect(self.login)
        self.buttons.rejected.connect(self.reject)
        form.addRow(self.buttons)

    def buildEndpoint(self, form, info):
        https = self.settings.onvifHttpsCheck.isChecked()
        self.port = QSpinBox()
        plainSpinBox(self.port)
        self.port.setRange(1, 65535)
        self.port.setValue(self.settings.onvifPortSpin.value() if https else info["port"])
        self.path = QLineEdit(info["path"])
        self.secure = QCheckBox("HTTPS")
        self.secure.setChecked(https)
        self.secure.toggled.connect(self.httpsChanged)
        form.addRow("Port", self.port)
        form.addRow("Endpoint", self.path)
        form.addRow(self.secure)

    def buildTrust(self, form):
        self.autoTrust = QCheckBox("Automatically fetch and trust camera certificate")
        self.autoTrust.setToolTip("Trust the certificate received from this address for this session only.")
        self.autoTrust.toggled.connect(self.trustChanged)
        form.addRow(self.autoTrust)
        self.certificate = QLineEdit()
        self.certificate.setPlaceholderText("System trust, or select camera certificate")
        browse = QPushButton("Browse…")
        browse.clicked.connect(self.chooseCertificate)
        self.certificateRow = QWidget()
        row = QHBoxLayout(self.certificateRow)
        row.setContentsMargins(0, 0, 0, 0)
        row.addWidget(self.certificate)
        row.addWidget(browse)
        form.addRow("Certificate", self.certificateRow)
        self.trustChanged()

    def trustChanged(self, *args):
        secure = self.secure.isChecked()
        self.autoTrust.setEnabled(secure)
        self.certificateRow.setEnabled(secure and not self.autoTrust.isChecked())

    def httpsChanged(self, enabled):
        self.trustChanged()
        if enabled and self.port.value() == HTTP_PORT:
            self.port.setValue(HTTPS_PORT)
        elif not enabled and self.port.value() == HTTPS_PORT:
            self.port.setValue(HTTP_PORT)

    def chooseCertificate(self):
        filename, _ = QFileDialog.getOpenFileName(self, "Camera certificate", self.certificate.text(), CERTIFICATE_FILTER)
        if filename:
            self.certificate.setText(filename)

    def certificatePem(self):
        """PEM chosen by the operator; empty for plain HTTP, system trust or automatic trust."""
        path = self.certificate.text().strip()
        if not self.secure.isChecked() or self.autoTrust.isChecked() or not path:
            return ""
        return readCertificateFile(path)

    def login(self):
        try:
            timeout = max(MIN_LOGIN_TIMEOUT, self.settings.timeoutSpin.value())
            config = Config(
                self.address, self.username.text(), self.password.text(), timeout, self.port.value(), self.path.text(), self.secure.isChecked()
            ).validate()
            pem = self.certificatePem()
        except CertificateRequired:
            self.status.setText(self.untrustedMessage())
            return
        except (ValueError, OSError) as exc:
            self.status.setText(str(exc))
            return
        autoTrust = self.secure.isChecked() and self.autoTrust.isChecked()
        self.buttons.button(QDialogButtonBox.StandardButton.Ok).setEnabled(False)
        self.status.setText("Connecting…")
        self.status.busySpinner.setBusy(True)
        transport = Transport(config, self.stop)
        self.task = OnvifTask(lambda: connectDevice(config, transport, pem, autoTrust), self)
        self.task.succeeded.connect(self.succeeded)
        self.task.failed.connect(self.failed)
        self.task.start()

    def untrustedMessage(self):
        return "Select the camera PEM certificate or enable automatic certificate trust, then try again."

    def succeeded(self, connection):
        self.status.busySpinner.setBusy(False)
        if not self.stop.is_set():
            self.connection = connection
            self.accept()

    def failed(self, message):
        self.status.busySpinner.setBusy(False)
        if self.stop.is_set():
            return
        self.status.setText(self.untrustedMessage() if any(marker in message for marker in UNTRUSTED_MARKERS) else message)
        self.buttons.button(QDialogButtonBox.StandardButton.Ok).setEnabled(True)

    def done(self, result):
        if result != QDialog.DialogCode.Accepted:
            self.stop.set()
        self.status.busySpinner.setBusy(False)
        self.password.clear()
        super().done(result)

    def busy(self):
        return self.task is not None and self.task.isRunning()
