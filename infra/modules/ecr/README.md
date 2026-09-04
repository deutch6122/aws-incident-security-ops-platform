# ecr module

Creates the four MVP container registries:

- `<name_prefix>-backend-api`
- `<name_prefix>-alarm-event-processor`
- `<name_prefix>-security-finding-worker`
- `<name_prefix>-monthly-summary-cronjob`

Each repository has scan-on-push enabled, AES256 at-rest encryption, `common_tags`, and `IMMUTABLE` image tags by default. `image_tag_mutability` may be explicitly changed to `MUTABLE` for a short-lived dev workflow, but immutable versioned tags are recommended for traceability and rollback safety.

The lifecycle policy deletes untagged images after seven days by default and limits retained tagged images (default 10) for the `v`, `release`, and `sha` tag prefixes. Application deployment must use one of those prefixes for the tagged retention rule to apply. Tune the expiration/retention variables after reviewing image promotion and rollback needs; the defaults prioritize dev cost control.

Encryption uses AWS-managed AES256. A customer-managed KMS key is intentionally a future extension when specific key policy or compliance requirements exist.

This module only declares Terraform resources. Image build/push and ECS/EKS application deployment remain separate App_Deploy work.
