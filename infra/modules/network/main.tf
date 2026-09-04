locals {
  subnet_layout = {
    for index, az in var.availability_zones : az => {
      public      = var.public_subnet_cidrs[index]
      private_app = var.private_app_subnet_cidrs[index]
      isolated_db = var.isolated_db_subnet_cidrs[index]
    }
  }
}

resource "aws_vpc" "this" {
  cidr_block           = var.vpc_cidr
  enable_dns_support   = true
  enable_dns_hostnames = true

  tags = merge(var.common_tags, {
    Name = "${var.name_prefix}-vpc"
    Tier = "network"
  })
}

resource "aws_internet_gateway" "this" {
  vpc_id = aws_vpc.this.id

  tags = merge(var.common_tags, {
    Name = "${var.name_prefix}-igw"
    Tier = "public"
  })
}

resource "aws_subnet" "public" {
  for_each = local.subnet_layout

  vpc_id                  = aws_vpc.this.id
  availability_zone       = each.key
  cidr_block              = each.value.public
  map_public_ip_on_launch = false

  tags = merge(var.common_tags, {
    Name = "${var.name_prefix}-public-${each.key}"
    Tier = "public"
  })
}

resource "aws_subnet" "private_app" {
  for_each = local.subnet_layout

  vpc_id                  = aws_vpc.this.id
  availability_zone       = each.key
  cidr_block              = each.value.private_app
  map_public_ip_on_launch = false

  tags = merge(var.common_tags, {
    Name = "${var.name_prefix}-private-app-${each.key}"
    Tier = "private-app"
  })
}

resource "aws_subnet" "isolated_db" {
  for_each = local.subnet_layout

  vpc_id                  = aws_vpc.this.id
  availability_zone       = each.key
  cidr_block              = each.value.isolated_db
  map_public_ip_on_launch = false

  tags = merge(var.common_tags, {
    Name = "${var.name_prefix}-isolated-db-${each.key}"
    Tier = "isolated-db"
  })
}

resource "aws_route_table" "public" {
  vpc_id = aws_vpc.this.id

  tags = merge(var.common_tags, {
    Name = "${var.name_prefix}-public-rt"
    Tier = "public"
  })
}

resource "aws_route" "public_internet" {
  route_table_id         = aws_route_table.public.id
  destination_cidr_block = "0.0.0.0/0"
  gateway_id             = aws_internet_gateway.this.id
}

resource "aws_route_table_association" "public" {
  for_each = aws_subnet.public

  subnet_id      = each.value.id
  route_table_id = aws_route_table.public.id
}

# The dev/MVP topology deliberately has one NAT Gateway in the first public AZ
# to reduce fixed cost. A production expansion can use one NAT Gateway and one
# private route table per AZ.
resource "aws_eip" "nat" {
  count  = var.enable_nat_gateway ? 1 : 0
  domain = "vpc"

  tags = merge(var.common_tags, {
    Name = "${var.name_prefix}-nat-eip"
    Tier = "public"
  })
}

resource "aws_nat_gateway" "this" {
  count = var.enable_nat_gateway ? 1 : 0

  allocation_id = aws_eip.nat[0].id
  subnet_id     = aws_subnet.public[var.availability_zones[0]].id

  tags = merge(var.common_tags, {
    Name = "${var.name_prefix}-nat-${var.availability_zones[0]}"
    Tier = "public"
  })

  depends_on = [aws_internet_gateway.this]
}

resource "aws_route_table" "private_app" {
  vpc_id = aws_vpc.this.id

  tags = merge(var.common_tags, {
    Name = "${var.name_prefix}-private-app-rt"
    Tier = "private-app"
  })
}

# No default route is created when NAT is disabled, so private application
# subnets remain valid and isolated rather than referring to a missing NAT.
resource "aws_route" "private_app_nat" {
  count = var.enable_nat_gateway ? 1 : 0

  route_table_id         = aws_route_table.private_app.id
  destination_cidr_block = "0.0.0.0/0"
  nat_gateway_id         = aws_nat_gateway.this[0].id
}

resource "aws_route_table_association" "private_app" {
  for_each = aws_subnet.private_app

  subnet_id      = each.value.id
  route_table_id = aws_route_table.private_app.id
}

# Intentionally has no Internet Gateway or NAT default route. Database traffic
# is limited to the VPC-local route and specific security-group rules below.
resource "aws_route_table" "isolated_db" {
  vpc_id = aws_vpc.this.id

  tags = merge(var.common_tags, {
    Name = "${var.name_prefix}-isolated-db-rt"
    Tier = "isolated-db"
  })
}

