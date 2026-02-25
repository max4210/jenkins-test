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
    # --- Global ---
    ["hostname ${try(local.router_data.hostname, "R1")}"],
    try(local.router_data.services.timestamps_debug, false) ? ["service timestamps debug datetime msec"] : [],
    try(local.router_data.services.timestamps_log, false) ? ["service timestamps log datetime msec"] : [],
    try(local.router_data.services.password_encryption, false) ? ["service password-encryption"] : [],
    ["no ip domain-lookup"],
    try(local.router_data.domain_name, "") != "" ? ["ip domain-name ${local.router_data.domain_name}"] : [],
    flatten([for ns in try(local.router_data.name_servers, []) : ["ip name-server ${ns}"]]),
    try(local.router_data.banner_motd, "") != "" ? ["banner motd ^${local.router_data.banner_motd}^"] : [],

    # --- Loopback ---
    local.router_loopback != null ? [
      "interface Loopback${local.router_loopback.id}",
      " ip address ${local.router_loopback.ip} ${local.router_loopback.mask}",
    ] : [],

    # --- Interfaces ---
    flatten([for iface in try(local.router_data.interfaces, []) : concat(
      ["interface ${iface.name}"],
      try(iface.description, "") != "" ? [" description ${iface.description}"] : [],
      try(iface.speed, "") != "" ? [" speed ${iface.speed}"] : [],
      try(iface.duplex, "") != "" ? [" duplex ${iface.duplex}"] : [],
      try(iface.dhcp, false) ? [" ip address dhcp"] : (
        try(iface.ip, "") != "" ? [" ip address ${iface.ip} ${iface.mask}"] : []
      ),
      flatten([for helper in try(iface.ip_helper_addresses, []) : [" ip helper-address ${helper}"]]),
      try(iface.shutdown, false) ? [" shutdown"] : [" no shutdown"],
    )]),

    # --- NTP ---
    try(local.router_data.ntp.timezone, "") != "" ? [
      "clock timezone ${local.router_data.ntp.timezone} ${try(local.router_data.ntp.timezone_offset, 0)}",
    ] : [],
    flatten([for srv in try(local.router_data.ntp.servers, []) : [
      "ntp server ${srv.address}${try(srv.prefer, false) ? " prefer" : ""}",
    ]]),

    # --- Logging ---
    try(local.router_data.logging.buffered_size, 0) > 0 ? [
      "logging buffered ${local.router_data.logging.buffered_size} ${try(local.router_data.logging.buffered_level, "informational")}",
    ] : [],
    try(local.router_data.logging.console_level, "") != "" ? ["logging console ${local.router_data.logging.console_level}"] : [],
    try(local.router_data.logging.trap_level, "") != "" ? ["logging trap ${local.router_data.logging.trap_level}"] : [],
    try(local.router_data.logging.source_interface, "") != "" ? ["logging source-interface ${local.router_data.logging.source_interface}"] : [],
    flatten([for h in try(local.router_data.logging.hosts, []) : ["logging host ${h}"]]),

    # --- SNMP ---
    try(local.router_data.snmp.location, "") != "" ? ["snmp-server location ${local.router_data.snmp.location}"] : [],
    try(local.router_data.snmp.contact, "") != "" ? ["snmp-server contact ${local.router_data.snmp.contact}"] : [],
    flatten([for c in try(local.router_data.snmp.communities, []) : [
      "snmp-server community ${c.name} ${c.access}${try(c.acl, "") != "" ? " ${c.acl}" : ""}",
    ]]),
    try(local.router_data.snmp.source_interface, "") != "" ? ["snmp-server source-interface informs ${local.router_data.snmp.source_interface}"] : [],
    flatten([for th in try(local.router_data.snmp.trap_hosts, []) : [
      "snmp-server host ${th.address} version ${try(th.version, "2c")} ${th.community}",
    ]]),

    # --- OSPF ---
    local.router_ospf != null ? concat(
      ["router ospf ${local.router_ospf.process_id}"],
      [" router-id ${local.router_ospf.router_id}"],
      try(local.router_ospf.passive_default, false) ? [" passive-interface default"] : [],
      [for ai in try(local.router_ospf.active_interfaces, []) : " no passive-interface ${ai}"],
      [for net in local.router_ospf.networks : " network ${net.network} ${net.wildcard} area ${net.area}"],
      try(local.router_ospf.default_information_originate, false) ? [" default-information originate"] : [],
      flatten([for r in try(local.router_ospf.redistribute, []) : [" redistribute ${r} subnets"]]),
    ) : [],

    # --- Static routes ---
    flatten([for sr in try(local.router_data.static_routes, []) : [
      "ip route ${sr.prefix} ${sr.mask} ${try(sr.next_hop, try(sr.interface, ""))}${try(sr.name, "") != "" ? " name ${sr.name}" : ""}${try(sr.ad, null) != null ? " ${sr.ad}" : ""}",
    ]]),

    local.auth_block,
  ))

  # ===================================================================
  #  SWITCH (iosvl2)
  # ===================================================================
  switch_loopback = try(local.switch_data.loopback, null)
  switch_ospf     = try(local.switch_data.ospf, null)

  switch_config = join("\n", concat(
    # --- Global ---
    ["hostname ${try(local.switch_data.hostname, "SW1")}"],
    try(local.switch_data.services.timestamps_debug, false) ? ["service timestamps debug datetime msec"] : [],
    try(local.switch_data.services.timestamps_log, false) ? ["service timestamps log datetime msec"] : [],
    try(local.switch_data.services.password_encryption, false) ? ["service password-encryption"] : [],
    ["no ip domain-lookup"],
    try(local.switch_data.domain_name, "") != "" ? ["ip domain-name ${local.switch_data.domain_name}"] : [],
    flatten([for ns in try(local.switch_data.name_servers, []) : ["ip name-server ${ns}"]]),
    try(local.switch_data.banner_motd, "") != "" ? ["banner motd ^${local.switch_data.banner_motd}^"] : [],

    # --- L3 routing ---
    try(local.switch_data.ip_routing, false) ? ["ip routing"] : [],

    # --- Spanning Tree ---
    try(local.switch_data.spanning_tree.mode, "") != "" ? ["spanning-tree mode ${local.switch_data.spanning_tree.mode}"] : [],
    flatten([for sp in try(local.switch_data.spanning_tree.vlan_priorities, []) : [
      "spanning-tree vlan ${sp.vlans} priority ${sp.priority}",
    ]]),

    # --- Loopback ---
    local.switch_loopback != null ? [
      "interface Loopback${local.switch_loopback.id}",
      " ip address ${local.switch_loopback.ip} ${local.switch_loopback.mask}",
    ] : [],

    # --- VLANs ---
    flatten([for v in try(local.switch_data.vlans, []) : [
      "vlan ${v.id}",
      " name ${try(v.name, "VLAN${v.id}")}",
    ]]),

    # --- VLAN interfaces (SVIs) ---
    flatten([for vi in try(local.switch_data.vlan_interfaces, []) : concat(
      ["interface Vlan${vi.vlan}"],
      try(vi.description, "") != "" ? [" description ${vi.description}"] : [],
      try(vi.dhcp, false) ? [" ip address dhcp"] : (
        try(vi.ip, "") != "" ? [" ip address ${vi.ip} ${vi.mask}"] : []
      ),
      flatten([for helper in try(vi.ip_helper_addresses, []) : [" ip helper-address ${helper}"]]),
      try(vi.shutdown, false) ? [" shutdown"] : [" no shutdown"],
    )]),

    # --- Physical interfaces ---
    flatten([for iface in try(local.switch_data.interfaces, []) : concat(
      ["interface ${iface.name}"],
      try(iface.description, "") != "" ? [" description ${iface.description}"] : [],
      try(iface.speed, "") != "" ? [" speed ${iface.speed}"] : [],
      try(iface.duplex, "") != "" ? [" duplex ${iface.duplex}"] : [],
      try(iface.mode, "access") == "trunk" ? concat(
        [" switchport trunk encapsulation dot1q"],
        [" switchport mode trunk"],
        try(iface.native_vlan, null) != null ? [" switchport trunk native vlan ${iface.native_vlan}"] : [],
        [" switchport trunk allowed vlan ${try(iface.allowed_vlans, "all")}"],
      ) : concat(
        [" switchport mode access"],
        [" switchport access vlan ${try(iface.vlan, 1)}"],
      ),
      try(iface.portfast, false) ? [" spanning-tree portfast"] : [],
      try(iface.bpduguard, false) ? [" spanning-tree bpduguard enable"] : [],
      try(iface.channel_group, null) != null ? [" channel-group ${iface.channel_group.id} mode ${iface.channel_group.mode}"] : [],
      try(iface.shutdown, false) ? [" shutdown"] : [" no shutdown"],
    )]),

    # --- DHCP excluded addresses ---
    flatten([for pool in try(local.switch_data.dhcp_pools, []) :
      flatten([for ex in try(pool.excluded_addresses, []) : [
        try(ex.end, "") != "" ?
          "ip dhcp excluded-address ${ex.start} ${ex.end}" :
          "ip dhcp excluded-address ${ex.start}",
      ]])
    ]),

    # --- DHCP pools ---
    flatten([for pool in try(local.switch_data.dhcp_pools, []) : concat(
      ["ip dhcp pool ${pool.name}"],
      [" network ${pool.network} ${pool.mask}"],
      try(pool.default_router, "") != "" ? [" default-router ${pool.default_router}"] : [],
      try(pool.dns_server, "") != "" ? [" dns-server ${pool.dns_server}"] : [],
      try(pool.domain_name, "") != "" ? [" domain-name ${pool.domain_name}"] : [],
      try(pool.lease_days, null) != null ? [" lease ${pool.lease_days}"] : [],
    )]),

    # --- NTP ---
    try(local.switch_data.ntp.timezone, "") != "" ? [
      "clock timezone ${local.switch_data.ntp.timezone} ${try(local.switch_data.ntp.timezone_offset, 0)}",
    ] : [],
    flatten([for srv in try(local.switch_data.ntp.servers, []) : [
      "ntp server ${srv.address}${try(srv.prefer, false) ? " prefer" : ""}",
    ]]),

    # --- Logging ---
    try(local.switch_data.logging.buffered_size, 0) > 0 ? [
      "logging buffered ${local.switch_data.logging.buffered_size} ${try(local.switch_data.logging.buffered_level, "informational")}",
    ] : [],
    try(local.switch_data.logging.console_level, "") != "" ? ["logging console ${local.switch_data.logging.console_level}"] : [],
    try(local.switch_data.logging.trap_level, "") != "" ? ["logging trap ${local.switch_data.logging.trap_level}"] : [],
    try(local.switch_data.logging.source_interface, "") != "" ? ["logging source-interface ${local.switch_data.logging.source_interface}"] : [],
    flatten([for h in try(local.switch_data.logging.hosts, []) : ["logging host ${h}"]]),

    # --- SNMP ---
    try(local.switch_data.snmp.location, "") != "" ? ["snmp-server location ${local.switch_data.snmp.location}"] : [],
    try(local.switch_data.snmp.contact, "") != "" ? ["snmp-server contact ${local.switch_data.snmp.contact}"] : [],
    flatten([for c in try(local.switch_data.snmp.communities, []) : [
      "snmp-server community ${c.name} ${c.access}${try(c.acl, "") != "" ? " ${c.acl}" : ""}",
    ]]),
    try(local.switch_data.snmp.source_interface, "") != "" ? ["snmp-server source-interface informs ${local.switch_data.snmp.source_interface}"] : [],
    flatten([for th in try(local.switch_data.snmp.trap_hosts, []) : [
      "snmp-server host ${th.address} version ${try(th.version, "2c")} ${th.community}",
    ]]),

    # --- OSPF ---
    local.switch_ospf != null ? concat(
      ["router ospf ${local.switch_ospf.process_id}"],
      [" router-id ${local.switch_ospf.router_id}"],
      try(local.switch_ospf.passive_default, false) ? [" passive-interface default"] : [],
      [for ai in try(local.switch_ospf.active_interfaces, []) : " no passive-interface ${ai}"],
      [for net in local.switch_ospf.networks : " network ${net.network} ${net.wildcard} area ${net.area}"],
      try(local.switch_ospf.default_information_originate, false) ? [" default-information originate"] : [],
      flatten([for r in try(local.switch_ospf.redistribute, []) : [" redistribute ${r} subnets"]]),
    ) : [],

    # --- Static routes ---
    flatten([for sr in try(local.switch_data.static_routes, []) : [
      "ip route ${sr.prefix} ${sr.mask} ${try(sr.next_hop, try(sr.interface, ""))}${try(sr.name, "") != "" ? " name ${sr.name}" : ""}${try(sr.ad, null) != null ? " ${sr.ad}" : ""}",
    ]]),

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
    # --- Global ---
    ["hostname ${try(local.wlc_data.hostname, "WLC1")}"],
    try(local.wlc_data.services.timestamps_debug, false) ? ["service timestamps debug datetime msec"] : [],
    try(local.wlc_data.services.timestamps_log, false) ? ["service timestamps log datetime msec"] : [],
    try(local.wlc_data.services.password_encryption, false) ? ["service password-encryption"] : [],
    ["no ip domain-lookup"],
    try(local.wlc_data.domain_name, "") != "" ? ["ip domain-name ${local.wlc_data.domain_name}"] : [],
    flatten([for ns in try(local.wlc_data.name_servers, []) : ["ip name-server ${ns}"]]),
    try(local.wlc_data.banner_motd, "") != "" ? ["banner motd ^${local.wlc_data.banner_motd}^"] : [],

    # --- Loopback ---
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
      ] : try(wlan.security.type, "open") == "wpa3-personal" ? [
        " security wpa psk set-key ascii 0 ${var.device_password}",
        " security wpa akm sae",
        " no security wpa akm dot1x",
        " security wpa wpa3",
      ] : [
        " no security wpa",
        " no security wpa akm dot1x",
        " no security ft",
      ],
      [" no shutdown"],
    )]),

    # --- Policy profiles ---
    flatten([for pp in local.wlc_pp : concat(
      ["wireless profile policy ${pp.name}"],
      [" vlan ${pp.vlan}"],
      try(pp.aaa_override, false) ? [" aaa-override"] : [],
      try(pp.central_switching, false) ? [" central switching"] : [],
      [" no shutdown"],
    )]),

    # --- Policy tags (map WLAN → policy profile) ---
    flatten([for pt in local.wlc_pt : concat(
      ["wireless tag policy ${pt.name}"],
      [for m in try(pt.mappings, []) : " wlan ${m.wlan} policy ${m.policy}"],
    )]),

    # --- NTP ---
    try(local.wlc_data.ntp.timezone, "") != "" ? [
      "clock timezone ${local.wlc_data.ntp.timezone} ${try(local.wlc_data.ntp.timezone_offset, 0)}",
    ] : [],
    flatten([for srv in try(local.wlc_data.ntp.servers, []) : [
      "ntp server ${srv.address}${try(srv.prefer, false) ? " prefer" : ""}",
    ]]),

    # --- Logging ---
    try(local.wlc_data.logging.buffered_size, 0) > 0 ? [
      "logging buffered ${local.wlc_data.logging.buffered_size} ${try(local.wlc_data.logging.buffered_level, "informational")}",
    ] : [],
    try(local.wlc_data.logging.console_level, "") != "" ? ["logging console ${local.wlc_data.logging.console_level}"] : [],
    try(local.wlc_data.logging.trap_level, "") != "" ? ["logging trap ${local.wlc_data.logging.trap_level}"] : [],
    try(local.wlc_data.logging.source_interface, "") != "" ? ["logging source-interface ${local.wlc_data.logging.source_interface}"] : [],
    flatten([for h in try(local.wlc_data.logging.hosts, []) : ["logging host ${h}"]]),

    # --- SNMP ---
    try(local.wlc_data.snmp.location, "") != "" ? ["snmp-server location ${local.wlc_data.snmp.location}"] : [],
    try(local.wlc_data.snmp.contact, "") != "" ? ["snmp-server contact ${local.wlc_data.snmp.contact}"] : [],
    flatten([for c in try(local.wlc_data.snmp.communities, []) : [
      "snmp-server community ${c.name} ${c.access}${try(c.acl, "") != "" ? " ${c.acl}" : ""}",
    ]]),
    try(local.wlc_data.snmp.source_interface, "") != "" ? ["snmp-server source-interface informs ${local.wlc_data.snmp.source_interface}"] : [],
    flatten([for th in try(local.wlc_data.snmp.trap_hosts, []) : [
      "snmp-server host ${th.address} version ${try(th.version, "2c")} ${th.community}",
    ]]),

    # --- OSPF ---
    local.wlc_ospf != null ? concat(
      ["router ospf ${local.wlc_ospf.process_id}"],
      [" router-id ${local.wlc_ospf.router_id}"],
      try(local.wlc_ospf.passive_default, false) ? [" passive-interface default"] : [],
      [for ai in try(local.wlc_ospf.active_interfaces, []) : " no passive-interface ${ai}"],
      [for net in local.wlc_ospf.networks : " network ${net.network} ${net.wildcard} area ${net.area}"],
      try(local.wlc_ospf.default_information_originate, false) ? [" default-information originate"] : [],
      flatten([for r in try(local.wlc_ospf.redistribute, []) : [" redistribute ${r} subnets"]]),
    ) : [],

    # --- Static routes (replaces hardcoded default route) ---
    flatten([for sr in try(local.wlc_data.static_routes, []) : [
      "ip route ${sr.prefix} ${sr.mask} ${try(sr.next_hop, try(sr.interface, ""))}${try(sr.name, "") != "" ? " name ${sr.name}" : ""}${try(sr.ad, null) != null ? " ${sr.ad}" : ""}",
    ]]),

    local.auth_block,
  ))
}
