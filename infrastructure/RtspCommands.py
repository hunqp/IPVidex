"""Bounded RTSP test connection, separate from the video player's session."""

import base64
import json
import os
import re
import sys
import threading
import time
from urllib.parse import urlsplit
from core.Models import Config
from infrastructure.Digest import digestAuthorization
from infrastructure.Media import defaultPort, pinnedUrl
from infrastructure.Network import Transport, fetchCertificate, pinnedTls, pinnedTlsContext

MAX_REQUEST_BYTES = 131072
MAX_HEADER_BYTES = 32768
MAX_BODY_BYTES = 1024 * 1024
MAX_REQUEST_BODY_BYTES = 65536
RECEIVE_BYTES = 65536
USER_AGENT = "IPVidex-RTSP-Console"
MANAGED_HEADERS = ("authorization", "cseq", "content-length", "session")
SESSION_METHODS = ("PLAY", "PAUSE", "TEARDOWN", "GET_PARAMETER", "SET_PARAMETER")
# Validation errors raised here carry fixed texts without URLs or credentials, so they may be shown.
PUBLIC_ERRORS = ("Invalid RTSP", "RTSP ", "Duplicate RTSP", "Unsupported ", "Use a local", "Request body", "Authorization/")


def localPath(path):
    return path.startswith("/") and not any(ord(c) < 33 for c in path)


def parseExtraHeaders(text):
    headers = []
    for line in text.splitlines():
        if not line.strip():
            continue
        key, separator, value = line.partition(":")
        if not separator or not re.fullmatch("[A-Za-z0-9-]+", key):
            raise ValueError("Invalid request header")
        if key.lower() in MANAGED_HEADERS:
            raise ValueError("Authorization/CSeq/Content-Length/Session are managed automatically")
        headers.append((key, value.strip()))
    return headers


def parseHeaders(lines):
    headers = {}
    for line in lines:
        key, separator, value = line.partition(":")
        if not separator:
            raise ValueError("Invalid RTSP header")
        key = key.lower()
        if key in ("content-length", "cseq") and key in headers:
            raise ValueError("Duplicate RTSP framing header")
        headers[key] = value.strip()
    return headers


def redacted(lines):
    return "\r\n".join("Authorization: [redacted]" if line.startswith("Authorization:") else line for line in lines)


