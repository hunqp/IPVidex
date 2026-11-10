"""Bounded single-target transport and camera certificate pinning; no redirects."""

import os
import re
import socket
import ssl
import threading
import time

MAX_CERTIFICATE_BYTES = 65536
DNS_POLL_SECONDS = 0.05
PEM_BLOCK = re.compile(r"-----BEGIN CERTIFICATE-----.+?-----END CERTIFICATE-----", re.S)


class Cancelled(Exception):
    pass


class CertificateRequired(Exception):
    pass


def hostAuthority(host):
    """Host as written inside a URL: IPv6 literals are bracketed."""
    return f"[{host}]" if ":" in host else host


def verifiedTlsContext():
    """RFC 9525 identity checks: SAN required; no legacy Common Name fallback."""
    context = ssl.create_default_context()
    context.hostname_checks_common_name = False
    return context


def fetchCertificate(transport, port):
    """Fetch the peer certificate without credentials, for explicit session trust."""
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    context.check_hostname = False
    context.verify_mode = ssl.CERT_NONE
    with transport.tls(port, context) as sock:
        certificate = sock.getpeercert(binary_form=True)
    if not certificate:
        raise CertificateRequired()
    transport.checkpoint()
    return ssl.DER_cert_to_PEM_cert(certificate)


def readCertificateFile(path):
    if not path or not os.path.isfile(path) or os.path.getsize(path) > MAX_CERTIFICATE_BYTES:
        raise CertificateRequired()
    with open(path, encoding="ascii") as handle:
        return handle.read()


def pinnedTlsContext(pem):
    """Trust exactly the certificate(s) exported from this camera; nothing else."""
    blocks = PEM_BLOCK.findall(pem or "")
    if not blocks:
        raise CertificateRequired()
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    # Camera certificates name the device, not its IP. Identity is the exact pinned
    # certificate match in checkPinned(), so hostname matching is not used.
    context.check_hostname = False
    context.load_verify_locations(cadata="\n".join(blocks))
    context.verify_flags |= ssl.VERIFY_X509_PARTIAL_CHAIN
    return context, {ssl.PEM_cert_to_DER_cert(block) for block in blocks}


def checkPinned(sock, pinned):
    if sock.getpeercert(binary_form=True) not in pinned:
        sock.close()
        raise ssl.SSLCertVerificationError("Certificate does not match the pinned file")
    return sock


def pinnedTls(transport, port, context, pinned):
    return checkPinned(transport.tls(port, context), pinned)


class Transport:
    def __init__(self, config, stop):
        self.config, self.stop, self.address = config, stop, None

    def checkpoint(self):
        if self.stop.is_set():
            raise Cancelled()

    def resolve(self):
        """Resolve on a helper thread so a slow DNS lookup stays cancellable and bounded."""
        self.checkpoint()
        done, answer = threading.Event(), []

        def lookup():
            try:
                answer.append(socket.getaddrinfo(self.config.host, None, type=socket.SOCK_STREAM)[0][4][0])
            except OSError:
                pass
            finally:
                done.set()

        threading.Thread(target=lookup, daemon=True).start()
        deadline = time.monotonic() + self.config.timeout
        while not done.wait(DNS_POLL_SECONDS):
            self.checkpoint()
            if time.monotonic() >= deadline:
                raise TimeoutError("DNS timeout")
        if not answer:
            raise OSError("DNS resolution failed")
        self.address = answer[0]

    def connect(self, port):
        self.checkpoint()
        if self.address is None:
            self.resolve()
        family = socket.AF_INET6 if ":" in self.address else socket.AF_INET
        sock = socket.socket(family, socket.SOCK_STREAM)
        sock.settimeout(self.config.timeout)
        try:
            sock.connect((self.address, port))
            return sock
        except BaseException:
            sock.close()
            raise

    def tls(self, port, context):
        sock = self.connect(port)
        try:
            return context.wrap_socket(sock, server_hostname=self.config.host)
        except BaseException:
            sock.close()
            raise
