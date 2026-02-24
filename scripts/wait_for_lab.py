#!/usr/bin/env python3
"""Poll CML until all lab nodes have reached BOOTED state."""

import argparse
import os
import sys
import time
import urllib3

import requests

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

DEFAULT_TIMEOUT = 600
POLL_INTERVAL = 15


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


def get_node_state(base_url, token, lab_id, node_id, verify_tls=False):
    headers = {"Authorization": f"Bearer {token}"}
    resp = requests.get(
        f"{base_url}/api/v2/labs/{lab_id}/nodes/{node_id}",
        headers=headers,
        verify=verify_tls,
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()


def wait_for_convergence(base_url, token, lab_id, timeout, verify_tls=False):
    start = time.time()
    while time.time() - start < timeout:
        node_ids = get_lab_nodes(base_url, token, lab_id, verify_tls)
        all_booted = True

        for node_id in node_ids:
            node = get_node_state(base_url, token, lab_id, node_id, verify_tls)
            label = node.get("label", node_id)
            state = node.get("state", "UNKNOWN")
            node_def = node.get("node_definition", "")

            if node_def == "external_connector":
                continue

            print(f"  {label}: {state}")
            if state != "BOOTED":
                all_booted = False

        if all_booted:
            print("\nAll nodes are BOOTED.")
            return True

        elapsed = int(time.time() - start)
        print(f"  ... waiting ({elapsed}s / {timeout}s)\n")
        time.sleep(POLL_INTERVAL)

    return False


def main():
    parser = argparse.ArgumentParser(description="Wait for CML lab nodes to boot")
    parser.add_argument("--lab-id", required=True, help="CML Lab ID")
    parser.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT,
                        help=f"Max seconds to wait (default: {DEFAULT_TIMEOUT})")
    args = parser.parse_args()

    base_url = os.environ.get("CML_URL", "https://192.168.137.125")
    username = os.environ.get("CML_USERNAME")
    password = os.environ.get("CML_PASSWORD")

    if not username or not password:
        print("ERROR: CML_USERNAME and CML_PASSWORD environment variables are required.")
        sys.exit(1)

    verify_tls = os.environ.get("CML_VERIFY_TLS", "false").lower() == "true"

    print(f"Authenticating to {base_url} ...")
    token = authenticate(base_url, username, password, verify_tls)

    print(f"Waiting for lab {args.lab_id} to converge (timeout: {args.timeout}s) ...\n")
    if wait_for_convergence(base_url, token, args.lab_id, args.timeout, verify_tls):
        sys.exit(0)
    else:
        print(f"\nERROR: Lab did not converge within {args.timeout} seconds.")
        sys.exit(1)


if __name__ == "__main__":
    main()
