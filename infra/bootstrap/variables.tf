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

variable "state_bucket_name" {
  description = "Nombre del bucket del estado. En AWS real debe ser único en el mundo (agrega un sufijo)."
  type        = string
  default     = "aegisvolt-tfstate"

  validation {
    condition     = can(regex("^[a-z0-9][a-z0-9-]{1,61}[a-z0-9]$", var.state_bucket_name))
    error_message = "Solo minúsculas, números y guiones; entre 3 y 63 caracteres."
  }
}

variable "noncurrent_version_days" {
  description = "Días que se conservan las versiones antiguas del tfstate"
  type        = number
  default     = 90
}
