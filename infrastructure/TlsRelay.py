"""Pinned TLS relay for native media players; no decoding dependencies."""

import re
import select
import socket
import ssl
import threading
from infrastructure.Network import hostAuthority, pinnedTls, pinnedTlsContext

MAX_HEADER_BYTES = 32768
MAX_BODY_BYTES = 1024 * 1024
RECEIVE_BYTES = 65536
CONTENT_LENGTH = re.compile(rb"(?im)^Content-Length:\s*(\d+)\s*$")
URL_HEADERS = (b"content-base:", b"content-location:", b"location:")


def relayPacket(packet, local, public, outgoing):
    """Rewrite complete RTSP messages only; never touch interleaved media."""
    head, _, body = packet.partition(b"\r\n\r\n")
    lines = head.split(b"\r\n")
    if outgoing:
        lines[0] = lines[0].replace(local, public)
        return b"\r\n".join(lines) + b"\r\n\r\n" + body
    # VLC follows absolute SDP track URLs and Content-Base. Keep those
    # requests inside the verified TLS relay instead of opening a new URL.
    aliases = (public, public.replace(b"rtsps://", b"rtsp://", 1))
    for alias in aliases:
        body = body.replace(alias, local)
    for index, line in enumerate(lines):
        lowered = line.lower()
        if lowered.startswith(URL_HEADERS):
            for alias in aliases:
                line = line.replace(alias, local)
            lines[index] = line
        elif lowered.startswith(b"content-length:"):
            lines[index] = b"Content-Length: " + str(len(body)).encode()
    return b"\r\n".join(lines) + b"\r\n\r\n" + body


def messageSize(buffer):
    """Length of the first complete RTSP or interleaved message, or None while incomplete."""
    if buffer[:1] == b"$":
        return 4 + int.from_bytes(buffer[2:4], "big") if len(buffer) >= 4 else None
    boundary = buffer.find(b"\r\n\r\n")
    if boundary < 0:
        if len(buffer) > MAX_HEADER_BYTES:
            raise ValueError("RTSP header exceeds limit")
        return None
    lengths = CONTENT_LENGTH.findall(bytes(buffer[:boundary]))
    bodySize = int(lengths[0]) if lengths else 0
    if bodySize > MAX_BODY_BYTES or boundary > MAX_HEADER_BYTES:
        raise ValueError("RTSP message exceeds limit")
    return boundary + 4 + bodySize


def forward(buffer, target, rewrite):
    """Send every complete message in buffer to target; rewrite = (local, public, outgoing)."""
    while (size := messageSize(buffer)) is not None and len(buffer) >= size:
        message = bytes(buffer[:size])
        target.sendall(message if message[:1] == b"$" else relayPacket(message, *rewrite))
        del buffer[:size]


def relay(client, upstream, local, public):
    with client, upstream:
        client.settimeout(None)
        upstream.settimeout(None)
        buffers = {client: bytearray(), upstream: bytearray()}
        try:
            while True:
                ready = [upstream] if upstream.pending() else select.select([client, upstream], [], [])[0]
                for source in ready:
                    data = source.recv(RECEIVE_BYTES)
                    if not data:
                        return
                    buffers[source].extend(data)
                    outgoing = source is client
                    forward(buffers[source], upstream if outgoing else client, (local, public, outgoing))
        except (OSError, ValueError):
            pass


def startTlsRelay(transport, port, certificatePem):
    """Terminate RTSPS with Python/OpenSSL (TLS 1.3 + pinned certificate) and hand the
    player a loopback-only plaintext socket; its own TLS backend can do neither."""
    context, pinned = pinnedTlsContext(certificatePem)
    # Verify once before the player starts, so credentials never reach an unverified peer.
    pinnedTls(transport, port, context, pinned).close()
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    listener.listen(4)
    local = f"rtsp://127.0.0.1:{listener.getsockname()[1]}".encode()
    public = f"rtsps://{hostAuthority(transport.config.host)}:{port}".encode()

    def serve():
        while True:
            client, _ = listener.accept()
            try:
                upstream = pinnedTls(transport, port, context, pinned)
            except (OSError, ssl.SSLError):
                client.close()
                continue
            threading.Thread(target=relay, args=(client, upstream, local, public), daemon=True).start()

    threading.Thread(target=serve, daemon=True).start()
    return listener.getsockname()[1]
