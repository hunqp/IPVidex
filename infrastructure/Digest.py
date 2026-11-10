"""HTTP/RTSP Digest access authentication (RFC 7616): MD5 and SHA-256, qop=auth."""

import hashlib
import os
from urllib.request import parse_http_list, parse_keqv_list

HASHES = {"MD5": "md5", "MD5-SESS": "md5", "SHA-256": "sha256", "SHA-256-SESS": "sha256"}


def quoted(value):
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def parseChallenge(challenge):
    """Fields of a 'Digest ...' challenge plus its upper-case algorithm; reject what is unsupported."""
    fields = parse_keqv_list(parse_http_list(challenge.partition(" ")[2]))
    algorithm = fields.get("algorithm", "MD5").upper()
    if algorithm not in HASHES:
        raise ValueError("Unsupported Digest algorithm")
    qop = fields.get("qop", "")
    if qop and "auth" not in [item.strip() for item in qop.split(",")]:
        raise ValueError("Unsupported Digest qop")
    return fields, algorithm


def digestAuthorization(challenge, method, uri, username, password, nonceCount=1):
    """Authorization header value answering a WWW-Authenticate Digest challenge."""
    fields, algorithm = parseChallenge(challenge)

    def digest(value):
        return hashlib.new(HASHES[algorithm], value.encode()).hexdigest()

    nonce, realm, qop = fields.get("nonce", ""), fields.get("realm", ""), fields.get("qop", "")
    cnonce, nc = os.urandom(12).hex(), f"{nonceCount:08x}"
    ha1 = digest(f"{username}:{realm}:{password}")
    if algorithm.endswith("-SESS"):
        ha1 = digest(f"{ha1}:{nonce}:{cnonce}")
    ha2 = digest(f"{method}:{uri}")
    response = digest(f"{ha1}:{nonce}:{nc}:{cnonce}:auth:{ha2}" if qop else f"{ha1}:{nonce}:{ha2}")
    parts = [f"{key}={quoted(value)}" for key, value in (("username", username), ("realm", realm), ("nonce", nonce), ("uri", uri), ("response", response))]
    # MD5 is implicit when the challenge omits algorithm; some cameras reject an unsolicited field.
    if "algorithm" in fields:
        parts.append(f"algorithm={algorithm}")
    if qop:
        parts += ["qop=auth", f"nc={nc}", f"cnonce={quoted(cnonce)}"]
    elif algorithm.endswith("-SESS"):
        parts.append(f"cnonce={quoted(cnonce)}")
    if "opaque" in fields:
        parts.append(f"opaque={quoted(fields['opaque'])}")
    return "Digest " + ", ".join(parts)
