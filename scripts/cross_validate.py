#!/usr/bin/env python3
"""Cross-file validation: checks consistency across all data/*.nac.yaml files.

Runs checks that nac-validate cannot do per-file:
  - Unique OSPF router-IDs across devices
  - Unique loopback IPs across devices
  - No duplicate IPs across any device
  - WLC management subnet matches switch SVI
  - WLC VLANs exist on the switch and are allowed on the trunk
"""

import os
import socket
import struct
import sys

import yaml


def load_all_data(data_dir):
    merged = {}
    for filename in sorted(os.listdir(data_dir)):
        if filename.endswith(".nac.yaml"):
            filepath = os.path.join(data_dir, filename)
            with open(filepath, encoding="utf-8") as fh:
                content = yaml.safe_load(fh)
            if content:
                merged.update(content)
    return merged


def _ip_to_int(ip_str):
    try:
        return struct.unpack("!I", socket.inet_aton(ip_str))[0]
    except (socket.error, struct.error, OSError):
        return None


def _network_of(ip_str, mask_str):
    ip_int = _ip_to_int(ip_str)
    mask_int = _ip_to_int(mask_str)
    if ip_int is not None and mask_int is not None:
        return ip_int & mask_int
    return None


# ── checks ──────────────────────────────────────────────────────────


def check_unique_router_ids(data):
    """OSPF router-IDs must be unique across all devices."""
    errors = []
    seen = {}
    for key in ("router", "switch", "wlc_9800"):
        device = data.get(key)
        if not device:
            continue
        rid = (device.get("ospf") or {}).get("router_id")
        if rid:
            if rid in seen:
                errors.append(
                    f"OSPF router-id '{rid}' used by both "
                    f"'{seen[rid]}' and '{key}'"
                )
            seen[rid] = key
    return errors


def check_unique_loopback_ips(data):
    """Loopback IPs must be unique across all devices."""
    errors = []
    seen = {}
    for key in ("router", "switch", "wlc_9800"):
        device = data.get(key)
        if not device:
            continue
        ip = (device.get("loopback") or {}).get("ip")
        if ip:
            if ip in seen:
                errors.append(
                    f"Loopback IP '{ip}' used by both "
                    f"'{seen[ip]}' and '{key}'"
                )
            seen[ip] = key
    return errors


def check_no_duplicate_ips(data):
    """No two interfaces across all devices may share the same IP."""
    errors = []
    all_ips = {}

    for key in ("router", "switch", "wlc_9800"):
        device = data.get(key)
        if not device:
            continue

        lo = device.get("loopback")
        if lo and lo.get("ip"):
            ctx = f"{key}.Loopback{lo.get('id', 0)}"
            ip = lo["ip"]
            if ip in all_ips:
                errors.append(f"Duplicate IP {ip}: {all_ips[ip]} and {ctx}")
            all_ips[ip] = ctx

        for iface in device.get("interfaces", []):
            ip = iface.get("ip")
            if ip:
                ctx = f"{key}.{iface.get('name', '?')}"
                if ip in all_ips:
                    errors.append(f"Duplicate IP {ip}: {all_ips[ip]} and {ctx}")
                all_ips[ip] = ctx

        for vi in device.get("vlan_interfaces", []):
            ip = vi.get("ip")
            if ip:
                ctx = f"{key}.Vlan{vi.get('vlan', '?')}"
                if ip in all_ips:
                    errors.append(f"Duplicate IP {ip}: {all_ips[ip]} and {ctx}")
                all_ips[ip] = ctx

        mgmt = device.get("management", {})
        if mgmt.get("ip"):
            ctx = f"{key}.management"
            ip = mgmt["ip"]
            if ip in all_ips:
                errors.append(f"Duplicate IP {ip}: {all_ips[ip]} and {ctx}")
            all_ips[ip] = ctx

    return errors


def check_transit_subnets(data):
    """WLC management IP and switch SVI must be in the same subnet;
    WLC gateway must point to the switch SVI IP."""
    errors = []
    switch = data.get("switch", {})
    wlc = data.get("wlc_9800", {})
    if not switch or not wlc:
        return errors

    switch_vis = {}
    for vi in switch.get("vlan_interfaces", []):
        if vi.get("ip") and vi.get("mask"):
            switch_vis[vi["vlan"]] = vi

    wlc_mgmt = wlc.get("management", {})
    mvlan = wlc_mgmt.get("vlan")
    if mvlan and wlc_mgmt.get("ip") and wlc_mgmt.get("mask"):
        wlc_net = _network_of(wlc_mgmt["ip"], wlc_mgmt["mask"])
        sw_vi = switch_vis.get(mvlan)
        if sw_vi:
            sw_net = _network_of(sw_vi["ip"], sw_vi["mask"])
            if wlc_net is not None and sw_net is not None and wlc_net != sw_net:
                errors.append(
                    f"WLC management ({wlc_mgmt['ip']}/{wlc_mgmt['mask']}) and "
                    f"Switch Vlan{mvlan} ({sw_vi['ip']}/{sw_vi['mask']}) "
                    f"are NOT in the same subnet"
                )
        else:
            errors.append(
                f"WLC management VLAN {mvlan} has no SVI on the switch"
            )

    gw = wlc_mgmt.get("gateway")
    if gw and mvlan:
        sw_vi = switch_vis.get(mvlan)
        if sw_vi and gw != sw_vi.get("ip"):
            errors.append(
                f"WLC gateway '{gw}' does not match "
                f"Switch Vlan{mvlan} IP '{sw_vi.get('ip')}'"
            )

    return errors