resource "aws_route_table_association" "isolated_db" {
  for_each = aws_subnet.isolated_db

  subnet_id      = each.value.id
  route_table_id = aws_route_table.isolated_db.id
}

# Security groups use standalone VPC security-group rule resources. egress = []
# removes the AWS-created implicit allow-all egress before explicit rules are
# added, including for the DB security group which intentionally has no egress.
resource "aws_security_group" "alb" {
  name        = "${var.name_prefix}-alb-sg"
  description = "Ingress boundary for the future ALB; HTTPS only from trusted CIDRs."
  vpc_id      = aws_vpc.this.id
  ingress     = []
  egress      = []

  tags = merge(var.common_tags, {
    Name = "${var.name_prefix}-alb-sg"
    Role = "alb"
  })
}

resource "aws_security_group" "ecs" {
  name        = "${var.name_prefix}-ecs-sg"
  description = "Backend API tasks; application ingress only from the ALB security group."
  vpc_id      = aws_vpc.this.id
  ingress     = []
  egress      = []

  tags = merge(var.common_tags, {
    Name = "${var.name_prefix}-ecs-sg"
    Role = "ecs"
  })
}

resource "aws_security_group" "eks" {
  name        = "${var.name_prefix}-eks-sg"
  description = "SQS-driven workers; no inbound rule is required."
  vpc_id      = aws_vpc.this.id
  ingress     = []
  egress      = []

  tags = merge(var.common_tags, {
    Name = "${var.name_prefix}-eks-sg"
    Role = "eks"
  })
}

resource "aws_security_group" "db" {
  name        = "${var.name_prefix}-db-sg"
  description = "Aurora boundary; PostgreSQL only from ECS and EKS. No egress."
  vpc_id      = aws_vpc.this.id
  ingress     = []
  egress      = []

  tags = merge(var.common_tags, {
    Name = "${var.name_prefix}-db-sg"
    Role = "db"
  })
}

resource "aws_vpc_security_group_ingress_rule" "alb_https" {
  for_each = toset(var.allowed_alb_ingress_cidrs)

  security_group_id = aws_security_group.alb.id
  cidr_ipv4         = each.value
  from_port         = 443
  ip_protocol       = "tcp"
  to_port           = 443

  tags = merge(var.common_tags, { Name = "${var.name_prefix}-alb-https-ingress" })
}

resource "aws_vpc_security_group_egress_rule" "alb_to_ecs" {
  security_group_id            = aws_security_group.alb.id
  referenced_security_group_id = aws_security_group.ecs.id
  from_port                    = var.app_port
  ip_protocol                  = "tcp"
  to_port                      = var.app_port

  tags = merge(var.common_tags, { Name = "${var.name_prefix}-alb-to-ecs" })
}

resource "aws_vpc_security_group_ingress_rule" "ecs_from_alb" {
  security_group_id            = aws_security_group.ecs.id
  referenced_security_group_id = aws_security_group.alb.id
  from_port                    = var.app_port
  ip_protocol                  = "tcp"
  to_port                      = var.app_port

  tags = merge(var.common_tags, { Name = "${var.name_prefix}-ecs-from-alb" })
}

resource "aws_vpc_security_group_egress_rule" "ecs_to_db" {
  security_group_id            = aws_security_group.ecs.id
  referenced_security_group_id = aws_security_group.db.id
  from_port                    = 5432
  ip_protocol                  = "tcp"
  to_port                      = 5432

  tags = merge(var.common_tags, { Name = "${var.name_prefix}-ecs-to-db" })
}

resource "aws_vpc_security_group_egress_rule" "eks_to_db" {
  security_group_id            = aws_security_group.eks.id
  referenced_security_group_id = aws_security_group.db.id
  from_port                    = 5432
  ip_protocol                  = "tcp"
  to_port                      = 5432

  tags = merge(var.common_tags, { Name = "${var.name_prefix}-eks-to-db" })
}

resource "aws_vpc_security_group_ingress_rule" "db_from_ecs" {
  security_group_id            = aws_security_group.db.id
  referenced_security_group_id = aws_security_group.ecs.id
  from_port                    = 5432
  ip_protocol                  = "tcp"
  to_port                      = 5432

  tags = merge(var.common_tags, { Name = "${var.name_prefix}-db-from-ecs" })
}

resource "aws_vpc_security_group_ingress_rule" "db_from_eks" {
  security_group_id            = aws_security_group.db.id
  referenced_security_group_id = aws_security_group.eks.id
  from_port                    = 5432
  ip_protocol                  = "tcp"
  to_port                      = 5432

  tags = merge(var.common_tags, { Name = "${var.name_prefix}-db-from-eks" })
}

