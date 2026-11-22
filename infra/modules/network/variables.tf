variable "name_prefix" {
  description = "Prefijo de nombres, p. ej. aegisvolt-dev"
  type        = string
}

variable "vpc_cidr" {
  description = "Rango de la VPC, p. ej. 10.10.0.0/16"
  type        = string

  validation {
    condition     = can(cidrhost(var.vpc_cidr, 0))
    error_message = "vpc_cidr debe ser un CIDR válido."
  }
}

variable "azs" {
  description = "Zonas de disponibilidad (mínimo 2 para alta disponibilidad)"
  type        = list(string)

  validation {
    condition     = length(var.azs) >= 2
    error_message = "Se requieren al menos 2 zonas de disponibilidad."
  }
}

variable "enable_nat_gateway" {
  description = "Salida a internet para subredes privadas. false: el tráfico a AWS va por VPC Endpoints."
  type        = bool
  default     = false
}
