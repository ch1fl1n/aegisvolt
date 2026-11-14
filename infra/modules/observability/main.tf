locals {
  namespace = "AegisVolt/${var.env}" # métricas separadas por ambiente
}

# ---------------------------------------------------------------
# Un log group por servicio y ambiente: /aegisvolt/<env>/<servicio>
# ---------------------------------------------------------------
resource "aws_cloudwatch_log_group" "service" {
  for_each = toset(var.services)

  name              = "/${var.project}/${var.env}/${each.key}"
  retention_in_days = var.retention_days

  tags = { Service = each.key }
}

# ---------------------------------------------------------------
# Métricas a partir de los logs JSON (las usa el canary)
# ---------------------------------------------------------------
resource "aws_cloudwatch_log_metric_filter" "requests" {
  for_each = aws_cloudwatch_log_group.service

  name           = "${each.key}-requests"
  log_group_name = each.value.name
  pattern        = "{ $.event = \"http_request\" }"

  metric_transformation {
    name      = "RequestCount"
    namespace = local.namespace
    value     = "1"
    unit      = "Count"
    dimensions = {
      Service = "$.service"
      Version = "$.version"
    }
  }
}

resource "aws_cloudwatch_log_metric_filter" "errors" {
  for_each = aws_cloudwatch_log_group.service

  name           = "${each.key}-errors"
  log_group_name = each.value.name
  pattern        = "{ $.event = \"http_request\" && $.status >= 500 }"

  metric_transformation {
    name      = "ErrorCount"
    namespace = local.namespace
    value     = "1"
    unit      = "Count"
    dimensions = {
      Service = "$.service"
      Version = "$.version"
    }
  }
}

# Cuántas SAGA terminaron en compensación (lo muestra Prefect y la demo).
resource "aws_cloudwatch_log_metric_filter" "saga_compensated" {
  name           = "saga-compensated"
  log_group_name = aws_cloudwatch_log_group.service[var.orchestrator_service].name
  pattern        = "{ $.event = \"saga_compensated\" }"

  metric_transformation {
    name      = "SagaCompensated"
    namespace = local.namespace
    value     = "1"
    unit      = "Count"
  }
}
