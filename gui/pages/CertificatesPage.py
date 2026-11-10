"""Device TLS certificates: create self-signed, enable / disable, delete."""

from PyQt6.QtWidgets import QInputDialog
from gui.pages.DevicePage import DevicePage
from gui.pages.Forms import button, buttonRow, dataTable, fillTable, pageLayout, selectedRecord


class CertificatesPage(DevicePage):
    ICON = "certificates"
    TITLE = "Certificates"

    def __init__(self, workspace):
        super().__init__(workspace)
        layout = pageLayout(self)
        self.table = dataTable(2)
        layout.addWidget(self.table, 1)
        buttonRow(
            layout,
            button("Create self-signed", self.create, primary=True),
            button("Enable / disable", self.toggle),
            button("Delete", self.delete),
        )

    def load(self, profile):
        self.table.setRowCount(0)
        self.present()
        self.run(self.device.certificates, self.show)

    def show(self, certificates):
        self.table.setHorizontalHeaderLabels(["ID", "Enabled"])
        fillTable(self.table, certificates, lambda cert: (cert["id"], "✓" if cert["enabled"] else ""), centered=(1,))
        self.workspace.loaded()

    def create(self):
        title = "Create certificate"
        subject, accepted = QInputDialog.getText(self, title, "Subject (e.g. CN=camera.local)")
        if accepted and self.workspace.confirm(title, [subject or "(device default subject)"]):
            self.run(lambda: self.device.createCertificate("", subject.strip()), lambda _: self.load(None), "Creating…")

    def toggle(self):
        cert = selectedRecord(self.table)
        if not cert:
            return
        states = ("enabled", "disabled") if cert["enabled"] else ("disabled", "enabled")
        lines = [
            f"{cert['id']}: {states[0]} → {states[1]}",
            "HTTPS/RTSPS clients may need the new certificate pinned again.",
        ]
        if self.workspace.confirm("Certificate status", lines):
            self.run(lambda: self.device.setCertificateStatus(cert["id"], not cert["enabled"]), lambda _: self.load(None), "Saving…")

    def delete(self):
        cert = selectedRecord(self.table)
        if not cert:
            return
        lines = [f"Delete certificate {cert['id']}? HTTPS/RTSPS using it stops working."]
        if self.workspace.confirmTyped("Delete certificate", lines, "DELETE"):
            self.run(lambda: self.device.deleteCertificate(cert["id"]), lambda _: self.load(None), "Deleting…")
