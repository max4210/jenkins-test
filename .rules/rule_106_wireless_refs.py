"""Policy tag mappings must reference WLANs and policy profiles that exist."""


class Rule:
    id = "106"
    description = "Policy tag mappings must reference existing WLANs and policy profiles"
    severity = "HIGH"

    @classmethod
    def match(cls, data):
        results = []
        device = data.get("wlc_9800")
        if not device:
            return results
        wireless = device.get("wireless")
        if not wireless:
            return results

        wlan_names = set()
        for w in wireless.get("wlans", []):
            wlan_names.add(w.get("ssid"))
            wlan_names.add(w.get("profile_name"))
        wlan_names.discard(None)

        pp_names = {pp.get("name") for pp in wireless.get("policy_profiles", [])}
        pp_names.discard(None)

        for pt in wireless.get("policy_tags", []):
            tag_name = pt.get("name", "?")
            for mapping in pt.get("mappings", []):
                wlan_ref = mapping.get("wlan")
                policy_ref = mapping.get("policy")
                if wlan_ref and wlan_ref not in wlan_names:
                    results.append(
                        f"wlc_9800.wireless.policy_tags.{tag_name}: "
                        f"WLAN '{wlan_ref}' not found in wlans list"
                    )
                if policy_ref and policy_ref not in pp_names:
                    results.append(
                        f"wlc_9800.wireless.policy_tags.{tag_name}: "
                        f"policy profile '{policy_ref}' is not defined"
                    )
        return results
