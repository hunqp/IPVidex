import hashlib
from urllib.request import parse_http_list, parse_keqv_list
import pytest
from infrastructure.Digest import digestAuthorization


def fields(header):
    return parse_keqv_list(parse_http_list(header.partition(" ")[2]))


def md5(text):
    return hashlib.md5(text.encode()).hexdigest()


def testQopAuthResponse():
    challenge = 'Digest realm="testrealm@host.com", qop="auth,auth-int", nonce="dcd98b", opaque="5ccc"'
    sent = fields(digestAuthorization(challenge, "GET", "/dir/index.html", "Mufasa", "Circle Of Life"))
    ha1, ha2 = md5("Mufasa:testrealm@host.com:Circle Of Life"), md5("GET:/dir/index.html")
    assert sent["response"] == md5(f"{ha1}:dcd98b:00000001:{sent['cnonce']}:auth:{ha2}")
    assert (sent["qop"], sent["nc"], sent["opaque"]) == ("auth", "00000001", "5ccc")


def testOmittedAlgorithmIsNotAdded():
    header = digestAuthorization('Digest realm="r", nonce="n"', "DESCRIBE", "rtsp://cam/live", "u", "p")
    assert "algorithm=" not in header
    assert fields(header)["response"] == md5(f"{md5('u:r:p')}:n:{md5('DESCRIBE:rtsp://cam/live')}")


def testSha256AndNonceCount():
    sent = fields(digestAuthorization('Digest realm="r", nonce="n", qop="auth", algorithm=SHA-256', "GET", "/", "u", "p", 3))

    def sha(text):
        return hashlib.sha256(text.encode()).hexdigest()

    assert sent["nc"] == "00000003"
    assert sent["response"] == sha(f"{sha('u:r:p')}:n:00000003:{sent['cnonce']}:auth:{sha('GET:/')}")


def testQuotesAreEscaped():
    assert r'username="a\"b"' in digestAuthorization('Digest realm="r", nonce="n"', "GET", "/", 'a"b', "p")


@pytest.mark.parametrize("challenge", ['Digest nonce="n", algorithm=SHA-512', 'Digest nonce="n", qop="auth-int"'])
def testUnsupportedChallenges(challenge):
    with pytest.raises(ValueError):
        digestAuthorization(challenge, "GET", "/", "u", "p")
