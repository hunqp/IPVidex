"""Glass-to-glass latency of the native player, no camera required (needs a real display).

A local MediaMTX RTSP server receives a camera-like stream (H.264 without B-frames
plus G.711 audio). Every frame carries its send time as 32 black/white blocks
(24 bits of milliseconds + 8 check bits). The real VlcProcess worker plays it into
a window; screen captures of that window are decoded and compared with the clock.
A direct FFmpeg (PyAV) decode of the same stream gives the floor of the test chain
(encoder, server, loopback and decoder) for comparison.

Usage: python tools/CheckLatency.py [--variants]
"""

import json
import socket
import statistics
import sys
import tempfile
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import av  # noqa: E402
import numpy as np  # noqa: E402
from PyQt6.QtCore import QProcess, QProcessEnvironment, Qt  # noqa: E402
from PyQt6.QtGui import QImage  # noqa: E402
from PyQt6.QtWidgets import QApplication, QLabel  # noqa: E402
from infrastructure.MediaMtx import BINARY, baseConfig  # noqa: E402

WIDTH, HEIGHT, FPS = 640, 360, 25
AUDIO_RATE = 8000
BITS, DATA_BITS = 32, 24
BAND_HEIGHT = 60
WARMUP_SECONDS, SAMPLE_SECONDS = 4, 8
CAPTURE_MS = 20
MAX_PLAUSIBLE_MS = 10000
ROOT = Path(__file__).resolve().parent.parent
STREAM_PATH = "/live/test"
# name: media options appended by the test; a :network-caching here replaces the app's value.
VARIANTS = {
    "VLC, app settings": (),
    "VLC, caching 300 (previous)": (":network-caching=300",),
    "VLC, caching 50": (":network-caching=50",),
}


def freePort():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def checksum(value):
    return (value + (value >> 8) + (value >> 16)) & 0xFF


def stamp(value):
    """Frame whose top band encodes value (24 bits) and its checksum (8 bits)."""
    word = value | checksum(value) << DATA_BITS
    pixels = np.full((HEIGHT, WIDTH, 3), 64, dtype=np.uint8)
    block = WIDTH // BITS
    for bit in range(BITS):
        pixels[:BAND_HEIGHT, bit * block : (bit + 1) * block] = 235 if word >> bit & 1 else 16
    return pixels


def readStamp(image):
    block, row = image.width() / BITS, int(image.height() * BAND_HEIGHT / HEIGHT / 2)
    word = sum(1 << bit for bit in range(BITS) if image.pixelColor(int((bit + 0.5) * block), row).lightness() > 128)
    value = word & 0xFFFFFF
    return value if word >> DATA_BITS == checksum(value) else None


def nowMs():
    return int(time.monotonic() * 1000) & 0xFFFFFF


def age(image):
    """Milliseconds since the frame shown in image was sent, or None when unreadable."""
    shown = readStamp(image)
    if shown is None:
        return None
    elapsed = (nowMs() - shown) & 0xFFFFFF
    return elapsed if elapsed < MAX_PLAUSIBLE_MS else None


def summary(name, samples):
    if not samples:
        return f"{name:30} no readable frames (is the window visible?)"
    samples.sort()
    p90 = samples[int(len(samples) * 0.9) - 1]
    return f"{name:30} median {statistics.median(samples):5.0f} ms   p90 {p90:5.0f} ms   ({len(samples)} samples)"


def publish(url, stop, errors):
    try:
        with av.open(url, "w", format="rtsp", options={"rtsp_transport": "tcp"}) as output:
            video = output.add_stream("libx264", rate=FPS)
            video.width, video.height, video.pix_fmt = WIDTH, HEIGHT, "yuv420p"
            video.options = {"preset": "ultrafast", "tune": "zerolatency", "g": str(FPS), "bf": "0"}
            audio = output.add_stream("pcm_mulaw", rate=AUDIO_RATE)
            audio.layout = "mono"
            samples = AUDIO_RATE // FPS
            started = time.monotonic()
            index = 0
            while not stop.is_set():
                time.sleep(max(0.0, started + index / FPS - time.monotonic()))
                frame = av.VideoFrame.from_ndarray(stamp(nowMs()), format="rgb24")
                frame.pts = index
                for packet in video.encode(frame):
                    output.mux(packet)
                sound = av.AudioFrame.from_ndarray(np.zeros((1, samples), dtype=np.int16), format="s16", layout="mono")
                sound.sample_rate, sound.pts = AUDIO_RATE, index * samples
                for packet in audio.encode(sound):
                    output.mux(packet)
                index += 1
    except Exception as exc:
        errors.append(f"publisher: {type(exc).__name__}: {exc}")


