"""ODM-style ONVIF device management: read and change device, network, time, media and imaging settings.

Settings are changed by editing the element the device returned and sending it back, so
fields this tool does not expose (multicast, session timeout, vendor extensions) and the
schema element order are preserved.
"""

import copy
import datetime
import ipaddress
import re
import time
import xml.etree.ElementTree as ET
from urllib.parse import quote
from xml.sax.saxutils import escape
from infrastructure.Network import hostAuthority
from infrastructure.Onvif import NS, localName, scopeValues

MAX_UPLOAD_DELAY_SECONDS = 60.0
DURATION = re.compile(r"P(?:T(?:(\d+)H)?(?:(\d+)M)?(?:(\d+(?:\.\d+)?)S)?)?")

TT = NS["tt"]
for _prefix, _uri in NS.items():
    ET.register_namespace(_prefix, _uri)


def child(element, path):
    """Find by '/'-separated tt: local names."""
    if element is None:
        return None
    return element.find("/".join(f"{{{TT}}}{part}" for part in path.split("/")))


def text(element, path, default=""):
    found = child(element, path)
    return (found.text or "").strip() if found is not None else default


def number(element, path, default=0):
    try:
        return int(float(text(element, path, str(default))))
    except ValueError:
        return default


def setText(element, path, value):
    found = child(element, path)
    if found is not None:
        found.text = str(value)
    return found is not None


def serialize(element, tag):
    clone = copy.deepcopy(element)
    clone.tag = tag
    return ET.tostring(clone, encoding="unicode")


def bounds(element, path):
    node = child(element, path)
    return (number(node, "Min"), number(node, "Max")) if node is not None else None


def boolean(value):
    return "true" if value else "false"


