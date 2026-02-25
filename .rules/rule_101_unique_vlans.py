"""VLAN IDs must be unique within a device."""


class Rule:
    id = "101"
    description = "VLAN IDs must be unique within a device"
    severity = "HIGH"

    @classmethod
    def match(cls, data):
        results = []
        for device_key in ("router", "switch", "wlc_9800"):
            device = data.get(device_key)
            if not device:
                continue
            vlans = device.get("vlans", [])
            seen = set()
            for vlan in vlans:
                vlan_id = vlan.get("id")
                if vlan_id is not None:
                    if vlan_id in seen:
                        results.append(
                            f"{device_key}.vlans: duplicate VLAN ID {vlan_id}"
                        )
                    seen.add(vlan_id)
        return results