def measureDecoderFloor(url):
    """Latency of a buffer-free FFmpeg decode of the same stream, without display."""
    samples = []
    options = {"rtsp_transport": "tcp", "fflags": "nobuffer", "flags": "low_delay"}
    with av.open(url, options=options, timeout=3) as container:
        started = time.monotonic()
        for frame in container.decode(video=0):
            if time.monotonic() - started > WARMUP_SECONDS / 2:
                pixels = frame.to_ndarray(format="rgb24")
                image = QImage(pixels.data, pixels.shape[1], pixels.shape[0], pixels.strides[0], QImage.Format.Format_RGB888)
                if (elapsed := age(image)) is not None:
                    samples.append(elapsed)
            if time.monotonic() - started > WARMUP_SECONDS / 2 + SAMPLE_SECONDS:
                break
    return summary("FFmpeg decode only (floor)", samples)


def workerScript(mediaOptions):
    """Run the real worker, adding only the media options under test."""
    replacesCaching = any(option.startswith(":network-caching=") for option in mediaOptions)
    return (
        "import vlc\n"
        "addOption = vlc.Media.add_option\n"
        "def option(media, value):\n"
        f"    if {replacesCaching!r} and value.startswith(':network-caching='): return\n"
        "    addOption(media, value)\n"
        "    if value == ':rtsp-tcp':\n"
        f"        for extra in {list(mediaOptions)!r}: addOption(media, extra)\n"
        "vlc.Media.add_option = option\n"
        "from infrastructure.VlcProcess import main\n"
        "raise SystemExit(main())\n"
    )


def measurePlayer(app, label, port, variant, folder):
    script = Path(folder) / "worker.py"
    script.write_text(workerScript(VARIANTS[variant]), encoding="utf-8")
    environment = QProcessEnvironment.systemEnvironment()
    environment.insert("PYTHONPATH", str(ROOT))
    process = QProcess()
    process.setProcessEnvironment(environment)
    process.setWorkingDirectory(str(ROOT))
    process.start(sys.executable, [str(script)])
    assert process.waitForStarted()
    data = dict(host="127.0.0.1", port=port, path=STREAM_PATH, timeout=2, hwnd=int(label.winId()), volume=0, muted=True)
    process.write(json.dumps(data).encode() + b"\n")
    samples, sampleFrom = [], time.monotonic() + WARMUP_SECONDS
    while time.monotonic() < sampleFrom + SAMPLE_SECONDS:
        app.processEvents()
        if time.monotonic() >= sampleFrom:
            origin = label.mapToGlobal(label.rect().topLeft())
            image = label.screen().grabWindow(0, origin.x(), origin.y(), label.width(), label.height()).toImage()
            if (elapsed := age(image)) is not None:
                samples.append(elapsed)
        time.sleep(CAPTURE_MS / 1000)
    output = bytes(process.readAllStandardOutput()).decode(errors="replace")
    process.write(b'{"stop":true}\n')
    if not process.waitForFinished(3000):
        process.kill()
        process.waitForFinished()
    if '"error"' in output:
        return f"{variant:30} worker error: {output.strip().splitlines()[-1]}"
    return summary(variant, samples)


def main():
    assert BINARY.is_file(), BINARY
    app = QApplication([])
    label = QLabel()
    label.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint)
    label.setFixedSize(WIDTH, HEIGHT)
    label.show()
    port = freePort()
    url = f"rtsp://127.0.0.1:{port}{STREAM_PATH}"
    config, _, _ = baseConfig("rtsp", "127.0.0.1", port, "live", False)
    config.update(rtspAddress=f"127.0.0.1:{port}", rtspTransports=["tcp"], rtspEncryption="no")
    stop, errors = threading.Event(), []
    with tempfile.TemporaryDirectory(prefix="ipvidex-latency-") as folder:
        (Path(folder) / "mediamtx.yml").write_text(json.dumps(config), encoding="utf-8")
        server = QProcess()
        server.setWorkingDirectory(folder)
        server.start(str(BINARY), [str(Path(folder) / "mediamtx.yml")])
        assert server.waitForStarted()
        time.sleep(1)
        publisher = threading.Thread(target=publish, args=(url, stop, errors), daemon=True)
        publisher.start()
        time.sleep(1)
        try:
            print(measureDecoderFloor(url), flush=True)
            for variant in VARIANTS if "--variants" in sys.argv else list(VARIANTS)[:1]:
                print(measurePlayer(app, label, port, variant, folder), flush=True)
        finally:
            stop.set()
            publisher.join(3)
            server.kill()
            server.waitForFinished(3000)
    assert not errors, errors


if __name__ == "__main__":
    main()
