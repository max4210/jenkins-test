"""Subnet masks must be valid contiguous masks (all 1s then all 0s)."""

import socket
import struct


def _is_valid_mask(mask_str):
    try:
        packed = socket.inet_aton(mask_str)
        num = struct.unpack("!I", packed)[0]
        if num == 0:
            return True
        inverted = (~num) & 0xFFFFFFFF
        return (inverted & (inverted + 1)) == 0
    except (socket.error, struct.error, OSError):
        return False


def _collect_masks(device, device_key):
    lo = device.get("loopback")
    if lo and lo.get("mask"):
        yield f"{device_key}.loopback.mask", lo["mask"]

    for i, iface in enumerate(device.get("interfaces", [])):
        if iface.get("mask"):
            name = iface.get("name", f"[{i}]")
            yield f"{device_key}.interfaces.{name}.mask", iface["mask"]

    for i, vi in enumerate(device.get("vlan_interfaces", [])):
        if vi.get("mask"):
            yield f"{device_key}.vlan_interfaces.Vlan{vi.get('vlan', i)}.mask", vi["mask"]

    mgmt = device.get("management", {})
    if mgmt.get("mask"):
        yield f"{device_key}.management.mask", mgmt["mask"]


class Rule:
    id = "103"
    description = "Subnet masks must be valid contiguous masks"
    severity = "HIGH"

    @classmethod
    def match(cls, data):
        results = []
        for device_key in ("router", "switch", "wlc_9800"):
            device = data.get(device_key)
            if not device:
                continue
            for path, value in _collect_masks(device, device_key):
                if not _is_valid_mask(value):
                    results.append(f"{path}: invalid subnet mask '{value}'")
        return results
