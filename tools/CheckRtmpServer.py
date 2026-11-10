"""Integration check: managed RTMP server, publish, external read, statistics, shutdown."""

import os

os.environ["QT_QPA_PLATFORM"] = "offscreen"
import sys
import socket
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import av
import numpy as np
from PyQt6.QtWidgets import QApplication
from gui.MediaServerTab import RtmpServerTab

app = QApplication([])
tab = RtmpServerTab()
tab.address.setCurrentIndex(tab.address.findData("127.0.0.1"))
with socket.socket() as probe:
    probe.bind(("127.0.0.1", 0))
    port = probe.getsockname()[1]
tab.port.setValue(port)
tab.start()


def pumpUntil(predicate, seconds=8):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        app.processEvents()
        if predicate():
            return
        time.sleep(0.02)
    raise AssertionError(tab.status.text() + "\n" + tab.logs.toPlainText())


pumpUntil(lambda: tab.status.text().startswith("Listening"))
stop = threading.Event()
errors = []
url = tab.url.text().replace("${key}", "camera1")


def publish():
    try:
        with av.open(url, "w", format="flv") as output:
            stream = output.add_stream("libx264", rate=20)
            stream.width = 320
            stream.height = 180
            stream.pix_fmt = "yuv420p"
            stream.options = {"preset": "ultrafast", "tune": "zerolatency", "g": "20"}
            index = 0
            while not stop.is_set():
                pixels = np.zeros((180, 320, 3), dtype=np.uint8)
                pixels[:, index % 280 : index % 280 + 40, 1] = 220
                frame = av.VideoFrame.from_ndarray(pixels, format="rgb24")
                frame.pts = index
                for packet in stream.encode(frame):
                    output.mux(packet)
                index += 1
                time.sleep(0.05)
            for packet in stream.encode(None):
                output.mux(packet)
    except Exception as exc:
        errors.append(type(exc).__name__)


thread = threading.Thread(target=publish, daemon=True)
thread.start()
try:
    pumpUntil(lambda: tab.table.rowCount() > 0 and any(tab.table.item(row, 1).text() == "publish" for row in range(tab.table.rowCount())))
    pumpUntil(lambda: any(float(tab.table.item(row, 4).text().split()[0]) > 0 for row in range(tab.table.rowCount())))
    readerResult = []

    def read():
        try:
            with av.open(url, timeout=(3, 3)) as reader:
                for packet in reader.demux(video=0):
                    if packet.size:
                        readerResult.append(packet.size)
                        break
        except Exception as exc:
            errors.append(type(exc).__name__)

    reader = threading.Thread(target=read, daemon=True)
    reader.start()
    pumpUntil(lambda: bool(readerResult) or bool(errors), seconds=10)
    assert readerResult and not errors, errors
finally:
    stop.set()
    thread.join(3)
    tab.stop()
    pumpUntil(lambda: tab.process is None)
assert not errors, errors
assert tab.temporary is None
with socket.socket() as probe:
    probe.settimeout(0.3)
    assert probe.connect_ex(("127.0.0.1", port)) != 0
print("PASS: RTMP publish + external read, receive rate, process and port cleanup")