def check_wlc_vlans_on_switch(data):
    """WLC VLANs must exist on the switch and be allowed on the trunk."""
    errors = []
    switch = data.get("switch", {})
    wlc = data.get("wlc_9800", {})
    if not switch or not wlc:
        return errors

    switch_vlans = {v.get("id") for v in switch.get("vlans", [])}
    switch_vlans.add(1)

    trunk_allowed = set()
    for iface in switch.get("interfaces", []):
        if iface.get("mode") == "trunk":
            raw = iface.get("allowed_vlans", "")
            if raw and raw != "all":
                for part in raw.split(","):
                    part = part.strip()
                    if "-" in part:
                        lo_s, hi_s = part.split("-", 1)
                        trunk_allowed.update(range(int(lo_s), int(hi_s) + 1))
                    elif part.isdigit():
                        trunk_allowed.add(int(part))

    for v in wlc.get("vlans", []):
        vid = v.get("id")
        if vid is None:
            continue
        if vid not in switch_vlans:
            errors.append(f"WLC VLAN {vid} is not defined on the switch")
        if trunk_allowed and vid not in trunk_allowed:
            errors.append(
                f"WLC VLAN {vid} is not in the switch trunk allowed list "
                f"({','.join(str(x) for x in sorted(trunk_allowed))})"
            )

    return errors


def check_ospf_network_covers_loopback(data):
    """OSPF must have a network statement that covers the loopback address."""
    errors = []
    for key in ("router", "switch", "wlc_9800"):
        device = data.get(key)
        if not device:
            continue
        lo = device.get("loopback")
        ospf = device.get("ospf")
        if not lo or not ospf:
            continue
        lo_ip = lo.get("ip")
        if not lo_ip:
            continue

        lo_int = _ip_to_int(lo_ip)
        if lo_int is None:
            continue

        covered = False
        for net in ospf.get("networks", []):
            net_addr = net.get("network")
            wildcard = net.get("wildcard")
            if not net_addr or not wildcard:
                continue
            net_int = _ip_to_int(net_addr)
            wc_int = _ip_to_int(wildcard)
            if net_int is None or wc_int is None:
                continue
            if (lo_int & ~wc_int) == (net_int & ~wc_int):
                covered = True
                break

        if not covered:
            errors.append(
                f"{key}: loopback IP {lo_ip} is not covered by any "
                f"OSPF network statement (will not be advertised)"
            )

    return errors


# ── main ────────────────────────────────────────────────────────────


CHECKS = [
    ("Unique OSPF router-IDs across devices", check_unique_router_ids),
    ("Unique loopback IPs across devices", check_unique_loopback_ips),
    ("No duplicate IPs across devices", check_no_duplicate_ips),
    ("WLC management subnet matches switch SVI", check_transit_subnets),
    ("WLC VLANs exist on switch trunk", check_wlc_vlans_on_switch),
    ("OSPF advertises loopback addresses", check_ospf_network_covers_loopback),
]


def main():
    data_dir = sys.argv[1] if len(sys.argv) > 1 else "data"
    if not os.path.isdir(data_dir):
        print(f"ERROR: data directory '{data_dir}' not found")
        sys.exit(1)

    data = load_all_data(data_dir)
    if not data:
        print(f"ERROR: no data loaded from '{data_dir}'")
        sys.exit(1)

    total_errors = 0
    for name, fn in CHECKS:
        errs = fn(data)
        if errs:
            print(f"  FAIL  {name}")
            for e in errs:
                print(f"          - {e}")
            total_errors += len(errs)
        else:
            print(f"  PASS  {name}")

    print()
    if total_errors:
        print(f"Cross-file validation FAILED ({total_errors} error(s))")
        sys.exit(1)
    else:
        print(f"Cross-file validation PASSED ({len(CHECKS)} checks)")


if __name__ == "__main__":
    main()
