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

resource "cml2_lab" "network_lab" {
  title       = var.lab_title
  description = "Automated lab managed by Jenkins + Terraform"
  topology    = file("${path.module}/topology.yaml")
}

resource "cml2_lifecycle" "network_lab" {
  lab_id = cml2_lab.network_lab.id

  # Bring all nodes to BOOTED state
  state = "STARTED"

  # Elements maps node labels to their runtime state.
  # The provider waits until all nodes reach the target state.
}
