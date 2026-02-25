"""All IP address fields must be valid IPv4 format."""

import re

_IPV4_RE = re.compile(r"^(\d{1,3})\.(\d{1,3})\.(\d{1,3})\.(\d{1,3})$")


def _is_valid_ipv4(addr):
    m = _IPV4_RE.match(str(addr))
    if not m:
        return False
    return all(0 <= int(g) <= 255 for g in m.groups())


def _collect_ips(device, device_key):
    """Walk the device dict and yield (path, value) for every IP-like field."""
    lo = device.get("loopback")
    if lo and lo.get("ip"):
        yield f"{device_key}.loopback.ip", lo["ip"]

    for i, iface in enumerate(device.get("interfaces", [])):
        name = iface.get("name", f"[{i}]")
        if iface.get("ip"):
            yield f"{device_key}.interfaces.{name}.ip", iface["ip"]
        if iface.get("mask"):
            yield f"{device_key}.interfaces.{name}.mask", iface["mask"]

    for i, vi in enumerate(device.get("vlan_interfaces", [])):
        label = f"Vlan{vi.get('vlan', i)}"
        if vi.get("ip"):
            yield f"{device_key}.vlan_interfaces.{label}.ip", vi["ip"]

    mgmt = device.get("management", {})
    for field in ("ip", "gateway"):
        if mgmt.get(field):
            yield f"{device_key}.management.{field}", mgmt[field]

    ospf = device.get("ospf", {})
    if ospf.get("router_id"):
        yield f"{device_key}.ospf.router_id", ospf["router_id"]
    for i, net in enumerate(ospf.get("networks", [])):
        if net.get("network"):
            yield f"{device_key}.ospf.networks[{i}].network", net["network"]
        if net.get("wildcard"):
            yield f"{device_key}.ospf.networks[{i}].wildcard", net["wildcard"]


class Rule:
    id = "102"
    description = "IP addresses must be valid IPv4 format"
    severity = "HIGH"

    @classmethod
    def match(cls, data):
        results = []
        for device_key in ("router", "switch", "wlc_9800"):
            device = data.get(device_key)
            if not device:
                continue
            for path, value in _collect_ips(device, device_key):
                if not _is_valid_ipv4(value):
                    results.append(f"{path}: invalid IPv4 '{value}'")
        return results
