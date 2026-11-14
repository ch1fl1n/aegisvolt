# ---------------------------------------------------------------
# Guardia: solo se permite planear/aplicar en dev, test o prod.
# Falla en el PLAN, antes de tocar cualquier recurso.
# ---------------------------------------------------------------
resource "terraform_data" "workspace_guard" {
  input = local.env

  lifecycle {
    precondition {
      condition     = contains(local.allowed_envs, terraform.workspace)
      error_message = "Workspace '${terraform.workspace}' no permitido. Usa: terraform workspace select dev|test|prod"
    }
  }
}

# ---------------------------------------------------------------
# Red del ambiente
# ---------------------------------------------------------------
module "network" {
  source = "../modules/network"

  name_prefix        = local.name_prefix
  vpc_cidr           = local.cfg.vpc_cidr
  azs                = var.azs
  enable_nat_gateway = false
}

# ---------------------------------------------------------------
# VPC Endpoints: acceso privado a S3, DynamoDB, API Gateway y CloudWatch
# ---------------------------------------------------------------
module "vpc_endpoints" {
  source = "../modules/vpc_endpoints"

  name_prefix             = local.name_prefix
  project                 = var.project
  env                     = local.env
  region                  = var.region
  vpc_id                  = module.network.vpc_id
  vpc_cidr                = module.network.vpc_cidr
  private_subnet_ids      = module.network.private_subnet_ids
  private_route_table_ids = [module.network.private_route_table_id]
  private_dns_enabled     = var.vpce_private_dns_enabled
}
