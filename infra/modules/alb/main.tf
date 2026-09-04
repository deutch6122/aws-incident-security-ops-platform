locals {
  # The module attaches either its own HTTPS-only security group or an existing
  # one (for example the network module's boundary SG). Exactly one is used.
  security_group_id = var.create_security_group ? aws_security_group.alb[0].id : var.alb_security_group_id
}

# ALB-attached security group. It intentionally follows the network module
# style: the aws_security_group body sets ingress = [] / egress = [] to remove
# the implicit allow-all rules, and standalone rule resources add only the
# HTTPS ingress from trusted CIDRs and the egress to the ECS tasks.
resource "aws_security_group" "alb" {
  count = var.create_security_group ? 1 : 0

  name        = "${var.name_prefix}-alb-sg"
  description = "ALB HTTPS ingress restricted to trusted CIDRs; egress only to ECS tasks."
  vpc_id      = var.vpc_id
  ingress     = []
  egress      = []

  tags = merge(var.common_tags, {
    Name = "${var.name_prefix}-alb-sg"
    Role = "alb"
  })
}

# HTTP (80) ingress is bounded to allowed_ingress_cidrs (dev/MVP fallback).
# The variable validation forbids 0.0.0.0/0, so even the demo public ALB is never open to the Internet.
resource "aws_vpc_security_group_ingress_rule" "http" {
  for_each = var.create_security_group ? toset(var.allowed_ingress_cidrs) : toset([])

  security_group_id = aws_security_group.alb[0].id
  cidr_ipv4         = each.value
  from_port         = 80
  ip_protocol       = "tcp"
  to_port           = 80

  tags = merge(var.common_tags, { Name = "${var.name_prefix}-alb-http-ingress" })
}

# HTTPS (443) ingress is bounded to allowed_ingress_cidrs. The variable validation
# forbids 0.0.0.0/0, so even the demo public ALB is never open to the Internet.
resource "aws_vpc_security_group_ingress_rule" "https" {
  for_each = var.create_security_group ? toset(var.allowed_ingress_cidrs) : toset([])

  security_group_id = aws_security_group.alb[0].id
  cidr_ipv4         = each.value
  from_port         = 443
  ip_protocol       = "tcp"
  to_port           = 443

  tags = merge(var.common_tags, { Name = "${var.name_prefix}-alb-https-ingress" })
}

# ALB egress is restricted to the ECS task security group (referenced SG),
# matching the network module style. It is created only when this module owns
# the SG and an ECS SG has been supplied. When ecs_security_group_id is null no
# egress rule is created, so the module never opens egress to 0.0.0.0/0.
resource "aws_vpc_security_group_egress_rule" "to_ecs" {
  count = var.create_security_group && var.ecs_security_group_id != null ? 1 : 0

  security_group_id            = aws_security_group.alb[0].id
  referenced_security_group_id = var.ecs_security_group_id
  from_port                    = var.app_port
  ip_protocol                  = "tcp"
  to_port                      = var.app_port

  tags = merge(var.common_tags, { Name = "${var.name_prefix}-alb-to-ecs" })
}

resource "aws_lb" "this" {
  name               = "${var.name_prefix}-alb"
  internal           = var.internal
  load_balancer_type = "application"
  security_groups    = [local.security_group_id]
  subnets            = var.public_subnet_ids

  drop_invalid_header_fields = true

  access_logs {
    bucket  = var.access_logs_bucket
    prefix  = var.access_logs_prefix
    enabled = true
  }

  tags = merge(var.common_tags, {
    Name = "${var.name_prefix}-alb"
    Tier = "public"
    Role = "alb"
  })
}

# target_type = "ip" because the backend runs on Fargate (awsvpc networking).
resource "aws_lb_target_group" "this" {
  name        = "${var.name_prefix}-tg"
  vpc_id      = var.vpc_id
  target_type = "ip"
  port        = var.app_port
  protocol    = "HTTP"

  health_check {
    path                = var.health_check_path
    protocol            = "HTTP"
    port                = "traffic-port"
    healthy_threshold   = 2
    unhealthy_threshold = 3
    timeout             = 5
    interval            = 30
    matcher             = "200"
  }

  tags = merge(var.common_tags, {
    Name = "${var.name_prefix}-tg"
    Role = "alb"
  })
}

# HTTPS (443) listener. It is created only when certificate_arn is provided; in
# dev without a certificate the ALB must not serve traffic until one is issued.
resource "aws_lb_listener" "https" {
  count = var.certificate_arn == null ? 0 : 1

  load_balancer_arn = aws_lb.this.arn
  port              = 443
  protocol          = "HTTPS"
  ssl_policy        = var.ssl_policy
  certificate_arn   = var.certificate_arn

  default_action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.this.arn
  }

  tags = merge(var.common_tags, {
    Name = "${var.name_prefix}-alb-https-listener"
    Role = "alb"
  })
}

# HTTP (80) listener. Created unconditionally for dev/MVP fallback when no ACM
# certificate is available yet. In production, use HTTPS with a certificate.
resource "aws_lb_listener" "http" {
  count = 1

  load_balancer_arn = aws_lb.this.arn
  port              = 80
  protocol          = "HTTP"

  default_action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.this.arn
  }

  tags = merge(var.common_tags, {
    Name = "${var.name_prefix}-alb-http-listener"
    Role = "alb"
  })
}
