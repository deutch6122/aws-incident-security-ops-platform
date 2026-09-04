output "vpc_id" {
  description = "ID of the network VPC."
  value       = aws_vpc.this.id
}

output "public_subnet_ids" {
  description = "Public subnet IDs keyed by Availability Zone."
  value       = { for az, subnet in aws_subnet.public : az => subnet.id }
}

output "private_app_subnet_ids" {
  description = "Private application subnet IDs keyed by Availability Zone."
  value       = { for az, subnet in aws_subnet.private_app : az => subnet.id }
}

output "isolated_db_subnet_ids" {
  description = "Isolated database subnet IDs keyed by Availability Zone."
  value       = { for az, subnet in aws_subnet.isolated_db : az => subnet.id }
}

output "security_group_ids" {
  description = "Security-group IDs for downstream ALB, ECS, EKS, and database modules."
  value = {
    alb = aws_security_group.alb.id
    ecs = aws_security_group.ecs.id
    eks = aws_security_group.eks.id
    db  = aws_security_group.db.id
  }
}

output "nat_gateway_id" {
  description = "Single-AZ NAT Gateway ID when enable_nat_gateway is true; otherwise null."
  value       = try(aws_nat_gateway.this[0].id, null)
}

output "vpc_endpoint_ids" {
  description = "Optional endpoint IDs, grouped by endpoint type."
  value = {
    s3        = try(aws_vpc_endpoint.s3[0].id, null)
    interface = { for service, endpoint in aws_vpc_endpoint.interface : service => endpoint.id }
  }
}
