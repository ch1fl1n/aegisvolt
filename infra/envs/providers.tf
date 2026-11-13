provider "aws" {
  region = var.region

  skip_credentials_validation = var.use_floci
  skip_metadata_api_check     = var.use_floci
  skip_requesting_account_id  = var.use_floci
  s3_use_path_style           = var.use_floci

  dynamic "endpoints" {
    for_each = var.use_floci ? [var.floci_endpoint] : []
    content {
      s3           = endpoints.value
      dynamodb     = endpoints.value
      sts          = endpoints.value
      iam          = endpoints.value
      ec2          = endpoints.value
      elbv2        = endpoints.value
      eks          = endpoints.value
      apigateway   = endpoints.value
      apigatewayv2 = endpoints.value
      logs         = endpoints.value
      cloudwatch   = endpoints.value
    }
  }

  default_tags {
    tags = {
      Project     = var.project
      Environment = local.env
      ManagedBy   = "terraform"
    }
  }
}
