import pytest
from infrastructure.Media import parseRtsp, pinnedUrl


def testDefaultPortsFollowScheme():
    assert parseRtsp("rtsp://cam/live")["port"] == 554
    assert parseRtsp("rtsps://cam/live")["port"] == 322


def testCredentialsInUrlAreDecodedAndSplitOut():
    data = parseRtsp("rtsp://admin:Admin%40123@192.0.2.1:8554/live?ch=1")
    assert (data["username"], data["password"], data["path"]) == ("admin", "Admin@123", "/live?ch=1")


@pytest.mark.parametrize("url", ["", "http://cam/live", "rtsp://cam", "rtsp://cam/live#x", "rtsp://cam/ live"])
def testRejectsInvalidUrls(url):
    with pytest.raises(ValueError):
        parseRtsp(url)


def testRejectsHostOtherThanTarget():
    with pytest.raises(ValueError):
        parseRtsp("rtsp://192.0.2.9/live", target="192.0.2.1")


def testRequiresBothCredentials():
    with pytest.raises(ValueError):
        parseRtsp("rtsp://cam/live", username="admin")


def testPinnedUrlBracketsIpv6AndQuotesCredentials():
    data = dict(username="a@b", password="p:w", port=554, path="/live 1", secure=False)
    assert pinnedUrl(data, "fe80::1") == "rtsp://a%40b:p%3Aw@[fe80::1]:554/live%201"
