variable "aws_region" {
  description = "AWS Region in which the bootstrap resources will be managed."
  type        = string

  validation {
    condition     = can(regex("^[a-z]{2}(-[a-z]+)+-[0-9]+$", var.aws_region))
    error_message = "aws_region must be a valid AWS Region name."
  }
}

variable "github_repository" {
  description = "GitHub repository allowed to assume the deploy roles, in owner/repository format."
  type        = string

  validation {
    condition     = can(regex("^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$", var.github_repository))
    error_message = "github_repository must use the exact owner/repository format without wildcards."
  }
}

variable "github_owner_id" {
  description = "Immutable numeric GitHub owner ID used in OIDC subject claims."
  type        = string

  validation {
    condition     = can(regex("^[0-9]+$", var.github_owner_id))
    error_message = "github_owner_id must contain only numeric characters."
  }
}

variable "github_repository_id" {
  description = "Immutable numeric GitHub repository ID used in OIDC subject claims."
  type        = string

  validation {
    condition     = can(regex("^[0-9]+$", var.github_repository_id))
    error_message = "github_repository_id must contain only numeric characters."
  }
}

variable "state_bucket_name" {
  description = "Globally unique name for the private Terraform state bucket."
  type        = string

  validation {
    condition = (
      length(var.state_bucket_name) >= 3 &&
      length(var.state_bucket_name) <= 63 &&
      can(regex("^[a-z0-9][a-z0-9.-]*[a-z0-9]$", var.state_bucket_name)) &&
      !can(regex("\\.\\.", var.state_bucket_name)) &&
      !can(regex("^[0-9]{1,3}(\\.[0-9]{1,3}){3}$", var.state_bucket_name)) &&
      !startswith(var.state_bucket_name, "xn--") &&
      !startswith(var.state_bucket_name, "sthree-") &&
      !startswith(var.state_bucket_name, "amzn-s3-demo-") &&
      !endswith(var.state_bucket_name, "-s3alias") &&
      !endswith(var.state_bucket_name, "--ol-s3") &&
      !endswith(var.state_bucket_name, ".mrap") &&
      !endswith(var.state_bucket_name, "--x-s3") &&
      !endswith(var.state_bucket_name, "--table-s3")
    )
    error_message = "state_bucket_name must satisfy the Amazon S3 general purpose bucket naming rules."
  }
}
