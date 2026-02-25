#!/usr/bin/env python3
"""Export CML lab device configs to NaC IOS-XE Terraform provider YAML format.

Connects to a CML 2.x server, reads all nodes in a lab, downloads their
running/startup configs, parses IOS-XE CLI into structured dicts, and writes
one YAML file per device in the NaC iosxe data model format.

Usage:
    python3 scripts/cml_export.py \\
        --url https://192.168.137.125 \\
        --user admin --password admin \\
        --lab "Jenkins-Terraform-Lab" \\
        --output data-nac/

    # Auto-start/stop a lab that is not running:
    python3 scripts/cml_export.py --lab <lab-id> --start

    # Target a running lab by ID:
    python3 scripts/cml_export.py --lab 9f64eda4-6400-4dfe-a8fb-e67c05e9a80c

Environment variable fallbacks: CML_URL, CML_USERNAME, CML_PASSWORD
Reads .env file automatically if present in the project root.
"""

import argparse
import difflib
import glob
import json
import os
import re
import sys
import time
from collections import OrderedDict
from datetime import datetime, timezone
from pathlib import Path

import urllib3
import requests
import yaml

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


def _load_dotenv():
    """Load .env from project root into os.environ (simple parser, no deps)."""
    for candidate in [
        Path(__file__).resolve().parent.parent / ".env",
        Path.cwd() / ".env",
    ]:
        if candidate.is_file():
            with open(candidate, encoding="utf-8") as fh:
                for line in fh:
                    line = line.strip()
                    if not line or line.startswith("#"):
                        continue
                    if "=" in line:
                        key, _, value = line.partition("=")
                        key = key.strip()
                        value = value.strip()
                        if key and key not in os.environ:
                            os.environ[key] = value
            return str(candidate)
    return None


_dotenv_path = _load_dotenv()

SKIP_NODE_DEFS = {"external_connector", "unmanaged_switch"}

NODE_DEF_MAP = {
    "iosv": "router",
    "iosvl2": "switch",
    "cat9800": "wlc",
    "csr1000v": "router",
    "iosxrv9000": None,
}


# ═══════════════════════════════════════════════════════════════════
#  CML API Client
# ═══════════════════════════════════════════════════════════════════


