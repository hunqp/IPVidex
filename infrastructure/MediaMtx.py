"""Managed, receive-only MediaMTX configurations: RTMP(S) and WebRTC (WHIP publish / WHEP read)."""

import ipaddress
import re
import secrets
import socket
from core.Paths import ROOT

BINARY = ROOT / "vendor" / "mediamtx" / "mediamtx.exe"
API_USER = "ipvidex-api"
PATH_SEGMENTS = r"[A-Za-z0-9_-]+(?:/[A-Za-z0-9_-]+)*"
PROTOCOLS = ("rtmp", "rtsp", "hls", "webrtc", "srt", "moq")


def pathPattern(prefix):
    """MediaMTX regex path that accepts any stream key a camera chooses under the fixed
    prefix, e.g. with prefix 'live': live/cam1, live/front/sub, so several cameras can
    publish to the same server on distinct keys."""
    prefix = prefix.strip().strip("/")
    if not re.fullmatch(PATH_SEGMENTS, prefix):
        raise ValueError("Base path may contain letters, digits, /, _ and - only.")
    # RE2 (Go) regex consumed by MediaMTX when the path name is prefixed with '~'.
    return "~^" + re.escape(prefix) + "/" + PATH_SEGMENTS + "$"


def freeLoopbackPort():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def baseConfig(protocol, address, port, prefix, debug):
    """Config with only `protocol` enabled; returns (config, apiPort, apiPassword)."""
    ipaddress.IPv4Address(address)
    if not 1 <= port <= 65535:
        raise ValueError("Invalid port")
    pattern = pathPattern(prefix)
    apiPort, password = freeLoopbackPort(), secrets.token_urlsafe(24)
    streams = [{"action": "publish", "path": pattern}, {"action": "read", "path": pattern}]
    config = {
        "logLevel": "debug" if debug else "info",
        "logDestinations": ["stdout"],
        **{name: name == protocol for name in PROTOCOLS},
        "playback": False,
        "metrics": False,
        "pprof": False,
        "api": True,
        "apiAddress": f"127.0.0.1:{apiPort}",
        "authMethod": "internal",
        "authInternalUsers": [
            {"user": "any", "pass": "", "ips": [], "permissions": streams},
            {"user": API_USER, "pass": password, "ips": ["127.0.0.1"], "permissions": [{"action": "api"}]},
        ],
        "pathDefaults": {"source": "publisher", "record": False, "overridePublisher": False},
        "paths": {pattern: {}},
    }
    return config, apiPort, password


def rtmpConfig(address, port, prefix, debug=False, tls=None):
    """RTMP(S) is both the publish endpoint and the read URL. tls is None or (certPath, keyPath)."""
    config, apiPort, password = baseConfig("rtmp", address, port, prefix, debug)
    if tls:
        config.update(rtmpEncryption="strict", rtmpsAddress=f"{address}:{port}", rtmpServerCert=tls[0], rtmpServerKey=tls[1])
    else:
        config.update(rtmpEncryption="no", rtmpAddress=f"{address}:{port}")
    return config, apiPort, password


def webRtcConfig(address, port, prefix, debug=False, tls=None):
    """WHIP/WHEP on one port. Media is always DTLS/SRTP; TLS only wraps the HTTP signalling."""
    config, apiPort, password = baseConfig("webrtc", address, port, prefix, debug)
    config.update(webrtcAddress=f"{address}:{port}", webrtcEncryption=bool(tls), webrtcAdditionalHosts=[address])
    if tls:
        config.update(webrtcServerCert=tls[0], webrtcServerKey=tls[1])
    return config, apiPort, password
