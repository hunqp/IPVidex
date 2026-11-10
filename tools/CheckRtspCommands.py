"""Offline RTSP protocol test: Digest, framing, CSeq and session commands."""

import hashlib
from pathlib import Path
import socket
import sys
import threading
from urllib.request import parse_http_list, parse_keqv_list

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from infrastructure.RtspCommands import RtspConnection


def h(value):
    return hashlib.md5(value.encode()).hexdigest()


listener = socket.socket()
listener.bind(("127.0.0.1", 0))
listener.listen(1)
errors = []
methods = []


def server():
    try:
        conn, _ = listener.accept()
        conn.settimeout(4)
        with conn:
            buffer = b""
            for index in range(6):
                while b"\r\n\r\n" not in buffer:
                    part = conn.recv(4096)
                    assert part
                    buffer += part
                head, _, buffer = buffer.partition(b"\r\n\r\n")
                lines = head.decode().split("\r\n")
                method, uri, _ = lines[0].split()
                headers = dict((key.lower(), value.strip()) for key, value in (line.split(":", 1) for line in lines[1:]))
                size = int(headers.get("content-length", "0"))
                while len(buffer) < size:
                    buffer += conn.recv(4096)
                buffer = buffer[size:]
                methods.append(method)
                cseq = headers["cseq"]
                if index == 0:
                    response = f'RTSP/1.0 401 Unauthorized\r\nCSeq: {cseq}\r\nWWW-Authenticate: Digest realm="test", nonce="abc", qop="auth", algorithm=MD5\r\nContent-Length: 0\r\n\r\n'.encode()
                else:
                    auth = parse_keqv_list(parse_http_list(headers["authorization"][7:]))
                    expected = h(f"{h('user:test:secret')}:abc:{auth['nc']}:{auth['cnonce']}:auth:{h(method + ':' + uri)}")
                    assert expected == auth["response"]
                    if method in ("PLAY", "TEARDOWN"):
                        assert headers["session"] == "session1"
                    body = b"v=0\r\nm=video 0 RTP/AVP 96\r\na=control:trackID=1\r\n" if method == "DESCRIBE" else b""
                    session = "Session: session1;timeout=60\r\n" if method == "SETUP" else ""
                    response = f"RTSP/1.0 200 OK\r\nCSeq: {cseq}\r\n{session}Content-Length: {len(body)}\r\n\r\n".encode() + body
                    if method == "PLAY":
                        response = b"$\x00\x00\x04abcd" + response
                conn.sendall(response[:12])
                conn.sendall(response[12:])
    except Exception as exc:
        errors.append(exc)
    finally:
        listener.close()


thread = threading.Thread(target=server)
thread.start()
client = RtspConnection(dict(host="127.0.0.1", port=listener.getsockname()[1], path="/live", timeout=2, username="user", password="secret", secure=False))
try:
    for method in ("OPTIONS", "DESCRIBE", "SETUP", "PLAY", "TEARDOWN"):
        result = client.request(dict(method=method))
        assert "RTSP/1.0 200 OK" in result["transcript"]
        assert "Authorization: [redacted]" in result["transcript"]
        assert "secret" not in result["transcript"]
    assert client.session == ""
finally:
    if client.sock:
        client.sock.close()
thread.join(5)
assert not thread.is_alive() and not errors, errors
assert methods == ["OPTIONS", "OPTIONS", "DESCRIBE", "SETUP", "PLAY", "TEARDOWN"]
client.challenge = 'Digest realm="EPCam", nonce="camera-nonce"'
implicit = client.authorization("DESCRIBE", "rtsps://camera/live/0")
assert "algorithm=" not in implicit
fields = parse_keqv_list(parse_http_list(implicit[7:]))
assert fields["response"] == h(f"{h('user:EPCam:secret')}:camera-nonce:{h('DESCRIBE:rtsps://camera/live/0')}")
print("PASS: RTSP Digest, partial response, interleaved packets, CSeq and session lifecycle")
