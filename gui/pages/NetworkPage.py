"""Network settings: addressing, gateway, hostname, DNS, NTP, discovery mode and protocols."""

from PyQt6.QtWidgets import QCheckBox, QFormLayout, QLabel, QLineEdit, QWidget
from gui.pages.DevicePage import DevicePage
from gui.pages.Forms import addRow, applyCancelRow, formLayout, numberBox, pageLayout, setEnabledAll

PROTOCOL_PORT_WIDTH = 120


class NetworkPage(DevicePage):
    ICON = "network"
    TITLE = "Network"

    def __init__(self, workspace):
        super().__init__(workspace)
        self.state = None
        self.protocolWidgets = []
        layout = pageLayout(self)
        form = formLayout()
        layout.addLayout(form)
        self.dhcp = addRow(form, "DHCP", QCheckBox())
        self.address = addRow(form, "IP address", QLineEdit())
        self.prefix = addRow(form, "Prefix length", numberBox(1, 32))
        self.gateway = addRow(form, "Default gateway", QLineEdit())
        self.hostname = addRow(form, "Hostname", QLineEdit())
        self.dnsFromDhcp = addRow(form, "DNS from DHCP", QCheckBox())
        self.dns = addRow(form, "DNS servers", QLineEdit())
        self.ntpFromDhcp = addRow(form, "NTP from DHCP", QCheckBox())
        self.ntp = addRow(form, "NTP servers", QLineEdit())
        self.discoverable = addRow(form, "Discoverable (WS-Discovery)", QCheckBox())
        self.mac = addRow(form, "MAC address", QLabel())
        protocols = QWidget()
        self.protocols = QFormLayout(protocols)
        self.protocols.setContentsMargins(0, 0, 0, 0)
        addRow(form, "Protocols", protocols)
        for check, edits in self.dhcpGroups():
            check.toggled.connect(lambda on, widgets=edits: setEnabledAll(widgets, not on))
        applyCancelRow(layout, self.apply, lambda: self.load(None))
        layout.addStretch(1)

    def dhcpGroups(self):
        """Each 'from DHCP' check box with the fields it overrides."""
        return (
            (self.dhcp, (self.address, self.prefix, self.gateway)),
            (self.dnsFromDhcp, (self.dns,)),
            (self.ntpFromDhcp, (self.ntp,)),
        )

    def load(self, profile):
        self.run(self.device.networkSettings, self.show)

    def show(self, state):
        self.state = state
        self.dhcp.setChecked(state["dhcp"])
        self.address.setText(state["address"])
        self.prefix.setValue(state["prefix"])
        self.gateway.setText(state["gateway"])
        self.hostname.setText(state["hostname"])
        self.dnsFromDhcp.setChecked(state["dnsFromDhcp"])
        self.dns.setText(state["dns"])
        self.ntpFromDhcp.setChecked(state["ntpFromDhcp"])
        self.ntp.setText(state["ntp"])
        self.discoverable.setChecked(state["discoverable"])
        self.mac.setText(state["mac"])
        for check, edits in self.dhcpGroups():
            setEnabledAll(edits, not check.isChecked())
        self.showProtocols(state["protocols"])
        self.present()
        self.workspace.loaded()

    def showProtocols(self, protocols):
        while self.protocols.rowCount():
            self.protocols.removeRow(0)
        self.protocolWidgets = []
        for protocol in protocols:
            enabled = QCheckBox(protocol["name"])
            enabled.setChecked(protocol["enabled"])
            port = numberBox(1, 65535)
            port.setValue(protocol["ports"][0] if protocol["ports"] else 1)
            port.setMaximumWidth(PROTOCOL_PORT_WIDTH)
            self.protocols.addRow(enabled, port)
            self.protocolWidgets.append((protocol, enabled, port))

    def edited(self):
        return dict(
            self.state,
            dhcp=self.dhcp.isChecked(),
            address=self.address.text().strip(),
            prefix=self.prefix.value(),
            gateway=self.gateway.text().strip(),
            hostname=self.hostname.text().strip(),
            dnsFromDhcp=self.dnsFromDhcp.isChecked(),
            dns=self.dns.text().strip(),
            ntpFromDhcp=self.ntpFromDhcp.isChecked(),
            ntp=self.ntp.text().strip(),
            discoverable=self.discoverable.isChecked(),
            protocols=[
                dict(protocol, enabled=enabled.isChecked(), ports=[port.value()] + protocol["ports"][1:]) for protocol, enabled, port in self.protocolWidgets
            ],
        )

    @staticmethod
    def changes(old, new):
        lines = [f"{key}: {old[key]} → {new[key]}" for key in new if key != "protocols" and new[key] != old[key]]
        for before, after in zip(old["protocols"], new["protocols"], strict=True):
            if before != after:
                lines.append(f"{after['name']}: enabled={before['enabled']}, port={before['ports']} → enabled={after['enabled']}, port={after['ports']}")
        if lines and (new["dhcp"], new["address"], new["prefix"]) != (old["dhcp"], old["address"], old["prefix"]):
            lines.append("WARNING: changing the IP address/DHCP can disconnect this device; reconnect at the new address.")
        return lines

    def apply(self):
        old, new = self.state, self.edited()
        lines = self.changes(old, new)
        if not lines or not self.workspace.confirm("Change network settings", lines):
            return
        self.workspace.runTask(lambda: self.device.setNetwork(old, new), self.saved, "Saving…")

    def saved(self, rebootNeeded):
        self.workspace.setStatus("Saved.")
        question = ["The device reports a reboot is needed to apply the change. Reboot now?"]
        if rebootNeeded and self.workspace.confirm("Reboot needed", question):
            self.workspace.runTask(self.device.reboot, lambda message: self.workspace.setStatus(message or "Rebooting…"))
        else:
            self.load(None)
