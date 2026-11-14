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

# ---------------------------------------------------------------
# DynamoDB: una tabla por servicio y por ambiente (Database-per-Service)
# ---------------------------------------------------------------
module "dynamodb" {
  source = "../modules/dynamodb"

  project             = var.project
  env                 = local.env
  deletion_protection = local.cfg.deletion_protection

  tables = {
    reservations = {
      hash_key   = "station_id"
      range_key  = "connector_id"
      attributes = { station_id = "S", connector_id = "S", saga_id = "S" }
      gsis       = [{ name = "by-saga", hash_key = "saga_id" }]
    }
    billing = {
      hash_key   = "account_id"
      range_key  = "sk"
      attributes = { account_id = "S", sk = "S", saga_id = "S" }
      gsis       = [{ name = "by-saga", hash_key = "saga_id" }]
    }
    dispatch = {
      hash_key      = "saga_id"
      range_key     = "sk"
      attributes    = { saga_id = "S", sk = "S" }
      ttl_attribute = "expires_at"
    }
    sagas = {
      hash_key   = "saga_id"
      attributes = { saga_id = "S", status = "S", updated_at = "S" }
      gsis       = [{ name = "by-status", hash_key = "status", range_key = "updated_at" }]
    }
    flags = {
      hash_key   = "flag_name"
      attributes = { flag_name = "S" }
    }
  }
}
