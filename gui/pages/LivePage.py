"""Live view of the selected media profile."""

from gui.pages.DevicePage import DevicePage
from gui.pages.Forms import pageLayout
from gui.pages.PreviewPanel import PreviewPanel


class LivePage(DevicePage):
    ICON = "live"
    TITLE = "Live"
    USES_PROFILE = True

    def __init__(self, workspace):
        super().__init__(workspace)
        self.panel = PreviewPanel(workspace, self)
        pageLayout(self).addWidget(self.panel, 1)

    def load(self, profile):
        self.present()
        self.panel.play(profile)

    def deactivate(self):
        self.panel.stop()
