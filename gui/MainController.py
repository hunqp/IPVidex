"""Main window: device discovery, RTSP Live and the managed media servers; no camera I/O on the GUI thread."""

from PyQt6 import uic
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QIcon, QPixmap
from PyQt6.QtWidgets import QDialog, QLabel, QMainWindow, QPushButton, QTabBar, QVBoxLayout, QWidget
from core.Paths import ROOT
from gui.AboutDialog import AboutDialog
from gui.Appearance import applyTheme
from gui.DiscoveryHub import DiscoveryHub
from gui.MediaServerTab import RtmpServerTab, WebRtcServerTab
from gui.RtspTab import RtspTab

TITLE = "IPVidex"
SUBTITLE = "IP Video Protocol Utility"
SETTINGS_TITLE = "Settings"
SETTINGS_DIALOG_SIZE = (520, 140)
BRAND_MARK_HEIGHT = 34


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        uic.loadUi(str(ROOT / "main.ui"), self)
        self.setWindowIcon(QIcon(str(ROOT / "assets" / "IPVidex.ico")))
        self.setWindowTitle(f"{TITLE} — {SUBTITLE}")
        self.buildBrand()
        self.buildSettingsDialog()
        self.aboutButton = QPushButton(self)
        self.aboutButton.setToolTip("About")
        self.aboutButton.clicked.connect(lambda: AboutDialog(self).exec())
        self.headerLayout.insertWidget(self.headerLayout.indexOf(self.settingsButton), self.aboutButton)
        self.rtsp = RtspTab(self)
        self.discoveryHub = DiscoveryHub(self)
        self.discoveryTab.layout().addWidget(self.discoveryHub)
        self.rtmpTab, self.webrtcTab = RtmpServerTab(self), WebRtcServerTab(self)
        self.buildTabs()
        self.rtsp.restoreSettings()
        applyTheme(self)

    def buildBrand(self):
        mark = QLabel()
        mark.setPixmap(QPixmap(str(ROOT / "assets" / "IPVidex-mark.png")).scaledToHeight(BRAND_MARK_HEIGHT, Qt.TransformationMode.SmoothTransformation))
        mark.setFixedSize(38, BRAND_MARK_HEIGHT)
        brand = QWidget()
        column = QVBoxLayout(brand)
        column.setContentsMargins(2, 0, 0, 0)
        column.setSpacing(0)
        for name, text in (("brandTitle", TITLE), ("brandSubtitle", SUBTITLE)):
            label = QLabel(text)
            label.setObjectName(name)
            column.addWidget(label)
        self.headerLayout.insertWidget(0, mark)
        self.headerLayout.insertWidget(1, brand)
        self.headerLayout.insertStretch(2, 1)

    def buildSettingsDialog(self):
        self.settingsDialog = QDialog(self)
        self.settingsDialog.setWindowTitle(SETTINGS_TITLE)
        QVBoxLayout(self.settingsDialog).addWidget(self.advancedContent)
        self.settingsDialog.resize(*SETTINGS_DIALOG_SIZE)
        self.settingsButton.setToolTip(SETTINGS_TITLE)
        self.settingsButton.clicked.connect(lambda: self.settingsDialog.exec())

    def buildTabs(self):
        """Discovery, RTSP, RTMP and P2P are fixed; only device workspace tabs can be closed."""
        self.tabs.insertTab(2, self.rtmpTab, "RTMP")
        self.tabs.insertTab(3, self.webrtcTab, "P2P")
        self.tabs.setTabsClosable(True)
        bar = self.tabs.tabBar()
        for index in range(self.tabs.count()):
            for side in (QTabBar.ButtonPosition.LeftSide, QTabBar.ButtonPosition.RightSide):
                bar.setTabButton(index, side, None)
        self.tabs.currentChanged.connect(self.rtsp.tabChanged)

    def closeEvent(self, event):
        if self.rtsp.running():
            self.rtsp.stop()
        self.rtsp.saveSettings()
        self.rtmpTab.shutdown()
        self.webrtcTab.shutdown()
        if self.discoveryHub.shutdown():
            event.accept()
        else:
            event.ignore()
