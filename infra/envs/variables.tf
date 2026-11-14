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
