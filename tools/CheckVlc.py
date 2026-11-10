"""Native rendering smoke check with generated video/audio, no camera required."""

import json
from pathlib import Path
import sys
import tempfile
import av
import numpy as np
from PyQt6.QtWidgets import QApplication, QLabel
from PyQt6.QtCore import QProcess, QTimer

root = Path(__file__).resolve().parent.parent
app = QApplication([])
label = QLabel()
label.resize(640, 360)
label.show()
with tempfile.TemporaryDirectory() as folder:
    path = Path(folder) / "sample.mp4"
    with av.open(str(path), "w") as output:
        video = output.add_stream("libx265" if "--hevc" in sys.argv else "mpeg4", rate=30)
        if "--hevc" in sys.argv:
            video.options = {"preset": "ultrafast", "x265-params": "log-level=error"}
        video.width, video.height, video.pix_fmt = 640, 360, "yuv420p"
        audio = output.add_stream("aac", rate=48000)
        audio.layout = "mono"
        for index in range(240):
            pixels = np.zeros((360, 640, 3), dtype=np.uint8)
            pixels[:, (index * 5) % 600 : (index * 5) % 600 + 40, 1] = 220
            frame = av.VideoFrame.from_ndarray(pixels, format="rgb24")
            for packet in video.encode(frame):
                output.mux(packet)
            sound = av.AudioFrame.from_ndarray(np.zeros((1, 1600), dtype=np.float32), format="flt", layout="mono")
            sound.sample_rate = 48000
            for packet in audio.encode(sound):
                output.mux(packet)
        for stream in (video, audio):
            for packet in stream.encode(None):
                output.mux(packet)
    process = QProcess()
    process.setWorkingDirectory(str(root))
    code = (
        "from infrastructure import Media, Network; Media.pinnedUrl=lambda *args: "
        + repr(str(path))
        + "; Network.Transport.resolve=lambda self: setattr(self,'address','127.0.0.1'); from infrastructure.VlcProcess import main; raise SystemExit(main())"
    )
    process.start(sys.executable, ["-c", code])
    assert process.waitForStarted()
    process.write(
        json.dumps(
            dict(host="127.0.0.1", port=554, path="/test", timeout=2, hwnd=int(label.winId()), volume=0, softwareDecode="--software" in sys.argv)
        ).encode()
        + b"\n"
    )
    QTimer.singleShot(4000, app.quit)
    app.exec()
    output = bytes(process.readAllStandardOutput()).decode()
    process.write(b'{"stop":true}\n')
    if not process.waitForFinished(3000):
        process.kill()
        process.waitForFinished()
    print(output)
    packets = [json.loads(line) for line in output.splitlines()]
    assert any(p.get("state") == "playing" for p in packets)
    assert any(p.get("metadata", {}).get("audio") for p in packets)
    assert any(p.get("metadata", {}).get("measuredFps", 0) > 10 for p in packets)
    assert not any("error" in p for p in packets)
    print("PASS: native video above 10 FPS and decoded audio track")
