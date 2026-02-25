# Read NAC YAML data and build IOS-XE / C9800 config strings
# Credentials come from Terraform variables (injected by Jenkins from credentials store)

locals {
  router_data = try(yamldecode(file("${path.module}/../data/router.nac.yaml"))["router"], {})
  switch_data = try(yamldecode(file("${path.module}/../data/switch.nac.yaml"))["switch"], {})
  wlc_data    = try(yamldecode(file("${path.module}/../data/wlc_9800.nac.yaml"))["wlc_9800"], {})

  # Common CLI block using credentials from variables
  auth_block = [
    "line con 0",
    " exec-timeout 0 0",
    "line vty 0 4",
    " login local",
    " transport input telnet ssh",
    "username ${var.device_username} privilege 15 secret ${var.device_password}",
    "enable secret ${var.device_password}",
    "ip domain-name lab.local",
    "crypto key generate rsa modulus 2048",
    "ip ssh version 2",
  ]

  # Router config: hostname + interfaces with IP (from data)
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
    local.auth_block
  ))

  # Switch config: hostname + vlans + vlan_interfaces (IPs from data) + interfaces
  switch_config = join("\n", concat(
    [
      "hostname ${try(local.switch_data.hostname, "SW1")}",
      "no ip domain-lookup",
    ],
    flatten([for v in try(local.switch_data.vlans, []) : [
      "vlan ${v.id}",
      " name ${try(v.name, "VLAN${v.id}")}",
    ]]),
    flatten([for vi in try(local.switch_data.vlan_interfaces, []) : [
      "interface Vlan${vi.vlan}",
      " ip address ${vi.ip} ${vi.mask}",
      " no shutdown",
    ]]),
    flatten([for iface in try(local.switch_data.interfaces, []) : [
      "interface ${iface.name}",
      " switchport mode access",
      " switchport access vlan ${iface.vlan}",
      " no shutdown",
    ]]),
    local.auth_block
  ))

  # WLC (C9800-CL) config: VLAN + management interface + wireless management interface
  # C9800-CL uses interface vlan X for management, not IP on physical port
  wlc_mgmt       = try(local.wlc_data.management, {})
  wlc_mgmt_vlan  = try(local.wlc_mgmt.vlan, 20)
  wlc_mgmt_ip    = try(local.wlc_mgmt.ip, "10.0.2.1")
  wlc_mgmt_mask  = try(local.wlc_mgmt.mask, "255.255.255.0")
  wlc_mgmt_gw    = try(local.wlc_mgmt.gateway, "10.0.2.2")

  wlc_config = join("\n", concat(
    [
      "hostname ${try(local.wlc_data.hostname, "WLC1")}",
      "no ip domain-lookup",
      "vlan ${local.wlc_mgmt_vlan}",
      " name management",
      "interface GigabitEthernet0",
      " switchport mode access",
      " switchport access vlan ${local.wlc_mgmt_vlan}",
      " no shutdown",
      "interface Vlan${local.wlc_mgmt_vlan}",
      " ip address ${local.wlc_mgmt_ip} ${local.wlc_mgmt_mask}",
      " no shutdown",
      "ip route 0.0.0.0 0.0.0.0 ${local.wlc_mgmt_gw}",
      "wireless management interface Vlan${local.wlc_mgmt_vlan}",
      "wireless country US",
      "wireless config vwlc-ssc key-size 2048 signature-algo sha256 password 0 ${var.device_password}",
    ],
    flatten([for ssid in try(local.wlc_data.wireless.ssids, []) : [
      "! SSID: ${ssid.name} vlan ${try(ssid.vlan, 1)} ${try(ssid.security, "")}",
    ]]),
    local.auth_block
  ))
}