class CMLClient:
    """Minimal CML 2.x REST API client."""

    def __init__(self, url, username, password, verify_tls=False):
        url = url.rstrip("/")
        if not url.startswith("http://") and not url.startswith("https://"):
            url = f"https://{url}"
        self.base = url
        self.session = requests.Session()
        self.session.verify = verify_tls
        self._authenticate(username, password)

    def _authenticate(self, username, password):
        resp = self.session.post(
            f"{self.base}/api/v0/authenticate",
            json={"username": username, "password": password},
        )
        resp.raise_for_status()
        token = resp.json()
        self.session.headers["Authorization"] = f"Bearer {token}"

    def get_labs(self):
        resp = self.session.get(f"{self.base}/api/v0/labs")
        resp.raise_for_status()
        return resp.json()

    def get_lab(self, lab_id):
        resp = self.session.get(f"{self.base}/api/v0/labs/{lab_id}")
        resp.raise_for_status()
        data = resp.json()
        if isinstance(data, dict):
            data.setdefault("id", lab_id)
        return data

    def get_lab_title(self, lab_id):
        """Get the lab title, trying multiple API response formats."""
        info = self.get_lab(lab_id)
        if isinstance(info, dict):
            return info.get("lab_title") or info.get("title") or info.get("name") or "?"
        return "?"

    def list_labs_detail(self):
        """Return list of (lab_id, title, state) tuples for all labs."""
        result = []
        for lab_id in self.get_labs():
            info = self.get_lab(lab_id)
            title = self.get_lab_title(lab_id)
            state = info.get("state", "?") if isinstance(info, dict) else "?"
            result.append((lab_id, title, state))
        return result

    def find_lab(self, title_or_id):
        labs = self.get_labs()
        for lab_id in labs:
            if lab_id == title_or_id:
                info = self.get_lab(lab_id)
                return info
            title = self.get_lab_title(lab_id)
            if title == title_or_id:
                info = self.get_lab(lab_id)
                return info
        return None

    def get_nodes(self, lab_id):
        resp = self.session.get(f"{self.base}/api/v0/labs/{lab_id}/nodes")
        resp.raise_for_status()
        node_ids = resp.json()
        nodes = []
        for nid in node_ids:
            node = self.get_node(lab_id, nid)
            nodes.append(node)
        return nodes

    def get_node(self, lab_id, node_id):
        resp = self.session.get(
            f"{self.base}/api/v0/labs/{lab_id}/nodes/{node_id}"
        )
        resp.raise_for_status()
        return resp.json()

    def get_node_config(self, lab_id, node_id):
        """Try multiple API paths to retrieve a node's configuration."""
        config_paths = [
            f"/api/v0/labs/{lab_id}/nodes/{node_id}/config",
            f"/api/v2/labs/{lab_id}/nodes/{node_id}/config",
        ]
        last_exc = None
        for path in config_paths:
            try:
                resp = self.session.get(f"{self.base}{path}")
                resp.raise_for_status()
                text = resp.text
                if text and text.strip():
                    return text
            except requests.HTTPError as exc:
                last_exc = exc

        node_info = self.get_node(lab_id, node_id)
        if isinstance(node_info, dict):
            cfg = node_info.get("configuration")
            if cfg and isinstance(cfg, str) and cfg.strip():
                return cfg

        if last_exc:
            raise last_exc
        raise requests.HTTPError(f"No config found for node {node_id}")

    # --- Lab lifecycle --------------------------------------------------

    def get_lab_state(self, lab_id):
        info = self.get_lab(lab_id)
        return info.get("state", "UNKNOWN") if isinstance(info, dict) else "UNKNOWN"

    def start_lab(self, lab_id):
        resp = self.session.put(f"{self.base}/api/v0/labs/{lab_id}/start")
        resp.raise_for_status()

    def stop_lab(self, lab_id):
        resp = self.session.put(f"{self.base}/api/v0/labs/{lab_id}/stop")
        resp.raise_for_status()

    def extract_node_config(self, lab_id, node_id):
        """Extract running config from a booted node. Returns True if successful."""
        resp = self.session.put(
            f"{self.base}/api/v0/labs/{lab_id}/nodes/{node_id}/extract_configuration"
        )
        resp.raise_for_status()
        return True

    def wait_for_lab_ready(self, lab_id, timeout=300, poll_interval=10):
        """Poll until all configurable nodes reach BOOTED state."""
        deadline = time.time() + timeout
        while time.time() < deadline:
            nodes = self.get_nodes(lab_id)
            pending = []
            for n in nodes:
                ndef = n.get("node_definition", "")
                if ndef in SKIP_NODE_DEFS:
                    continue
                nstate = n.get("state", "")
                if nstate != "BOOTED":
                    pending.append(f"{n.get('label', '?')} ({nstate})")
            if not pending:
                return True
            remaining = int(deadline - time.time())
            print(f"    Waiting for nodes to boot ({remaining}s left): "
                  + ", ".join(pending))
            time.sleep(poll_interval)
        return False


# ═══════════════════════════════════════════════════════════════════
#  CLI Block Parser
# ═══════════════════════════════════════════════════════════════════


def split_cli_blocks(config_text):
    """Split IOS-XE config into a list of (command, [child_lines]) tuples.

    A new block starts at every line that begins at column 0 and is not
    a comment (!) or blank.
    """
    blocks = []
    current_cmd = None
    current_children = []

    for line in config_text.splitlines():
        stripped = line.rstrip()
        if not stripped or stripped.startswith("!"):
            continue
        if not line[0].isspace():
            if current_cmd is not None:
                blocks.append((current_cmd, current_children))
            current_cmd = stripped
            current_children = []
        else:
            current_children.append(stripped.strip())

    if current_cmd is not None:
        blocks.append((current_cmd, current_children))

    return blocks