resource "aws_vpc_security_group_egress_rule" "ecs_https_external" {
  for_each = toset(var.external_https_egress_cidrs)

  security_group_id = aws_security_group.ecs.id
  cidr_ipv4         = each.value
  from_port         = 443
  ip_protocol       = "tcp"
  to_port           = 443

  tags = merge(var.common_tags, { Name = "${var.name_prefix}-ecs-https-egress" })
}

resource "aws_vpc_security_group_egress_rule" "eks_https_external" {
  for_each = toset(var.external_https_egress_cidrs)

  security_group_id = aws_security_group.eks.id
  cidr_ipv4         = each.value
  from_port         = 443
  ip_protocol       = "tcp"
  to_port           = 443

  tags = merge(var.common_tags, { Name = "${var.name_prefix}-eks-https-egress" })
}

# VPC endpoints are an opt-in cost and security optimization. S3 is a gateway
# endpoint; the remaining services are PrivateLink interface endpoints placed
# in private application subnets.
data "aws_region" "current" {}

resource "aws_vpc_endpoint" "s3" {
  count = var.enable_vpc_endpoints ? 1 : 0

  vpc_id            = aws_vpc.this.id
  service_name      = "com.amazonaws.${data.aws_region.current.name}.s3"
  vpc_endpoint_type = "Gateway"
  route_table_ids   = [aws_route_table.private_app.id]

  tags = merge(var.common_tags, {
    Name = "${var.name_prefix}-s3-endpoint"
    Role = "vpc-endpoint"
  })
}

resource "aws_security_group" "vpc_endpoint" {
  count = var.enable_vpc_endpoints ? 1 : 0

  name        = "${var.name_prefix}-vpce-sg"
  description = "HTTPS ingress from ECS/EKS to optional interface VPC endpoints."
  vpc_id      = aws_vpc.this.id
  ingress     = []
  egress      = []

  tags = merge(var.common_tags, {
    Name = "${var.name_prefix}-vpce-sg"
    Role = "vpc-endpoint"
  })
}

resource "aws_vpc_security_group_ingress_rule" "vpc_endpoint_from_ecs" {
  count = var.enable_vpc_endpoints ? 1 : 0

  security_group_id            = aws_security_group.vpc_endpoint[0].id
  referenced_security_group_id = aws_security_group.ecs.id
  from_port                    = 443
  ip_protocol                  = "tcp"
  to_port                      = 443

  tags = merge(var.common_tags, { Name = "${var.name_prefix}-vpce-from-ecs" })
}

resource "aws_vpc_security_group_ingress_rule" "vpc_endpoint_from_eks" {
  count = var.enable_vpc_endpoints ? 1 : 0

  security_group_id            = aws_security_group.vpc_endpoint[0].id
  referenced_security_group_id = aws_security_group.eks.id
  from_port                    = 443
  ip_protocol                  = "tcp"
  to_port                      = 443

  tags = merge(var.common_tags, { Name = "${var.name_prefix}-vpce-from-eks" })
}

resource "aws_vpc_security_group_egress_rule" "ecs_to_vpc_endpoint" {
  count = var.enable_vpc_endpoints ? 1 : 0

  security_group_id            = aws_security_group.ecs.id
  referenced_security_group_id = aws_security_group.vpc_endpoint[0].id
  from_port                    = 443
  ip_protocol                  = "tcp"
  to_port                      = 443

  tags = merge(var.common_tags, { Name = "${var.name_prefix}-ecs-to-vpce" })
}

resource "aws_vpc_security_group_egress_rule" "eks_to_vpc_endpoint" {
  count = var.enable_vpc_endpoints ? 1 : 0

  security_group_id            = aws_security_group.eks.id
  referenced_security_group_id = aws_security_group.vpc_endpoint[0].id
  from_port                    = 443
  ip_protocol                  = "tcp"
  to_port                      = 443

  tags = merge(var.common_tags, { Name = "${var.name_prefix}-eks-to-vpce" })
}

resource "aws_vpc_endpoint" "interface" {
  for_each = var.enable_vpc_endpoints ? var.interface_vpc_endpoint_services : toset([])

  vpc_id              = aws_vpc.this.id
  service_name        = "com.amazonaws.${data.aws_region.current.name}.${each.value}"
  vpc_endpoint_type   = "Interface"
  private_dns_enabled = true
  subnet_ids          = values(aws_subnet.private_app)[*].id
  security_group_ids  = [aws_security_group.vpc_endpoint[0].id]

  tags = merge(var.common_tags, {
    Name = "${var.name_prefix}-${replace(each.value, ".", "-")}-endpoint"
    Role = "vpc-endpoint"
  })
}
