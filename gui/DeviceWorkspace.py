"""One authenticated device: toolbar, page navigation, background calls and status line."""

from PyQt6.QtCore import QSize, Qt
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import QComboBox, QFrame, QHBoxLayout, QInputDialog, QLabel, QMessageBox, QStackedWidget, QTabBar, QVBoxLayout, QWidget
from core.Paths import ICONS
from gui.BusySpinner import statusRow
from gui.OnvifTask import OnvifTask
from gui.pages.CertificatesPage import CertificatesPage
from gui.pages.DevicePage import LOADING
from gui.pages.EventsPage import EventsPage
from gui.pages.ImagingPage import ImagingPage
from gui.pages.LivePage import LivePage
from gui.pages.MaintenancePage import MaintenancePage
from gui.pages.NetworkPage import NetworkPage
from gui.pages.OverviewPage import OverviewPage
from gui.pages.ProfilesPage import ProfilesPage
from gui.pages.PtzPage import PtzPage
from gui.pages.TimePage import TimePage
from gui.pages.UsersPage import UsersPage
from gui.pages.VideoPage import VideoPage

PAGES = (OverviewPage, LivePage, VideoPage, ImagingPage, PtzPage, ProfilesPage, NetworkPage, TimePage, UsersPage, CertificatesPage, EventsPage, MaintenancePage)
PROFILE_COMBO_WIDTH = 250
NO_FRAMES_HINT = (
    " — the device accepted PLAY but sent no video. Its RTSP server may not stream this channel's"
    " codec (e.g. H.265 announced as H264) or its session limit is reached."
)