def _parse_interface_name(full_name):
    """Split 'GigabitEthernet0/0' -> ('GigabitEthernet', '0/0')."""
    m = re.match(r"^([A-Za-z\-]+)(\d.*)$", full_name)
    if m:
        return m.group(1), m.group(2)
    return full_name, ""


# ═══════════════════════════════════════════════════════════════════
#  Interface Parser Helpers
# ═══════════════════════════════════════════════════════════════════


def _parse_interface_block(children):
    """Parse child lines of an interface block into a raw dict."""
    info = {}
    for line in children:
        if line.startswith("ip address dhcp"):
            info["dhcp"] = True
        elif line.startswith("ip address "):
            parts = line.split()
            if len(parts) >= 4:
                info["ipv4_address"] = parts[2]
                info["ipv4_mask"] = parts[3]
        elif line.startswith("description "):
            info["description"] = line[len("description "):]
        elif line == "shutdown":
            info["shutdown"] = True
        elif line == "no shutdown":
            info["shutdown"] = False
        elif line == "no switchport":
            info["no_switchport"] = True
        elif line.startswith("switchport mode "):
            info["sw_mode"] = line.split()[-1]
        elif line.startswith("switchport access vlan "):
            info["sw_access_vlan"] = int(line.split()[-1])
        elif line.startswith("switchport trunk allowed vlan "):
            raw = line[len("switchport trunk allowed vlan "):]
            info["sw_trunk_allowed"] = raw
        elif line.startswith("switchport trunk encapsulation"):
            pass
        elif line.startswith("switchport trunk native vlan "):
            info["sw_trunk_native"] = int(line.split()[-1])
    return info


def _build_nac_ethernet(iface_type, iface_id, raw):
    """Build a NaC-format ethernet dict from parsed interface info."""
    eth = OrderedDict()
    eth["type"] = iface_type
    eth["id"] = iface_id
    if raw.get("description"):
        eth["description"] = raw["description"]
    if raw.get("shutdown") is True:
        eth["shutdown"] = True

    if raw.get("ipv4_address") and not raw.get("sw_mode"):
        eth["ipv4"] = OrderedDict()
        eth["ipv4"]["address"] = raw["ipv4_address"]
        eth["ipv4"]["address_mask"] = raw["ipv4_mask"]

    if raw.get("sw_mode"):
        sw = OrderedDict()
        sw["mode"] = raw["sw_mode"]
        if raw["sw_mode"] == "access" and raw.get("sw_access_vlan"):
            sw["access_vlan"] = raw["sw_access_vlan"]
        elif raw["sw_mode"] == "trunk" and raw.get("sw_trunk_allowed"):
            vlan_ids = _parse_vlan_list(raw["sw_trunk_allowed"])
            if vlan_ids:
                sw["trunk_allowed_vlans"] = {"vlans": {"ids": vlan_ids}}
        if raw.get("sw_trunk_native"):
            sw["trunk_native_vlan_id"] = raw["sw_trunk_native"]
        eth["switchport"] = sw

    return eth


def _build_nac_loopback(lo_id, raw):
    """Build a NaC-format loopback dict."""
    lo = OrderedDict()
    lo["id"] = int(lo_id)
    if raw.get("description"):
        lo["description"] = raw["description"]
    if raw.get("ipv4_address"):
        lo["ipv4"] = OrderedDict()
        lo["ipv4"]["address"] = raw["ipv4_address"]
        lo["ipv4"]["address_mask"] = raw["ipv4_mask"]
    return lo


def _build_nac_vlan_svi(vlan_id, raw):
    """Build a NaC-format VLAN SVI dict."""
    svi = OrderedDict()
    svi["id"] = int(vlan_id)
    if raw.get("description"):
        svi["description"] = raw["description"]
    if raw.get("shutdown") is True:
        svi["shutdown"] = True
    if raw.get("dhcp"):
        pass
    elif raw.get("ipv4_address"):
        svi["ipv4"] = OrderedDict()
        svi["ipv4"]["address"] = raw["ipv4_address"]
        svi["ipv4"]["address_mask"] = raw["ipv4_mask"]
    return svi


