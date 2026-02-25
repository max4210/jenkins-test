# Build IOS-XE / C9800-CL day-0 configs from data/*.nac.yaml
# Credentials injected via Terraform variables (Jenkins credentials store)

locals {
  router_data = try(yamldecode(file("${path.module}/../data/router.nac.yaml"))["router"], {})
  switch_data = try(yamldecode(file("${path.module}/../data/switch.nac.yaml"))["switch"], {})
  wlc_data    = try(yamldecode(file("${path.module}/../data/wlc_9800.nac.yaml"))["wlc_9800"], {})

  # ---------- shared auth block ----------
  auth_block = [
    "username ${var.device_username} privilege 15 secret ${var.device_password}",
    "enable secret ${var.device_password}",
    "ip domain-name lab.local",
    "crypto key generate rsa modulus 2048",
    "ip ssh version 2",
    "line con 0",
    " exec-timeout 0 0",
    " logging synchronous",
    "line vty 0 4",
    " login local",
    " transport input telnet ssh",
  ]

  # ===================================================================
  #  ROUTER (iosv)
  # ===================================================================
  router_loopback = try(local.router_data.loopback, null)
  router_ospf     = try(local.router_data.ospf, null)

  router_config = join("\n", concat(
    ["hostname ${try(local.router_data.hostname, "R1")}"],
    ["no ip domain-lookup"],

    # Loopback
    local.router_loopback != null ? [
      "interface Loopback${local.router_loopback.id}",
      " ip address ${local.router_loopback.ip} ${local.router_loopback.mask}",
    ] : [],

    # Interfaces (static IP or DHCP)
    flatten([for iface in try(local.router_data.interfaces, []) : concat(
      ["interface ${iface.name}"],
      try(iface.description, "") != "" ? [" description ${iface.description}"] : [],
      try(iface.dhcp, false) ? [" ip address dhcp"] : [
        " ip address ${iface.ip} ${iface.mask}",
      ],
      [" no shutdown"],
    )]),

    # OSPF
    local.router_ospf != null ? concat(
      ["router ospf ${local.router_ospf.process_id}"],
      [" router-id ${local.router_ospf.router_id}"],
      try(local.router_ospf.passive_default, false) ? [" passive-interface default"] : [],
      [for ai in try(local.router_ospf.active_interfaces, []) : " no passive-interface ${ai}"],
      [for net in local.router_ospf.networks : " network ${net.network} ${net.wildcard} area ${net.area}"],
    ) : [],

    local.auth_block,
  ))

  # ===================================================================
  #  SWITCH (iosvl2)
  # ===================================================================
  switch_loopback = try(local.switch_data.loopback, null)
  switch_ospf     = try(local.switch_data.ospf, null)

  switch_config = join("\n", concat(
    ["hostname ${try(local.switch_data.hostname, "SW1")}"],
    ["no ip domain-lookup"],

    # Enable L3 routing
    try(local.switch_data.ip_routing, false) ? ["ip routing"] : [],

    # Loopback
    local.switch_loopback != null ? [
      "interface Loopback${local.switch_loopback.id}",
      " ip address ${local.switch_loopback.ip} ${local.switch_loopback.mask}",
    ] : [],

    # VLANs
    flatten([for v in try(local.switch_data.vlans, []) : [
      "vlan ${v.id}",
      " name ${try(v.name, "VLAN${v.id}")}",
    ]]),

    # VLAN interfaces (SVIs) — static IP or DHCP
    flatten([for vi in try(local.switch_data.vlan_interfaces, []) : concat(
      ["interface Vlan${vi.vlan}"],
      try(vi.dhcp, false) ? [" ip address dhcp"] : [
        " ip address ${vi.ip} ${vi.mask}",
      ],
      [" no shutdown"],
    )]),

    # Physical interfaces — access or trunk
    flatten([for iface in try(local.switch_data.interfaces, []) : concat(
      ["interface ${iface.name}"],
      try(iface.description, "") != "" ? [" description ${iface.description}"] : [],
      try(iface.mode, "access") == "trunk" ? [
        " switchport trunk encapsulation dot1q",
        " switchport mode trunk",
        " switchport trunk allowed vlan ${try(iface.allowed_vlans, "all")}",
      ] : [
        " switchport mode access",
        " switchport access vlan ${try(iface.vlan, 1)}",
      ],
      [" no shutdown"],
    )]),

    # OSPF
    local.switch_ospf != null ? concat(
      ["router ospf ${local.switch_ospf.process_id}"],
      [" router-id ${local.switch_ospf.router_id}"],
      try(local.switch_ospf.passive_default, false) ? [" passive-interface default"] : [],
      [for ai in try(local.switch_ospf.active_interfaces, []) : " no passive-interface ${ai}"],
      [for net in local.switch_ospf.networks : " network ${net.network} ${net.wildcard} area ${net.area}"],
    ) : [],

    local.auth_block,
  ))

  # ===================================================================
  #  WLC — C9800-CL
  # ===================================================================
  wlc_loopback   = try(local.wlc_data.loopback, null)
  wlc_ospf       = try(local.wlc_data.ospf, null)
  wlc_mgmt       = try(local.wlc_data.management, {})
  wlc_mgmt_vlan  = try(local.wlc_mgmt.vlan, 20)
  wlc_mgmt_ip    = try(local.wlc_mgmt.ip, "10.0.20.1")
  wlc_mgmt_mask  = try(local.wlc_mgmt.mask, "255.255.255.0")
  wlc_mgmt_gw    = try(local.wlc_mgmt.gateway, "10.0.20.2")
  wlc_trunk_if   = try(local.wlc_data.trunk_interface, "GigabitEthernet1")
  wlc_dhcp_if    = try(local.wlc_data.mgmt_dhcp_interface, "GigabitEthernet2")
  wlc_vlans      = try(local.wlc_data.vlans, [])
  wlc_country    = try(local.wlc_data.wireless.country, "US")
  wlc_wlans      = try(local.wlc_data.wireless.wlans, [])
  wlc_pp         = try(local.wlc_data.wireless.policy_profiles, [])
  wlc_pt         = try(local.wlc_data.wireless.policy_tags, [])

  wlc_config = join("\n", concat(
    # --- base ---
    ["hostname ${try(local.wlc_data.hostname, "WLC1")}"],
    ["no ip domain-lookup"],

    # Loopback
    local.wlc_loopback != null ? [
      "interface Loopback${local.wlc_loopback.id}",
      " ip address ${local.wlc_loopback.ip} ${local.wlc_loopback.mask}",
    ] : [],

    # --- VLANs ---
    flatten([for v in local.wlc_vlans : [
      "vlan ${v.id}",
      " name ${try(v.name, "VLAN${v.id}")}",
    ]]),

    # --- Trunk port (slot 0) ---
    [
      "interface ${local.wlc_trunk_if}",
      " switchport mode trunk",
      " switchport trunk allowed vlan ${join(",", [for v in local.wlc_vlans : tostring(v.id)])}",
      " no shutdown",
    ],

    # --- DHCP management port (slot 1, routed) ---
    [
      "interface ${local.wlc_dhcp_if}",
      " no switchport",
      " ip address dhcp",
      " no shutdown",
    ],

    # --- Management SVI ---
    [
      "interface Vlan${local.wlc_mgmt_vlan}",
      " ip address ${local.wlc_mgmt_ip} ${local.wlc_mgmt_mask}",
      " no shutdown",
    ],

    # Default route via switch
    ["ip route 0.0.0.0 0.0.0.0 ${local.wlc_mgmt_gw}"],

    # --- Wireless core ---
    [
      "wireless management interface Vlan${local.wlc_mgmt_vlan}",
      "wireless country ${local.wlc_country}",
      "wireless config vwlc-ssc key-size 2048 signature-algo sha256 password 0 ${var.device_password}",
    ],

    # --- WLAN profiles (SSIDs + security) ---
    flatten([for wlan in local.wlc_wlans : concat(
      ["wlan ${wlan.ssid} ${wlan.wlan_id} ${wlan.ssid}"],
      try(wlan.security.type, "open") == "wpa2-personal" ? [
        " security wpa psk set-key ascii 0 ${var.device_password}",
        " security wpa akm psk",
        " no security wpa akm dot1x",
      ] : [
        " no security wpa",
        " no security wpa akm dot1x",
        " no security ft",
      ],
      [" no shutdown"],
    )]),

    # --- Policy profiles ---
    flatten([for pp in local.wlc_pp : [
      "wireless profile policy ${pp.name}",
      " vlan ${pp.vlan}",
      " no shutdown",
    ]]),

    # --- Policy tags (map WLAN → policy profile) ---
    flatten([for pt in local.wlc_pt : concat(
      ["wireless tag policy ${pt.name}"],
      [for m in try(pt.mappings, []) : " wlan ${m.wlan} policy ${m.policy}"],
    )]),

    # --- OSPF ---
    local.wlc_ospf != null ? concat(
      ["router ospf ${local.wlc_ospf.process_id}"],
      [" router-id ${local.wlc_ospf.router_id}"],
      try(local.wlc_ospf.passive_default, false) ? [" passive-interface default"] : [],
      [for ai in try(local.wlc_ospf.active_interfaces, []) : " no passive-interface ${ai}"],
      [for net in local.wlc_ospf.networks : " network ${net.network} ${net.wildcard} area ${net.area}"],
    ) : [],

    local.auth_block,
  ))
}
