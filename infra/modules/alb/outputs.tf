output "alb_arn" {
  description = "ARN of the Application Load Balancer."
  value       = aws_lb.this.arn
}

output "alb_dns_name" {
  description = "Public DNS name of the ALB used by CloudFront/clients."
  value       = aws_lb.this.dns_name
}

output "alb_zone_id" {
  description = "Route53 hosted-zone ID of the ALB for alias records."
  value       = aws_lb.this.zone_id
}

output "target_group_arn" {
  description = "ARN of the target group; wired into the ECS service load_balancer block."
  value       = aws_lb_target_group.this.arn
}

output "listener_arn" {
  description = "ARN of the HTTPS (443) listener, or null when no certificate_arn was supplied."
  value       = try(aws_lb_listener.https[0].arn, null)
}

output "security_group_id" {
  description = "Security group attached to the ALB (module-created or supplied)."
  value       = local.security_group_id
}