def _parse_vlan_list(raw_str):
    """Parse '20,100,200' or '10-20,30' into a list of ints."""
    ids = []
    for part in raw_str.split(","):
        part = part.strip()
        if "-" in part:
            lo, hi = part.split("-", 1)
            ids.extend(range(int(lo), int(hi) + 1))
        elif part.isdigit():
            ids.append(int(part))
    return sorted(ids)


# ═══════════════════════════════════════════════════════════════════
#  OSPF Parser
# ═══════════════════════════════════════════════════════════════════


def _parse_ospf_block(cmd, children):
    """Parse 'router ospf <id>' block into NaC ospf_process dict."""
    m = re.match(r"router ospf (\d+)", cmd)
    if not m:
        return None
    ospf = OrderedDict()
    ospf["id"] = int(m.group(1))
    networks = []
    passive_ifs = []
    active_ifs = []
    passive_default = False

    for line in children:
        if line.startswith("router-id "):
            ospf["router_id"] = line.split()[-1]
        elif line == "passive-interface default":
            passive_default = True
        elif line.startswith("no passive-interface "):
            iface_full = line[len("no passive-interface "):]
            itype, iid = _parse_interface_name(iface_full)
            active_ifs.append((itype, iid))
        elif line.startswith("passive-interface ") and "default" not in line:
            iface_full = line[len("passive-interface "):]
            itype, iid = _parse_interface_name(iface_full)
            passive_ifs.append((itype, iid))
        elif line.startswith("network "):
            parts = line.split()
            if len(parts) >= 5:
                net = OrderedDict()
                net["ip"] = parts[1]
                net["wildcard"] = parts[2]
                net["area"] = _ospf_area_value(parts[4])
                networks.append(net)

    if passive_default:
        ospf["passive_interface_default"] = True
    if networks:
        ospf["networks"] = networks

    return ospf


def _ospf_area_value(raw):
    """Return area as int if numeric, else string."""
    try:
        return int(raw)
    except ValueError:
        return raw


# ═══════════════════════════════════════════════════════════════════
#  VLAN Parser
# ═══════════════════════════════════════════════════════════════════


def _parse_vlan_block(cmd, children):
    """Parse 'vlan <id>' block into NaC vlan dict."""
    m = re.match(r"vlan (\d+)", cmd)
    if not m:
        return None
    vlan = OrderedDict()
    vlan["id"] = int(m.group(1))
    for line in children:
        if line.startswith("name "):
            vlan["name"] = line[len("name "):]
    return vlan


# ═══════════════════════════════════════════════════════════════════
#  C9800 Wireless Parser (raw CLI extraction)
# ═══════════════════════════════════════════════════════════════════


def _parse_wireless_blocks(blocks):
    """Extract C9800 wireless-specific config blocks as raw CLI text."""
    wireless_lines = []
    wireless_prefixes = (
        "wireless ", "wlan ", "ap ", "aaa ",
    )
    for cmd, children in blocks:
        if any(cmd.startswith(p) for p in wireless_prefixes):
            wireless_lines.append(cmd)
            for child in children:
                wireless_lines.append(f" {child}")
            wireless_lines.append("!")
    return "\n".join(wireless_lines) if wireless_lines else None


# ═══════════════════════════════════════════════════════════════════
#  Device Parsers
# ═══════════════════════════════════════════════════════════════════


