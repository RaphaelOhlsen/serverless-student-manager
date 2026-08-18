variable "role_name" {
  description = "Name of the IAM role assumed by the operational GitHub Actions workflow."
  type        = string

  validation {
    condition     = length(trimspace(var.role_name)) > 0
    error_message = "role_name must not be empty."
  }
}

variable "role_description" {
  description = "Description of the operational IAM role."
  type        = string

  validation {
    condition     = length(trimspace(var.role_description)) > 0
    error_message = "role_description must not be empty."
  }
}

variable "oidc_provider_arn" {
  description = "ARN of the existing GitHub Actions OIDC provider."
  type        = string

  validation {
    condition     = can(regex("^arn:aws:iam::[0-9]{12}:oidc-provider/token\\.actions\\.githubusercontent\\.com$", var.oidc_provider_arn))
    error_message = "oidc_provider_arn must be the GitHub Actions OIDC provider ARN."
  }
}

variable "oidc_subject" {
  description = "Exact GitHub Actions OIDC subject allowed to assume the role."
  type        = string

  validation {
    condition     = length(trimspace(var.oidc_subject)) > 0 && !strcontains(var.oidc_subject, "*")
    error_message = "oidc_subject must be an exact non-empty subject without wildcards."
  }
}

variable "policy_name" {
  description = "Name of the managed IAM policy attached to the operational role."
  type        = string

  validation {
    condition     = length(trimspace(var.policy_name)) > 0
    error_message = "policy_name must not be empty."
  }
}

variable "policy_description" {
  description = "Description of the managed IAM policy."
  type        = string

  validation {
    condition     = length(trimspace(var.policy_description)) > 0
    error_message = "policy_description must not be empty."
  }
}

variable "policy_json" {
  description = "JSON document containing the least-privilege permissions for the operational capability."
  type        = string

  validation {
    condition     = can(jsondecode(var.policy_json))
    error_message = "policy_json must contain valid JSON."
  }
}

variable "max_session_duration" {
  description = "Maximum session duration, in seconds, for the operational role."
  type        = number
  default     = 3600

  validation {
    condition     = var.max_session_duration >= 3600 && var.max_session_duration <= 43200
    error_message = "max_session_duration must be between 3600 and 43200 seconds."
  }
}

variable "data_classification" {
  description = "Data classification tag applied to operational IAM resources."
  type        = string
  default     = "restricted"

  validation {
    condition     = length(trimspace(var.data_classification)) > 0
    error_message = "data_classification must not be empty."
  }
}

variable "tags" {
  description = "Additional tags applied to operational IAM resources."
  type        = map(string)
  default     = {}
}
