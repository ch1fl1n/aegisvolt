terraform {
  required_version = ">= 1.10, < 2.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.0"
    }
  }

  # Configuración PARCIAL: lo común va aquí; lo que cambia entre Floci y AWS real
  # (endpoints, flags) se pasa en "terraform init -backend-config=<archivo>.hcl".
  backend "s3" {
    key                  = "terraform.tfstate"
    workspace_key_prefix = "env:" # => env:/dev/..., env:/test/..., env:/prod/...
    encrypt              = true
    use_lockfile         = true # bloqueo nativo en S3 (Terraform >= 1.10)
  }
}
