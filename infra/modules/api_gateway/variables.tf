variable "project" {
  type = string
}

variable "env" {
  type = string
}

variable "name_prefix" {
  type = string
}

variable "vpc_id" {
  type = string
}

variable "vpc_cidr" {
  type = string
}

variable "private_subnet_ids" {
  description = "Subredes privadas para el NLB y las interfaces del VPC Link"
  type        = list(string)
}

variable "ingress_port" {
  description = "Puerto del Ingress del clúster"
  type        = number
  default     = 80
}

variable "ingress_target_ip" {
  description = "IP del Ingress del clúster. Vacío = aún no se registra destino (se llena en el Bloque D)."
  type        = string
  default     = ""
}

variable "cors_allow_origins" {
  description = "Orígenes del frontend permitidos"
  type        = list(string)
}

variable "throttle_rate_limit" {
  description = "Peticiones por segundo sostenidas"
  type        = number
  default     = 50
}

variable "throttle_burst_limit" {
  description = "Pico máximo de peticiones simultáneas"
  type        = number
  default     = 100
}

variable "log_retention_days" {
  type = number
}
