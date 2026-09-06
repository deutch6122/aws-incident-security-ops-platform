# Committed partial S3 backend configuration. The account-specific bucket name
# is supplied only at init time:
#   terraform init -backend-config="bucket=<bootstrap state_bucket_name>"
# Never add a real bucket name, account ID, credential, or secret to this file.
terraform {
  backend "s3" {
    key          = "environments/dev/terraform.tfstate"
    region       = "ap-northeast-1"
    encrypt      = true
    use_lockfile = true
  }
}
