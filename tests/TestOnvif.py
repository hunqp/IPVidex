import pytest
from infrastructure.Onvif import ADDRESSING, DISCOVERY, decodeScope, parseProbeMatches, xmlRoot
from services.OnvifDevice import OnvifDevice


def probeMatch(xaddrs, relatesTo="urn:uuid:1"):
    return f'''<e:Envelope xmlns:e="http://www.w3.org/2003/05/soap-envelope" xmlns:a="{ADDRESSING}" xmlns:d="{DISCOVERY}">
    <e:Header><a:RelatesTo>{relatesTo}</a:RelatesTo></e:Header><e:Body><d:ProbeMatches><d:ProbeMatch>
    <d:Scopes>onvif://www.onvif.org/name/Front%2520Door onvif://www.onvif.org/location/Gate</d:Scopes>
    <d:XAddrs>{xaddrs}</d:XAddrs></d:ProbeMatch></d:ProbeMatches></e:Body></e:Envelope>'''.encode()


def testProbeMatchUsesXaddrOfTheRespondingHost():
    devices = parseProbeMatches(probeMatch("http://192.0.2.1:8080/onvif/dev"), "urn:uuid:1", "192.0.2.1")
    assert devices == [{"address": "192.0.2.1", "port": 8080, "path": "/onvif/dev", "name": "Front Door", "location": "Gate", "hardware": ""}]


def testProbeMatchIgnoresXaddrOfAnotherHost():
    device = parseProbeMatches(probeMatch("http://203.0.113.9:8080/evil"), "urn:uuid:1", "192.0.2.1")[0]
    assert (device["address"], device["port"], device["path"]) == ("192.0.2.1", 80, "/onvif/device_service")


def testProbeMatchForAnotherProbeIsIgnored():
    assert parseProbeMatches(probeMatch("http://192.0.2.1/x", relatesTo="urn:uuid:2"), "urn:uuid:1", "192.0.2.1") == []


def testDecodeScopeUndoesRepeatedEncoding():
    assert decodeScope("Front%2520Door") == "Front Door"


def testXmlRootRejectsEntities():
    with pytest.raises(ValueError):
        xmlRoot(b'<!DOCTYPE x [<!ENTITY a "b">]><x>&a;</x>')


@pytest.mark.parametrize(
    "kind, value, expected",
    [
        ("DNS", " 192.0.2.53 ", "<tt:IPv4Address>192.0.2.53</tt:IPv4Address>"),
        ("NTP", "pool.ntp.org", "<tt:DNSname>pool.ntp.org</tt:DNSname>"),
    ],
)
def testAddressEntry(kind, value, expected):
    assert expected in OnvifDevice.addressEntry(kind, value)


@pytest.mark.parametrize("value", ["999.1.1.1", "dns.example"])
def testAddressEntryRejectsInvalidDnsServer(value):
    with pytest.raises(ValueError):
        OnvifDevice.addressEntry("DNS", value)


@pytest.mark.parametrize("duration, seconds", [("PT5S", 5), ("PT1M30S", 90), ("PT1H", 3600), ("bad", 0.0)])
def testDurationSeconds(duration, seconds):
    assert OnvifDevice.seconds(duration) == seconds
