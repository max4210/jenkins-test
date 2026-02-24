variable "cml_url" {
  description = "CML server URL"
  type        = string
  default     = "https://192.168.137.125"
}

variable "cml_username" {
  description = "CML username"
  type        = string
  sensitive   = true
}

variable "cml_password" {
  description = "CML password"
  type        = string
  sensitive   = true
}

variable "cml_skip_verify" {
  description = "Skip TLS certificate verification (for self-signed certs in lab environments)"
  type        = bool
  default     = true
}

variable "lab_title" {
  description = "Name of the CML lab to create"
  type        = string
  default     = "Jenkins-Terraform-Lab"
}

variable "wlc_node_definition" {
  description = "CML node definition for WLC (C9800-CL if licensed, else iosv)"
  type        = string
  default     = "iosv"
}

variable "device_username" {
  description = "Username for device login (router, switch, WLC)"
  type        = string
  sensitive   = true
}

variable "device_password" {
  description = "Password for device login and enable"
  type        = string
  sensitive   = true
}
