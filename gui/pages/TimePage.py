"""Device date and time: NTP, manual UTC, or synchronized with this computer."""

import datetime
from PyQt6.QtCore import QDate, QDateTime, QTime, QTimeZone
from PyQt6.QtWidgets import QCheckBox, QDateTimeEdit, QLabel, QLineEdit, QRadioButton, QVBoxLayout, QWidget
from gui.pages.DevicePage import DevicePage
from gui.pages.Forms import addRow, applyCancelRow, formLayout, pageLayout

STAMP = "%Y-%m-%d %H:%M:%S"


def formatStamp(value):
    return value.strftime(STAMP) if value else "—"


class TimePage(DevicePage):
    ICON = "time"
    TITLE = "Time"

    def __init__(self, workspace):
        super().__init__(workspace)
        self.state = None
        layout = pageLayout(self)
        form = formLayout()
        layout.addLayout(form)
        self.utc = addRow(form, "Device time (UTC)", QLabel())
        self.local = addRow(form, "Device time (local)", QLabel())
        self.zone = addRow(form, "Time zone (POSIX)", QLineEdit())
        self.zone.setPlaceholderText("e.g. <+07>-7 for UTC+7")
        self.daylight = addRow(form, "Daylight saving", QCheckBox())
        addRow(form, "Mode", self.buildModes())
        self.edit = addRow(form, "UTC date and time", QDateTimeEdit())
        self.edit.setDisplayFormat("yyyy-MM-dd HH:mm:ss")
        self.edit.setTimeZone(QTimeZone.utc())
        self.manual.toggled.connect(self.edit.setEnabled)
        applyCancelRow(layout, self.apply, lambda: self.load(None))
        layout.addStretch(1)

    def buildModes(self):
        modes = QWidget()
        box = QVBoxLayout(modes)
        box.setContentsMargins(0, 0, 0, 0)
        self.ntp = QRadioButton("Synchronize with NTP")
        self.manual = QRadioButton("Set manually (UTC)")
        self.computer = QRadioButton("Synchronize with this computer")
        for button in (self.ntp, self.manual, self.computer):
            box.addWidget(button)
        return modes

    def load(self, profile):
        self.run(self.device.timeSettings, self.show)

    def show(self, state):
        self.state = state
        self.utc.setText(formatStamp(state["utc"]))
        self.local.setText(formatStamp(state["local"]))
        self.zone.setText(state["timeZone"])
        self.daylight.setChecked(state["daylight"])
        (self.ntp if state["mode"] == "NTP" else self.manual).setChecked(True)
        utc = state["utc"] or datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)
        self.edit.setDateTime(QDateTime(QDate(utc.year, utc.month, utc.day), QTime(utc.hour, utc.minute, utc.second), QTimeZone.utc()))
        self.edit.setEnabled(self.manual.isChecked())
        self.present()
        self.workspace.loaded()

    def chosenMode(self):
        """(mode, utc to set or None, description) from the radio buttons."""
        if self.ntp.isChecked():
            return "NTP", None, "NTP"
        if self.computer.isChecked():
            return "Manual", datetime.datetime.now(datetime.timezone.utc), "this computer's time"
        value = self.edit.dateTime().toUTC()
        date, time = value.date(), value.time()
        utc = datetime.datetime(date.year(), date.month(), date.day(), time.hour(), time.minute(), time.second())
        return "Manual", utc, utc.strftime(STAMP + " UTC")

    def apply(self):
        old = self.state
        zone = self.zone.text().strip()
        # Devices may report a display form they cannot parse back, so the zone is only sent when changed.
        timeZone = zone if zone != old["timeZone"] else None
        daylight = self.daylight.isChecked()
        mode, utc, label = self.chosenMode()
        lines = [f"Mode: {old['mode']} → {mode} ({label})", f"Daylight saving: {old['daylight']} → {daylight}"]
        if timeZone is not None:
            lines.append(f"Time zone: {old['timeZone']} → {timeZone}")
        if self.workspace.confirm("Change date and time", lines):
            self.save(lambda: self.device.setTime(mode, daylight, timeZone, utc), lambda: self.load(None))
