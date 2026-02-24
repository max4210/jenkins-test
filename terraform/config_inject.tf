# Read NAC YAML data and build IOS-XE / C9800 config strings

locals {
  router_data = try(yamldecode(file("${path.module}/../data/router.nac.yaml"))["router"], {})
  switch_data = try(yamldecode(file("${path.module}/../data/switch.nac.yaml"))["switch"], {})
  wlc_data    = try(yamldecode(file("${path.module}/../data/wlc_9800.nac.yaml"))["wlc_9800"], {})

  # Router config: hostname + interfaces with IP
  router_config = join("\n", concat(
    [
      "hostname ${try(local.router_data.hostname, "R1")}",
      "no ip domain-lookup",
    ],
    flatten([for iface in try(local.router_data.interfaces, []) : [
      "interface ${iface.name}",
      " ip address ${iface.ip} ${iface.mask}",
      " no shutdown",
    ]]),
    [
      "line con 0",
      " exec-timeout 0 0",
      "line vty 0 4",
      " login local",
      " transport input telnet ssh",
      "username admin privilege 15 secret admin",
      "enable secret admin",
      "ip domain-name lab.local",
      "crypto key generate rsa modulus 2048",
      "ip ssh version 2",
    ]
  ))

  # Switch config: hostname + vlans + interfaces
  switch_config = join("\n", concat(
    [
      "hostname ${try(local.switch_data.hostname, "SW1")}",
      "no ip domain-lookup",
    ],
    flatten([for v in try(local.switch_data.vlans, []) : [
      "vlan ${v.id}",
      " name ${try(v.name, "VLAN${v.id}")}",
    ]]),
    flatten([for iface in try(local.switch_data.interfaces, []) : [
      "interface ${iface.name}",
      " switchport mode access",
      " switchport access vlan ${iface.vlan}",
      " no shutdown",
    ]]),
    [
      "line con 0",
      " exec-timeout 0 0",
      "line vty 0 4",
      " login local",
      " transport input telnet ssh",
      "username admin privilege 15 secret admin",
      "enable secret admin",
      "ip domain-name lab.local",
      "crypto key generate rsa modulus 2048",
      "ip ssh version 2",
    ]
  ))

  # WLC config: use iosv as fallback (C9800-CL may not be available)
  # Simplified IOS-XE style for WLC placeholder
  wlc_config = join("\n", concat(
    [
      "hostname ${try(local.wlc_data.hostname, "WLC1")}",
      "no ip domain-lookup",
    ],
    flatten([for ssid in try(local.wlc_data.wireless.ssids, []) : [
      "! SSID: ${ssid.name} vlan ${try(ssid.vlan, 1)} ${try(ssid.security, "")}",
    ]]),
    [
      "interface GigabitEthernet0",
      " ip address 10.0.3.1 255.255.255.0",
      " no shutdown",
      "line con 0",
      " exec-timeout 0 0",
      "line vty 0 4",
      " login local",
      " transport input telnet ssh",
      "username admin privilege 15 secret admin",
      "enable secret admin",
      "ip domain-name lab.local",
      "crypto key generate rsa modulus 2048",
      "ip ssh version 2",
    ]
  ))
}
