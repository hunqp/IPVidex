"""Video encoder settings of the selected profile, beside its live view."""

from PyQt6.QtWidgets import QComboBox
from gui.pages.DevicePage import DevicePage
from gui.pages.Forms import addRow, applyCancelRow, numberBox, settingsAndVideo, sliderRow
from gui.pages.PreviewPanel import PreviewPanel

DEFAULT_RANGES = {"fps": (1, 120), "interval": (1, 1), "bitrate": (16, 65535), "gov": (1, 1000), "quality": (0, 100)}


class VideoPage(DevicePage):
    ICON = "streaming"
    TITLE = "Video"
    USES_PROFILE = True

    def __init__(self, workspace):
        super().__init__(workspace)
        self.profile = None
        self.encoderState = None
        form, settings, video = settingsAndVideo(self)
        self.panel = PreviewPanel(workspace, self)
        video.addWidget(self.panel, 1)
        self.resolution = addRow(form, "Encoder and resolution", QComboBox())
        self.fps = addRow(form, "Frame rate, fps", numberBox())
        self.interval, self.intervalValue = sliderRow(form, "Encoding interval")
        self.bitrate = addRow(form, "Bitrate limit, kbps", numberBox())
        self.quality, self.qualityValue = sliderRow(form, "Quality")
        self.gov = addRow(form, "GOV length", numberBox())
        self.resolution.currentIndexChanged.connect(self.encodingChanged)
        applyCancelRow(settings, self.apply, lambda: self.load(self.profile))
        settings.addStretch(1)

    def load(self, profile):
        self.profile = profile
        self.run(lambda: self.device.encoder(profile["vec"], profile["token"]), self.show)

    def deactivate(self):
        self.panel.stop()

    def show(self, result):
        _, options, values = self.encoderState = result
        self.fillResolutions(options, values)
        self.quality.setRange(*(options["quality"] or DEFAULT_RANGES["quality"]))
        self.quality.setValue(values["quality"])
        self.encodingChanged()
        self.fps.setValue(values["fps"])
        self.interval.setValue(values["interval"])
        self.bitrate.setValue(values["bitrate"])
        self.gov.setValue(values["gov"])
        self.qualityValue.setText(str(values["quality"]))
        self.intervalValue.setText(str(values["interval"]))
        self.present()
        self.panel.play(self.profile)

    def fillResolutions(self, options, values):
        """Every encoding × resolution the device offers, plus the current one if it is not listed."""
        self.resolution.blockSignals(True)
        self.resolution.clear()
        for encoding, spec in options["encodings"].items():
            for width, height in spec["resolutions"]:
                self.resolution.addItem(f"{encoding}  {width}×{height}", (encoding, width, height))
        current = (values["encoding"], values["width"], values["height"])
        if self.resolution.findData(current) < 0:
            self.resolution.addItem(f"{current[0]}  {current[1]}×{current[2]}", current)
        self.resolution.setCurrentIndex(self.resolution.findData(current))
        self.resolution.blockSignals(False)

    def encodingChanged(self, *args):
        data = self.resolution.currentData()
        if not data or not self.encoderState:
            return
        spec = self.encoderState[1]["encodings"].get(data[0], {})
        self.fps.setRange(*(spec.get("fps") or DEFAULT_RANGES["fps"]))
        self.interval.setRange(*(spec.get("interval") or DEFAULT_RANGES["interval"]))
        self.bitrate.setRange(*(spec.get("bitrate") or DEFAULT_RANGES["bitrate"]))
        self.gov.setEnabled(bool(spec.get("gov")))
        self.gov.setRange(*(spec.get("gov") or DEFAULT_RANGES["gov"]))

    def apply(self):
        config, _, old = self.encoderState
        encoding, width, height = self.resolution.currentData()
        new = dict(
            old,
            encoding=encoding,
            width=width,
            height=height,
            fps=self.fps.value(),
            interval=self.interval.value(),
            bitrate=self.bitrate.value(),
            quality=self.quality.value(),
            gov=self.gov.value(),
        )
        changes = [f"{key}: {old[key]} → {new[key]}" for key in new if new[key] != old[key]]
        if not changes or not self.workspace.confirm("Change video encoder", changes):
            return
        self.panel.stop()
        profile = self.profile

        def reload():
            self.workspace.refreshProfiles()
            self.load(profile)

        self.save(lambda: self.device.setEncoder(config, new), reload)
