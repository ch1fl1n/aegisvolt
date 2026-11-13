output "environment" {
  description = "Ambiente (workspace) aplicado"
  value       = local.env
}

output "name_prefix" {
  description = "Prefijo de nombres de este ambiente"
  value       = local.name_prefix
}

output "vpc_cidr" {
  description = "Rango de red reservado para este ambiente"
  value       = local.cfg.vpc_cidr
}
