"""Overview: identification (editable name and location), network, time, profiles and web links."""

from concurrent.futures import ThreadPoolExecutor
from PyQt6.QtCore import QUrl
from PyQt6.QtGui import QDesktopServices
from PyQt6.QtWidgets import QHBoxLayout, QLineEdit, QPushButton, QVBoxLayout
from gui.pages.DevicePage import DevicePage
from gui.pages.Forms import addRow, applyCancelRow, section, summaryForm, valueRow
from infrastructure.Network import hostAuthority

IDENTITY_FIELDS = (
    "Manufacturer",
    "Model",
    "Firmware version",
    "Serial number",
    "Hardware ID",
    "MAC address",
    "ONVIF version",
    "Device service URI",
)
NETWORK_FIELDS = (
    ("address", "IP address"),
    ("dhcp", "Addressing"),
    ("gateway", "Gateway"),
    ("dns", "DNS"),
    ("ntp", "NTP"),
    ("protocols", "Services"),
)
TIME_FIELDS = (("local", "Device time"), ("mode", "Synchronization"), ("zone", "Time zone"))
DEFAULT_WEB_PORTS = (80, 443)


def networkSummary(network):
    fromDhcp = "from DHCP"
    return {
        "address": f"{network['address']}/{network['prefix']}",
        "dhcp": "DHCP" if network["dhcp"] else "Static",
        "gateway": network["gateway"] or "—",
        "dns": (fromDhcp if network["dnsFromDhcp"] else network["dns"]) or "—",
        "ntp": (fromDhcp if network["ntpFromDhcp"] else network["ntp"]) or "—",
        "protocols": ", ".join(f"{p['name']} {','.join(map(str, p['ports']))}" + ("" if p["enabled"] else " (off)") for p in network["protocols"]),
    }


def webUrls(host, network):
    authority = hostAuthority(host)
    urls = [
        f"{p['name'].lower()}://{authority}" + ("" if p["ports"][0] in DEFAULT_WEB_PORTS else f":{p['ports'][0]}")
        for p in (network or {}).get("protocols", [])
        if p["name"] in ("HTTP", "HTTPS") and p["enabled"] and p["ports"]
    ]
    return urls or [f"http://{authority}"]


class OverviewPage(DevicePage):
    ICON = "identification"
    TITLE = "Overview"

    def __init__(self, workspace):
        super().__init__(workspace)
        columns = QHBoxLayout(self)
        columns.setContentsMargins(0, 0, 0, 0)
        columns.setSpacing(24)
        left, right = QVBoxLayout(), QVBoxLayout()
        left.setSpacing(4)
        right.setSpacing(4)
        columns.addLayout(left, 1)
        columns.addLayout(right, 1)
        self.buildIdentification(left)
        self.buildSummaries(right)

    def buildIdentification(self, layout):
        form = summaryForm(layout, "Identification")
        self.name = addRow(form, "Name", QLineEdit())
        self.location = addRow(form, "Location", QLineEdit())
        self.identityFields = {key: valueRow(form, key) for key in IDENTITY_FIELDS}
        applyCancelRow(layout, self.apply, lambda: self.load(None))
        layout.addStretch(1)

    def buildSummaries(self, layout):
        form = summaryForm(layout, "Network")
        self.networkFields = {key: valueRow(form, label) for key, label in NETWORK_FIELDS}
        form = summaryForm(layout, "Date and time")
        self.timeFields = {key: valueRow(form, label) for key, label in TIME_FIELDS}
        form = summaryForm(layout, "Media profiles")
        self.profilesField = valueRow(form, "Profiles")
        section(layout, "Web interface")
        self.webLinks = QHBoxLayout()
        self.webLinks.setSpacing(4)
        layout.addLayout(self.webLinks)
        layout.addStretch(1)

    def load(self, profile):
        self.run(self.gather, self.show)

    def gather(self):
        """Read every group in parallel; optional groups show as unavailable instead of failing the page."""
        device = self.device
        optional = (("network", device.networkSettings), ("time", device.timeSettings), ("profiles", device.profiles))
        with ThreadPoolExecutor(max_workers=len(optional) + 1) as pool:
            identity = pool.submit(device.identification)
            futures = {key: pool.submit(function) for key, function in optional}
            state = {"identification": identity.result()}
            for key, future in futures.items():
                try:
                    state[key] = future.result()
                except Exception:
                    state[key] = None  # the dedicated page reports the device error
        return state

    def show(self, state):
        self.showIdentification(state["identification"])
        unavailable = "unavailable"
        summary = networkSummary(state["network"]) if state["network"] else {}
        for key, label in self.networkFields.items():
            label.setText(summary.get(key, unavailable))
        self.showTime(state["time"], unavailable)
        profiles = state["profiles"]
        self.profilesField.setText("\n".join(f"{p['token']} · {p['name']} — {p['encoding']} {p['resolution']}" for p in profiles) if profiles else unavailable)
        self.showWebLinks(state["network"])
        self.present()
        self.workspace.loaded()

    def showIdentification(self, identity):
        self.workspace.identification = identity
        self.name.setText(identity["Name"])
        self.location.setText(identity["Location"])
        for key, label in self.identityFields.items():
            label.setText(identity.get(key, "") or "—")

    def showTime(self, clock, unavailable):
        if not clock:
            for label in self.timeFields.values():
                label.setText(unavailable)
            return
        local = clock["local"].strftime("%Y-%m-%d %H:%M:%S") if clock["local"] else "—"
        for key, value in (("local", local), ("mode", clock["mode"]), ("zone", clock["timeZone"] or "—")):
            self.timeFields[key].setText(value)

    def showWebLinks(self, network):
        while self.webLinks.count():
            item = self.webLinks.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        for url in webUrls(self.device.session.config.host, network):
            link = QPushButton(f"Open {url}")
            link.clicked.connect(lambda _, target=url: QDesktopServices.openUrl(QUrl(target)))
            self.webLinks.addWidget(link)
        self.webLinks.addStretch(1)

    def apply(self):
        old = self.workspace.identification
        name, location = self.name.text().strip(), self.location.text().strip()
        if (name, location) == (old["Name"], old["Location"]):
            return
        lines = [f"Name: {old['Name']} → {name}", f"Location: {old['Location']} → {location}"]
        if self.workspace.confirm("Change identification", lines):
            self.save(lambda: self.device.setIdentification(name, location), lambda: self.load(None))
