"""Native VLC renderer subprocess. Credentials arrive only through stdin."""

import contextlib
import json
import os
import queue
import ssl
import sys
import threading
import time
from core.Models import Config
from infrastructure.Media import pinnedUrl
from infrastructure.Network import CertificateRequired, Transport, fetchCertificate
from infrastructure.TlsRelay import startTlsRelay

MAX_REQUEST_BYTES = 131072
POLL_SECONDS = 0.1
STATS_SECONDS = 1.0
MIN_STALL_SECONDS = 15
# libVLC's own input buffer. Each 100 ms adds 100 ms of delay behind real time
# (tools/CheckLatency.py); 100 still absorbs I-frame bursts on a wired LAN.
NETWORK_CACHING_MS = 100
CODEC_NAMES = {"h264": "H264", "hevc": "HEVC", "alaw": "pcm_alaw", "ulaw": "pcm_mulaw", "mp4a": "aac"}


def emit(packet):
    print(json.dumps(packet), flush=True)


def streamUrl(data):
    """Pinned-address URL; RTSPS goes through a local relay that verifies the camera certificate."""
    transport = Transport(Config(data["host"], timeout=data["timeout"]).validate(), threading.Event())
    transport.resolve()
    if not data.get("secure"):
        return pinnedUrl(data, transport.address)
    pem = fetchCertificate(transport, data["port"]) if data.get("autoTrust") else data.get("certificatePem", "")
    port = startTlsRelay(transport, data["port"], pem)
    return pinnedUrl(dict(data, secure=False, port=port), "127.0.0.1")


def readCommands():
    commands = queue.Queue()

    def read():
        for line in sys.stdin.buffer:
            with contextlib.suppress(ValueError):
                commands.put(json.loads(line))
        commands.put({"stop": True})

    threading.Thread(target=read, daemon=True).start()
    return commands


def trackMetadata(vlc, media, result):
    for track in media.tracks_get() or []:
        codec = int(track.codec).to_bytes(4, "little").decode("ascii", errors="replace").strip("\x00 ")
        codec = CODEC_NAMES.get(codec, codec)
        if track.type == vlc.TrackType.video:
            result["codec"] = codec
        elif track.type == vlc.TrackType.audio:
            result["audio"].append(dict(codec=codec, sampleRate=track.audio.contents.rate))
    return result


def statsPacket(player, stats, decoder, frameRate, elapsed):
    width, height = player.video_get_size(0)
    return dict(
        width=width,
        height=height,
        codec="",
        audio=[],
        decodedFrames=stats.decoded_video,
        displayedFrames=stats.displayed_pictures,
        lostFrames=stats.lost_pictures,
        decoderMode=decoder,
        measuredFps=round(frameRate, 1),
        wallSampleSeconds=round(elapsed, 1),
    )


def watchPlayback(vlc, player, media, data, decoder):
    """Apply volume commands, report statistics once a second, fail when frames stop."""
    commands = readCommands()
    volume, muted = data.get("volume", 80), data.get("muted", False)
    started = lastStats = lastProgress = time.monotonic()
    lastFrames, playing = 0, False
    stallSeconds = max(MIN_STALL_SECONDS, 2 * data["timeout"])
    while True:
        try:
            command = commands.get(timeout=POLL_SECONDS)
            if command.get("stop"):
                return
            volume, muted = command.get("volume", volume), command.get("muted", muted)
        except queue.Empty:
            pass
        # libVLC drops a volume set before its audio output exists, so it is re-applied.
        player.audio_set_volume(0 if muted else volume)
        if player.get_state() in (vlc.State.Error, vlc.State.Ended):
            raise RuntimeError()
        now = time.monotonic()
        stats = vlc.MediaStats()
        media.get_stats(stats)
        if stats.displayed_pictures > lastFrames:
            lastProgress = now
            if not playing:
                playing = True
                emit({"state": "playing"})
        if now - lastProgress > stallSeconds:
            raise TimeoutError()
        if now - lastStats >= STATS_SECONDS:
            frameRate = (stats.displayed_pictures - lastFrames) / (now - lastStats)
            result = statsPacket(player, stats, decoder, frameRate, now - started)
            emit({"metadata": trackMetadata(vlc, media, result)})
            lastStats, lastFrames = now, stats.displayed_pictures


def errorCode(exc, runtimeLoaded):
    if isinstance(exc, CertificateRequired):
        return "CERTIFICATE_REQUIRED"
    if isinstance(exc, ssl.SSLCertVerificationError):
        return "CERTIFICATE_UNTRUSTED"
    if not runtimeLoaded:
        return "VLC_NOT_INSTALLED"
    return "NO_FRAMES" if isinstance(exc, TimeoutError) else "STREAM_ERROR"


def main():
    with open(os.devnull, "w") as sink:
        os.dup2(sink.fileno(), 2)
    player = media = instance = None
    runtimeLoaded = False
    try:
        data = json.loads(sys.stdin.buffer.readline(MAX_REQUEST_BYTES))
        import vlc

        vlc.libvlc_get_version()
        runtimeLoaded = True
        url = streamUrl(data)
        decoder = "none" if data.get("softwareDecode") else "any"
        instance = vlc.Instance("--no-video-title-show", "--quiet", f"--avcodec-hw={decoder}", "--no-osd", "--stats", "--no-interact")
        if instance is None:
            raise RuntimeError()
        player = instance.media_player_new()
        player.set_hwnd(int(data["hwnd"]))
        player.video_set_mouse_input(False)
        player.video_set_key_input(False)
        media = instance.media_new(url)
        media.add_option(":rtsp-tcp")
        media.add_option(f":network-caching={NETWORK_CACHING_MS}")
        player.set_media(media)
        if player.play() == -1:
            raise RuntimeError()
        watchPlayback(vlc, player, media, data, decoder)
        return 0
    except Exception as exc:
        emit({"error": errorCode(exc, runtimeLoaded)})
        return 2
    finally:
        if player:
            player.stop()
            player.release()
        if media:
            media.release()
        if instance:
            instance.release()


if __name__ == "__main__":
    sys.exit(main())
