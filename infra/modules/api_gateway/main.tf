# ---------------------------------------------------------------
# Access logs de API Gateway (JSON, en el log group del ambiente)
# ---------------------------------------------------------------
resource "aws_cloudwatch_log_group" "access" {
  name              = "/${var.project}/${var.env}/api-gateway"
  retention_in_days = var.log_retention_days
}

# ---------------------------------------------------------------
# Security groups: VPC Link -> NLB, todo dentro de la VPC
# ---------------------------------------------------------------
resource "aws_security_group" "vpc_link" {
  name        = "${var.name_prefix}-apigw-vpclink-sg"
  description = "Interfaces del VPC Link: solo salen hacia el NLB"
  vpc_id      = var.vpc_id
  tags        = { Name = "${var.name_prefix}-apigw-vpclink-sg" }
}

resource "aws_vpc_security_group_egress_rule" "vpc_link_to_nlb" {
  security_group_id = aws_security_group.vpc_link.id
  cidr_ipv4         = var.vpc_cidr
  ip_protocol       = "tcp"
  from_port         = var.ingress_port
  to_port           = var.ingress_port
}

resource "aws_security_group" "nlb" {
  name        = "${var.name_prefix}-nlb-sg"
  description = "NLB interno: solo tráfico desde la VPC"
  vpc_id      = var.vpc_id
  tags        = { Name = "${var.name_prefix}-nlb-sg" }
}

resource "aws_vpc_security_group_ingress_rule" "nlb_from_vpc" {
  security_group_id = aws_security_group.nlb.id
  cidr_ipv4         = var.vpc_cidr
  ip_protocol       = "tcp"
  from_port         = var.ingress_port
  to_port           = var.ingress_port
}

resource "aws_vpc_security_group_egress_rule" "nlb_to_cluster" {
  security_group_id = aws_security_group.nlb.id
  cidr_ipv4         = var.vpc_cidr
  ip_protocol       = "tcp"
  from_port         = var.ingress_port
  to_port           = var.ingress_port
}

# ---------------------------------------------------------------
# NLB interno (sin IP pública) en subredes privadas
# ---------------------------------------------------------------
resource "aws_lb" "internal" {
  name               = "${var.name_prefix}-nlb"
  internal           = true
  load_balancer_type = "network"
  subnets            = var.private_subnet_ids
  security_groups    = [aws_security_group.nlb.id]
}

resource "aws_lb_target_group" "ingress" {
  name        = "${var.name_prefix}-ingress-tg"
  port        = var.ingress_port
  protocol    = "TCP"
  target_type = "ip"
  vpc_id      = var.vpc_id

  # HTTP y no TCP: confirma que el ingress-nginx RESPONDE (no solo que el puerto abre).
  # Además Floci devuelve matcher en checks TCP y el provider rechaza esa combinación.
  health_check {
    protocol            = "HTTP"
    port                = "traffic-port"
    path                = "/healthz" # respuesta 200 del servidor por defecto de ingress-nginx
    matcher             = "200"
    healthy_threshold   = 2
    unhealthy_threshold = 2
    interval            = 10
  }
}

resource "aws_lb_listener" "ingress" {
  load_balancer_arn = aws_lb.internal.arn
  port              = var.ingress_port
  protocol          = "TCP"

  default_action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.ingress.arn
  }
}

# Destino del NLB: el Ingress del clúster (solo cuando ya conocemos su IP).
resource "aws_lb_target_group_attachment" "ingress" {
  count            = var.ingress_target_ip == "" ? 0 : 1
  target_group_arn = aws_lb_target_group.ingress.arn
  target_id        = var.ingress_target_ip
  port             = var.ingress_port
}

# ---------------------------------------------------------------
# API Gateway HTTP API + VPC Link
# ---------------------------------------------------------------
resource "aws_apigatewayv2_vpc_link" "this" {
  name               = "${var.name_prefix}-vpclink"
  subnet_ids         = var.private_subnet_ids
  security_group_ids = [aws_security_group.vpc_link.id]
}

resource "aws_apigatewayv2_api" "this" {
  name          = "${var.name_prefix}-api"
  protocol_type = "HTTP"
  description   = "Entrada GraphQL de AegisVolt (${var.env})"

  cors_configuration {
    allow_origins = var.cors_allow_origins
    allow_methods = ["GET", "POST", "OPTIONS"]
    allow_headers = ["content-type", "authorization", "x-correlation-id"]
    max_age       = 300
  }
}

resource "aws_apigatewayv2_integration" "cluster" {
  api_id             = aws_apigatewayv2_api.this.id
  integration_type   = "HTTP_PROXY"
  integration_method = "ANY"
  connection_type    = "VPC_LINK"
  connection_id      = aws_apigatewayv2_vpc_link.this.id
  integration_uri    = aws_lb_listener.ingress.arn # el VPC Link entrega al listener del NLB

  payload_format_version = "1.0"
  timeout_milliseconds   = 29000
}

resource "aws_apigatewayv2_route" "default" {
  api_id    = aws_apigatewayv2_api.this.id
  route_key = "$default" # todo lo que llegue (p. ej. POST /graphql) va al clúster
  target    = "integrations/${aws_apigatewayv2_integration.cluster.id}"
}

resource "aws_apigatewayv2_stage" "default" {
  api_id      = aws_apigatewayv2_api.this.id
  name        = "$default"
  auto_deploy = true

  default_route_settings {
    throttling_rate_limit  = var.throttle_rate_limit
    throttling_burst_limit = var.throttle_burst_limit
  }

  access_log_settings {
    destination_arn = aws_cloudwatch_log_group.access.arn
    format = jsonencode({
      event              = "apigw_access"
      env                = var.env
      requestId          = "$context.requestId"
      ip                 = "$context.identity.sourceIp"
      method             = "$context.httpMethod"
      path               = "$context.path"
      status             = "$context.status"
      latencyMs          = "$context.responseLatency"
      integrationLatency = "$context.integrationLatency"
    })
  }
}
