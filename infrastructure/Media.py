"""RTSP URL parsing; credentials are split out so they never travel inside logged URLs."""

from urllib.parse import quote, unquote, urlsplit
from core.Models import Config
from infrastructure.Network import hostAuthority

RTSP_PORT = 554
# RFC 7826 registers 322 for RTSP over TLS; plaintext RTSP stays on 554.
RTSPS_PORT = 322


def defaultPort(secure):
    return RTSPS_PORT if secure else RTSP_PORT


def parseRtsp(url: str, username="", password="", target=None):
    if not url or any(ord(c) < 33 for c in url):
        raise ValueError("Enter a valid RTSP URL without whitespace.")
    parts = urlsplit(url)
    if parts.scheme not in ("rtsp", "rtsps") or not parts.hostname or not parts.path or parts.fragment:
        raise ValueError("Expected rtsp://host:port/path or rtsps://host:port/path.")
    Config(parts.hostname).validate()
    if target and parts.hostname.lower().rstrip(".") != target.lower().rstrip("."):
        raise ValueError("RTSP URL host must match Camera IP / Hostname.")
    secure = parts.scheme == "rtsps"
    port = parts.port or defaultPort(secure)
    username = unquote(parts.username) if parts.username is not None else username
    password = unquote(parts.password) if parts.password is not None else password
    if bool(username) != bool(password):
        raise ValueError("Supply both RTSP username and password.")
    return dict(
        host=parts.hostname,
        port=port,
        path=parts.path + ("?" + parts.query if parts.query else ""),
        username=username,
        password=password,
        secure=secure,
    )


def pinnedUrl(data, address):
    auth = f"{quote(data['username'], safe='')}:{quote(data['password'], safe='')}@" if data.get("username") else ""
    scheme = "rtsps" if data.get("secure") else "rtsp"
    return f"{scheme}://{auth}{hostAuthority(address)}:{data['port']}" + quote(data["path"], safe="/%?=&:;,+@")
