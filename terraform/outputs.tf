output "lab_id" {
  description = "CML Lab ID"
  value       = cml2_lab.network_lab.id
}

output "lab_title" {
  description = "CML Lab title"
  value       = cml2_lab.network_lab.title
}

output "nodes" {
  description = "Map of node labels to their details from the lifecycle resource"
  value       = cml2_lifecycle.network_lab.nodes
}
