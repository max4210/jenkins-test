#!/usr/bin/env python3
"""
pyATS test suite for the CML lab.

Validates that all devices are reachable, interfaces are up,
and basic routing is functioning after Terraform provisioning.

Run with:
    pyats run job tests/test_basic.py --testbed-file tests/testbed.yaml
"""

import logging
import os

from pyats import aetest
from genie.testbed import load

logger = logging.getLogger(__name__)

EXPECTED_DEVICES = ["router1", "router2", "switch1"]

PING_TARGETS = {
    "router1": ["10.0.12.2", "10.0.1.2"],
    "router2": ["10.0.12.1", "10.0.2.2"],
}


class CommonSetup(aetest.CommonSetup):
    """Connect to all devices in the testbed."""

    @aetest.subsection
    def load_testbed(self, testbed):
        self.parent.parameters["testbed"] = testbed

    @aetest.subsection
    def connect_to_devices(self, testbed):
        for name in EXPECTED_DEVICES:
            device = testbed.devices.get(name)
            if device is None:
                self.failed(f"Device '{name}' not found in testbed")
            logger.info("Connecting to %s ...", name)
            device.connect(
                log_stdout=False,
                learn_hostname=True,
                init_exec_commands=[],
                init_config_commands=[],
            )


class TestDeviceReachability(aetest.Testcase):
    """Verify all expected devices are connected and responsive."""

    @aetest.test
    def check_connected(self, testbed):
        for name in EXPECTED_DEVICES:
            device = testbed.devices[name]
            if not device.connected:
                self.failed(f"{name} is not connected")
            logger.info("%s: connected", name)

    @aetest.test
    def check_show_version(self, testbed):
        for name in EXPECTED_DEVICES:
            device = testbed.devices[name]
            version = device.parse("show version")
            hostname = version.get("version", {}).get("hostname", "UNKNOWN")
            logger.info("%s: hostname from 'show version' = %s", name, hostname)


class TestInterfaces(aetest.Testcase):
    """Verify key interfaces are up/up."""

    @aetest.test
    def check_interfaces_up(self, testbed):
        failed_interfaces = []
        for name in EXPECTED_DEVICES:
            device = testbed.devices[name]
            interfaces = device.parse("show ip interface brief")

            intf_data = interfaces.get("interface", {})
            for intf_name, intf_info in intf_data.items():
                if "Loopback" in intf_name:
                    continue
                status = intf_info.get("status", "unknown")
                protocol = intf_info.get("protocol", "unknown")
                if status != "up" or protocol != "up":
                    failed_interfaces.append(
                        f"{name} {intf_name}: {status}/{protocol}"
                    )
                    logger.warning(
                        "%s %s: %s/%s", name, intf_name, status, protocol
                    )
                else:
                    logger.info(
                        "%s %s: up/up", name, intf_name
                    )

        if failed_interfaces:
            self.failed(
                f"Interfaces not up/up: {', '.join(failed_interfaces)}"
            )


class TestRouting(aetest.Testcase):
    """Verify basic IP routing between routers."""

    @aetest.test
    def check_routing_table(self, testbed):
        for name in ["router1", "router2"]:
            device = testbed.devices[name]
            routes = device.parse("show ip route")
            route_entries = routes.get("vrf", {}).get("default", {}).get(
                "address_family", {}
            ).get("ipv4", {}).get("routes", {})
            logger.info("%s: %d routes in table", name, len(route_entries))
            if len(route_entries) < 3:
                self.failed(
                    f"{name} has fewer routes than expected "
                    f"({len(route_entries)} < 3)"
                )

    @aetest.test
    def check_ping_reachability(self, testbed):
        failures = []
        for device_name, targets in PING_TARGETS.items():
            device = testbed.devices[device_name]
            for target_ip in targets:
                logger.info("%s: pinging %s ...", device_name, target_ip)
                try:
                    result = device.ping(target_ip, count=3)
                    if "!!!" not in str(result) and "Success rate is 100" not in str(result):
                        failures.append(f"{device_name} -> {target_ip}")
                        logger.warning("%s -> %s: FAILED", device_name, target_ip)
                    else:
                        logger.info("%s -> %s: OK", device_name, target_ip)
                except Exception as exc:
                    failures.append(f"{device_name} -> {target_ip} ({exc})")
                    logger.warning(
                        "%s -> %s: EXCEPTION %s", device_name, target_ip, exc
                    )

        if failures:
            self.failed(f"Ping failures: {', '.join(failures)}")


class TestLoopbackReachability(aetest.Testcase):
    """Verify routers can reach each other's loopbacks."""

    @aetest.test
    def ping_loopbacks(self, testbed):
        router1 = testbed.devices["router1"]
        router2 = testbed.devices["router2"]

        failures = []

        logger.info("router1: pinging router2 loopback 2.2.2.2 ...")
        try:
            result = router1.ping("2.2.2.2", source="1.1.1.1", count=5)
            if "Success rate is 0" in str(result):
                failures.append("router1(1.1.1.1) -> router2(2.2.2.2)")
        except Exception as exc:
            failures.append(f"router1 -> 2.2.2.2 ({exc})")

        logger.info("router2: pinging router1 loopback 1.1.1.1 ...")
        try:
            result = router2.ping("1.1.1.1", source="2.2.2.2", count=5)
            if "Success rate is 0" in str(result):
                failures.append("router2(2.2.2.2) -> router1(1.1.1.1)")
        except Exception as exc:
            failures.append(f"router2 -> 1.1.1.1 ({exc})")

        if failures:
            self.failed(f"Loopback ping failures: {', '.join(failures)}")


class CommonCleanup(aetest.CommonCleanup):
    """Disconnect from all devices."""

    @aetest.subsection
    def disconnect_from_devices(self, testbed):
        for name, device in testbed.devices.items():
            if device.connected:
                logger.info("Disconnecting from %s ...", name)
                device.disconnect()


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--testbed", default="tests/testbed.yaml")
    args = parser.parse_args()

    testbed = load(args.testbed)
    aetest.main(testbed=testbed)