def parse_iosxe_router(config_text, label):
    """Parse an IOS-XE router config into NaC device dict."""
    blocks = split_cli_blocks(config_text)
    device = OrderedDict()
    device["name"] = label

    config = OrderedDict()
    system = OrderedDict()
    loopbacks = []
    ethernets = []
    ospf_processes = []

    for cmd, children in blocks:
        if cmd.startswith("hostname "):
            system["hostname"] = cmd.split(None, 1)[1]

        elif cmd.startswith("interface Loopback"):
            _, lo_id = _parse_interface_name(cmd.split(None, 1)[1])
            raw = _parse_interface_block(children)
            loopbacks.append(_build_nac_loopback(lo_id, raw))

        elif cmd.startswith("interface "):
            iface_name = cmd.split(None, 1)[1]
            itype, iid = _parse_interface_name(iface_name)
            if itype.lower().startswith("loopback"):
                continue
            raw = _parse_interface_block(children)
            ethernets.append(_build_nac_ethernet(itype, iid, raw))

        elif cmd.startswith("router ospf "):
            ospf = _parse_ospf_block(cmd, children)
            if ospf:
                ospf_processes.append(ospf)

    if system:
        config["system"] = system
    interfaces = OrderedDict()
    if loopbacks:
        interfaces["loopbacks"] = loopbacks
    if ethernets:
        interfaces["ethernets"] = ethernets
    if interfaces:
        config["interfaces"] = interfaces
    if ospf_processes:
        config["routing"] = {"ospf_processes": ospf_processes}

    device["configuration"] = config
    return device


def parse_iosxe_switch(config_text, label):
    """Parse an IOSvL2 / IOS-XE switch config into NaC device dict."""
    blocks = split_cli_blocks(config_text)
    device = OrderedDict()
    device["name"] = label

    config = OrderedDict()
    system = OrderedDict()
    vlans = []
    loopbacks = []
    svis = []
    ethernets = []
    ospf_processes = []
    has_ip_routing = False

    for cmd, children in blocks:
        if cmd.startswith("hostname "):
            system["hostname"] = cmd.split(None, 1)[1]

        elif cmd == "ip routing":
            has_ip_routing = True

        elif re.match(r"^vlan \d+$", cmd):
            v = _parse_vlan_block(cmd, children)
            if v:
                vlans.append(v)

        elif cmd.startswith("interface Loopback"):
            _, lo_id = _parse_interface_name(cmd.split(None, 1)[1])
            raw = _parse_interface_block(children)
            loopbacks.append(_build_nac_loopback(lo_id, raw))

        elif re.match(r"^interface Vlan\d+$", cmd):
            vlan_id = cmd.split("Vlan")[1]
            raw = _parse_interface_block(children)
            svis.append(_build_nac_vlan_svi(vlan_id, raw))

        elif cmd.startswith("interface "):
            iface_name = cmd.split(None, 1)[1]
            if iface_name.startswith("Vlan") or iface_name.startswith("Loopback"):
                continue
            itype, iid = _parse_interface_name(iface_name)
            raw = _parse_interface_block(children)
            ethernets.append(_build_nac_ethernet(itype, iid, raw))

        elif cmd.startswith("router ospf "):
            ospf = _parse_ospf_block(cmd, children)
            if ospf:
                ospf_processes.append(ospf)

    if has_ip_routing:
        system["ip_routing"] = True
    if system:
        config["system"] = system
    if vlans:
        config["vlan"] = {"vlans": vlans}

    interfaces = OrderedDict()
    if loopbacks:
        interfaces["loopbacks"] = loopbacks
    if svis:
        interfaces["vlans"] = svis
    if ethernets:
        interfaces["ethernets"] = ethernets
    if interfaces:
        config["interfaces"] = interfaces
    if ospf_processes:
        config["routing"] = {"ospf_processes": ospf_processes}

    device["configuration"] = config
    return device


