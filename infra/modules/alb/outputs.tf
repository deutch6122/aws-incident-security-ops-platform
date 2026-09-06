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

output "https_listener_arn" {
  description = "ARN of the HTTPS (443) listener. Always present because certificate_arn is required and the HTTPS listener is created unconditionally."
  value       = aws_lb_listener.https.arn
}

output "http_listener_arn" {
  description = "ARN of the HTTP (80) redirect listener that returns HTTP_301 to HTTPS."
  value       = aws_lb_listener.http.arn
}

output "security_group_id" {
  description = "Security group attached to the ALB (module-created or supplied)."
  value       = local.security_group_id
}
