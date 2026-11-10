"""Base class of one navigation page inside a device workspace."""

from PyQt6.QtWidgets import QWidget

LOADING = "Loading…"


class DevicePage(QWidget):
    ICON = ""
    TITLE = ""
    USES_PROFILE = False

    def __init__(self, workspace):
        super().__init__(workspace.stack)
        self.workspace = workspace

    @property
    def device(self):
        return self.workspace.device

    def load(self, profile):
        raise NotImplementedError

    def deactivate(self):
        """Stop live activity (video, event polling) when the page or the device is left."""

    def present(self):
        self.workspace.stack.setCurrentWidget(self)

    def run(self, function, done, busyText=None):
        self.workspace.runTask(function, done, busyText or LOADING)

    def save(self, function, reload):
        """Run a device write, then reload the page and report success."""

        def saved(_):
            reload()
            self.workspace.setStatus("Saved.")

        self.workspace.runTask(function, saved, "Saving…")
