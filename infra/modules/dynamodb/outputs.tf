output "table_names" {
  description = "Mapa servicio => nombre de la tabla"
  value       = { for k, t in aws_dynamodb_table.this : k => t.name }
}

output "table_arns" {
  description = "Mapa servicio => ARN (para políticas IAM de cada servicio)"
  value       = { for k, t in aws_dynamodb_table.this : k => t.arn }
}
