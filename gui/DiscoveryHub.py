"""Shared discovery list; each authenticated device opens in its own workspace tab."""

from PyQt6.QtCore import QSize, Qt, QThread, QTimer
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QHBoxLayout,
    QHeaderView,
    QInputDialog,
    QLabel,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)
from core.Models import Config
from core.Paths import ICONS
from core.Version import VERSION
from gui.BusySpinner import statusRow
from gui.DeviceLoginDialog import DeviceLoginDialog
from gui.DeviceWorkspace import DeviceWorkspace
from infrastructure.LanDiscovery import OnvifDiscoveryWorker

ROW_HEIGHT = 34
RETRY_MS = 100


class DiscoveryHub(QWidget):
    def __init__(self, window):
        super().__init__(window)
        self.window = window
        self.devices, self.workspaces = {}, {}
        self.worker = None
        self.pendingLogin = None
        layout = QVBoxLayout(self)
        toolbar = QHBoxLayout()
        self.scanButton = self.toolButton("refresh.svg", self.scan)
        self.addButton = self.toolButton("add.svg", self.addDevice)
        toolbar.addWidget(self.scanButton)
        toolbar.addWidget(self.addButton)
        toolbar.addStretch()
        layout.addLayout(toolbar)
        self.table = QTableWidget(0, 4)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.verticalHeader().hide()
        self.table.verticalHeader().setMinimumSectionSize(ROW_HEIGHT)
        self.table.verticalHeader().setDefaultSectionSize(ROW_HEIGHT)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.cellDoubleClicked.connect(self.openDevice)
        layout.addWidget(self.table)
        self.status = QLabel()
        footer = QHBoxLayout()
        footer.addWidget(statusRow(self.status), 1)
        version = QLabel(f"Version {VERSION}")
        version.setObjectName("versionLabel")
        footer.addWidget(version)
        layout.addLayout(footer)
        window.tabs.tabCloseRequested.connect(self.closeTab)
        self.scanButton.setToolTip("Scan devices")
        self.addButton.setToolTip("Add device")
        self.table.setHorizontalHeaderLabels(["Name", "IP / Host", "Location", "Status"])
        self.status.setText("Double-click a device to log in.")

    def toolButton(self, icon, handler):
        button = QPushButton()
        button.setIcon(QIcon(str(ICONS / icon)))
        button.setIconSize(QSize(18, 18))
        button.setFixedSize(34, 28)
        button.clicked.connect(handler)
        return button

    # ---- device list ----------------------------------------------------------------
    def scan(self):
        if self.worker and self.worker.isRunning():
            return
        self.devices = {key: value for key, value in self.devices.items() if value.get("manual") or key in self.workspaces}
        self.render()
        self.scanButton.setEnabled(False)
        self.status.busySpinner.setBusy(True)
        self.status.setText("Scanning…")
        self.worker = OnvifDiscoveryWorker(self)
        self.worker.deviceFound.connect(self.found)
        self.worker.finished.connect(self.scanFinished)
        self.worker.start()

    def found(self, info):
        self.devices.setdefault(info["address"], {}).update(info)
        self.render()

    def scanFinished(self):
        self.status.busySpinner.setBusy(False)
        self.scanButton.setEnabled(True)
        count = len(self.devices)
        self.status.setText(f"{count} device(s). Double-click a device to log in.")
        self.worker.deleteLater()
        self.worker = None

    def render(self):
        selected = self.table.selectedItems()
        selectedAddress = selected[0].data(Qt.ItemDataRole.UserRole) if selected else None
        self.table.setRowCount(0)
        for address, info in sorted(self.devices.items()):
            row = self.table.rowCount()
            self.table.insertRow(row)
            status = "Connected" if address in self.workspaces else "Not connected"
            for column, value in enumerate((info.get("name", ""), address, info.get("location", ""), status)):
                item = QTableWidgetItem(value)
                item.setData(Qt.ItemDataRole.UserRole, address)
                self.table.setItem(row, column, item)
            if address == selectedAddress:
                self.table.selectRow(row)

    def addDevice(self):
        address, accepted = QInputDialog.getText(self, "Add device", "IP / Hostname")
        if not accepted:
            return
        try:
            address = Config(address).validate().host
        except ValueError as exc:
            QMessageBox.warning(self, "ONVIF", str(exc))
            return
        self.found(dict(address=address, port=self.window.onvifPortSpin.value(), path=self.window.onvifPathEdit.text(), manual=True))

    # ---- workspaces ------------------------------------------------------------------
    def openDevice(self, row, column):
        address = self.table.item(row, 0).data(Qt.ItemDataRole.UserRole)
        if address in self.workspaces:
            self.window.tabs.setCurrentWidget(self.workspaces[address])
            return
        if self.pendingLogin is not None:
            self.status.setText("Waiting for the previous connection to finish…")
            return
        dialog = DeviceLoginDialog(self, address, self.devices[address], self.window)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.openWorkspace(address, *dialog.connection)
        if dialog.busy():
            # Keep a cancelled login's receivers alive until its authentication call has returned.
            self.pendingLogin = dialog
            dialog.task.finished.connect(self.loginSettled)
        else:
            dialog.deleteLater()

    def loginSettled(self):
        self.pendingLogin.deleteLater()
        self.pendingLogin = None

    def openWorkspace(self, address, device, state):
        workspace = DeviceWorkspace(self.window.tabs, device, state)
        self.workspaces[address] = workspace
        index = self.window.tabs.addTab(workspace, f"{state['identification'].get('Name') or address} ({address})")
        self.window.tabs.setCurrentIndex(index)
        self.render()

    def closeTab(self, index):
        workspace = self.window.tabs.widget(index)
        if not isinstance(workspace, DeviceWorkspace):
            return
        workspace.dispose()
        self.window.tabs.removeTab(index)
        address = next(key for key, value in self.workspaces.items() if value is workspace)
        del self.workspaces[address]
        self.retire(workspace)
        self.render()

    def retire(self, workspace):
        """Delete a closed workspace once none of its threads is still running."""
        if any(task.isRunning() for task in workspace.findChildren(QThread)):
            QTimer.singleShot(RETRY_MS, lambda: self.retire(workspace))
        else:
            workspace.deleteLater()

    def shutdown(self):
        """Begin stopping everything; True once no discovery or device thread is running."""
        if self.worker:
            self.worker.cancel()
        for workspace in self.workspaces.values():
            if not workspace.disposed:
                workspace.dispose()
        running = self.findChildren(QThread) + self.window.tabs.findChildren(QThread)
        if (self.worker and self.worker.isRunning()) or any(task.isRunning() for task in running):
            QTimer.singleShot(RETRY_MS, self.window.close)
            return False
        return True
