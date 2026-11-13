# Backend apuntando al emulador local. Para AWS real se crea backend-aws.hcl
# solo con bucket y region.
bucket = "aegisvolt-tfstate"
region = "us-east-1"

endpoints = {
  s3  = "http://localhost:4566"
  sts = "http://localhost:4566"
}

use_path_style              = true
skip_credentials_validation = true
skip_region_validation      = true
skip_requesting_account_id  = true
skip_metadata_api_check     = true
