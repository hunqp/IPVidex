"""Media profiles: list, create with the first compatible source and encoder, delete."""

from PyQt6.QtWidgets import QInputDialog
from gui.pages.DevicePage import DevicePage
from gui.pages.Forms import button, buttonRow, dataTable, fillTable, pageLayout, selectedRecord

HEADERS = ("Token", "Name", "Fixed", "Encoder", "Resolution")


def profileCells(profile):
    return profile["token"], profile["name"], "✓" if profile["fixed"] else "", profile["encoding"], profile["resolution"]


class ProfilesPage(DevicePage):
    ICON = "profiles"
    TITLE = "Profiles"

    def __init__(self, workspace):
        super().__init__(workspace)
        layout = pageLayout(self)
        self.table = dataTable(len(HEADERS))
        layout.addWidget(self.table, 1)
        buttonRow(layout, button("New profile", self.create), button("Delete profile", self.delete))

    def load(self, profile):
        self.run(self.device.profiles, self.show)

    def show(self, profiles):
        self.workspace.setProfiles(profiles)
        self.table.setHorizontalHeaderLabels(list(HEADERS))
        fillTable(self.table, profiles, profileCells, centered=(0, 2, 3, 4))
        self.present()
        self.workspace.loaded()

    def create(self):
        name, accepted = QInputDialog.getText(self, "New profile", "Profile name")
        name = name.strip()
        if not accepted or not name:
            return
        question = f"Create profile '{name}' with the first compatible video source and encoder?"
        if self.workspace.confirm("Create media profile", [question]):
            self.run(lambda: self.device.createProfile(name), lambda _: self.load(None), "Creating…")

    def delete(self):
        profile = selectedRecord(self.table)
        if not profile:
            return
        if profile["fixed"]:
            self.workspace.warn("Fixed profiles cannot be deleted.")
            return
        question = f"Delete profile {profile['token']} ({profile['name']})? This cannot be undone."
        if self.workspace.confirm("Delete media profile", [question]):
            self.run(lambda: self.device.deleteProfile(profile["token"]), lambda _: self.load(None), "Deleting…")
