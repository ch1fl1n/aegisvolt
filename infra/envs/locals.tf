locals {
  allowed_envs = ["dev", "test", "prod"]

  # El ambiente SALE del workspace: nunca se escribe a mano.
  env         = terraform.workspace
  name_prefix = "${var.project}-${local.env}" # p. ej. aegisvolt-test

  # Diferencias por ambiente en un solo lugar.
  env_config = {
    dev  = { vpc_cidr = "10.10.0.0/16", log_retention_days = 7, deletion_protection = false }
    test = { vpc_cidr = "10.20.0.0/16", log_retention_days = 14, deletion_protection = false }
    prod = { vpc_cidr = "10.30.0.0/16", log_retention_days = 30, deletion_protection = true }
  }

  # lookup con valor por defecto para que "default" llegue a la guardia y no rompa antes.
  cfg = lookup(local.env_config, local.env, local.env_config["dev"])
}
