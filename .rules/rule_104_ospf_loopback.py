"""OSPF router-ID should match the device loopback IP for consistency."""


class Rule:
    id = "104"
    description = "OSPF router-ID should match loopback IP"
    severity = "MEDIUM"

    @classmethod
    def match(cls, data):
        results = []
        for device_key in ("router", "switch", "wlc_9800"):
            device = data.get(device_key)
            if not device:
                continue
            ospf = device.get("ospf")
            loopback = device.get("loopback")
            if ospf and loopback:
                rid = ospf.get("router_id")
                lo_ip = loopback.get("ip")
                if rid and lo_ip and rid != lo_ip:
                    results.append(
                        f"{device_key}: OSPF router-id '{rid}' "
                        f"does not match Loopback IP '{lo_ip}'"
                    )
        return results
