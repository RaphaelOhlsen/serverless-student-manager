variable "aws_region" {
  description = "AWS region used by the dev environment."
  type        = string
}

variable "aws_account_id" {
  description = "AWS account ID allowed for the dev environment."
  type        = string

  validation {
    condition     = can(regex("^[0-9]{12}$", var.aws_account_id))
    error_message = "aws_account_id must contain exactly 12 numeric characters."
  }
}

variable "students_api_bootstrap_package_filename" {
  description = "Path to the ZIP package used to bootstrap the students-api Lambda function."
  type        = string

  validation {
    condition     = length(trimspace(var.students_api_bootstrap_package_filename)) > 0
    error_message = "students_api_bootstrap_package_filename must not be empty."
  }
}

variable "users_api_bootstrap_package_filename" {
  description = "Path to the ZIP package used to bootstrap the users-api Lambda function."
  type        = string

  validation {
    condition     = length(trimspace(var.users_api_bootstrap_package_filename)) > 0
    error_message = "users_api_bootstrap_package_filename must not be empty."
  }
}

variable "github_repository" {
  description = "GitHub repository allowed to assume operational roles, in owner/repository format."
  type        = string

  validation {
    condition     = can(regex("^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$", var.github_repository))
    error_message = "github_repository must use the exact owner/repository format without wildcards."
  }
}

variable "github_owner_id" {
  description = "Immutable numeric GitHub owner ID used in operational OIDC subject claims."
  type        = string

  validation {
    condition     = can(regex("^[0-9]+$", var.github_owner_id))
    error_message = "github_owner_id must contain only numeric characters."
  }
}

variable "github_repository_id" {
  description = "Immutable numeric GitHub repository ID used in operational OIDC subject claims."
  type        = string

  validation {
    condition     = can(regex("^[0-9]+$", var.github_repository_id))
    error_message = "github_repository_id must contain only numeric characters."
  }
}