class DeviceWorkspace(QWidget):
    def __init__(self, parent, device, state):
        super().__init__(parent)
        self.device = device
        self.identification, self.profiles = state["identification"], state["profiles"]
        self.disposed = False
        self.generation = 0
        self.tasks, self.busyTasks, self.openingPreviews = set(), set(), set()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)
        layout.addLayout(self.buildToolbar())
        self.navBar = self.buildNavigation()
        layout.addWidget(self.navBar)
        layout.addWidget(self.buildContent(), 1)
        self.status = QLabel()
        self.status.setObjectName("discoveryStatus")
        self.status.setWordWrap(True)
        layout.addWidget(statusRow(self.status))
        self.pages = [page(self) for page in PAGES]
        for page in self.pages:
            self.stack.addWidget(page)
            self.navBar.addTab(QIcon(str(ICONS / f"{page.ICON}.svg")), page.TITLE)
        self.navBar.currentChanged.connect(self.navigate)
        self.renderConnection()
        self.renderProfilePicker()

    # ---- construction -----------------------------------------------------------
    def buildToolbar(self):
        toolbar = QHBoxLayout()
        toolbar.setSpacing(4)
        self.profileLabel = QLabel("Profile")
        self.profileCombo = QComboBox()
        self.profileCombo.setMinimumWidth(PROFILE_COMBO_WIDTH)
        self.profileCombo.currentIndexChanged.connect(self.profileChanged)
        self.connectionLabel = QLabel()
        self.connectionLabel.setObjectName("discoveryConnection")
        toolbar.addWidget(self.profileLabel)
        toolbar.addWidget(self.profileCombo)
        toolbar.addStretch(1)
        toolbar.addWidget(self.connectionLabel)
        return toolbar

    def buildNavigation(self):
        navBar = QTabBar()
        navBar.setObjectName("discoveryNav")
        navBar.setDrawBase(False)
        navBar.setExpanding(False)
        navBar.setIconSize(QSize(16, 16))
        return navBar

    def buildContent(self):
        content = QFrame()
        content.setObjectName("discoveryPanel")
        box = QVBoxLayout(content)
        box.setContentsMargins(10, 8, 10, 8)
        self.stack = QStackedWidget()
        box.addWidget(self.stack)
        self.emptyPage = QLabel("The device reports no media profile.")
        self.emptyPage.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.stack.addWidget(self.emptyPage)
        return content

    # ---- navigation -------------------------------------------------------------
    def showEvent(self, event):
        super().showEvent(event)
        if not self.disposed:
            self.navigate(self.navBar.currentIndex())

    def hideEvent(self, event):
        self.stopActivity()
        super().hideEvent(event)

    def navigate(self, index):
        if self.disposed or not 0 <= index < len(self.pages):
            return
        page = self.pages[index]
        self.profileLabel.setVisible(page.USES_PROFILE)
        self.profileCombo.setVisible(page.USES_PROFILE)
        self.stopActivity()
        profile = self.profileCombo.currentData() if page.USES_PROFILE else None
        if page.USES_PROFILE and profile is None:
            self.stack.setCurrentWidget(self.emptyPage)
            self.setStatus("")
            return
        page.load(profile)

    def profileChanged(self, *args):
        if self.pages[self.navBar.currentIndex()].USES_PROFILE:
            self.navigate(self.navBar.currentIndex())

    def stopActivity(self):
        """Invalidate pending results and stop previews and event polling."""
        self.generation += 1
        for page in self.pages:
            page.deactivate()

    def dispose(self):
        self.disposed = True
        self.stopActivity()
        self.device.session.transport.stop.set()
        self.device.session.config.password = ""

    # ---- profiles and identity ---------------------------------------------------
    def setProfiles(self, profiles):
        self.profiles = profiles
        self.renderProfilePicker()

    def refreshProfiles(self):
        self.runTask(self.device.profiles, self.setProfiles)

    def renderProfilePicker(self):
        current = self.profileCombo.currentData()
        self.profileCombo.blockSignals(True)
        self.profileCombo.clear()
        for profile in self.profiles:
            self.profileCombo.addItem(f"{profile['token']} · {profile['name']} — {profile['resolution']}", profile)
        tokens = [profile["token"] for profile in self.profiles]
        if current and current["token"] in tokens:
            self.profileCombo.setCurrentIndex(tokens.index(current["token"]))
        self.profileCombo.blockSignals(False)

    def renderConnection(self):
        identity, host = self.identification, self.device.session.config.host
        firmware = identity.get("Firmware version")
        parts = (identity.get("Name") or host, identity.get("Model", ""), f"FW {firmware}" if firmware else "", host)
        self.connectionLabel.setText("<span style='color:#2DA44E'>●</span>&nbsp;&nbsp;" + "  ·  ".join(p for p in parts if p))

    def deviceName(self):
        return self.identification.get("Name") or self.device.session.config.host

    # ---- background calls ---------------------------------------------------------
    def runTask(self, function, done=None, busyText=None, failed=None, quiet=False):
        """Run a device call off the GUI thread; results arriving after navigation are dropped.
        quiet tasks (PTZ moves) neither show the busy indicator nor change the status line."""
        if self.disposed:
            return
        generation = self.generation

        def current():
            return not self.disposed and generation == self.generation

        task = OnvifTask(function, self)
        self.tasks.add(task)
        task.succeeded.connect(lambda value: done(value) if done and current() else None)
        task.failed.connect(lambda message: (failed or self.deviceError)(message) if current() else None)
        task.finished.connect(lambda: self.taskFinished(task))
        if not quiet:
            self.busyTasks.add(task)
            self.updateBusy()
            if busyText or not self.status.text():
                self.setStatus(busyText or LOADING)
        task.start()

    def taskFinished(self, task):
        self.tasks.discard(task)
        self.busyTasks.discard(task)
        self.updateBusy()
        task.deleteLater()

    def updateBusy(self):
        self.status.busySpinner.setBusy(bool(self.busyTasks) or bool(self.openingPreviews))

    # ---- previews ----------------------------------------------------------------
    def registerPreview(self, preview):
        preview.stateChanged.connect(lambda state, error: self.previewState(preview, state, error))

    def previewState(self, preview, state, error):
        if state == "opening":
            self.openingPreviews.add(preview)
        else:
            self.openingPreviews.discard(preview)
        self.updateBusy()
        texts = {
            "opening": "Opening stream…",
            "playing": "Live — no recording",
            "stopped": "Stream stopped.",
            "error": "Stream error" + (f" [{error}]" if error else "") + (NO_FRAMES_HINT if error == "NO_FRAMES" else ""),
        }
        self.setStatus(texts.get(state, state))

    # ---- status and dialogs --------------------------------------------------------
    def setStatus(self, text):
        self.status.setText(text)

    def loaded(self):
        """Clear only the loading notice so a preceding "Saved." stays visible."""
        if self.status.text() == LOADING:
            self.status.clear()

    def deviceError(self, message):
        self.setStatus("Device error: " + message)

    def warn(self, message):
        QMessageBox.warning(self, "Warning", message)

    def confirm(self, title, lines):
        buttons = QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        answer = QMessageBox.question(self, title, "\n".join(lines), buttons, QMessageBox.StandardButton.No)
        return answer == QMessageBox.StandardButton.Yes

    def confirmTyped(self, title, lines, word):
        """Destructive actions: the operator must type a confirmation word."""
        prompt = "\n".join(lines) + "\n\n" + f"Type {word} to continue:"
        value, accepted = QInputDialog.getText(self, title, prompt)
        return accepted and value.strip() == word
