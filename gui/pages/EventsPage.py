"""Device events through a WS-BaseNotification pull point."""

import threading
from PyQt6.QtCore import QThread, pyqtSignal
from PyQt6.QtWidgets import QHeaderView, QTableWidgetItem
from gui.OnvifTask import faultMessage
from gui.pages.DevicePage import DevicePage
from gui.pages.Forms import button, buttonRow, dataTable, pageLayout
from infrastructure.Onvif import OnvifFault
from services.OnvifDevice import OnvifDevice

MAX_EVENT_ROWS = 500
RETRY_SECONDS = 2
SUBSCRIPTION_LIFETIME = "PT600S"
PULL_TIMEOUT = "PT1S"


class EventWorker(QThread):
    """Poll a pull-point subscription until stopped; recreate it if the device drops it."""

    eventReceived = pyqtSignal(object)
    failed = pyqtSignal(str)

    def __init__(self, device, parent=None):
        super().__init__(parent)
        self.stopEvent = threading.Event()
        self.session = device.session.clone(self.stopEvent)

    def stop(self):
        self.stopEvent.set()

    def run(self):
        pull = None
        while not self.stopEvent.is_set():
            try:
                pull = pull or self.session.createPullPoint(termination=SUBSCRIPTION_LIFETIME)
                for message in self.session.pullMessages(pull, timeout=PULL_TIMEOUT):
                    self.eventReceived.emit(OnvifDevice.eventRow(message))
            except Exception as exc:
                if self.stopEvent.is_set():
                    break  # cancelled: keep `pull` so the subscription is released below
                self.failed.emit(faultMessage(exc) if isinstance(exc, OnvifFault) else str(exc) or type(exc).__name__)
                pull = None
                self.stopEvent.wait(RETRY_SECONDS)
        if pull is not None:
            # The polling transport is cancelled by now; release the device slot on a fresh one.
            self.session.clone(threading.Event()).unsubscribe(pull)


class EventsPage(DevicePage):
    ICON = "events"
    TITLE = "Events"

    def __init__(self, workspace):
        super().__init__(workspace)
        self.worker = None
        layout = pageLayout(self)
        self.table = dataTable(4)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.table.setWordWrap(False)
        layout.addWidget(self.table, 1)
        self.toggleButton = button("Stop", self.toggle, primary=True)
        buttonRow(layout, self.toggleButton, button("Clear", lambda: self.table.setRowCount(0)))

    def load(self, profile):
        self.table.setHorizontalHeaderLabels(["Time", "Topic", "Source", "Data"])
        self.present()
        self.start()

    def deactivate(self):
        self.stop()

    def start(self):
        self.stop()
        self.worker = EventWorker(self.device, self)
        self.worker.eventReceived.connect(self.addEvent)
        self.worker.failed.connect(self.workspace.deviceError)
        self.worker.start()
        self.toggleButton.setText("Stop")
        self.workspace.setStatus("Listening for events (pull point)…")

    def stop(self):
        """Never block the UI on network I/O: the thread stays owned until it has really exited."""
        worker, self.worker = self.worker, None
        if worker is not None:
            worker.stop()
            worker.eventReceived.disconnect()
            worker.failed.disconnect()
            worker.finished.connect(worker.deleteLater)
        self.toggleButton.setText("Start")

    def toggle(self):
        if self.worker is not None:
            self.stop()
            self.workspace.setStatus("Event listening stopped.")
        else:
            self.start()

    def addEvent(self, row):
        self.table.insertRow(0)
        for column, value in enumerate(row):
            item = QTableWidgetItem(value)
            item.setToolTip(value)
            self.table.setItem(0, column, item)
        if self.table.rowCount() > MAX_EVENT_ROWS:
            self.table.removeRow(self.table.rowCount() - 1)
