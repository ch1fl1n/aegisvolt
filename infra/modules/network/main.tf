# ---------------------------------------------------------------
# VPC del ambiente
# ---------------------------------------------------------------
resource "aws_vpc" "this" {
  cidr_block           = var.vpc_cidr
  enable_dns_support   = true # requerido por los VPC Endpoints de tipo Interface
  enable_dns_hostnames = true # permite el "private DNS" de esos endpoints

  tags = { Name = "${var.name_prefix}-vpc" }
}

# Cierra el security group por defecto: ningún recurso queda abierto "por accidente".
resource "aws_default_security_group" "this" {
  vpc_id = aws_vpc.this.id
  tags   = { Name = "${var.name_prefix}-default-sg-cerrado" }
}

resource "aws_internet_gateway" "this" {
  vpc_id = aws_vpc.this.id
  tags   = { Name = "${var.name_prefix}-igw" }
}

# ---------------------------------------------------------------
# Subredes: /24 dentro del /16.  Públicas: .0.x y .1.x · Privadas: .10.x y .11.x
# ---------------------------------------------------------------
resource "aws_subnet" "public" {
  count = length(var.azs)

  vpc_id                  = aws_vpc.this.id
  cidr_block              = cidrsubnet(var.vpc_cidr, 8, count.index)
  availability_zone       = var.azs[count.index]
  map_public_ip_on_launch = false # nada recibe IP pública automáticamente

  tags = {
    Name                     = "${var.name_prefix}-public-${var.azs[count.index]}"
    Tier                     = "public"
    "kubernetes.io/role/elb" = "1" # aquí irían balanceadores públicos de EKS
  }
}

resource "aws_subnet" "private" {
  count = length(var.azs)

  vpc_id            = aws_vpc.this.id
  cidr_block        = cidrsubnet(var.vpc_cidr, 8, count.index + 10)
  availability_zone = var.azs[count.index]

  tags = {
    Name                              = "${var.name_prefix}-private-${var.azs[count.index]}"
    Tier                              = "private"
    "kubernetes.io/role/internal-elb" = "1" # aquí va el NLB interno (VPC Link)
  }
}

# ---------------------------------------------------------------
# Tablas de ruta
# ---------------------------------------------------------------
resource "aws_route_table" "public" {
  vpc_id = aws_vpc.this.id
  tags   = { Name = "${var.name_prefix}-rt-public" }
}

resource "aws_route" "public_internet" {
  route_table_id         = aws_route_table.public.id
  destination_cidr_block = "0.0.0.0/0"
  gateway_id             = aws_internet_gateway.this.id
}

resource "aws_route_table_association" "public" {
  count          = length(var.azs)
  subnet_id      = aws_subnet.public[count.index].id
  route_table_id = aws_route_table.public.id
}

# Privada: SIN ruta 0.0.0.0/0. Solo la ruta "local" de la VPC y, en el siguiente paso,
# las rutas a S3 y DynamoDB que agregan los VPC Endpoints de tipo Gateway.
resource "aws_route_table" "private" {
  vpc_id = aws_vpc.this.id
  tags   = { Name = "${var.name_prefix}-rt-private" }
}

resource "aws_route_table_association" "private" {
  count          = length(var.azs)
  subnet_id      = aws_subnet.private[count.index].id
  route_table_id = aws_route_table.private.id
}

# ---------------------------------------------------------------
# NAT opcional (apagado por defecto)
# ---------------------------------------------------------------
resource "aws_eip" "nat" {
  count  = var.enable_nat_gateway ? 1 : 0
  domain = "vpc"
  tags   = { Name = "${var.name_prefix}-nat-eip" }
}

resource "aws_nat_gateway" "this" {
  count         = var.enable_nat_gateway ? 1 : 0
  allocation_id = aws_eip.nat[0].id
  subnet_id     = aws_subnet.public[0].id
  tags          = { Name = "${var.name_prefix}-nat" }

  depends_on = [aws_internet_gateway.this]
}

resource "aws_route" "private_nat" {
  count                  = var.enable_nat_gateway ? 1 : 0
  route_table_id         = aws_route_table.private.id
  destination_cidr_block = "0.0.0.0/0"
  nat_gateway_id         = aws_nat_gateway.this[0].id
}
