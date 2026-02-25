"""WLAN security type must be a recognized value."""

ALLOWED_TYPES = {
    "wpa2-personal",
    "wpa2-enterprise",
    "wpa3-personal",
    "wpa3-enterprise",
    "open",
}


class Rule:
    id = "108"
    description = "WLAN security type must be a recognized value"
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

        for wlan in wireless.get("wlans", []):
            sec = wlan.get("security", {})
            sec_type = sec.get("type")
            if sec_type and sec_type not in ALLOWED_TYPES:
                results.append(
                    f"wlc_9800.wireless.wlans.{wlan.get('ssid', '?')}: "
                    f"unknown security type '{sec_type}' "
                    f"(allowed: {', '.join(sorted(ALLOWED_TYPES))})"
                )
        return results