def parse_iosxe_wlc(config_text, label):
    """Parse a C9800-CL config into NaC device dict + wireless raw CLI."""
    blocks = split_cli_blocks(config_text)
    device = OrderedDict()
    device["name"] = label

    config = OrderedDict()
    system = OrderedDict()
    vlans = []
    loopbacks = []
    svis = []
    ethernets = []
    ospf_processes = []

    for cmd, children in blocks:
        if cmd.startswith("hostname "):
            system["hostname"] = cmd.split(None, 1)[1]

        elif re.match(r"^vlan \d+$", cmd):
            v = _parse_vlan_block(cmd, children)
            if v:
                vlans.append(v)

        elif cmd.startswith("interface Loopback"):
            _, lo_id = _parse_interface_name(cmd.split(None, 1)[1])
            raw = _parse_interface_block(children)
            loopbacks.append(_build_nac_loopback(lo_id, raw))

        elif re.match(r"^interface Vlan\d+$", cmd):
            vlan_id = cmd.split("Vlan")[1]
            raw = _parse_interface_block(children)
            svis.append(_build_nac_vlan_svi(vlan_id, raw))

        elif cmd.startswith("interface "):
            iface_name = cmd.split(None, 1)[1]
            if iface_name.startswith("Vlan") or iface_name.startswith("Loopback"):
                continue
            itype, iid = _parse_interface_name(iface_name)
            raw = _parse_interface_block(children)
            ethernets.append(_build_nac_ethernet(itype, iid, raw))

        elif cmd.startswith("router ospf "):
            ospf = _parse_ospf_block(cmd, children)
            if ospf:
                ospf_processes.append(ospf)

    if system:
        config["system"] = system
    if vlans:
        config["vlan"] = {"vlans": vlans}

    interfaces = OrderedDict()
    if loopbacks:
        interfaces["loopbacks"] = loopbacks
    if svis:
        interfaces["vlans"] = svis
    if ethernets:
        interfaces["ethernets"] = ethernets
    if interfaces:
        config["interfaces"] = interfaces
    if ospf_processes:
        config["routing"] = {"ospf_processes": ospf_processes}

    device["configuration"] = config

    wireless_cli = _parse_wireless_blocks(blocks)
    if wireless_cli:
        device["_wireless_cli"] = wireless_cli

    return device


# ═══════════════════════════════════════════════════════════════════
#  YAML Writer
# ═══════════════════════════════════════════════════════════════════


class _OrderedDumper(yaml.SafeDumper):
    pass


def _dict_representer(dumper, data):
    return dumper.represent_mapping("tag:yaml.org,2002:map", data.items())


_OrderedDumper.add_representer(OrderedDict, _dict_representer)


def _yaml_to_string(doc):
    """Serialize an OrderedDict document to a YAML string."""
    return yaml.dump(
        doc,
        Dumper=_OrderedDumper,
        default_flow_style=False,
        sort_keys=False,
        allow_unicode=True,
    )


def _find_latest_previous(output_dir, role, suffix, current_ts):
    """Find the most recent timestamped file for a role, excluding current_ts."""
    pattern = os.path.join(output_dir, f"{role}.*.{suffix}")
    candidates = sorted(glob.glob(pattern), reverse=True)
    for path in candidates:
        if current_ts not in os.path.basename(path):
            return path
    return None


def _write_delta(old_path, new_path, delta_path, label):
    """Compare two text files and write a unified diff as the delta."""
    old_lines = []
    if old_path and os.path.isfile(old_path):
        with open(old_path, encoding="utf-8") as fh:
            old_lines = fh.readlines()

    with open(new_path, encoding="utf-8") as fh:
        new_lines = fh.readlines()

    old_name = os.path.basename(old_path) if old_path else "(none)"
    new_name = os.path.basename(new_path)

    diff = list(difflib.unified_diff(
        old_lines, new_lines,
        fromfile=old_name, tofile=new_name,
        lineterm="",
    ))

    if not diff:
        print(f"    delta: no changes for {label}")
        return False

    added = sum(1 for l in diff if l.startswith("+") and not l.startswith("+++"))
    removed = sum(1 for l in diff if l.startswith("-") and not l.startswith("---"))

    with open(delta_path, "w", encoding="utf-8") as fh:
        fh.write(f"! Delta for {label}\n")
        fh.write(f"! Compared: {old_name} -> {new_name}\n")
        fh.write(f"! Lines added: {added}, removed: {removed}\n")
        fh.write("!\n")
        for line in diff:
            fh.write(line.rstrip("\n") + "\n")

    print(f"    delta: +{added} -{removed} -> {delta_path}")
    return True


