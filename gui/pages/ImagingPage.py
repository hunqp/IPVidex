"""Imaging settings of the selected profile's video source, beside its live view."""

from PyQt6.QtWidgets import QComboBox, QLabel
from gui.pages.DevicePage import DevicePage
from gui.pages.Forms import addRow, applyCancelRow, settingsAndVideo, sliderRow
from gui.pages.PreviewPanel import PreviewPanel

LABELS = {
    "Brightness": "Brightness",
    "ColorSaturation": "Color saturation",
    "Contrast": "Contrast",
    "Sharpness": "Sharpness",
    "IrCutFilter": "IR cut filter",
    "BacklightCompensation/Mode": "Backlight compensation",
    "WideDynamicRange/Mode": "Wide dynamic range",
    "WhiteBalance/Mode": "White balance",
    "Exposure/Mode": "Exposure",
    "Exposure/ExposureTime": "Exposure time (µs)",
    "Exposure/Gain": "Gain (dB)",
    "Exposure/Iris": "Iris",
    "WhiteBalance/CrGain": "Red gain (Cr)",
    "WhiteBalance/CbGain": "Blue gain (Cb)",
    "WideDynamicRange/Level": "WDR level",
    "BacklightCompensation/Level": "Backlight level",
}


def label(path):
    return LABELS.get(path, path)


class ImagingPage(DevicePage):
    ICON = "imaging"
    TITLE = "Image"
    USES_PROFILE = True

    def __init__(self, workspace):
        super().__init__(workspace)
        self.profile = None
        self.state = None
        self.widgets = {}
        self.form, settings, video = settingsAndVideo(self)
        self.panel = PreviewPanel(workspace, self)
        video.addWidget(self.panel, 1)
        applyCancelRow(settings, self.apply, lambda: self.load(self.profile))
        settings.addStretch(1)

    def load(self, profile):
        self.profile = profile
        self.run(lambda: self.device.imaging(profile["source"]), self.show)
        if not self.panel.running():
            self.panel.play(profile)  # keeps playing across Apply reloads

    def deactivate(self):
        self.panel.stop()

    def show(self, result):
        self.state = result
        while self.form.rowCount():
            self.form.removeRow(0)
        self.widgets = {}
        dependents = []
        for path, kind, data, value, parent, active in result[1]:
            if kind == "range":
                self.widgets[path] = self.addSlider(path, data, value)
                if parent:
                    dependents.append((self.widgets[path], parent, active))
            else:
                self.widgets[path] = self.addChoice(path, data, value)
        for slider, parent, active in dependents:
            self.followMode(slider, parent, active)
        if not result[1]:
            self.form.addRow(QLabel("No adjustable imaging setting."))
        self.present()
        self.workspace.loaded()

    def addSlider(self, path, bounds, value):
        slider, valueLabel = sliderRow(self.form, label(path))
        slider.setRange(*bounds)
        slider.setValue(value)
        valueLabel.setText(str(value))
        return slider

    def addChoice(self, path, choices, value):
        combo = QComboBox()
        combo.addItems(choices)
        combo.setCurrentText(value)
        return addRow(self.form, label(path), combo)

    def followMode(self, slider, parent, active):
        """Show a sub-parameter row only while its parent mode is one that enables it."""
        combo = self.widgets.get(parent)
        if combo is None:
            return
        holder = slider.parentWidget()
        name = self.form.labelForField(holder)

        def update(*_):
            visible = combo.currentText() in active
            holder.setVisible(visible)
            if name is not None:
                name.setVisible(visible)

        combo.currentTextChanged.connect(update)
        update()

    def apply(self):
        settings, fields = self.state
        values, changes = {}, []
        for path, kind, _, old, _, _ in fields:
            widget = self.widgets[path]
            if kind == "range" and not widget.isVisibleTo(self):
                continue  # sub-parameter whose mode is inactive (row hidden); do not push it
            new = widget.value() if kind == "range" else widget.currentText()
            if new != old:
                values[path] = new
                changes.append(f"{path}: {old} → {new}")
        if not changes or not self.workspace.confirm("Change imaging settings", changes):
            return
        profile = self.profile
        self.save(lambda: self.device.setImaging(profile["source"], settings, values), lambda: self.load(profile))
