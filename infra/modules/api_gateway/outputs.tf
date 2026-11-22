output "api_id" {
  value = aws_apigatewayv2_api.this.id
}

output "api_endpoint" {
  description = "URL pública de la API (en AWS real)"
  value       = aws_apigatewayv2_api.this.api_endpoint
}

output "vpc_link_id" {
  value = aws_apigatewayv2_vpc_link.this.id
}

output "nlb_arn" {
  value = aws_lb.internal.arn
}

output "nlb_dns_name" {
  value = aws_lb.internal.dns_name
}

output "target_group_arn" {
  value = aws_lb_target_group.ingress.arn
}
