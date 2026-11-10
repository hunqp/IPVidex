import pytest
from infrastructure.MediaMtx import API_USER, pathPattern, rtmpConfig, webRtcConfig


def testPathPatternAcceptsNestedKeysUnderPrefix():
    assert pathPattern(" /live/ ") == "~^live/[A-Za-z0-9_-]+(?:/[A-Za-z0-9_-]+)*$"


@pytest.mark.parametrize("prefix", ["", "live/../x", "live key", "live?x"])
def testPathPatternRejectsUnsafePrefixes(prefix):
    with pytest.raises(ValueError):
        pathPattern(prefix)


def testRtmpEnablesOnlyRtmp():
    config, apiPort, password = rtmpConfig("127.0.0.1", 1935, "live")
    assert config["rtmp"] and not any(config[name] for name in ("rtsp", "hls", "webrtc", "srt", "moq"))
    assert config["rtmpAddress"] == "127.0.0.1:1935" and config["rtmpEncryption"] == "no"
    assert config["apiAddress"] == f"127.0.0.1:{apiPort}"
    api = next(user for user in config["authInternalUsers"] if user["user"] == API_USER)
    assert api["pass"] == password and api["ips"] == ["127.0.0.1"]


def testRtmpsUsesCertificate():
    config, _, _ = rtmpConfig("127.0.0.1", 1936, "live", tls=("c.crt", "c.key"))
    assert (config["rtmpEncryption"], config["rtmpsAddress"], config["rtmpServerCert"]) == ("strict", "127.0.0.1:1936", "c.crt")
    assert "rtmpAddress" not in config


def testWebRtcAdvertisesListenAddress():
    config, _, _ = webRtcConfig("192.0.2.5", 8889, "live", tls=("c.crt", "c.key"))
    assert config["webrtc"] and not config["rtmp"]
    assert config["webrtcAdditionalHosts"] == ["192.0.2.5"] and config["webrtcEncryption"] is True


@pytest.mark.parametrize("address, port", [("::1", 1935), ("127.0.0.1", 0), ("127.0.0.1", 70000)])
def testRejectsInvalidListenSettings(address, port):
    with pytest.raises(ValueError):
        rtmpConfig(address, port, "live")
