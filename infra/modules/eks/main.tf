# ---------------------------------------------------------------
# Llave KMS para cifrar los Secrets de Kubernetes
# ---------------------------------------------------------------
resource "aws_kms_key" "eks" {
  description             = "Cifrado de secrets de ${var.name_prefix}"
  enable_key_rotation     = true
  deletion_window_in_days = 7
}

resource "aws_kms_alias" "eks" {
  name          = "alias/${var.name_prefix}-eks"
  target_key_id = aws_kms_key.eks.key_id
}

# ---------------------------------------------------------------
# Rol IAM que asume el plano de control de EKS
# ---------------------------------------------------------------
resource "aws_iam_role" "cluster" {
  name = "${var.name_prefix}-eks-cluster-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "eks.amazonaws.com" }
      Action    = ["sts:AssumeRole", "sts:TagSession"]
    }]
  })
}

resource "aws_iam_role_policy_attachment" "cluster" {
  role       = aws_iam_role.cluster.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonEKSClusterPolicy"
}

# ---------------------------------------------------------------
# Security group del API del clúster: HTTPS solo desde la VPC
# ---------------------------------------------------------------
resource "aws_security_group" "cluster" {
  name        = "${var.name_prefix}-eks-cluster-sg"
  description = "API de Kubernetes solo desde la VPC"
  vpc_id      = var.vpc_id
  tags        = { Name = "${var.name_prefix}-eks-cluster-sg" }
}

resource "aws_vpc_security_group_ingress_rule" "cluster_api" {
  security_group_id = aws_security_group.cluster.id
  description       = "kubectl / nodos hacia el API server"
  cidr_ipv4         = var.vpc_cidr
  ip_protocol       = "tcp"
  from_port         = 443
  to_port           = 443
}

resource "aws_vpc_security_group_egress_rule" "cluster_to_vpc" {
  security_group_id = aws_security_group.cluster.id
  description       = "Plano de control hacia los nodos (solo dentro de la VPC)"
  cidr_ipv4         = var.vpc_cidr
  ip_protocol       = "-1"
}

# ---------------------------------------------------------------
# Clúster EKS
# ---------------------------------------------------------------
resource "aws_eks_cluster" "this" {
  name     = var.name_prefix # aegisvolt-dev | aegisvolt-test | aegisvolt-prod
  version  = var.kubernetes_version
  role_arn = aws_iam_role.cluster.arn

  vpc_config {
    subnet_ids              = var.private_subnet_ids
    security_group_ids      = [aws_security_group.cluster.id]
    endpoint_private_access = true
    endpoint_public_access  = var.endpoint_public_access
  }

  access_config {
    authentication_mode                         = "API"
    bootstrap_cluster_creator_admin_permissions = true
  }

  encryption_config {
    resources = ["secrets"]
    provider {
      key_arn = aws_kms_key.eks.arn
    }
  }

  enabled_cluster_log_types = ["api", "audit", "authenticator"]

  depends_on = [aws_iam_role_policy_attachment.cluster]
}

# ---------------------------------------------------------------
# Nodos (grupo administrado) — opcional
# ---------------------------------------------------------------
resource "aws_iam_role" "nodes" {
  count = var.create_node_group ? 1 : 0
  name  = "${var.name_prefix}-eks-node-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "ec2.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })
}

resource "aws_iam_role_policy_attachment" "nodes" {
  for_each = var.create_node_group ? toset([
    "arn:aws:iam::aws:policy/AmazonEKSWorkerNodePolicy",
    "arn:aws:iam::aws:policy/AmazonEKS_CNI_Policy",
    "arn:aws:iam::aws:policy/AmazonEC2ContainerRegistryReadOnly",
  ]) : toset([])

  role       = aws_iam_role.nodes[0].name
  policy_arn = each.value
}

resource "aws_eks_node_group" "this" {
  count = var.create_node_group ? 1 : 0

  cluster_name    = aws_eks_cluster.this.name
  node_group_name = "${var.name_prefix}-nodes"
  node_role_arn   = aws_iam_role.nodes[0].arn
  subnet_ids      = var.private_subnet_ids
  instance_types  = var.node_instance_types
  capacity_type   = "ON_DEMAND"

  scaling_config {
    min_size     = var.node_scaling.min
    desired_size = var.node_scaling.desired
    max_size     = var.node_scaling.max
  }

  update_config {
    max_unavailable = 1 # actualiza los nodos de uno en uno
  }

  depends_on = [aws_iam_role_policy_attachment.nodes]
}
