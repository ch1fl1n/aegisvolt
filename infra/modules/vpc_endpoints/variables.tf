variable "name_prefix" {
  description = "Prefijo de nombres, p. ej. aegisvolt-dev"
  type        = string
}

variable "project" {
  description = "Nombre del proyecto (para la política de DynamoDB)"
  type        = string
}

variable "env" {
  description = "Ambiente: dev, test o prod"
  type        = string
}

variable "region" {
  description = "Región de AWS"
  type        = string
}

variable "vpc_id" {
  type = string
}

variable "vpc_cidr" {
  description = "Solo este rango puede usar los endpoints de tipo Interface"
  type        = string
}

variable "private_subnet_ids" {
  description = "Subredes donde se crean las interfaces de red de los endpoints"
  type        = list(string)
}

variable "private_route_table_ids" {
  description = "Tablas de ruta donde se agregan las rutas de los endpoints Gateway"
  type        = list(string)
}

variable "interface_services" {
  description = "Servicios con endpoint de tipo Interface"
  type        = list(string)
  default     = ["execute-api", "logs", "monitoring"]
}

variable "private_dns_enabled" {
  description = "Resolver el nombre público del servicio hacia la IP privada del endpoint"
  type        = bool
  default     = true
}
