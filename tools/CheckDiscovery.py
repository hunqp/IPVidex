"""Offline integration check for independent ONVIF login tabs."""

import os
import ssl
import sys
import time
from pathlib import Path
from unittest.mock import patch

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from PyQt6.QtCore import QCoreApplication, QEvent, QThread, QTimer  # noqa: E402
from PyQt6.QtWidgets import QApplication, QCheckBox, QDialog, QDialogButtonBox, QLineEdit, QSpinBox  # noqa: E402
from gui.MainController import MainWindow  # noqa: E402
from services.OnvifDevice import OnvifDevice  # noqa: E402

FIXED_TABS = 4  # Discovery, RTSP(S), RTMP, P2P

app = QApplication([])
window = MainWindow()
hub = window.discoveryHub
errors = []


def recordError(kind, value, tb):
    errors.append(f"{kind.__name__}: {value}")
    sys.__excepthook__(kind, value, tb)


sys.excepthook = recordError


def drain():
    deadline = time.monotonic() + 3
    while time.monotonic() < deadline:
        app.processEvents()
        if not any(thread.isRunning() for thread in window.findChildren(QThread)):
            app.processEvents()
            # Outside a running event loop, deleteLater() only takes effect when flushed explicitly.
            QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete.value)
            return
        time.sleep(0.01)
    raise AssertionError("Background task did not finish")


def enterCredentials():
    dialog = app.activeModalWidget()
    assert isinstance(dialog, QDialog)
    fields = dialog.findChildren(QLineEdit)
    fields[0].setText("admin")
    fields[1].setText("password-" + str(len(hub.workspaces)))
    if not hub.workspaces:
        checks = dialog.findChildren(QCheckBox)
        checks[0].setChecked(True)  # HTTPS
        checks[1].setChecked(True)  # automatic certificate trust
        assert dialog.findChild(QSpinBox).value() == 443
        assert not fields[-1].isEnabled()
    dialog.findChild(QDialogButtonBox).accepted.emit()


def cancelLogin():
    app.activeModalWidget().reject()


def rowOf(address):
    return next(row for row in range(hub.table.rowCount()) if hub.table.item(row, 1).text() == address)


certificate = ssl.DER_cert_to_PEM_cert(ssl.create_default_context().get_ca_certs(binary_form=True)[0])
with (
    patch.object(OnvifDevice, "connect", lambda device: device),
    patch.object(OnvifDevice, "identification", lambda device: {"Name": device.session.config.host, "Location": ""}),
    patch.object(OnvifDevice, "networkSettings", lambda device: None),
    patch.object(OnvifDevice, "timeSettings", lambda device: None),
    patch.object(OnvifDevice, "profiles", lambda device: []),
    patch("gui.DeviceLoginDialog.fetchCertificate", return_value=certificate),
):
    for address in ("192.0.2.1", "192.0.2.2"):
        hub.found(dict(address=address, port=80, path="/onvif/device_service"))
        hub.table.selectRow(hub.table.rowCount() - 1)
        hub.table.cellClicked.emit(hub.table.currentRow(), 0)
        assert app.activeModalWidget() is None
        QTimer.singleShot(0, enterCredentials)
        hub.table.cellDoubleClicked.emit(hub.table.currentRow(), 0)
        drain()
    assert window.tabs.count() == FIXED_TABS + 2
    first, second = hub.workspaces.values()
    assert first.device is not second.device
    assert first.device.session.config.password != second.device.session.config.password
    assert first.identification is not second.identification
    assert first.device.session.certificatePem == certificate
    assert first.device.session.pinned
    hub.table.cellDoubleClicked.emit(0, 0)
    assert window.tabs.count() == FIXED_TABS + 2
    assert window.tabs.currentWidget() is first
    assert second.navBar.tabText(0) == "Overview"

    # A cancelled login must not break the next attempt.
    hub.found(dict(address="192.0.2.3", port=80, path="/onvif/device_service"))
    for _ in range(2):
        QTimer.singleShot(0, cancelLogin)
        hub.table.cellDoubleClicked.emit(rowOf("192.0.2.3"), 0)
        drain()
    assert hub.pendingLogin is None and not errors, errors

    # A login cancelled while its call still runs blocks new logins until that call returns.
    with patch.object(OnvifDevice, "connect", lambda device: time.sleep(0.5) or device):
        QTimer.singleShot(0, lambda: (enterCredentials(), QTimer.singleShot(100, cancelLogin)))
        hub.table.cellDoubleClicked.emit(rowOf("192.0.2.3"), 0)
        assert hub.pendingLogin is not None
        hub.table.cellDoubleClicked.emit(rowOf("192.0.2.3"), 0)
        assert app.activeModalWidget() is None and hub.status.text().startswith("Waiting")
        drain()
    assert hub.pendingLogin is None
    QTimer.singleShot(0, cancelLogin)
    hub.table.cellDoubleClicked.emit(rowOf("192.0.2.3"), 0)
    drain()
    assert not errors, errors

    hub.closeTab(window.tabs.indexOf(first))
    drain()
    assert window.tabs.count() == FIXED_TABS + 1
    assert first.disposed and not first.device.session.config.password
    assert not second.disposed
    assert second.device.session.config.password
    window.close()
    drain()
assert not errors, errors
print("PASS: independent logins, tab reuse, login retry after cancel, close and shutdown")
