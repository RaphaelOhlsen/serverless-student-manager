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
