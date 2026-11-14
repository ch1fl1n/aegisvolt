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
