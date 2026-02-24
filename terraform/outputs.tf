output "lab_id" {
  description = "CML Lab ID"
  value       = cml2_lab.network_lab.id
}

output "lab_title" {
  description = "CML Lab title"
  value       = cml2_lab.network_lab.title
}

output "router1_id" {
  description = "Router1 node ID"
  value       = cml2_node.router1.id
}

output "router2_id" {
  description = "Router2 node ID"
  value       = cml2_node.router2.id
}

output "switch1_id" {
  description = "Switch1 node ID"
  value       = cml2_node.switch1.id
}
