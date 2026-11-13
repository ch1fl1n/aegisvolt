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

# Los módulos (network, vpc_endpoints, dynamodb, ...) se agregan en los siguientes pasos.
