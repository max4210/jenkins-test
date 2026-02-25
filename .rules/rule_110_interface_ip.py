"""Routed interfaces must have either a static IP + mask or DHCP enabled."""


class Rule:
    id = "110"
    description = "Routed interfaces must have IP address or DHCP"
    severity = "MEDIUM"

    @classmethod
    def match(cls, data):
        results = []
        for device_key in ("router",):
            device = data.get(device_key)
            if not device:
                continue
            for iface in device.get("interfaces", []):
                name = iface.get("name", "")
                if name.lower().startswith("loopback"):
                    continue
                if iface.get("shutdown"):
                    continue
                if iface.get("mode") in ("access", "trunk"):
                    continue
                has_ip = bool(iface.get("ip") and iface.get("mask"))
                has_dhcp = bool(iface.get("dhcp"))
                if not has_ip and not has_dhcp:
                    results.append(
                        f"{device_key}.interfaces.{name}: "
                        "no IP address or DHCP configured on routed interface"
                    )
        return results
