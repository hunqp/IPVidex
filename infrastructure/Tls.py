"""Self-signed TLS certificate for the managed MediaMTX servers (RTMPS / HTTPS).

One certificate is generated per bind address and cached under the app data
directory, so the .crt a user exports and imports into a camera stays valid
across restarts. The private key never leaves the machine.
"""

import datetime
import ipaddress
from pathlib import Path

from core.Paths import DATA_ROOT


def _folder():
    path = DATA_ROOT / "tls"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _safe(address):
    return address.replace(":", "_").replace("/", "_")


def ensureCertificate(address):
    """Return (certPath, keyPath) as strings for a self-signed cert covering `address`."""
    folder = _folder()
    cert = folder / f"cert-{_safe(address)}.crt"
    key = folder / f"cert-{_safe(address)}.key"
    if not (cert.is_file() and key.is_file()):
        _generate(cert, key, address)
    return str(cert), str(key)


def _generate(certPath: Path, keyPath: Path, address):
    from cryptography import x509
    from cryptography.x509.oid import NameOID
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "IPVidex")])
    altNames = [x509.DNSName("localhost")]
    for value in dict.fromkeys([address, "127.0.0.1"]):
        try:
            altNames.append(x509.IPAddress(ipaddress.ip_address(value)))
        except ValueError:
            altNames.append(x509.DNSName(value))
    now = datetime.datetime.now(datetime.timezone.utc)
    certificate = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - datetime.timedelta(days=1))
        .not_valid_after(now + datetime.timedelta(days=3650))
        .add_extension(x509.SubjectAlternativeName(altNames), critical=False)
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
        .sign(key, hashes.SHA256())
    )
    keyPath.write_bytes(
        key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.TraditionalOpenSSL,
            serialization.NoEncryption(),
        )
    )
    certPath.write_bytes(certificate.public_bytes(serialization.Encoding.PEM))
