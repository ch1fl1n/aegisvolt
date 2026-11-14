variable "name_prefix" {
  description = "Prefijo de nombres; el clúster se llama igual (aegisvolt-dev)"
  type        = string
}

variable "kubernetes_version" {
  type    = string
  default = "1.33"
}

variable "vpc_id" {
  type = string
}

variable "vpc_cidr" {
  description = "Solo este rango puede hablar con el API del clúster"
  type        = string
}

variable "private_subnet_ids" {
  description = "El clúster y los nodos viven SOLO en subredes privadas"
  type        = list(string)
}

variable "endpoint_public_access" {
  description = "Exponer el API de Kubernetes a internet (false = buena práctica)"
  type        = bool
  default     = false
}

variable "create_node_group" {
  description = "Crear el grupo de nodos administrado"
  type        = bool
  default     = true
}

variable "node_instance_types" {
  type    = list(string)
  default = ["t3.medium"]
}

variable "node_scaling" {
  type = object({
    min     = number
    desired = number
    max     = number
  })
  default = { min = 1, desired = 2, max = 3 }
}
