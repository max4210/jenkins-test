"""VLANs referenced in interfaces, SVIs, management, and policy profiles must exist in the vlans list."""


class Rule:
    id = "107"
    description = "Referenced VLANs must exist in the vlans list"
    severity = "HIGH"

    @classmethod
    def match(cls, data):
        results = []
        for device_key in ("router", "switch", "wlc_9800"):
            device = data.get(device_key)
            if not device:
                continue

            defined_vlans = {
                v.get("id") for v in device.get("vlans", []) if v.get("id") is not None
            }
            defined_vlans.add(1)

            if not defined_vlans - {1}:
                continue

            for iface in device.get("interfaces", []):
                vlan = iface.get("vlan")
                if vlan is not None and vlan not in defined_vlans:
                    results.append(
                        f"{device_key}.interfaces.{iface.get('name', '?')}: "
                        f"references VLAN {vlan} not in vlans list"
                    )

            for vi in device.get("vlan_interfaces", []):
                vlan = vi.get("vlan")
                if vlan is not None and vlan not in defined_vlans:
                    results.append(
                        f"{device_key}.vlan_interfaces.Vlan{vlan}: "
                        f"SVI for VLAN {vlan} but VLAN not in vlans list"
                    )

            mgmt = device.get("management", {})
            mvlan = mgmt.get("vlan")
            if mvlan is not None and mvlan not in defined_vlans:
                results.append(
                    f"{device_key}.management.vlan: "
                    f"management VLAN {mvlan} not in vlans list"
                )

            wireless = device.get("wireless", {})
            for pp in wireless.get("policy_profiles", []):
                ppvlan = pp.get("vlan")
                if ppvlan is not None and ppvlan not in defined_vlans:
                    results.append(
                        f"{device_key}.wireless.policy_profiles.{pp.get('name', '?')}: "
                        f"VLAN {ppvlan} not in vlans list"
                    )
        return results
