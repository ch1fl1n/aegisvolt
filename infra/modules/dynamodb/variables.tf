variable "project" {
  type = string
}

variable "env" {
  description = "dev, test o prod (va al final del nombre de cada tabla)"
  type        = string
}

variable "tables" {
  description = "Mapa servicio => definición de su tabla"
  type = map(object({
    hash_key   = string
    range_key  = optional(string)
    attributes = map(string) # SOLO atributos usados como llave (en tabla o índices): nombre => "S" | "N"
    gsis = optional(list(object({
      name      = string
      hash_key  = string
      range_key = optional(string)
    })), [])
    ttl_attribute = optional(string)
  }))
}

variable "deletion_protection" {
  description = "Impide borrar las tablas (true en prod)"
  type        = bool
  default     = false
}

variable "point_in_time_recovery" {
  description = "Backups continuos para restaurar a cualquier segundo de los últimos 35 días"
  type        = bool
  default     = true
}