class RtspConnection:
    def __init__(self, data):
        self.data = data
        self.transport = Transport(Config(data["host"], timeout=data["timeout"]).validate(), threading.Event())
        self.transport.resolve()
        self.sock = None
        self.buffer = bytearray()
        self.sequence = 0
        self.session = ""
        self.challenge = ""
        self.nonceCount = 0
        self.trackPath = None

    def open(self):
        if self.sock:
            return
        if not self.data.get("secure"):
            self.sock = self.transport.connect(self.data["port"])
            return
        pem = fetchCertificate(self.transport, self.data["port"]) if self.data.get("autoTrust") else self.data.get("certificatePem", "")
        context, pins = pinnedTlsContext(pem)
        self.sock = pinnedTls(self.transport, self.data["port"], context, pins)

    def close(self):
        if self.sock:
            self.sock.close()
            self.sock = None
        self.buffer.clear()

    def authorization(self, method, uri):
        username, password = self.data.get("username", ""), self.data.get("password", "")
        if not username or not self.challenge:
            return ""
        kind = self.challenge.partition(" ")[0].lower()
        if kind == "basic":
            return "Basic " + base64.b64encode(f"{username}:{password}".encode()).decode()
        if kind != "digest":
            raise ValueError("Unsupported authentication scheme")
        self.nonceCount += 1
        return digestAuthorization(self.challenge, method, uri, username, password, self.nonceCount)

    # ---- framing ----------------------------------------------------------------
    def fill(self, size, deadline):
        while len(self.buffer) < size:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError()
            self.sock.settimeout(remaining)
            part = self.sock.recv(min(RECEIVE_BYTES, max(4096, size - len(self.buffer))))
            if not part:
                raise ConnectionError()
            self.buffer.extend(part)

    def skipInterleaved(self, deadline):
        """Discard interleaved RTP/RTCP frames on the test session's TCP connection."""
        while True:
            self.fill(1, deadline)
            if self.buffer[:1] != b"$":
                return
            self.fill(4, deadline)
            size = 4 + int.from_bytes(self.buffer[2:4], "big")
            self.fill(size, deadline)
            del self.buffer[:size]

    def receive(self):
        deadline = time.monotonic() + self.data["timeout"]
        self.skipInterleaved(deadline)
        while b"\r\n\r\n" not in self.buffer:
            if len(self.buffer) > MAX_HEADER_BYTES:
                raise ValueError("RTSP headers exceed limit")
            self.fill(len(self.buffer) + 1, deadline)
        head = self.buffer.partition(b"\r\n\r\n")[0]
        if len(head) > MAX_HEADER_BYTES:
            raise ValueError("RTSP headers exceed limit")
        lines = head.decode("iso-8859-1").split("\r\n")
        if not re.fullmatch(r"RTSP/\d\.\d \d{3}.*", lines[0]):
            raise ValueError("Invalid RTSP status")
        headers = parseHeaders(lines[1:])
        size = int(headers.get("content-length", "0"))
        if not 0 <= size <= MAX_BODY_BYTES:
            raise ValueError("RTSP body exceeds limit")
        length = len(head) + 4 + size
        self.fill(length, deadline)
        raw = bytes(self.buffer[:length])
        del self.buffer[:length]
        if headers.get("cseq") != str(self.sequence):
            raise ValueError("RTSP CSeq mismatch")
        return int(lines[0].split()[1]), headers, raw.decode("utf-8", errors="replace")

    # ---- requests ---------------------------------------------------------------
    def request(self, command):
        """Resolve SDP tracks internally and establish the test session as needed."""
        method = command["method"].strip().upper()
        preparation = []
        if method == "SETUP" and not self.trackPath:
            described = self.send(dict(method="DESCRIBE"))
            preparation.extend(described["exchanges"])
            if described["exchanges"][-1]["status"] // 100 != 2:
                return described
            if not self.trackPath:
                return dict(exchanges=preparation, session=self.session, transcript=described["transcript"], error="The SDP has no usable media track.")
        if method in SESSION_METHODS and not self.session:
            setup = self.request(dict(method="SETUP"))
            preparation.extend(setup.get("exchanges", []))
            if not self.session:
                return setup
        actual = dict(command, path=self.trackPath) if method == "SETUP" else command
        result = self.send(actual)
        result["exchanges"] = preparation + result["exchanges"]
        return result

    def trackFromControl(self, control, headers):
        if "://" in control:
            parts = urlsplit(control)
            if parts.hostname != self.data["host"] or (parts.port or defaultPort(parts.scheme == "rtsps")) != self.data["port"]:
                return None
            return parts.path + ("?" + parts.query if parts.query else "")
        if control.startswith("/"):
            return control
        base = headers.get("content-base") or headers.get("content-location")
        basePath = urlsplit(base).path if base else self.data["path"].split("?")[0].rstrip("/") + "/"
        return basePath.rsplit("/", 1)[0] + "/" + control

    def rememberTrack(self, headers, response):
        inMedia = False
        for line in response.partition("\r\n\r\n")[2].splitlines():
            inMedia = inMedia or line.startswith("m=")
            if not inMedia or not line.startswith("a=control:"):
                continue
            control = line[len("a=control:") :].strip()
            path = self.trackFromControl(control, headers) if control and control != "*" else None
            if path and localPath(path):
                self.trackPath = path
                return

    def requestLines(self, method, uri, extra, body):
        self.sequence += 1
        lines = [f"{method} {uri} RTSP/1.0", f"CSeq: {self.sequence}", f"User-Agent: {USER_AGENT}"]
        if self.session:
            lines.append(f"Session: {self.session}")
        names = {key.lower() for key, _ in extra}
        if method == "DESCRIBE" and "accept" not in names:
            lines.append("Accept: application/sdp")
        if method == "SETUP" and "transport" not in names:
            lines.append("Transport: RTP/AVP/TCP;unicast;interleaved=0-1")
        lines += [f"{key}: {value}" for key, value in extra]
        authorization = self.authorization(method, uri)
        if authorization:
            lines.append(f"Authorization: {authorization}")
        lines.append(f"Content-Length: {len(body)}")
        return lines

    def remember(self, method, status, headers, response):
        if status // 100 == 2:
            if method == "DESCRIBE":
                self.rememberTrack(headers, response)
            if "session" in headers:
                self.session = headers["session"].split(";")[0]
            if method == "TEARDOWN":
                self.session = ""
        if headers.get("connection", "").lower() == "close":
            self.close()

    def send(self, command):
        method = command["method"].strip().upper()
        if not re.fullmatch("[A-Z_]+", method):
            raise ValueError("Invalid RTSP method")
        path = command.get("path") or self.data["path"]
        if not localPath(path):
            raise ValueError("Use a local RTSP path without whitespace")
        uri = pinnedUrl(dict(self.data, path=path, username="", password=""), self.data["host"])
        extra = parseExtraHeaders(command.get("headers", ""))
        body = command.get("body", "").encode()
        if len(body) > MAX_REQUEST_BODY_BYTES:
            raise ValueError("Request body exceeds limit")
        self.open()
        exchanges = []
        for attempt in range(2):
            lines = self.requestLines(method, uri, extra, body)
            self.sock.sendall(("\r\n".join(lines) + "\r\n\r\n").encode() + body)
            status, headers, response = self.receive()
            exchanges.append(dict(request=redacted(lines) + "\r\n\r\n" + body.decode(errors="replace"), response=response, status=status))
            if status == 401 and attempt == 0 and self.data.get("username"):
                self.challenge = headers.get("www-authenticate", "")
                if headers.get("connection", "").lower() == "close":
                    self.close()
                    self.open()
                continue
            self.remember(method, status, headers, response)
            transcript = "\n\n".join(f"Request\n{e['request']}\nResponse\n{e['response']}" for e in exchanges)
            return dict(transcript=transcript, exchanges=exchanges, session=self.session)
        raise RuntimeError()


def publicError(exc):
    """Exceptions may contain credential-bearing URLs; expose only fixed validation texts or the type."""
    if isinstance(exc, ValueError) and str(exc).startswith(PUBLIC_ERRORS):
        return str(exc)
    return type(exc).__name__


def main():
    with open(os.devnull, "w") as sink:
        os.dup2(sink.fileno(), 2)
    connection = None
    try:
        connection = RtspConnection(json.loads(sys.stdin.buffer.readline(MAX_REQUEST_BYTES)))
        for line in sys.stdin.buffer:
            try:
                result = connection.request(json.loads(line))
            except Exception as exc:
                result = {"error": publicError(exc)}
                connection.close()
            print(json.dumps(result), flush=True)
    finally:
        if connection:
            connection.close()


if __name__ == "__main__":
    main()
