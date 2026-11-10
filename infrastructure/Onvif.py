"""ONVIF SOAP 1.2 and WS-Discovery: authenticated session to one pinned device address."""

import base64
import contextlib
import copy
import dataclasses
import datetime
import hashlib
import os
import xml.etree.ElementTree as ET
from urllib.parse import unquote, urlsplit
from xml.sax.saxutils import escape
from infrastructure.Digest import digestAuthorization
from infrastructure.Network import Transport, checkPinned, hostAuthority, pinnedTlsContext, verifiedTlsContext
from infrastructure.Responses import readResponse

SOAP = "http://www.w3.org/2003/05/soap-envelope"
DEVICE = "http://www.onvif.org/ver10/device/wsdl"
DISCOVERY = "http://schemas.xmlsoap.org/ws/2005/04/discovery"
ADDRESSING = "http://schemas.xmlsoap.org/ws/2004/08/addressing"
DEFAULT_DEVICE_PATH = "/onvif/device_service"
USER_AGENT = "IPVidex/1.0"
MAX_DISCOVERY_BYTES = 65536
MAX_SOAP_BYTES = 1024 * 1024
MAX_TRANSFER_BYTES = 64 * 1024 * 1024
TRANSFER_TIMEOUT_SECONDS = 120.0
MAX_FAULT_REASON = 160


def xmlRoot(data: bytes, limit: int = MAX_DISCOVERY_BYTES):
    if len(data) > limit or b"<!DOCTYPE" in data.upper() or b"<!ENTITY" in data.upper():
        raise ValueError("Unsafe or oversized XML")
    return ET.fromstring(data)


def discoveryProbe(messageId: str) -> bytes:
    return f'''<s:Envelope xmlns:s="{SOAP}" xmlns:a="{ADDRESSING}" xmlns:d="{DISCOVERY}" xmlns:dn="http://www.onvif.org/ver10/network/wsdl"><s:Header><a:MessageID>{messageId}</a:MessageID><a:To>urn:schemas-xmlsoap-org:ws:2005:04:discovery</a:To><a:Action>{DISCOVERY}/Probe</a:Action></s:Header><s:Body><d:Probe><d:Types>dn:NetworkVideoTransmitter</d:Types></d:Probe></s:Body></s:Envelope>'''.encode()


def decodeScope(value):
    """Some cameras percent-encode their scope labels more than once."""
    for _ in range(3):
        decoded = unquote(value)
        if decoded == value:
            break
        value = decoded
    return value


def scopeValues(scopes, kind):
    prefix = f"onvif://www.onvif.org/{kind}/"
    return ", ".join(decodeScope(scope[len(prefix) :]).strip() for scope in scopes if scope.startswith(prefix))


def deviceEndpoint(match, peer):
    """Port and path of the device service; an XAddr only counts when it names the responding host."""
    for xaddr in (match.findtext(f"{{{DISCOVERY}}}XAddrs") or "").split():
        try:
            parts = urlsplit(xaddr)
            if parts.hostname == peer and parts.scheme == "http":
                return parts.port or 80, parts.path or DEFAULT_DEVICE_PATH
        except ValueError:
            continue
    return 80, DEFAULT_DEVICE_PATH


def parseProbeMatches(data, messageId, peer):
    """Device-list view of a ProbeMatches reply. The address is always the responding peer,
    so a reply cannot point the client at another host."""
    root = xmlRoot(data)
    related = root.find(f".//{{{ADDRESSING}}}RelatesTo")
    if related is None or related.text != messageId:
        return []
    devices = []
    for match in root.iter(f"{{{DISCOVERY}}}ProbeMatch"):
        scopes = (match.findtext(f"{{{DISCOVERY}}}Scopes") or "").split()
        port, path = deviceEndpoint(match, peer)
        info = {"address": peer, "port": port, "path": path}
        for key in ("name", "location", "hardware"):
            info[key] = scopeValues(scopes, key)
        devices.append(info)
    return devices


