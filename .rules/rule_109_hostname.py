"""Hostnames must be RFC 1123 compliant."""

import re

_HOSTNAME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9\-]{0,62}$")


class Rule:
    id = "109"
    description = "Hostname must be RFC 1123 compliant"
    severity = "MEDIUM"

    @classmethod
    def match(cls, data):
        results = []
        for device_key in ("router", "switch", "wlc_9800"):
            device = data.get(device_key)
            if not device:
                continue
            hostname = device.get("hostname")
            if hostname and not _HOSTNAME_RE.match(hostname):
                results.append(
                    f"{device_key}.hostname: '{hostname}' is not RFC 1123 compliant "
                    "(must start with a letter, contain only alphanumeric/hyphens, max 63 chars)"
                )
        return results
