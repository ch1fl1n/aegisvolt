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

output "vpc_id" {
  value = module.network.vpc_id
}

output "private_subnet_ids" {
  value = module.network.private_subnet_ids
}

output "vpc_endpoint_ids" {
  value = merge(
    {
      s3       = module.vpc_endpoints.s3_endpoint_id
      dynamodb = module.vpc_endpoints.dynamodb_endpoint_id
    },
    module.vpc_endpoints.interface_endpoint_ids,
  )
}

output "dynamodb_tables" {
  value = module.dynamodb.table_names
}

output "log_groups" {
  value = module.observability.log_group_names
}

output "metrics_namespace" {
  value = module.observability.metrics_namespace
}

output "eks_cluster_name" {
  value = module.eks.cluster_name
}

output "api_id" {
  value = module.api_gateway.api_id
}

output "api_endpoint" {
  value = module.api_gateway.api_endpoint
}

output "nlb_dns_name" {
  value = module.api_gateway.nlb_dns_name
}
