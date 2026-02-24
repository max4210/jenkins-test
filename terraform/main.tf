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
  description = "Automated lab managed by Jenkins + Terraform"
}

# --- Nodes ---

resource "cml2_node" "router1" {
  lab_id         = cml2_lab.network_lab.id
  label          = "router1"
  nodedefinition = "iosv"
  x              = -200
  y              = 0
  configuration  = <<-EOT
    hostname router1
    no ip domain-lookup
    interface GigabitEthernet0/0
     description to-switch1
     ip address 10.0.1.1 255.255.255.0
     no shutdown
    interface GigabitEthernet0/1
     description to-router2
     ip address 10.0.12.1 255.255.255.0
     no shutdown
    interface Loopback0
     ip address 1.1.1.1 255.255.255.255
    ip route 2.2.2.2 255.255.255.255 10.0.12.2
    ip route 10.0.2.0 255.255.255.0 10.0.12.2
    line con 0
     exec-timeout 0 0
    line vty 0 4
     login local
     transport input telnet ssh
    username admin privilege 15 secret admin
    enable secret admin
    ip domain-name lab.local
    crypto key generate rsa modulus 2048
    ip ssh version 2
  EOT
}

resource "cml2_node" "router2" {
  lab_id         = cml2_lab.network_lab.id
  label          = "router2"
  nodedefinition = "iosv"
  x              = 200
  y              = 0
  configuration  = <<-EOT
    hostname router2
    no ip domain-lookup
    interface GigabitEthernet0/0
     description to-switch1
     ip address 10.0.2.1 255.255.255.0
     no shutdown
    interface GigabitEthernet0/1
     description to-router1
     ip address 10.0.12.2 255.255.255.0
     no shutdown
    interface Loopback0
     ip address 2.2.2.2 255.255.255.255
    ip route 1.1.1.1 255.255.255.255 10.0.12.1
    ip route 10.0.1.0 255.255.255.0 10.0.12.1
    line con 0
     exec-timeout 0 0
    line vty 0 4
     login local
     transport input telnet ssh
    username admin privilege 15 secret admin
    enable secret admin
    ip domain-name lab.local
    crypto key generate rsa modulus 2048
    ip ssh version 2
  EOT
}

resource "cml2_node" "switch1" {
  lab_id         = cml2_lab.network_lab.id
  label          = "switch1"
  nodedefinition = "iosvl2"
  x              = 0
  y              = 150
  configuration  = <<-EOT
    hostname switch1
    no ip domain-lookup
    vlan 10
     name ROUTER1
    vlan 20
     name ROUTER2
    interface GigabitEthernet0/0
     description to-router1
     switchport mode access
     switchport access vlan 10
     no shutdown
    interface GigabitEthernet0/1
     description to-router2
     switchport mode access
     switchport access vlan 20
     no shutdown
    interface Vlan10
     ip address 10.0.1.2 255.255.255.0
     no shutdown
    interface Vlan20
     ip address 10.0.2.2 255.255.255.0
     no shutdown
    line con 0
     exec-timeout 0 0
    line vty 0 4
     login local
     transport input telnet ssh
    username admin privilege 15 secret admin
    enable secret admin
    ip domain-name lab.local
    crypto key generate rsa modulus 2048
    ip ssh version 2
  EOT
}

# --- Links ---

resource "cml2_link" "router1_to_switch1" {
  lab_id = cml2_lab.network_lab.id
  node_a = cml2_node.router1.id
  slot_a = 0
  node_b = cml2_node.switch1.id
  slot_b = 0
}

resource "cml2_link" "router2_to_switch1" {
  lab_id = cml2_lab.network_lab.id
  node_a = cml2_node.router2.id
  slot_a = 0
  node_b = cml2_node.switch1.id
  slot_b = 1
}

resource "cml2_link" "router1_to_router2" {
  lab_id = cml2_lab.network_lab.id
  node_a = cml2_node.router1.id
  slot_a = 1
  node_b = cml2_node.router2.id
  slot_b = 1
}

# --- Lifecycle ---

resource "cml2_lifecycle" "network_lab" {
  lab_id = cml2_lab.network_lab.id
  state  = "STARTED"

  depends_on = [
    cml2_node.router1,
    cml2_node.router2,
    cml2_node.switch1,
    cml2_link.router1_to_switch1,
    cml2_link.router2_to_switch1,
    cml2_link.router1_to_router2,
  ]
}