def write_nac_yaml(device_dict, output_dir, role, timestamp):
    """Wrap a device dict in iosxe.devices[] and write timestamped files + deltas."""
    wireless_cli = device_dict.pop("_wireless_cli", None)

    doc = OrderedDict()
    doc["iosxe"] = OrderedDict()
    doc["iosxe"]["devices"] = [device_dict]

    yaml_filename = f"{role}.{timestamp}.nac.yaml"
    yaml_path = os.path.join(output_dir, yaml_filename)

    with open(yaml_path, "w", encoding="utf-8") as fh:
        fh.write(_yaml_to_string(doc))

    print(f"    -> {yaml_path}")

    prev_yaml = _find_latest_previous(output_dir, role, "nac.yaml", timestamp)
    delta_yaml_path = os.path.join(output_dir, f"{role}.{timestamp}.delta.yaml")
    _write_delta(prev_yaml, yaml_path, delta_yaml_path, f"{role} YAML")

    if wireless_cli:
        cli_filename = f"{role}.{timestamp}.wireless.cli"
        cli_path = os.path.join(output_dir, cli_filename)
        with open(cli_path, "w", encoding="utf-8") as fh:
            fh.write(f"! Wireless CLI from {device_dict.get('name', '?')}\n")
            fh.write("! Not part of the NaC IOS-XE data model\n")
            fh.write("!\n")
            fh.write(wireless_cli)
            fh.write("\n")
        print(f"    wireless CLI -> {cli_path}")

        prev_cli = _find_latest_previous(output_dir, role, "wireless.cli", timestamp)
        delta_cli_path = os.path.join(output_dir, f"{role}.{timestamp}.delta.wireless.cli")
        _write_delta(prev_cli, cli_path, delta_cli_path, f"{role} wireless CLI")


# ═══════════════════════════════════════════════════════════════════
#  Main
# ═══════════════════════════════════════════════════════════════════


PARSER_MAP = {
    "iosv": ("router", parse_iosxe_router),
    "csr1000v": ("router", parse_iosxe_router),
    "iosvl2": ("switch", parse_iosxe_switch),
    "cat9800": ("wlc", parse_iosxe_wlc),
}


def main():
    parser = argparse.ArgumentParser(
        description="Export CML lab configs to NaC IOS-XE YAML format"
    )
    parser.add_argument(
        "--url",
        default=os.environ.get("CML_URL", "https://192.168.137.125"),
        help="CML server URL (default: $CML_URL or https://192.168.137.125)",
    )
    parser.add_argument(
        "--user",
        default=os.environ.get("CML_USERNAME", ""),
        help="CML username (default: $CML_USERNAME)",
    )
    parser.add_argument(
        "--password",
        default=os.environ.get("CML_PASSWORD", ""),
        help="CML password (default: $CML_PASSWORD)",
    )
    parser.add_argument(
        "--lab",
        default="Jenkins-Terraform-Lab",
        help="Lab title or lab ID",
    )
    parser.add_argument(
        "--output", "-o",
        default="data-nac",
        help="Output directory for NaC YAML files (default: data-nac/)",
    )
    parser.add_argument(
        "--start",
        action="store_true",
        help="Start the lab if not running, extract configs, then stop it",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print YAML to stdout instead of writing files",
    )
    args = parser.parse_args()

    if _dotenv_path:
        print(f"Loaded credentials from {_dotenv_path}")

    if not args.user or not args.password:
        print("ERROR: CML credentials required.")
        print("  Option 1: Add CML_USERNAME and CML_PASSWORD to .env file")
        print("  Option 2: Pass --user and --password arguments")
        print("  Option 3: Set CML_USERNAME / CML_PASSWORD environment variables")
        sys.exit(1)

    print(f"Connecting to CML at {args.url} ...")
    client = CMLClient(args.url, args.user, args.password)

    print(f"Looking for lab: {args.lab}")
    lab = client.find_lab(args.lab)
    if not lab:
        print(f"ERROR: Lab '{args.lab}' not found.")
        print("Available labs:")
        for lid, title, state in client.list_labs_detail():
            print(f"  - {title} (id: {lid}, state: {state})")
        print(f"\nTip: pass --lab <id> to use a lab ID directly.")
        sys.exit(1)

    lab_id = lab["id"]
    title = lab.get("lab_title") or lab.get("title") or lab.get("name") or lab_id
    lab_state = lab.get("state", "UNKNOWN")
    print(f"Found lab: {title} (id: {lab_id}, state: {lab_state})")

    # --- Handle non-running labs ----------------------------------------
    auto_started = False
    if lab_state != "STARTED":
        if not args.start:
            print(f"\nWARNING: Lab is not running (state: {lab_state}).")
            print("Node configs are only available after the lab has been started.")
            print("Options:")
            print("  1. Start the lab in CML UI, then re-run this script")
            print("  2. Re-run with --start to auto-start/stop the lab")
            print("  3. Use --lab <id> to target a running lab instead")
            sys.exit(1)

        print(f"\nLab is not running (state: {lab_state}). Starting it...")
        client.start_lab(lab_id)
        auto_started = True

        print("Waiting for all nodes to boot (timeout: 300s)...")
        if not client.wait_for_lab_ready(lab_id, timeout=300):
            print("ERROR: Timed out waiting for nodes to boot.")
            print("Stopping lab to clean up...")
            try:
                client.stop_lab(lab_id)
            except requests.HTTPError:
                pass
            sys.exit(1)
        print("All nodes are BOOTED.\n")

    try:
        _export_nodes(client, lab_id, args)
    finally:
        if auto_started:
            print("\nStopping lab (auto-started)...")
            try:
                client.stop_lab(lab_id)
                print("Lab stopped.")
            except requests.HTTPError as exc:
                print(f"WARNING: could not stop lab: {exc}")


