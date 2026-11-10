import socket
import threading
import time
import pytest
from core.Models import Config
from infrastructure.Network import Cancelled, CertificateRequired, Transport, hostAuthority, pinnedTlsContext
from infrastructure.Responses import readResponse
from infrastructure.TlsRelay import messageSize, relayPacket


@pytest.fixture
def listener():
    server = socket.socket()
    server.bind(("127.0.0.1", 0))
    server.listen(8)
    yield server
    server.close()


def transport(timeout=2.0):
    return Transport(Config("127.0.0.1", timeout=timeout), threading.Event())


def testConnectHasNoFixedDelay(listener):
    """Regression: every connection used to wait 100 ms before connecting."""
    client = transport()
    started = time.monotonic()
    for _ in range(5):
        client.connect(listener.getsockname()[1]).close()
    assert time.monotonic() - started < 0.25


def testConnectHonoursCancellation(listener):
    client = transport()
    client.stop.set()
    with pytest.raises(Cancelled):
        client.connect(listener.getsockname()[1])


def respond(listener, payload):
    def serve():
        connection, _ = listener.accept()
        with connection:
            connection.sendall(payload)

    threading.Thread(target=serve, daemon=True).start()


def testReadResponseBody(listener):
    respond(listener, b"HTTP/1.1 200 OK\r\nContent-Type: text/xml\r\nContent-Length: 5\r\n\r\nhello")
    client = transport()
    with client.connect(listener.getsockname()[1]) as sock:
        response = readResponse(sock, client, limit=1024)
    assert (response.status, response.headers["content-type"], response.body) == (200, "text/xml", b"hello")


def testReadResponseRejectsAmbiguousLength(listener):
    respond(listener, b"HTTP/1.1 200 OK\r\nContent-Length: 5\r\nContent-Length: 6\r\n\r\nhello!")
    client = transport()
    with client.connect(listener.getsockname()[1]) as sock, pytest.raises(ValueError):
        readResponse(sock, client, limit=1024)


def testHostAuthority():
    assert (hostAuthority("192.0.2.1"), hostAuthority("fe80::1")) == ("192.0.2.1", "[fe80::1]")


def testPinnedContextNeedsACertificate():
    with pytest.raises(CertificateRequired):
        pinnedTlsContext("not a certificate")


@pytest.mark.parametrize(
    "buffer, size",
    [
        (b"$\x00\x00\x04abcd", 8),
        (b"$\x00", None),
        (b"RTSP/1.0 200 OK\r\nContent-Length: 3\r\n\r\nabc", 41),
        (b"RTSP/1.0 200 OK\r\n", None),
    ],
)
def testMessageSize(buffer, size):
    assert messageSize(bytearray(buffer)) == size


def testMessageSizeRejectsOversizedBody():
    with pytest.raises(ValueError):
        messageSize(bytearray(b"RTSP/1.0 200 OK\r\nContent-Length: 99999999\r\n\r\n"))


def testRelayRewritesOutgoingRequestLineOnly():
    packet = b"PLAY rtsp://127.0.0.1:1/live RTSP/1.0\r\nX: rtsp://127.0.0.1:1\r\n\r\n"
    rewritten = relayPacket(packet, b"rtsp://127.0.0.1:1", b"rtsps://cam:322", True)
    assert rewritten == b"PLAY rtsps://cam:322/live RTSP/1.0\r\nX: rtsp://127.0.0.1:1\r\n\r\n"
