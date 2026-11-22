output "s3_endpoint_id" {
  value = aws_vpc_endpoint.s3.id
}

output "dynamodb_endpoint_id" {
  value = aws_vpc_endpoint.dynamodb.id
}

output "interface_endpoint_ids" {
  description = "Mapa servicio => id del endpoint"
  value       = { for k, ep in aws_vpc_endpoint.interface : k => ep.id }
}

output "execute_api_endpoint_id" {
  description = "Lo usará API Gateway privado (siguiente módulo)"
  value       = aws_vpc_endpoint.interface["execute-api"].id
}

output "endpoints_security_group_id" {
  value = aws_security_group.endpoints.id
}
