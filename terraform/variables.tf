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