NS = {
    "tds": DEVICE,
    "trt": "http://www.onvif.org/ver10/media/wsdl",
    "tr2": "http://www.onvif.org/ver20/media/wsdl",
    "timg": "http://www.onvif.org/ver20/imaging/wsdl",
    "tev": "http://www.onvif.org/ver10/events/wsdl",
    "tptz": "http://www.onvif.org/ver20/ptz/wsdl",
    "tmd": "http://www.onvif.org/ver10/deviceIO/wsdl",
    "tan": "http://www.onvif.org/ver20/analytics/wsdl",
    "tt": "http://www.onvif.org/ver10/schema",
    "wsnt": "http://docs.oasis-open.org/wsn/b-2",
    "wsa": "http://www.w3.org/2005/08/addressing",
    "tns1": "http://www.onvif.org/ver10/topics",
}
SERVICES = {NS[prefix]: prefix for prefix in ("tds", "trt", "tr2", "timg", "tev", "tptz", "tmd", "tan")}
CAPABILITY_SERVICES = {"Media": "trt", "Events": "tev", "Imaging": "timg", "PTZ": "tptz"}
PULL = "http://www.onvif.org/ver10/events/wsdl/PullPointSubscription/PullMessagesRequest"
UNSUBSCRIBE = "http://docs.oasis-open.org/wsn/bw-2/SubscriptionManager/UnsubscribeRequest"
WSSE = "http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-wssecurity-secext-1.0.xsd"
WSU = "http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-wssecurity-utility-1.0.xsd"
DIGEST_TYPE = "http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-username-token-profile-1.0#PasswordDigest"
NONCE_TYPE = "http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-soap-message-security-1.0#Base64Binary"
ENVELOPE_NAMESPACES = " ".join(f'xmlns:{key}="{value}"' for key, value in NS.items())


class OnvifFault(Exception):
    """SOAP fault or HTTP error; carries only codes, never response bodies."""

    def __init__(self, status, code="", subcode="", reason=""):
        super().__init__(f"HTTP {status} {subcode or code}".strip())
        self.status, self.code, self.subcode, self.reason = status, code, subcode, reason


def localName(tag):
    return tag.rsplit("}", 1)[-1]


def faultFrom(status, root):
    fault = root.find(f".//{{{SOAP}}}Fault") if root is not None else None
    if fault is None:
        return OnvifFault(status)
    values = [element.text or "" for element in fault.iter(f"{{{SOAP}}}Value")]
    code = values[0] if values else ""
    subcode = values[-1] if len(values) > 1 else ""
    reason = (fault.findtext(f".//{{{SOAP}}}Text") or "")[:MAX_FAULT_REASON]
    return OnvifFault(status, code, subcode, reason)


def xmlBody(response):
    if not response.body or "xml" not in response.headers.get("content-type", "").lower():
        return None
    try:
        return xmlRoot(response.body, MAX_SOAP_BYTES)
    except (ValueError, ET.ParseError):
        return None


