# ---------------------------------------------------------------
# Endpoints de tipo GATEWAY: agregan rutas a la tabla de ruta privada
# ---------------------------------------------------------------
resource "aws_vpc_endpoint" "s3" {
  vpc_id            = var.vpc_id
  service_name      = "com.amazonaws.${var.region}.s3"
  vpc_endpoint_type = "Gateway"
  route_table_ids   = var.private_route_table_ids

  tags = { Name = "${var.name_prefix}-vpce-s3" }
}

resource "aws_vpc_endpoint" "dynamodb" {
  vpc_id            = var.vpc_id
  service_name      = "com.amazonaws.${var.region}.dynamodb"
  vpc_endpoint_type = "Gateway"
  route_table_ids   = var.private_route_table_ids

  # Mínimo privilegio: desde la red de este ambiente solo se tocan SUS tablas.
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Sid       = "SoloTablasDeEsteAmbiente"
      Effect    = "Allow"
      Principal = "*"
      Action    = "dynamodb:*"
      Resource = [
        "arn:aws:dynamodb:${var.region}:*:table/${var.project}-*-${var.env}",
        "arn:aws:dynamodb:${var.region}:*:table/${var.project}-*-${var.env}/*",
      ]
    }]
  })

  tags = { Name = "${var.name_prefix}-vpce-dynamodb" }
}

# ---------------------------------------------------------------
# Security group de los endpoints Interface: HTTPS solo desde la VPC
# ---------------------------------------------------------------
resource "aws_security_group" "endpoints" {
  name        = "${var.name_prefix}-vpce-sg"
  description = "HTTPS hacia los VPC endpoints solo desde la VPC"
  vpc_id      = var.vpc_id

  # Sin bloques egress: Terraform elimina la regla "todo permitido" que AWS crea por defecto.
  tags = { Name = "${var.name_prefix}-vpce-sg" }
}

resource "aws_vpc_security_group_ingress_rule" "https_from_vpc" {
  security_group_id = aws_security_group.endpoints.id
  description       = "HTTPS desde dentro de la VPC"
  cidr_ipv4         = var.vpc_cidr
  ip_protocol       = "tcp"
  from_port         = 443
  to_port           = 443
}

# ---------------------------------------------------------------
# Endpoints de tipo INTERFACE: una interfaz de red con IP privada por subred
# ---------------------------------------------------------------
resource "aws_vpc_endpoint" "interface" {
  for_each = toset(var.interface_services)

  vpc_id              = var.vpc_id
  service_name        = "com.amazonaws.${var.region}.${each.key}"
  vpc_endpoint_type   = "Interface"
  subnet_ids          = var.private_subnet_ids
  security_group_ids  = [aws_security_group.endpoints.id]
  private_dns_enabled = var.private_dns_enabled

  tags = { Name = "${var.name_prefix}-vpce-${each.key}" }
}
