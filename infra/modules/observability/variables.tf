variable "project" {
  type = string
}

variable "env" {
  type = string
}

variable "services" {
  description = "Servicios que escriben logs (un log group por cada uno)"
  type        = list(string)
}

variable "orchestrator_service" {
  description = "Servicio que orquesta la SAGA (escribe los eventos saga_*)"
  type        = string
}

variable "retention_days" {
  description = "Días que se conservan los logs"
  type        = number
}
