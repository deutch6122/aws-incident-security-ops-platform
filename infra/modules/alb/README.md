# alb module

Product_A internet-facing Application Load Balancer for the dev MVP: the ALB
itself, a Fargate (`ip`) target group with a `/health` health check, a
**mandatory HTTPS (443) listener**, an **HTTP (80) listener that 301-redirects to
HTTPS**, always-on access logging, and support for either a module-owned
HTTPS-only security group or an externally supplied one.

- Requirements: Req 15.1, 15.3

## TLS: mandatory HTTPS + HTTP→HTTPS redirect

- `certificate_arn` is a **required** input (no default, not nullable) and is
  validated as an ACM certificate ARN. The real ARN is supplied at wiring time
  via the Parameter Sheet and is never committed to the repository.
- **HTTPS (443) listener**: always created (no `count`/certificate fallback),
  `protocol = HTTPS`, `ssl_policy = var.ssl_policy` (default TLS 1.3), forwards
  to the backend target group.
- **HTTP (80) listener**: always created, its default action is a
  `redirect` to `HTTPS` port `443` with `status_code = HTTP_301`. It never
  forwards to the target group, so plaintext is never served by the backend.

## Target group

`target_type = "ip"` for Fargate (awsvpc) targets, protocol HTTP on `app_port`
(default 8080, restricted to 8000/8080), health check path `/health`. In-cluster
container communication remains HTTP (TLS terminates at the ALB).

## Access logging

Access logging is always enabled, so `access_logs_bucket` (an existing S3 bucket)
is a required input, written under `access_logs_prefix` (default `alb`).

**Ownership**: this module does **not** create the access-log S3 bucket or its
bucket policy. The dev root (Task 27) owns the ALB access-log bucket, its
account/region-unique name, and the bucket policy granting the ELB log-delivery
principal write access. This module only references the bucket by name.

## Security group boundary

`network` module owns the SG boundary intent. This module supports two modes:

- `create_security_group = true` (default): creates `${name_prefix}-alb-sg`
  (body `ingress = []` / `egress = []` plus standalone rule resources). HTTP(80)
  and HTTPS(443) ingress are restricted to `allowed_ingress_cidrs` (validation
  forbids `0.0.0.0/0`). Egress is a **referenced** rule to `ecs_security_group_id`
  only, created only when that SG is supplied (never `0.0.0.0/0`).
- `create_security_group = false`: attaches the supplied `alb_security_group_id`
  (e.g. `module.network.security_group_ids.alb`) and creates no rules.

**In Task 27 the dev root passes the network module's SG** (`create_security_group = false`
with `alb_security_group_id = module.network.security_group_ids.alb`) so the ALB
and network modules never double-create the same SG. No new public `0.0.0.0/0`
ingress is added by this module.

## Outputs

- `alb_arn`, `alb_dns_name`, `alb_zone_id`, `target_group_arn`, `security_group_id`
- `https_listener_arn` (**always present / non-nullable** — HTTPS listener is
  unconditional)
- `http_listener_arn` (the 301 redirect listener)

No secret value is output.

## dev root wiring

This module is **not** wired into the dev root here. Wiring — including passing
the network SG, the ACM certificate ARN, and the access-log bucket + policy — is
performed in Task 27.

## Tests

`tests/test_alb_snapshot.py` is a static text/regex check (no Terraform/AWS). It
verifies the mandatory certificate input, unconditional HTTPS listener, HTTP→443
`HTTP_301` redirect with no forward, HTTP/ip/app_port target group, always-on
access logging with no in-module bucket, the external SG interface, a
non-nullable HTTPS listener output, and the absence of real ARNs / account IDs /
secrets.

## Verification category

- Category A (required): the static test above, `terraform validate`.
- Category C (deferred, real AWS): HTTP→HTTPS redirect response and TLS behaviour
  against a live ALB.
