# network module

Creates the Product_A dev network foundation: one VPC, two AZs (`ap-northeast-1a` and `ap-northeast-1c` by default), public/private-app/isolated-db subnet tiers, an IGW, route tables, a cost-oriented single-AZ NAT Gateway, and security groups for the future ALB, ECS tasks, EKS workers, and Aurora.

## Security and routing

- `allowed_alb_ingress_cidrs` defaults to the documentation-only `203.0.113.0/24`; it is **not** `0.0.0.0/0` and must be replaced with trusted operator CIDRs before deployment. The module creates HTTPS/443 ingress only; it deliberately creates no HTTP/80 redirect rule because the ALB itself is a later task.
- ECS accepts `app_port` (`8080` by default; `8000` is also supported) only from the ALB SG. ECS/EKS have no inbound rules because EKS workers are SQS-driven.
- ECS and EKS can reach Aurora only over PostgreSQL/5432. The DB SG accepts that port only from ECS and EKS and has no egress rule.
- AWS's implicit SG egress is removed with `egress = []`; every required egress is created explicitly with `aws_vpc_security_group_*_rule` resources. HTTPS/443 egress is explicit and configurable through `external_https_egress_cidrs`.
- The isolated DB route table has no NAT or Internet Gateway default route. It retains only VPC-local routing.

## NAT and endpoints

`enable_nat_gateway=true` is the MVP default. It creates exactly one EIP-backed NAT Gateway in the first public AZ and one private-app default route. This reduces fixed dev cost but is not AZ-resilient; production can expand to per-AZ NAT route tables/gateways.

`enable_nat_gateway=false` omits both the NAT and the private default route, so private subnets do not contain a broken NAT reference. In that mode, workloads need VPC endpoints or otherwise intentionally restricted network requirements.

`enable_vpc_endpoints=false` is the default because endpoints are optional in the MVP. When enabled, the module creates an S3 Gateway endpoint on the private-app route table and configurable interface endpoints for ECR API/DKR, Secrets Manager, CloudWatch Logs, and SQS. These endpoints can reduce NAT data processing and enable workloads to set `external_https_egress_cidrs = []` when their complete dependency set is endpoint-backed. Interface endpoint hourly charges still need cost review.

## Inputs and outputs

All taggable resources receive `name_prefix` and `common_tags`. Subnet CIDRs and AZs are variables with two-AZ/count/CIDR validation, allowing a caller to supply production-sized CIDRs without changing module code. Outputs expose subnet and SG IDs for later ALB/ECS/EKS/Aurora modules.

This module declares infrastructure only. It does not run Terraform, use the AWS CLI, or create resources by itself.
