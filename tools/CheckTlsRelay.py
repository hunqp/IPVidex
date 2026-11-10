"""Regression checks for encoded names and fragmented RTSP/TLS relay messages."""

import socket
import sys
import threading
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from infrastructure.Onvif import decodeScope
from infrastructure.TlsRelay import relay, relayPacket

assert decodeScope("Front%20Door") == "Front Door"
assert decodeScope("Front%2520Door") == "Front Door"
local = b"rtsp://127.0.0.1:12345"
public = b"rtsps://192.0.2.1:322"
body = b"v=0\r\na=rtpmap:96 H265/90000\r\na=control:" + public + b"/live/0/track1\r\n"
reply = b"RTSP/1.0 200 OK\r\nContent-Base: " + public + b"/live/0/\r\nContent-Length: " + str(len(body)).encode() + b"\r\n\r\n" + body
converted = relayPacket(reply, local, public, False)
head, _, newbody = converted.partition(b"\r\n\r\n")
assert public not in converted
assert b"H265/90000" in newbody
assert b"Content-Length: " + str(len(newbody)).encode() in head


class Upstream:
    def __init__(self, sock):
        self.sock = sock

    def pending(self):
        return 0

    def fileno(self):
        return self.sock.fileno()

    def __getattr__(self, key):
        return getattr(self.sock, key)

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.sock.close()


client, relayClient = socket.socketpair()
relayUp, server = socket.socketpair()
thread = threading.Thread(target=relay, args=(relayClient, Upstream(relayUp), local, public), daemon=True)
thread.start()
client.settimeout(2)
server.settimeout(2)


def receive(sock, size):
    result = b""
    while len(result) < size:
        result += sock.recv(size - len(result))
    return result


request = b"SETUP " + local + b"/live/0/track1 RTSP/1.0\r\nCSeq: 3\r\n\r\n"
for part in (request[:9], request[9:20], request[20:]):
    client.sendall(part)
expected = request.replace(local, public)
assert receive(server, len(expected)) == expected
frame = b"$\x00\x00\x06\x00\x01test"
for part in (reply[:7], reply[7:] + frame[:2], frame[2:]):
    server.sendall(part)
assert receive(client, len(converted) + len(frame)) == converted + frame
client.close()
server.close()
thread.join(2)
assert not thread.is_alive()
print("PASS: scope labels, H265 SDP URLs, Content-Length, fragmented RTSP and binary media")
