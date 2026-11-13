provider "aws" {
  region = var.region

  # En Floci se saltan las validaciones contra AWS real; en AWS real quedan activas.
  skip_credentials_validation = var.use_floci
  skip_metadata_api_check     = var.use_floci
  skip_requesting_account_id  = var.use_floci
  s3_use_path_style           = var.use_floci

  # Solo con Floci se redirigen los servicios al emulador.
  dynamic "endpoints" {
    for_each = var.use_floci ? [var.floci_endpoint] : []
    content {
      s3       = endpoints.value
      dynamodb = endpoints.value
      sts      = endpoints.value
      iam      = endpoints.value
    }
  }

  default_tags {
    tags = {
      Project   = var.project
      ManagedBy = "terraform"
      Component = "bootstrap"
    }
  }
}