class OnvifDevice:
    def __init__(self, session):
        self.session = session
        self.services = {}

    def connect(self):
        self.session.syncClock()
        self.services = self.session.loadServices()
        return self

    # ---- identification -------------------------------------------------------
    def scopes(self):
        response = self.session.call("tds", "GetScopes")
        return [(text(scope, "ScopeDef"), text(scope, "ScopeItem")) for scope in response.findall(f"{{{NS['tds']}}}Scopes")]

    def identification(self):
        info = self.session.call("tds", "GetDeviceInformation")
        values = {localName(e.tag): (e.text or "").strip() for e in info}
        scopes = [item for _, item in self.scopes()]

        nic = self.session.call("tds", "GetNetworkInterfaces").find(f"{{{NS['tds']}}}NetworkInterfaces")
        address = text(nic, "IPv4/Config/Manual/Address") or text(nic, "IPv4/Config/FromDHCP/Address")
        host = hostAuthority(self.session.config.host)
        return {
            "Name": scopeValues(scopes, "name"),
            "Location": scopeValues(scopes, "location"),
            "Manufacturer": values.get("Manufacturer", ""),
            "Model": values.get("Model", ""),
            "Firmware version": values.get("FirmwareVersion", ""),
            "Serial number": values.get("SerialNumber", ""),
            "Hardware ID": values.get("HardwareId", ""),
            "IP address": address,
            "MAC address": text(nic, "Info/HwAddress"),
            "ONVIF version": self.services.get("tds", ("", "?"))[1],
            "Device service URI": f"{'https' if self.session.config.onvifHttps else 'http'}://{host}:{self.session.config.onvifPort}{self.session.paths['tds']}",
        }

    def setIdentification(self, name, location):
        configurable = [item for definition, item in self.scopes() if definition == "Configurable"]
        keep = [item for item in configurable if not item.startswith(("onvif://www.onvif.org/name/", "onvif://www.onvif.org/location/"))]
        if name:
            keep.append("onvif://www.onvif.org/name/" + quote(name.strip(), safe="/"))
        for part in (p.strip() for p in location.split(",")):
            if part:
                keep.append("onvif://www.onvif.org/location/" + quote(part, safe="/"))
        body = "".join(f"<tds:Scopes>{escape(item)}</tds:Scopes>" for item in keep)
        self.session.call("tds", "SetScopes", body)

    # ---- time -----------------------------------------------------------------
    def timeSettings(self):
        response = self.session.call("tds", "GetSystemDateAndTime")
        value = response.find(f"{{{NS['tds']}}}SystemDateAndTime")

        def stamp(path):
            node = child(value, path)
            if node is None:
                return None
            try:
                return datetime.datetime(
                    number(node, "Date/Year"),
                    number(node, "Date/Month"),
                    number(node, "Date/Day"),
                    number(node, "Time/Hour"),
                    number(node, "Time/Minute"),
                    number(node, "Time/Second"),
                )
            except ValueError:
                return None

        return {
            "mode": text(value, "DateTimeType", "Manual"),
            "daylight": text(value, "DaylightSavings") == "true",
            "timeZone": text(value, "TimeZone/TZ"),
            "utc": stamp("UTCDateTime"),
            "local": stamp("LocalDateTime"),
        }

    def setTime(self, mode, daylight, timeZone=None, utc=None):
        """timeZone=None keeps the device zone. Devices may report a display form (e.g.
        "+07-7:00") they cannot parse back, so it is only sent when the user changed it."""
        body = f"<tds:DateTimeType>{'NTP' if mode == 'NTP' else 'Manual'}</tds:DateTimeType><tds:DaylightSavings>{boolean(daylight)}</tds:DaylightSavings>"
        if timeZone is not None:
            body += f"<tds:TimeZone><tt:TZ>{escape(timeZone)}</tt:TZ></tds:TimeZone>"
        if mode != "NTP" and utc is not None:
            body += (
                "<tds:UTCDateTime><tt:Time>"
                f"<tt:Hour>{utc.hour}</tt:Hour><tt:Minute>{utc.minute}</tt:Minute><tt:Second>{utc.second}</tt:Second>"
                "</tt:Time><tt:Date>"
                f"<tt:Year>{utc.year}</tt:Year><tt:Month>{utc.month}</tt:Month><tt:Day>{utc.day}</tt:Day>"
                "</tt:Date></tds:UTCDateTime>"
            )
        self.session.call("tds", "SetSystemDateAndTime", body)

    # ---- network --------------------------------------------------------------
    def networkSettings(self):
        nic = self.session.call("tds", "GetNetworkInterfaces").find(f"{{{NS['tds']}}}NetworkInterfaces")
        dhcp = text(nic, "IPv4/Config/DHCP") == "true"
        source = "FromDHCP" if dhcp else "Manual"
        dns = self.session.call("tds", "GetDNS").find(f"{{{NS['tds']}}}DNSInformation")
        ntp = self.session.call("tds", "GetNTP").find(f"{{{NS['tds']}}}NTPInformation")
        gateway = self.session.call("tds", "GetNetworkDefaultGateway")
        protocols = self.session.call("tds", "GetNetworkProtocols")
        mode = self.session.call("tds", "GetDiscoveryMode")

        def servers(info, manual, fromDhcp):
            group = fromDhcp if text(info, "FromDHCP") == "true" else manual
            return (
                [text(entry, "IPv4Address") or text(entry, "DNSname") or text(entry, "IPv6Address") for entry in info.findall(f"{{{TT}}}{group}")]
                if info is not None
                else []
            )

        return {
            "token": nic.get("token", "") if nic is not None else "",
            "mac": text(nic, "Info/HwAddress"),
            "dhcp": dhcp,
            "address": text(nic, f"IPv4/Config/{source}/Address"),
            "prefix": number(nic, f"IPv4/Config/{source}/PrefixLength", 24),
            "gateway": ", ".join(e.text or "" for e in gateway.iter(f"{{{TT}}}IPv4Address")),
            "hostname": text(self.session.call("tds", "GetHostname").find(f"{{{NS['tds']}}}HostnameInformation"), "Name"),
            "dnsFromDhcp": text(dns, "FromDHCP") == "true",
            "dns": ", ".join(servers(dns, "DNSManual", "DNSFromDHCP")),
            "ntpFromDhcp": text(ntp, "FromDHCP") == "true",
            "ntp": ", ".join(servers(ntp, "NTPManual", "NTPFromDHCP")),
            "discoverable": (mode.findtext(f"{{{NS['tds']}}}DiscoveryMode") or "") == "Discoverable",
            "protocols": [
                {
                    "name": text(p, "Name"),
                    "enabled": text(p, "Enabled") == "true",
                    "ports": [int(e.text) for e in p.findall(f"{{{TT}}}Port") if (e.text or "").isdigit()],
                }
                for p in protocols.findall(f"{{{NS['tds']}}}NetworkProtocols")
            ],
        }

    @staticmethod
    def addressEntry(kind, value):
        value = value.strip()
        try:
            return f"<tt:Type>IPv4</tt:Type><tt:IPv4Address>{ipaddress.IPv4Address(value)}</tt:IPv4Address>"
        except ValueError:
            if kind != "NTP":
                raise ValueError(f"Invalid IPv4 address: {value}") from None
        return f"<tt:Type>DNS</tt:Type><tt:DNSname>{escape(value)}</tt:DNSname>"

    def setNetwork(self, old, new):
        """Apply only changed groups; the interface address goes last. Returns True if a reboot is needed."""
        reboot = False
        if new["hostname"] != old["hostname"]:
            self.session.call("tds", "SetHostname", f"<tds:Name>{escape(new['hostname'])}</tds:Name>")
        if (new["dnsFromDhcp"], new["dns"]) != (old["dnsFromDhcp"], old["dns"]):
            manual = "".join(f"<tds:DNSManual>{self.addressEntry('DNS', v)}</tds:DNSManual>" for v in new["dns"].split(",") if v.strip())
            self.session.call("tds", "SetDNS", f"<tds:FromDHCP>{boolean(new['dnsFromDhcp'])}</tds:FromDHCP>" + ("" if new["dnsFromDhcp"] else manual))
        if (new["ntpFromDhcp"], new["ntp"]) != (old["ntpFromDhcp"], old["ntp"]):
            manual = "".join(f"<tds:NTPManual>{self.addressEntry('NTP', v)}</tds:NTPManual>" for v in new["ntp"].split(",") if v.strip())
            self.session.call("tds", "SetNTP", f"<tds:FromDHCP>{boolean(new['ntpFromDhcp'])}</tds:FromDHCP>" + ("" if new["ntpFromDhcp"] else manual))
        if new["protocols"] != old["protocols"]:
            body = "".join(
                f"<tds:NetworkProtocols><tt:Name>{escape(p['name'])}</tt:Name><tt:Enabled>{boolean(p['enabled'])}</tt:Enabled>"
                + "".join(f"<tt:Port>{port}</tt:Port>" for port in p["ports"])
                + "</tds:NetworkProtocols>"
                for p in new["protocols"]
            )
            self.session.call("tds", "SetNetworkProtocols", body)
        if new["discoverable"] != old["discoverable"]:
            mode = "Discoverable" if new["discoverable"] else "NonDiscoverable"
            self.session.call("tds", "SetDiscoveryMode", f"<tds:DiscoveryMode>{mode}</tds:DiscoveryMode>")
        if not new["dhcp"] and new["gateway"] != old["gateway"] and new["gateway"].strip():
            body = "".join(f"<tds:IPv4Address>{escape(v.strip())}</tds:IPv4Address>" for v in new["gateway"].split(",") if v.strip())
            self.session.call("tds", "SetNetworkDefaultGateway", body)
        if (new["dhcp"], new["address"], new["prefix"]) != (old["dhcp"], old["address"], old["prefix"]):
            ipv4 = "<tt:Enabled>true</tt:Enabled>" + (
                "<tt:DHCP>true</tt:DHCP>"
                if new["dhcp"]
                else f"<tt:Manual><tt:Address>{escape(new['address'])}</tt:Address>"
                f"<tt:PrefixLength>{int(new['prefix'])}</tt:PrefixLength></tt:Manual><tt:DHCP>false</tt:DHCP>"
            )
            response = self.session.call(
                "tds",
                "SetNetworkInterfaces",
                f"<tds:InterfaceToken>{escape(old['token'])}</tds:InterfaceToken>"
                f"<tds:NetworkInterface><tt:Enabled>true</tt:Enabled><tt:IPv4>{ipv4}</tt:IPv4></tds:NetworkInterface>",
            )
            reboot = (response.findtext(f"{{{NS['tds']}}}RebootNeeded") or "") == "true"
        return reboot

    def reboot(self):
        response = self.session.call("tds", "SystemReboot")
        return response.findtext(f"{{{NS['tds']}}}Message") or ""

    # ---- media profiles -------------------------------------------------------
    def profiles(self):
        response = self.session.call("trt", "GetProfiles")
        rows = []
        for p in response.findall(f"{{{NS['trt']}}}Profiles"):
            vsc, vec = child(p, "VideoSourceConfiguration"), child(p, "VideoEncoderConfiguration")
            rows.append(
                {
                    "token": p.get("token", ""),
                    "name": text(p, "Name"),
                    "fixed": p.get("fixed", "false") == "true",
                    "vsc": vsc.get("token", "") if vsc is not None else "",
                    "source": text(vsc, "SourceToken"),
                    "vec": vec.get("token", "") if vec is not None else "",
                    "encoding": text(vec, "Encoding"),
                    "resolution": f"{text(vec, 'Resolution/Width')}×{text(vec, 'Resolution/Height')}" if vec is not None else "",
                }
            )
        return rows

    def streamUri(self, profileToken):
        response = self.session.call(
            "trt",
            "GetStreamUri",
            "<trt:StreamSetup><tt:Stream>RTP-Unicast</tt:Stream><tt:Transport><tt:Protocol>RTSP</tt:Protocol>"
            f"</tt:Transport></trt:StreamSetup><trt:ProfileToken>{escape(profileToken)}</trt:ProfileToken>",
        )
        return response.findtext(f".//{{{TT}}}Uri") or ""

    def createProfile(self, name):
        response = self.session.call("trt", "CreateProfile", f"<trt:Name>{escape(name)}</trt:Name>")
        profile = response.find(f"{{{NS['trt']}}}Profile")
        token = profile.get("token", "") if profile is not None else ""
        for kind in ("VideoSource", "VideoEncoder"):
            compatible = self.session.call("trt", f"GetCompatible{kind}Configurations", f"<trt:ProfileToken>{escape(token)}</trt:ProfileToken>")
            first = next(iter(compatible), None)
            if first is not None:
                self.session.call(
                    "trt",
                    f"Add{kind}Configuration",
                    f"<trt:ProfileToken>{escape(token)}</trt:ProfileToken><trt:ConfigurationToken>{escape(first.get('token', ''))}</trt:ConfigurationToken>",
                )
        return token

    def deleteProfile(self, token):
        self.session.call("trt", "DeleteProfile", f"<trt:ProfileToken>{escape(token)}</trt:ProfileToken>")

    # ---- video encoder --------------------------------------------------------
    def encoder(self, configurationToken, profileToken):
        config = self.session.call(
            "trt", "GetVideoEncoderConfiguration", f"<trt:ConfigurationToken>{escape(configurationToken)}</trt:ConfigurationToken>"
        ).find(f"{{{NS['trt']}}}Configuration")
        options = self.session.call(
            "trt",
            "GetVideoEncoderConfigurationOptions",
            f"<trt:ConfigurationToken>{escape(configurationToken)}</trt:ConfigurationToken><trt:ProfileToken>{escape(profileToken)}</trt:ProfileToken>",
        ).find(f"{{{NS['trt']}}}Options")
        encodings = {}
        for name in ("JPEG", "MPEG4", "H264"):
            node = child(options, name)
            if node is None:
                continue
            encodings[name] = {
                "resolutions": [(number(r, "Width"), number(r, "Height")) for r in node.findall(f"{{{TT}}}ResolutionsAvailable")],
                "fps": bounds(node, "FrameRateRange"),
                "interval": bounds(node, "EncodingIntervalRange"),
                "gov": bounds(node, "GovLengthRange"),
                "bitrate": bounds(options, f"Extension/{name}/BitrateRange"),
            }
        values = {
            "encoding": text(config, "Encoding"),
            "width": number(config, "Resolution/Width"),
            "height": number(config, "Resolution/Height"),
            "quality": number(config, "Quality"),
            "fps": number(config, "RateControl/FrameRateLimit"),
            "interval": number(config, "RateControl/EncodingInterval", 1),
            "bitrate": number(config, "RateControl/BitrateLimit"),
            "gov": number(config, "H264/GovLength") or number(config, "MPEG4/GovLength"),
        }
        return config, {"quality": bounds(options, "QualityRange"), "encodings": encodings}, values

    def setEncoder(self, config, values):
        config = copy.deepcopy(config)
        setText(config, "Encoding", values["encoding"])
        setText(config, "Resolution/Width", values["width"])
        setText(config, "Resolution/Height", values["height"])
        setText(config, "Quality", values["quality"])
        setText(config, "RateControl/FrameRateLimit", values["fps"])
        setText(config, "RateControl/EncodingInterval", values["interval"])
        setText(config, "RateControl/BitrateLimit", values["bitrate"])
        codec = values["encoding"] if values["encoding"] in ("H264", "MPEG4") else None
        if codec:
            node = child(config, codec)
            if node is None:
                # Schema order: ... RateControl, MPEG4, H264, Multicast, SessionTimeout.
                node = ET.Element(f"{{{TT}}}{codec}")
                ET.SubElement(node, f"{{{TT}}}GovLength")
                ET.SubElement(node, f"{{{TT}}}{codec}Profile").text = "Main" if codec == "H264" else "SP"
                anchor = child(config, "Multicast")
                if anchor is None:
                    anchor = child(config, "SessionTimeout")
                position = list(config).index(anchor) if anchor is not None else len(config)
                config.insert(position, node)
            setText(config, f"{codec}/GovLength", values["gov"])
        self.session.call(
            "trt",
            "SetVideoEncoderConfiguration",
            serialize(config, f"{{{NS['trt']}}}Configuration") + "<trt:ForcePersistence>true</trt:ForcePersistence>",
        )

    # ---- imaging --------------------------------------------------------------
    NUMERIC = ("Brightness", "ColorSaturation", "Contrast", "Sharpness")
    MODES = (
        ("IrCutFilter", "IrCutFilterModes"),
        ("BacklightCompensation/Mode", "BacklightCompensation/Mode"),
        ("WideDynamicRange/Mode", "WideDynamicRange/Mode"),
        ("WhiteBalance/Mode", "WhiteBalance/Mode"),
        ("Exposure/Mode", "Exposure/Mode"),
    )
    # Fallback choices when the device reports the setting but GetOptions does not
    # enumerate its modes (common on budget cameras), so the combo still appears.
    MODE_DEFAULTS = {
        "IrCutFilter": ["ON", "OFF", "AUTO"],
        "BacklightCompensation/Mode": ["ON", "OFF"],
        "WideDynamicRange/Mode": ["ON", "OFF"],
        "WhiteBalance/Mode": ["AUTO", "MANUAL"],
        "Exposure/Mode": ["AUTO", "MANUAL"],
    }
    # Numeric parameters that only apply under a specific mode. Each is:
    # (settings path, options range path, parent mode path, modes that enable it, fallback bounds).
    SUBPARAMS = (
        ("Exposure/ExposureTime", "Exposure/ExposureTimeRange", "Exposure/Mode", ("MANUAL",), None),
        ("Exposure/Gain", "Exposure/GainRange", "Exposure/Mode", ("MANUAL",), (0, 100)),
        ("Exposure/Iris", "Exposure/IrisRange", "Exposure/Mode", ("MANUAL",), None),
        ("WhiteBalance/CrGain", "WhiteBalance/YrGain", "WhiteBalance/Mode", ("MANUAL",), (0, 255)),
        ("WhiteBalance/CbGain", "WhiteBalance/YbGain", "WhiteBalance/Mode", ("MANUAL",), (0, 255)),
        ("WideDynamicRange/Level", "WideDynamicRange/Level", "WideDynamicRange/Mode", ("ON",), (0, 100)),
        ("BacklightCompensation/Level", "BacklightCompensation/Level", "BacklightCompensation/Mode", ("ON",), (0, 100)),
    )

    def imaging(self, sourceToken):
        if "timg" not in self.services:
            raise ValueError("Imaging service not advertised by the device.")
        token = f"<timg:VideoSourceToken>{escape(sourceToken)}</timg:VideoSourceToken>"
        settings = self.session.call("timg", "GetImagingSettings", token).find(f"{{{NS['timg']}}}ImagingSettings")
        options = self.session.call("timg", "GetOptions", token).find(f"{{{NS['timg']}}}ImagingOptions")
        fields = []
        for name in self.NUMERIC:
            if child(settings, name) is not None and bounds(options, name):
                fields.append((name, "range", bounds(options, name), number(settings, name), None, None))
        for path, optionPath in self.MODES:
            if child(settings, path) is not None:
                choices = [e.text for e in options.findall("/".join(f"{{{TT}}}{p}" for p in optionPath.split("/")))]
                choices = [c for c in choices if c] or list(self.MODE_DEFAULTS.get(path, []))
                current = text(settings, path)
                if current and current not in choices:
                    choices = [current] + choices
                if choices:
                    fields.append((path, "choice", choices, current, None, None))
        for path, optionPath, parent, active, fallback in self.SUBPARAMS:
            if child(settings, path) is not None:
                rng = bounds(options, optionPath) or fallback
                if rng and rng[1] > rng[0]:
                    fields.append((path, "range", rng, number(settings, path), parent, tuple(active)))
        return settings, fields

    def setImaging(self, sourceToken, settings, values):
        settings = copy.deepcopy(settings)
        for path, value in values.items():
            setText(settings, path, value)
        self.session.call(
            "timg",
            "SetImagingSettings",
            f"<timg:VideoSourceToken>{escape(sourceToken)}</timg:VideoSourceToken>"
            + serialize(settings, f"{{{NS['timg']}}}ImagingSettings")
            + "<timg:ForcePersistence>true</timg:ForcePersistence>",
        )

    # ---- ptz ------------------------------------------------------------------
    def ptzSupported(self):
        return "tptz" in self.services

    def ptzMove(self, profileToken, pan, tilt, zoom):
        """Continuous move. pan/tilt/zoom are velocities in [-1, 1]; 0 means that axis is idle."""
        if "tptz" not in self.services:
            raise ValueError("PTZ service not advertised by the device.")
        velocity = ""
        if pan or tilt:
            velocity += f'<tt:PanTilt x="{pan}" y="{tilt}"/>'
        if zoom:
            velocity += f'<tt:Zoom x="{zoom}"/>'
        self.session.call(
            "tptz",
            "ContinuousMove",
            f"<tptz:ProfileToken>{escape(profileToken)}</tptz:ProfileToken><tptz:Velocity>{velocity}</tptz:Velocity>",
        )

    def ptzStop(self, profileToken):
        if "tptz" not in self.services:
            raise ValueError("PTZ service not advertised by the device.")
        self.session.call(
            "tptz",
            "Stop",
            f"<tptz:ProfileToken>{escape(profileToken)}</tptz:ProfileToken><tptz:PanTilt>true</tptz:PanTilt><tptz:Zoom>true</tptz:Zoom>",
        )

    def ptzPresets(self, profileToken):
        if "tptz" not in self.services:
            raise ValueError("PTZ service not advertised by the device.")
        response = self.session.call("tptz", "GetPresets", f"<tptz:ProfileToken>{escape(profileToken)}</tptz:ProfileToken>")
        return [{"token": p.get("token", ""), "name": text(p, "Name")} for p in response.findall(f"{{{NS['tptz']}}}Preset")]

    def ptzGoto(self, profileToken, presetToken):
        self.session.call(
            "tptz",
            "GotoPreset",
            f"<tptz:ProfileToken>{escape(profileToken)}</tptz:ProfileToken><tptz:PresetToken>{escape(presetToken)}</tptz:PresetToken>",
        )

    def ptzSetPreset(self, profileToken, name):
        self.session.call(
            "tptz",
            "SetPreset",
            f"<tptz:ProfileToken>{escape(profileToken)}</tptz:ProfileToken><tptz:PresetName>{escape(name)}</tptz:PresetName>",
        )

    def ptzRemovePreset(self, profileToken, presetToken):
        self.session.call(
            "tptz",
            "RemovePreset",
            f"<tptz:ProfileToken>{escape(profileToken)}</tptz:ProfileToken><tptz:PresetToken>{escape(presetToken)}</tptz:PresetToken>",
        )

    # ---- users ----------------------------------------------------------------
    LEVELS = ("Administrator", "Operator", "User")

    def users(self):
        response = self.session.call("tds", "GetUsers")
        return [{"username": text(user, "Username"), "level": text(user, "UserLevel")} for user in response.findall(f"{{{NS['tds']}}}User")]

    @staticmethod
    def userXml(tag, username, password, level):
        # ONVIF carries the password in the SOAP body; the GUI warns when the session is not HTTPS.
        password = f"<tt:Password>{escape(password)}</tt:Password>" if password else ""
        return f"<tds:{tag}><tt:Username>{escape(username)}</tt:Username>{password}<tt:UserLevel>{escape(level)}</tt:UserLevel></tds:{tag}>"

    def createUser(self, username, password, level):
        self.session.call("tds", "CreateUsers", self.userXml("User", username, password, level))

    def setUser(self, username, password, level):
        self.session.call("tds", "SetUser", self.userXml("User", username, password, level))

    def deleteUser(self, username):
        self.session.call("tds", "DeleteUsers", f"<tds:Username>{escape(username)}</tds:Username>")

    # ---- maintenance ----------------------------------------------------------
    def factoryDefault(self, kind):
        if kind not in ("Soft", "Hard"):
            raise ValueError("Factory default must be Soft or Hard.")
        self.session.call("tds", "SetSystemFactoryDefault", f"<tds:FactoryDefault>{kind}</tds:FactoryDefault>")

    def systemLog(self, kind):
        response = self.session.call("tds", "GetSystemLog", f"<tds:LogType>{'Access' if kind == 'Access' else 'System'}</tds:LogType>")
        return response.findtext(f".//{{{TT}}}String") or "(log returned as binary attachment; not displayed)"

    def supportInformation(self):
        response = self.session.call("tds", "GetSystemSupportInformation")
        return response.findtext(f".//{{{TT}}}String") or "(returned as binary attachment; not displayed)"

    def systemUris(self):
        response = self.session.call("tds", "GetSystemUris")
        return {
            "backup": response.findtext(f"{{{NS['tds']}}}SystemBackupUri") or "",
            "support": response.findtext(f"{{{NS['tds']}}}SupportInfoUri") or "",
            "logs": [e.text or "" for e in response.iter(f"{{{TT}}}Uri")],
        }

    def backup(self):
        uri = self.systemUris()["backup"]
        if not uri:
            raise ValueError("The device does not provide a system backup URI.")
        return self.session.transfer("GET", uri)

    @staticmethod
    def seconds(duration, default=0.0):
        """xs:duration such as PT5S / PT1M30S to seconds."""
        match = DURATION.fullmatch((duration or "").strip())
        if not match:
            return default
        hours, minutes, secs = (float(v) if v else 0.0 for v in match.groups())
        return hours * 3600 + minutes * 60 + secs

    def upload(self, operation, payload, contentType):
        """StartFirmwareUpgrade / StartSystemRestore, then HTTP POST to the device upload URI."""
        response = self.session.call("tds", operation)
        uri = response.findtext(f"{{{NS['tds']}}}UploadUri") or ""
        delay = self.seconds(response.findtext(f"{{{NS['tds']}}}UploadDelay"))
        downtime = self.seconds(response.findtext(f"{{{NS['tds']}}}ExpectedDownTime"), 0)
        if not uri:
            raise ValueError(f"{operation} returned no upload URI.")
        time.sleep(min(delay, MAX_UPLOAD_DELAY_SECONDS))
        self.session.transfer("POST", uri, payload, contentType)
        return downtime

    def firmwareUpgrade(self, payload):
        return self.upload("StartFirmwareUpgrade", payload, "application/octet-stream")

    def restore(self, payload):
        return self.upload("StartSystemRestore", payload, "application/octet-stream")

    # ---- certificates ---------------------------------------------------------
    def certificates(self):
        response = self.session.call("tds", "GetCertificates")
        status = {}
        try:
            states = self.session.call("tds", "GetCertificatesStatus")
            status = {text(s, "CertificateID"): text(s, "Status") == "true" for s in states.findall(f"{{{NS['tds']}}}CertificateStatus")}
        except Exception:
            pass  # status is optional on some devices
        return [
            {"id": text(cert, "CertificateID"), "enabled": status.get(text(cert, "CertificateID"), False)}
            for cert in response.findall(f"{{{NS['tds']}}}NvtCertificate")
        ]

    def setCertificateStatus(self, certificateId, enabled):
        self.session.call(
            "tds",
            "SetCertificatesStatus",
            f"<tds:CertificateStatus><tt:CertificateID>{escape(certificateId)}</tt:CertificateID>"
            f"<tt:Status>{boolean(enabled)}</tt:Status></tds:CertificateStatus>",
        )

    def createCertificate(self, certificateId, subject):
        body = (f"<tds:CertificateID>{escape(certificateId)}</tds:CertificateID>" if certificateId else "") + (
            f"<tds:Subject>{escape(subject)}</tds:Subject>" if subject else ""
        )
        self.session.call("tds", "CreateCertificate", body)

    def deleteCertificate(self, certificateId):
        self.session.call("tds", "DeleteCertificates", f"<tds:CertificateID>{escape(certificateId)}</tds:CertificateID>")

    # ---- events ---------------------------------------------------------------
    @staticmethod
    def eventRow(message):
        """(time, topic, source, data) from a wsnt:NotificationMessage."""
        topic = (message.findtext(f"{{{NS['wsnt']}}}Topic") or "").strip()
        body = message.find(f".//{{{TT}}}Message")

        def items(group):
            node = child(body, group)
            return ", ".join(f"{item.get('Name')}={item.get('Value')}" for item in node.iter(f"{{{TT}}}SimpleItem")) if node is not None else ""

        stamp = body.get("UtcTime", "") if body is not None else ""
        return stamp, topic, items("Source"), items("Data")
