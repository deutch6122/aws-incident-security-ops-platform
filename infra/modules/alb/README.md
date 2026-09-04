# alb module

This module defines the Product_A internet-facing Application Load Balancer for the dev MVP: the ALB itself, a Fargate (`ip`) target group with a `/health` health check, an HTTPS (443) listener, always-on access logging, and an HTTPS-only security group whose ingress is restricted to trusted CIDRs.

- Requirements: Req 15.1, 15.3
- Implemented in Task 9.1.

## HTTPS and HTTP ingress, bounded to trusted CIDRs

The ALB is `internal = false` by default (a demo public ALB), but both HTTP (80) and HTTPS (443) ingress are always bounded to `allowed_ingress_cidrs`. The variable validation forbids `0.0.0.0/0`, mirroring the network module's `allowed_alb_ingress_cidrs`, so the ALB is never open to the entire Internet.

## Security group relationship with the network module

The Task 4 network module already defines an `alb` boundary security group (443 ingress from trusted CIDRs, egress to the ECS SG). To keep a single owner of the ALB's live SG this module supports two modes:

- `create_security_group = true` (default): the module creates and attaches its own `${name_prefix}-alb-sg`. HTTPS (443) ingress is restricted to `allowed_ingress_cidrs`, and egress to the app port is a **referenced** egress rule targeting `ecs_security_group_id` — the ECS task SG — rather than a CIDR. Following the network module style, the `aws_security_group` body sets `ingress = []` / `egress = []` and standalone `aws_vpc_security_group_ingress_rule` / `aws_vpc_security_group_egress_rule` resources add the explicit rules.
  - The egress rule is created **only when `ecs_security_group_id` is non-null**. When `ecs_security_group_id` is `null` the module creates no egress rule at all and never opens egress to `0.0.0.0/0`; the ALB SG body keeps `egress = []` until a concrete ECS SG is supplied. This is the safe default when the destination SG is not yet known.
- `create_security_group = false`: the module attaches the supplied `alb_security_group_id` (for example `module.network.security_group_ids.alb`) and creates no rules, letting the network module remain the single owner.

The network module's SG expresses the boundary intent; this module's SG (when created) is the one actually attached to the ALB. Choose one owner per environment to avoid double management.

## Listener and TLS

The module creates two listeners:

- **HTTP (80) listener**: Always created as a dev/MVP fallback when no ACM certificate is available. This allows the Backend API to be accessed during development before a certificate is issued.
- **HTTPS (443) listener**: Created only when `certificate_arn` is provided. In production, configure an ACM certificate and use HTTPS.

The HTTPS listener uses `ssl_policy` defaulting to a TLS 1.3 policy. When `certificate_arn` is `null` (dev without a certificate), only the HTTP listener is active. The HTTP fallback is intended for dev/MVP use; `0.0.0.0/0` is forbidden by the `allowed_ingress_cidrs` validation, so access is always restricted to trusted CIDRs.

## Target group

`target_type = "ip"` for Fargate (awsvpc) targets, protocol HTTP on `app_port` (default 8080, restricted to 8000/8080), health check path `/health`.

## Access logging

Access logging is always enabled, so `access_logs_bucket` (an existing S3 bucket owned outside this module) is required. Objects are written under `access_logs_prefix` (default `alb`).

## Outputs

`alb_arn`, `alb_dns_name`, `alb_zone_id`, `target_group_arn`, `listener_arn` (null when no certificate), and `security_group_id`. No secret value is output.

## dev root wiring

This module is **not** wired into the dev root in Task 9. The ALB/ECS stack still depends on inputs owned by later tasks — IAM roles (Task 10+), an ACM certificate, the access-log S3 bucket, and the container image URI. Wiring is deferred until those dependencies exist so the Task 4 "wire only what the task implements" policy is preserved. See `apps/backend-api` / dev root notes for the deferral.

## Not run by this module

This module does not run Terraform (`init`/`validate`/`plan`/`apply`) and does not contact AWS. The Task 9.3 tests are static text/regex checks only.
