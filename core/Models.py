"""Connection settings for one device: host, session account and ONVIF endpoint."""

from dataclasses import dataclass, field
import ipaddress
import re
from urllib.parse import urlsplit


@dataclass
class Config:
    host: str
    username: str = field(default="", repr=False)
    password: str = field(default="", repr=False)
    timeout: float = 2.0
    onvifPort: int = 80
    onvifPath: str = "/onvif/device_service"
    onvifHttps: bool = False

    def validate(self):
        self.host = self.host.strip()
        try:
            ipaddress.ip_address(self.host)
        except ValueError:
            if (
                re.fullmatch(r"[0-9.]+", self.host)
                or len(self.host) > 253
                or not all(re.fullmatch(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?", x) for x in self.host.rstrip(".").split("."))
            ):
                raise ValueError("Invalid IP/hostname. Enter a host without URL or port.") from None
        if not 0.2 <= self.timeout <= 10:
            raise ValueError("Timeout must be 0.2–10 seconds.")
        if bool(self.username) != bool(self.password):
            raise ValueError("Supply both username and password, or leave both empty.")
        if not 1 <= self.onvifPort <= 65535:
            raise ValueError("ONVIF port must be between 1 and 65535.")
        path = self.onvifPath
        if path and (
            not path.startswith("/") or path.startswith("//") or any(ord(c) < 33 or ord(c) == 127 for c in path) or urlsplit(path).netloc or "#" in path
        ):
            raise ValueError("Endpoint must be a local path beginning with /, without spaces or control characters.")
        return self