def _export_nodes(client, lab_id, args):
    """Download, parse, and write configs for all eligible nodes."""
    nodes = client.get_nodes(lab_id)
    print(f"Nodes in lab: {len(nodes)}")

    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    print(f"Export timestamp: {ts}")

    if not args.dry_run:
        os.makedirs(args.output, exist_ok=True)

    exported = 0
    for node in nodes:
        node_def = node.get("node_definition", "")
        label = node.get("label", "unknown")
        state = node.get("state", "?")
        nid = node.get("id", "")

        if node_def in SKIP_NODE_DEFS:
            print(f"  [{label}] ({node_def}) — skipping non-configurable node")
            continue

        if node_def not in PARSER_MAP:
            print(f"  [{label}] ({node_def}) — no parser for this node type, skipping")
            continue

        print(f"  [{label}] ({node_def}, state: {state}) — extracting config...")
        try:
            client.extract_node_config(lab_id, nid)
            time.sleep(2)
        except requests.HTTPError as exc:
            print(f"    extract returned {exc} (non-fatal, trying download anyway)")

        print(f"  [{label}] downloading config...")
        try:
            config_text = client.get_node_config(lab_id, nid)
        except requests.HTTPError as exc:
            print(f"    WARNING: could not get config ({exc}), skipping")
            continue

        if not config_text or not config_text.strip():
            print(f"    WARNING: config is empty, skipping")
            continue

        role, parse_fn = PARSER_MAP[node_def]
        device = parse_fn(config_text, label)

        if args.dry_run:
            print(f"\n--- {role}.{ts}.nac.yaml ---")
            doc = OrderedDict()
            doc["iosxe"] = OrderedDict()
            doc["iosxe"]["devices"] = [device]
            yaml.dump(doc, sys.stdout, Dumper=_OrderedDumper,
                       default_flow_style=False, sort_keys=False)
            wireless = device.pop("_wireless_cli", None)
            if wireless:
                print(f"\n--- {role}.{ts}.wireless.cli ---")
                print(wireless)
        else:
            write_nac_yaml(device, args.output, role, ts)
            exported += 1

    if not args.dry_run:
        print(f"\nExported {exported} device(s) to {args.output}/")
        print(f"Files use timestamp: {ts}")
    print("Done.")


if __name__ == "__main__":
    main()
