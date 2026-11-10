"""Bounded HTTP response reader with one deadline for headers and body."""

from dataclasses import dataclass
import http.client
import io
import time

MAX_HEADER_BYTES = 32768
READ_CHUNK = 4096


@dataclass
class HttpObservation:
    status: int
    headers: dict[str, str]
    body: bytes = b""
    truncated: bool = False


def remainingTime(transport, deadline, stage):
    transport.checkpoint()
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise TimeoutError(f"HTTP {stage} deadline")
    return remaining


def readHead(sock, transport, deadline):
    wire = bytearray()
    while b"\r\n\r\n" not in wire:
        sock.settimeout(remainingTime(transport, deadline, "header"))
        part = sock.recv(READ_CHUNK)
        if not part:
            raise ValueError("Incomplete HTTP headers")
        wire.extend(part)
        if len(wire) > MAX_HEADER_BYTES:
            raise ValueError("HTTP headers exceed limit")
    return bytes(wire).split(b"\r\n\r\n", 1)


def parseHead(head):
    first = head.split(b"\r\n", 1)[0].split()
    if len(first) < 2 or first[0] not in (b"HTTP/1.0", b"HTTP/1.1"):
        raise ValueError("Invalid HTTP response")
    status = int(first[1])
    if not 100 <= status <= 599:
        raise ValueError("Invalid HTTP status")
    fields = head.split(b"\r\n", 1)[1] + b"\r\n\r\n" if b"\r\n" in head else b"\r\n"
    parsed = http.client.parse_headers(io.BytesIO(fields))
    lengths = parsed.get_all("Content-Length", [])
    if lengths and (len(set(lengths)) > 1 or not lengths[0].isdigit()):
        raise ValueError("Ambiguous HTTP length")
    if lengths and parsed.get("Transfer-Encoding"):
        raise ValueError("Ambiguous HTTP framing")
    return status, {key.lower(): ", ".join(parsed.get_all(key)) for key in parsed}


def readResponse(sock, transport, limit=0):
    """Header and body share one absolute deadline, including buffered socket reads."""
    deadline = time.monotonic() + transport.config.timeout
    head, prefix = readHead(sock, transport, deadline)
    status, headers = parseHead(head)
    if not limit:
        return HttpObservation(status, headers)

    class Reader(io.RawIOBase):
        def __init__(self):
            self.initial = bytearray(head + b"\r\n\r\n" + prefix)

        def readable(self):
            return True

        def readinto(self, buffer):
            if self.initial:
                count = min(len(buffer), len(self.initial))
                buffer[:count] = self.initial[:count]
                del self.initial[:count]
                return count
            sock.settimeout(remainingTime(transport, deadline, "body"))
            part = sock.recv(min(len(buffer), READ_CHUNK))
            buffer[: len(part)] = part
            return len(part)

    class ResponseSocket:
        def makefile(self, *args):
            return io.BufferedReader(Reader(), buffer_size=READ_CHUNK)

    # http.client handles chunked and length-delimited bodies against the same deadline.
    response = http.client.HTTPResponse(ResponseSocket())
    response.begin()
    try:
        body = response.read(limit + 1)
        truncated = len(body) > limit or response.length is not None and response.length > 0
        return HttpObservation(status, headers, body[:limit], truncated)
    finally:
        response.close()
