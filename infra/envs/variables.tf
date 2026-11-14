variable "project" {
  description = "Prefijo de todos los recursos"
  type        = string
  default     = "aegisvolt"
}

variable "region" {
  description = "Región de AWS"
  type        = string
  default     = "us-east-1"
}

variable "use_floci" {
  description = "true = emulador local Floci; false = AWS real"
  type        = bool
  default     = false
}

variable "floci_endpoint" {
  description = "URL del emulador cuando use_floci = true"
  type        = string
  default     = "http://localhost:4566"
}

variable "azs" {
  description = "Zonas de disponibilidad"
  type        = list(string)
  default     = ["us-east-1a", "us-east-1b"]
}

variable "vpce_private_dns_enabled" {
  description = "Private DNS en los endpoints Interface (en AWS real siempre true)"
  type        = bool
  default     = true
}

variable "eks_create_node_group" {
  description = "Crear nodos administrados de EKS (en Floci los pods corren en minikube)"
  type        = bool
  default     = true
}

variable "ingress_target_ip" {
  description = "IP del Ingress del clúster (minikube en local). Vacío hasta el Bloque D."
  type        = string
  default     = ""
}

variable "cors_allow_origins" {
  description = "Orígenes del frontend autorizados a llamar a la API"
  type        = list(string)
  default     = ["http://localhost:5173"]
}
