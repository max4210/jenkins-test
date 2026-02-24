output "lab_id" {
  description = "CML Lab ID"
  value       = cml2_lab.network_lab.id
}

output "lab_title" {
  description = "CML Lab title"
  value       = cml2_lab.network_lab.title
}

output "nodes" {
  description = "All node details from the lifecycle resource"
  value       = cml2_lifecycle.network_lab.nodes
}

output "devices" {
  description = "Device connection info for pyATS testbed generation"
  value = {
    router1 = {
      id             = cml2_node.router1.id
      label          = cml2_node.router1.label
      nodedefinition = cml2_node.router1.nodedefinition
      state          = cml2_node.router1.state
      interfaces     = try(cml2_lifecycle.network_lab.nodes[cml2_node.router1.id].interfaces, [])
    }
    router2 = {
      id             = cml2_node.router2.id
      label          = cml2_node.router2.label
      nodedefinition = cml2_node.router2.nodedefinition
      state          = cml2_node.router2.state
      interfaces     = try(cml2_lifecycle.network_lab.nodes[cml2_node.router2.id].interfaces, [])
    }
    switch1 = {
      id             = cml2_node.switch1.id
      label          = cml2_node.switch1.label
      nodedefinition = cml2_node.switch1.nodedefinition
      state          = cml2_node.switch1.state
      interfaces     = try(cml2_lifecycle.network_lab.nodes[cml2_node.switch1.id].interfaces, [])
    }
  }
}
