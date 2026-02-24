#!/usr/bin/env python3
"""Generate a pyATS testbed YAML from Terraform outputs and CML node data."""

import argparse
import json
import os
import sys
import urllib3

import requests
import yaml

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


def authenticate(base_url, username, password, verify_tls=False):
    resp = requests.post(
        f"{base_url}/api/v2/authenticate",
        json={"username": username, "password": password},
        verify=verify_tls,
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()


def get_lab_nodes(base_url, token, lab_id, verify_tls=False):
    headers = {"Authorization": f"Bearer {token}"}
    resp = requests.get(
        f"{base_url}/api/v2/labs/{lab_id}/nodes",
        headers=headers,
        verify=verify_tls,
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()


def get_node_detail(base_url, token, lab_id, node_id, verify_tls=False):
    headers = {"Authorization": f"Bearer {token}"}
    resp = requests.get(
        f"{base_url}/api/v2/labs/{lab_id}/nodes/{node_id}",
        headers=headers,
        verify=verify_tls,
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()


NODE_DEF_TO_OS = {
    "iosv": "iosxe",
    "iosvl2": "iosxe",
    "csr1000v": "iosxe",
    "cat8000v": "iosxe",
    "iosxrv9000": "iosxr",
    "nxosv9000": "nxos",
    "asav": "asa",
}

NODE_DEF_TO_PLATFORM = {
    "iosv": "iosv",
    "iosvl2": "iosvl2",
    "csr1000v": "csr1000v",
    "cat8000v": "cat8000v",
    "iosxrv9000": "iosxrv9000",
    "nxosv9000": "nxosv",
    "asav": "asav",
}


def build_testbed(base_url, token, lab_id, device_username, device_password,
                  verify_tls=False):
    """Query CML for node details and build a pyATS testbed dictionary."""
    node_ids = get_lab_nodes(base_url, token, lab_id, verify_tls)

    testbed = {
        "testbed": {
            "name": f"CML-Lab-{lab_id}",
            "credentials": {
                "default": {
                    "username": device_username,
                    "password": device_password,
                },
                "enable": {
                    "password": device_password,
                },
            },
        },
        "devices": {},
    }

    for node_id in node_ids:
        node = get_node_detail(base_url, token, lab_id, node_id, verify_tls)
        node_def = node.get("node_definition", "")
        label = node.get("label", node_id)

        if node_def in ("external_connector", "unmanaged_switch"):
            continue

        os_type = NODE_DEF_TO_OS.get(node_def, "ios")
        platform = NODE_DEF_TO_PLATFORM.get(node_def, node_def)

        device_entry = {
            "os": os_type,
            "platform": platform,
            "type": "router" if "router" in label else "switch",
            "connections": {
                "defaults": {"class": "unicon.Unicon"},
                "console": {
                    "protocol": "telnet",
                    "ip": base_url.replace("https://", "").replace("http://", ""),
                    "port": node.get("console_port"),
                },
            },
        }

        ssh_port = node.get("ssh_port")
        if ssh_port:
            device_entry["connections"]["ssh"] = {
                "protocol": "ssh",
                "ip": base_url.replace("https://", "").replace("http://", ""),
                "port": ssh_port,
            }

        testbed["devices"][label] = device_entry

    return testbed


def main():
    parser = argparse.ArgumentParser(
        description="Generate pyATS testbed from CML lab"
    )
    parser.add_argument("--lab-id", required=True, help="CML Lab ID")
    parser.add_argument("--output", default="tests/testbed.yaml",
                        help="Output testbed file path")
    args = parser.parse_args()

    base_url = os.environ.get("CML_URL", "https://192.168.137.125")
    username = os.environ.get("CML_USERNAME")
    password = os.environ.get("CML_PASSWORD")
    device_user = os.environ.get("DEVICE_USERNAME", "admin")
    device_pass = os.environ.get("DEVICE_PASSWORD", "admin")

    if not username or not password:
        print("ERROR: CML_USERNAME and CML_PASSWORD environment variables are required.")
        sys.exit(1)

    verify_tls = os.environ.get("CML_VERIFY_TLS", "false").lower() == "true"

    print(f"Authenticating to {base_url} ...")
    token = authenticate(base_url, username, password, verify_tls)

    print(f"Building testbed for lab {args.lab_id} ...")
    testbed = build_testbed(
        base_url, token, args.lab_id, device_user, device_pass, verify_tls
    )

    with open(args.output, "w", encoding="utf-8") as f:
        yaml.dump(testbed, f, default_flow_style=False, sort_keys=False)

    print(f"Testbed written to {args.output}")
    print(f"Devices found: {list(testbed['devices'].keys())}")


if __name__ == "__main__":
    main()
