"""Thread lifecycle and stale-callback regression tests, no device or writes."""

import os
import sys
import threading
import time
from pathlib import Path

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from PyQt6.QtCore import QThread  # noqa: E402
from PyQt6.QtWidgets import QApplication  # noqa: E402
from core.Models import Config  # noqa: E402
from gui.DeviceWorkspace import DeviceWorkspace  # noqa: E402
from gui.MainController import MainWindow  # noqa: E402
from gui.pages.EventsPage import EventsPage, EventWorker  # noqa: E402
from infrastructure.Network import Transport  # noqa: E402
from infrastructure.Onvif import OnvifSession  # noqa: E402
from services.OnvifDevice import OnvifDevice  # noqa: E402


def pump(app, seconds=1.0):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        app.processEvents()
        time.sleep(0.01)


app = QApplication([])
window = MainWindow()
config = Config("127.0.0.1")
device = OnvifDevice(OnvifSession(config, Transport(config, threading.Event())))
workspace = DeviceWorkspace(window.tabs, device, {"identification": {"Name": "Test", "Location": ""}, "profiles": []})

# A result that arrives after the operator navigated away is dropped.
results = []
workspace.runTask(lambda: (time.sleep(0.12), "old")[1], results.append)
workspace.stopActivity()
pump(app)
assert results == [], results

# A worker whose shutdown takes longer than the UI event stays owned and alive
# while EventsPage.stop() returns immediately.
events = next(page for page in workspace.pages if isinstance(page, EventsPage))
worker = EventWorker(device, events)
worker.run = lambda: time.sleep(0.25)
worker.eventReceived.connect(lambda row: None)
worker.failed.connect(lambda message: None)
events.worker = worker
worker.start()
started = time.monotonic()
events.stop()
assert time.monotonic() - started < 0.1
assert worker.isRunning()

workspace.dispose()
window.discoveryHub.retire(workspace)
pump(app)
assert not any(thread.isRunning() for thread in window.findChildren(QThread))
window.close()
print("PASS: stale UI results ignored, non-blocking Events stop, thread retained until exit")