class OnvifSession:
    """Authenticated SOAP 1.2 to one pinned device address.

    Passwords are never sent in clear: WS-UsernameToken uses PasswordDigest and HTTP uses
    Digest. Service XAddrs only contribute their path; requests always go to the
    configured host and port, so a device cannot redirect the session elsewhere.
    """

    def __init__(self, config, transport, certificatePem=""):
        self.config, self.transport = config, transport
        self.certificatePem = certificatePem
        self.context, self.pinned = None, None
        if config.onvifHttps:
            self.context, self.pinned = pinnedTlsContext(certificatePem) if certificatePem else (verifiedTlsContext(), None)
        self.clockOffset = 0.0
        self.paths = {"tds": config.onvifPath or DEFAULT_DEVICE_PATH}

    def clone(self, stop):
        """Same device session over an independent, separately cancellable transport."""
        session = copy.copy(self)
        session.config = dataclasses.replace(self.config)
        session.paths = dict(self.paths)
        session.transport = Transport(session.config, stop)
        session.transport.address = self.transport.address
        return session

    def setPath(self, prefix, xaddr):
        try:
            path = urlsplit(xaddr).path
        except ValueError:
            return
        if path.startswith("/"):
            self.paths[prefix] = path

    def syncClock(self):
        """Align WS-UsernameToken timestamps with the device clock (unauthenticated read)."""
        try:
            response = self.call("tds", "GetSystemDateAndTime", authenticated=False)
            utc = response.find(f".//{{{NS['tt']}}}UTCDateTime")
            parts = {localName(e.tag): int(e.text) for e in utc.iter() if (e.text or "").strip().isdigit()}
            device = datetime.datetime(
                parts["Year"],
                parts["Month"],
                parts["Day"],
                parts["Hour"],
                parts["Minute"],
                parts["Second"],
                tzinfo=datetime.timezone.utc,
            )
        except (OnvifFault, AttributeError, KeyError, ValueError, TypeError):
            return
        self.clockOffset = (device - datetime.datetime.now(datetime.timezone.utc)).total_seconds()

    def loadServices(self):
        """Return {prefix: (xaddr, version)} from GetServices, falling back to GetCapabilities."""
        try:
            services = self.servicesFromGetServices()
        except OnvifFault:
            services = self.servicesFromCapabilities()
        for prefix, (xaddr, _) in services.items():
            self.setPath(prefix, xaddr)
        return services

    def servicesFromGetServices(self):
        services = {}
        response = self.call("tds", "GetServices", "<tds:IncludeCapability>false</tds:IncludeCapability>")
        for service in response:
            prefix = SERVICES.get(service.findtext(f"{{{DEVICE}}}Namespace") or "")
            if not prefix:
                continue
            version = service.find(f"{{{DEVICE}}}Version")
            number = ".".join(version.findtext(f"{{{NS['tt']}}}{part}") or "?" for part in ("Major", "Minor")) if version is not None else "?"
            services[prefix] = (service.findtext(f"{{{DEVICE}}}XAddr") or "", number)
        return services

    def servicesFromCapabilities(self):
        services = {}
        response = self.call("tds", "GetCapabilities", "<tds:Category>All</tds:Category>")
        for element in response.iter():
            prefix = CAPABILITY_SERVICES.get(localName(element.tag))
            xaddr = element.findtext(f"{{{NS['tt']}}}XAddr")
            if prefix and xaddr:
                services[prefix] = (xaddr, "from GetCapabilities")
        return services

    # ---- event pull points (WS-BaseNotification subscription manager) -------------
    def createPullPoint(self, termination="PT60S"):
        body = f"<tev:InitialTerminationTime>{termination}</tev:InitialTerminationTime>"
        response = self.call("tev", "CreatePullPointSubscription", body)
        reference = response.find(f"{{{NS['tev']}}}SubscriptionReference")
        address = reference.findtext(f"{{{NS['wsa']}}}Address") if reference is not None else ""
        if not address:
            raise OnvifFault(200, reason="No SubscriptionReference address")
        params = reference.find(f"{{{NS['wsa']}}}ReferenceParameters")
        extra = "".join(ET.tostring(child, encoding="unicode") for child in params) if params is not None else ""
        # Only the path is used: the subscription is always reached on the configured host.
        return {"address": address, "path": urlsplit(address).path or self.paths["tev"], "extra": extra}

    def subscriptionCall(self, pull, prefix, operation, body, action):
        header = f"<wsa:Action>{action}</wsa:Action><wsa:To>{escape(pull['address'])}</wsa:To>{pull['extra']}"
        return self.call(prefix, operation, body, path=pull["path"], header=header, action=action)

    def pullMessages(self, pull, timeout="PT2S", limit=50):
        body = f"<tev:Timeout>{timeout}</tev:Timeout><tev:MessageLimit>{limit}</tev:MessageLimit>"
        response = self.subscriptionCall(pull, "tev", "PullMessages", body, PULL)
        return response.findall(f"{{{NS['wsnt']}}}NotificationMessage")

    def unsubscribe(self, pull):
        # Best effort: the subscription's termination time cleans up anyway.
        with contextlib.suppress(Exception):
            self.subscriptionCall(pull, "wsnt", "Unsubscribe", "", UNSUBSCRIBE)

    # ---- SOAP -----------------------------------------------------------------------
    def securityHeader(self):
        nonce = os.urandom(16)
        created = (datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(seconds=self.clockOffset)).strftime("%Y-%m-%dT%H:%M:%SZ")
        digest = base64.b64encode(hashlib.sha1(nonce + created.encode() + self.config.password.encode()).digest()).decode()
        return (
            f'<wsse:Security xmlns:wsse="{WSSE}" xmlns:wsu="{WSU}" s:mustUnderstand="1">'
            f"<wsse:UsernameToken><wsse:Username>{escape(self.config.username)}</wsse:Username>"
            f'<wsse:Password Type="{DIGEST_TYPE}">{digest}</wsse:Password>'
            f'<wsse:Nonce EncodingType="{NONCE_TYPE}">{base64.b64encode(nonce).decode()}</wsse:Nonce>'
            f"<wsu:Created>{created}</wsu:Created></wsse:UsernameToken></wsse:Security>"
        )

    def envelope(self, body, header):
        return (
            f'<?xml version="1.0" encoding="UTF-8"?><s:Envelope xmlns:s="{SOAP}" {ENVELOPE_NAMESPACES}>'
            f"<s:Header>{header}</s:Header><s:Body>{body}</s:Body></s:Envelope>"
        ).encode()

    def call(self, prefix, operation, body="", authenticated=True, path=None, header="", action=None):
        """Return the response Body child; raise OnvifFault for HTTP errors and SOAP faults."""
        path = path or self.paths.get(prefix)
        if not path:
            raise OnvifFault(0, subcode="NoSuchService")
        action = action or f"{NS[prefix]}/{operation}"
        security = self.securityHeader() if authenticated and self.config.username else ""
        payload = self.envelope(f"<{prefix}:{operation}>{body}</{prefix}:{operation}>", security + header)
        contentType = f'Content-Type: application/soap+xml; charset=utf-8; action="{action}"'
        target = (self.transport, self.config.onvifPort, self.config.onvifHttps)
        response = self.send(target, "POST", path, [contentType], payload, MAX_SOAP_BYTES)
        root = xmlBody(response)
        if response.status != 200 or root is None or root.find(f".//{{{SOAP}}}Fault") is not None:
            raise faultFrom(response.status, root)
        body = root.find(f"{{{SOAP}}}Body")
        return body[0] if body is not None and len(body) else body

    # ---- HTTP -----------------------------------------------------------------------
    def open(self, transport, port, secure):
        if not secure:
            return transport.connect(port)
        sock = transport.tls(port, self.context or verifiedTlsContext())
        return checkPinned(sock, self.pinned) if self.pinned else sock

    def send(self, target, method, path, headers, payload, limit):
        transport, port, secure = target
        sock = self.open(transport, port, secure)
        try:
            lines = [f"{method} {path} HTTP/1.1", f"Host: {hostAuthority(self.config.host)}:{port}", "Connection: close", f"User-Agent: {USER_AGENT}", *headers]
            if method == "POST":
                lines.append(f"Content-Length: {len(payload)}")
            sock.sendall(("\r\n".join(lines) + "\r\n\r\n").encode("ascii") + payload)
            return readResponse(sock, transport, limit)
        finally:
            sock.close()

    def transfer(self, method, uri, payload=b"", contentType="application/octet-stream"):
        """HTTP GET/POST to a device-provided URI (firmware, backup, restore) with HTTP Digest.

        The URI must name the configured host, so a device cannot redirect an upload or
        download to another machine. Transfers get a longer deadline than SOAP calls.
        """
        parts = urlsplit(uri)
        if parts.scheme not in ("http", "https") or (parts.hostname or "").lower() != self.config.host.lower():
            raise ValueError("Device URI must point to the configured host over HTTP(S).")
        secure = parts.scheme == "https"
        path = (parts.path or "/") + (f"?{parts.query}" if parts.query else "")
        transport = Transport(dataclasses.replace(self.config, timeout=max(self.config.timeout, TRANSFER_TIMEOUT_SECONDS)), self.transport.stop)
        transport.address = self.transport.address
        target = (transport, parts.port or (443 if secure else 80), secure)
        headers = [f"Content-Type: {contentType}"] if method == "POST" else []
        response = self.send(target, method, path, headers, payload, MAX_TRANSFER_BYTES)
        challenge = response.headers.get("www-authenticate", "")
        if response.status == 401 and challenge.lower().startswith("digest") and self.config.username:
            authorization = digestAuthorization(challenge, method, path, self.config.username, self.config.password)
            response = self.send(target, method, path, headers + [f"Authorization: {authorization}"], payload, MAX_TRANSFER_BYTES)
        if response.status not in (200, 201, 204):
            raise OnvifFault(response.status, reason=f"HTTP {response.status} from device transfer URI")
        return response.body
