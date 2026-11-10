"""Reboot, factory reset, firmware upgrade, backup / restore and device logs."""

import os
from PyQt6.QtWidgets import QFileDialog, QHBoxLayout, QLineEdit, QPlainTextEdit
from gui.pages.DevicePage import DevicePage
from gui.pages.Forms import button, buttonRow, pageLayout, section

MAX_UPLOAD_BYTES = 256 * 1024 * 1024
FIRMWARE_FILTER = "Firmware (*.bin *.img *.pkg *.dav *.zip);;All files (*)"


def readUpload(path):
    if not path or not os.path.isfile(path):
        raise ValueError("Select a file first.")
    if os.path.getsize(path) > MAX_UPLOAD_BYTES:
        raise ValueError("File exceeds 256 MB.")
    with open(path, "rb") as handle:
        return handle.read()


class MaintenancePage(DevicePage):
    ICON = "maintenance"
    TITLE = "Maintenance"

    def __init__(self, workspace):
        super().__init__(workspace)
        layout = pageLayout(self)
        section(layout, "Device")
        buttonRow(layout, button("Reboot", self.reboot))
        section(layout, "Factory default")
        buttonRow(
            layout,
            button("Soft reset (keep network)", lambda: self.factoryReset("Soft")),
            button("Hard reset (everything)", lambda: self.factoryReset("Hard")),
        )
        section(layout, "Firmware upgrade")
        layout.addLayout(self.buildFirmwareRow())
        section(layout, "Backup / restore")
        buttonRow(layout, button("Save backup…", self.saveBackup), button("Restore…", self.restore))
        section(layout, "Logs and support information")
        buttonRow(
            layout,
            button("System log", lambda: self.showLog("System")),
            button("Access log", lambda: self.showLog("Access")),
            button("Support information", lambda: self.showLog("Support")),
        )
        self.logView = QPlainTextEdit()
        self.logView.setReadOnly(True)
        layout.addWidget(self.logView, 1)

    def buildFirmwareRow(self):
        self.firmwarePath = QLineEdit()
        self.firmwarePath.setReadOnly(True)
        self.firmwarePath.setPlaceholderText("Select a firmware file")
        row = QHBoxLayout()
        row.addWidget(self.firmwarePath, 1)
        row.addWidget(button("Browse…", self.chooseFirmware))
        row.addWidget(button("Upgrade", self.upgradeFirmware, primary=True))
        return row

    def load(self, profile):
        self.logView.clear()
        self.present()
        self.workspace.setStatus("")

    def report(self, message):
        return lambda _: self.workspace.setStatus(message)

    def reboot(self):
        name = self.workspace.deviceName()
        lines = [f"Reboot {name}? Streams and connections drop until it is back online."]
        if self.workspace.confirm("Reboot device", lines):
            self.run(self.device.reboot, lambda message: self.workspace.setStatus(message or "Rebooting…"), "Sending reboot…")

    def factoryReset(self, kind):
        name = self.workspace.deviceName()
        scope = "network settings are kept" if kind == "Soft" else "ALL settings including network, users and certificates are erased"
        lines = [f"{kind} factory reset of {name}: {scope}.", "This cannot be undone."]
        if self.workspace.confirmTyped("Factory default", lines, "RESET"):
            self.run(
                lambda: self.device.factoryDefault(kind),
                self.report("Factory reset sent."),
                "Sending factory reset…",
            )

    def chooseFirmware(self):
        path, _ = QFileDialog.getOpenFileName(self, "Firmware file", "", FIRMWARE_FILTER)
        if path:
            self.firmwarePath.setText(path)

    def upgradeFirmware(self):
        path = self.firmwarePath.text()
        try:
            payload = readUpload(path)
        except ValueError as exc:
            self.workspace.warn(str(exc))
            return
        name, size = os.path.basename(path), len(payload) // 1024
        device = self.workspace.deviceName()
        lines = [
            f"Upload {name} ({size} KB) to {device}.",
            "A wrong or interrupted image can make the device unusable. Do not power it off.",
        ]
        if not self.workspace.confirmTyped("Firmware upgrade", lines, "UPGRADE"):
            return
        self.run(lambda: self.device.firmwareUpgrade(payload), self.firmwareUploaded, "Uploading firmware…")

    def firmwareUploaded(self, downtime):
        self.workspace.setStatus(f"Firmware uploaded; expected downtime {downtime:.0f} s.")

    def saveBackup(self):
        path, _ = QFileDialog.getSaveFileName(self, "Save backup", f"{self.workspace.deviceName()}-backup.bin")
        if not path:
            return

        def write(data):
            with open(path, "wb") as handle:
                handle.write(data)
            size = len(data) // 1024
            self.workspace.setStatus(f"Backup saved ({size} KB).")

        self.run(self.device.backup, write, "Downloading backup…")

    def restore(self):
        path, _ = QFileDialog.getOpenFileName(self, "Restore backup")
        if not path:
            return
        try:
            payload = readUpload(path)
        except ValueError as exc:
            self.workspace.warn(str(exc))
            return
        lines = ["The current configuration is replaced by the backup file."]
        if self.workspace.confirmTyped("Restore configuration", lines, "RESTORE"):
            self.run(
                lambda: self.device.restore(payload),
                self.report("Restore uploaded."),
                "Uploading backup…",
            )

    def showLog(self, kind):
        function = self.device.supportInformation if kind == "Support" else (lambda: self.device.systemLog(kind))

        def show(text):
            self.logView.setPlainText(text)
            self.workspace.loaded()

        self.logView.clear()
        self.run(function, show)
