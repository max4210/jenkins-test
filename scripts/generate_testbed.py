#!/usr/bin/env python3
"""Generate a pyATS testbed YAML from Terraform outputs (no CML API calls)."""

import argparse
import json
import os
import subprocess
import sys

import yaml


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

DEVICE_TYPE = {
    "iosv": "router",
    "iosvl2": "switch",
    "csr1000v": "router",
    "cat8000v": "router",
}


def get_terraform_output(tf_dir):
    """Run 'terraform output -json' and return parsed JSON."""
    result = subprocess.run(
        ["terraform", "output", "-json"],
        cwd=tf_dir,
        capture_output=True,
        text=True,
        check=True,
    )
    return json.loads(result.stdout)


def find_management_ip(interfaces):
    """Extract the first available IPv4 address from node interfaces."""
    for iface in interfaces:
        ip4_list = iface.get("ip4") or []
        for ip in ip4_list:
            if ip and not ip.startswith("127."):
                return ip
    return None


def build_testbed(tf_outputs, cml_host, device_username, device_password):
    """Build a pyATS testbed dict from Terraform output data."""
    devices_output = tf_outputs.get("devices", {}).get("value", {})

    testbed = {
        "testbed": {
            "name": f"CML-Lab-{tf_outputs.get('lab_id', {}).get('value', 'unknown')}",
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

    for device_name, device_info in devices_output.items():
        node_def = device_info.get("nodedefinition", "")
        label = device_info.get("label", device_name)
        interfaces = device_info.get("interfaces", [])

        os_type = NODE_DEF_TO_OS.get(node_def, "ios")
        platform = NODE_DEF_TO_PLATFORM.get(node_def, node_def)
        dev_type = DEVICE_TYPE.get(node_def, "router")

        mgmt_ip = find_management_ip(interfaces)

        device_entry = {
            "os": os_type,
            "platform": platform,
            "type": dev_type,
            "connections": {
                "defaults": {"class": "unicon.Unicon"},
            },
        }

        if mgmt_ip:
            device_entry["connections"]["cli"] = {
                "protocol": "ssh",
                "ip": mgmt_ip,
                "port": 22,
            }
        else:
            device_entry["connections"]["cli"] = {
                "protocol": "telnet",
                "ip": cml_host,
                "proxy": f"jump_host:{label}",
            }

        testbed["devices"][label] = device_entry

    return testbed


def main():
    parser = argparse.ArgumentParser(
        description="Generate pyATS testbed from Terraform outputs"
    )
    parser.add_argument("--tf-dir", default="terraform",
                        help="Path to Terraform directory")
    parser.add_argument("--output", default="tests/testbed.yaml",
                        help="Output testbed file path")
    args = parser.parse_args()

    cml_host = os.environ.get("CML_URL", "https://192.168.137.125")
    cml_host = cml_host.replace("https://", "").replace("http://", "")
    device_user = os.environ.get("DEVICE_USERNAME", "admin")
    device_pass = os.environ.get("DEVICE_PASSWORD", "admin")

    print(f"Reading Terraform outputs from {args.tf_dir} ...")
    tf_outputs = get_terraform_output(args.tf_dir)

    print("Building testbed ...")
    testbed = build_testbed(tf_outputs, cml_host, device_user, device_pass)

    with open(args.output, "w", encoding="utf-8") as f:
        yaml.dump(testbed, f, default_flow_style=False, sort_keys=False)

    print(f"Testbed written to {args.output}")
    print(f"Devices: {list(testbed['devices'].keys())}")


if __name__ == "__main__":
    main()
