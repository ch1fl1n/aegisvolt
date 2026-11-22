output "log_group_names" {
  description = "Mapa servicio => log group"
  value       = { for k, g in aws_cloudwatch_log_group.service : k => g.name }
}

output "metrics_namespace" {
  value = local.namespace
}
