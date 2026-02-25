terraform {
  required_providers {
    cml2 = {
      source  = "CiscoDevNet/cml2"
      version = "~> 0.8"
    }
  }
  required_version = ">= 1.5.0"
}

provider "cml2" {
  address  = var.cml_url
  username = var.cml_username
  password = var.cml_password

  skip_verify = var.cml_skip_verify
}

# --- Lab ---

resource "cml2_lab" "network_lab" {
  title       = var.lab_title
  description = "NAC-style lab: router, switch, C9800 WLC with OSPF, bridge0 management"
}

# --- External Connector (bridge0) ---

resource "cml2_node" "ext_connector" {
  lab_id         = cml2_lab.network_lab.id
  label          = "bridge0"
  nodedefinition = "external_connector"
  configuration  = "System Bridge"
  x              = 0
  y              = -250
}

resource "cml2_node" "mgmt_switch" {
  lab_id         = cml2_lab.network_lab.id
  label          = "mgmt-hub"
  nodedefinition = "unmanaged_switch"
  x              = 0
  y              = -150
}

# --- Nodes (config from locals in config_inject.tf) ---

resource "cml2_node" "router" {
  lab_id         = cml2_lab.network_lab.id
  label          = "router"
  nodedefinition = "iosv"
  x              = -200
  y              = 0
  configuration  = local.router_config
}

resource "cml2_node" "switch" {
  lab_id         = cml2_lab.network_lab.id
  label          = "switch"
  nodedefinition = "iosvl2"
  x              = 0
  y              = 100
  configuration  = local.switch_config
}

resource "cml2_node" "wlc" {
  lab_id         = cml2_lab.network_lab.id
  label          = "wlc"
  nodedefinition = var.wlc_node_definition
  x              = 200
  y              = 0
  configuration  = local.wlc_config
}

# --- Data-plane Links ---

resource "cml2_link" "router_to_switch" {
  lab_id = cml2_lab.network_lab.id
  node_a = cml2_node.router.id
  slot_a = 0                          # Router Gi0/0
  node_b = cml2_node.switch.id
  slot_b = 0                          # Switch Gi0/0
}

resource "cml2_link" "wlc_to_switch" {
  lab_id = cml2_lab.network_lab.id
  node_a = cml2_node.wlc.id
  slot_a = 0                          # WLC Gi1 (trunk)
  node_b = cml2_node.switch.id
  slot_b = 1                          # Switch Gi0/1
}

# --- Management Links (bridge0 → mgmt-hub → all devices) ---

resource "cml2_link" "ext_to_mgmt_hub" {
  lab_id = cml2_lab.network_lab.id
  node_a = cml2_node.ext_connector.id
  slot_a = 0
  node_b = cml2_node.mgmt_switch.id
  slot_b = 0
}

resource "cml2_link" "router_to_mgmt_hub" {
  lab_id = cml2_lab.network_lab.id
  node_a = cml2_node.router.id
  slot_a = 1                          # Router Gi0/1
  node_b = cml2_node.mgmt_switch.id
  slot_b = 1
}

resource "cml2_link" "switch_to_mgmt_hub" {
  lab_id = cml2_lab.network_lab.id
  node_a = cml2_node.switch.id
  slot_a = 2                          # Switch Gi0/2
  node_b = cml2_node.mgmt_switch.id
  slot_b = 2
}

resource "cml2_link" "wlc_to_mgmt_hub" {
  lab_id = cml2_lab.network_lab.id
  node_a = cml2_node.wlc.id
  slot_a = 1                          # WLC Gi2 (routed, DHCP)
  node_b = cml2_node.mgmt_switch.id
  slot_b = 3
}

# --- Lifecycle ---

resource "cml2_lifecycle" "network_lab" {
  lab_id = cml2_lab.network_lab.id
  state  = "STARTED"

  depends_on = [
    cml2_node.router,
    cml2_node.switch,
    cml2_node.wlc,
    cml2_node.ext_connector,
    cml2_node.mgmt_switch,
    cml2_link.router_to_switch,
    cml2_link.wlc_to_switch,
    cml2_link.ext_to_mgmt_hub,
    cml2_link.router_to_mgmt_hub,
    cml2_link.switch_to_mgmt_hub,
    cml2_link.wlc_to_mgmt_hub,
  ]
}
