"""WLAN IDs and SSID names must be unique on the WLC."""


class Rule:
    id = "105"
    description = "WLAN IDs and SSIDs must be unique"
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

        seen_ids = set()
        seen_ssids = set()
        for wlan in wireless.get("wlans", []):
            wlan_id = wlan.get("wlan_id")
            ssid = wlan.get("ssid")
            if wlan_id is not None:
                if wlan_id in seen_ids:
                    results.append(
                        f"wlc_9800.wireless.wlans: duplicate WLAN ID {wlan_id}"
                    )
                seen_ids.add(wlan_id)
            if ssid:
                if ssid in seen_ssids:
                    results.append(
                        f"wlc_9800.wireless.wlans: duplicate SSID '{ssid}'"
                    )
                seen_ssids.add(ssid)
        return results
