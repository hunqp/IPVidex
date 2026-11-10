"""WS-Discovery of ONVIF devices on every active IPv4 interface."""

import select
import socket
import threading
import time
import uuid
from PyQt6.QtCore import QThread, pyqtSignal
from PyQt6.QtNetwork import QAbstractSocket, QNetworkInterface
from infrastructure.Onvif import discoveryProbe, parseProbeMatches

WS_DISCOVERY = ("239.255.255.250", 3702)
MAX_DATAGRAM = 65536
POLL_SECONDS = 0.1


def interfaces():
    """[(interface name, IPv4 address)] for interfaces that are up, without loopback or link-local."""
    rows = []
    for interface in QNetworkInterface.allInterfaces():
        flags = interface.flags()
        if not flags & QNetworkInterface.InterfaceFlag.IsUp or flags & QNetworkInterface.InterfaceFlag.IsLoopBack:
            continue
        for entry in interface.addressEntries():
            ip = entry.ip()
            if ip.protocol() == QAbstractSocket.NetworkLayerProtocol.IPv4Protocol and not ip.toString().startswith("169.254."):
                rows.append((interface.humanReadableName(), ip.toString()))
    return rows


def openProbe(source):
    """Send one multicast Probe from `source`; return (socket, messageId) or None."""
    messageId = "urn:uuid:" + str(uuid.uuid4())
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.bind((source, 0))
        sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_IF, socket.inet_aton(source))
        sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 1)
        sock.sendto(discoveryProbe(messageId), WS_DISCOVERY)
        return sock, messageId
    except OSError:
        sock.close()
        return None


class OnvifDiscoveryWorker(QThread):
    """ODM-style device list: one WS-Discovery Probe per active IPv4 interface."""

    deviceFound = pyqtSignal(object)
    discoveryDone = pyqtSignal()

    def __init__(self, parent=None, seconds=3.0):
        super().__init__(parent)
        self.seconds = seconds
        self.stopEvent = threading.Event()

    def cancel(self):
        self.stopEvent.set()

    def run(self):
        probes = {}
        try:
            probes.update(filter(None, (openProbe(source) for _, source in interfaces())))
            self.collect(probes)
        finally:
            for sock in probes:
                sock.close()
            self.discoveryDone.emit()

    def collect(self, probes):
        seen = set()
        deadline = time.monotonic() + self.seconds
        while probes and not self.stopEvent.is_set() and time.monotonic() < deadline:
            ready = select.select(list(probes), [], [], POLL_SECONDS)[0]
            for sock in ready:
                try:
                    data, peer = sock.recvfrom(MAX_DATAGRAM)
                    devices = parseProbeMatches(data, probes[sock], peer[0])
                except Exception:
                    continue
                for device in devices:
                    if device["address"] not in seen:
                        seen.add(device["address"])
                        self.deviceFound.emit(device)
