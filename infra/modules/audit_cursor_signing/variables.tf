variable "alias_name" {
  description = "Alias assigned to the KMS HMAC key used to authenticate audit cursors."
  type        = string

  validation {
    condition     = startswith(var.alias_name, "alias/") && length(trimspace(var.alias_name)) > 6
    error_message = "alias_name must be a non-empty KMS alias beginning with alias/."
  }
}

variable "description" {
  description = "Description of the KMS HMAC key."
  type        = string
  default     = "Authenticates Audit Query API pagination cursors."
}

variable "deletion_window_in_days" {
  description = "Waiting period before a scheduled KMS key deletion."
  type        = number
  default     = 30

  validation {
    condition     = var.deletion_window_in_days >= 7 && var.deletion_window_in_days <= 30
    error_message = "deletion_window_in_days must be between 7 and 30."
  }
}

variable "data_classification" {
  description = "Data classification tag applied to the KMS key."
  type        = string
  default     = "confidential"

  validation {
    condition     = length(trimspace(var.data_classification)) > 0
    error_message = "data_classification must not be empty."
  }
}

variable "tags" {
  description = "Additional tags applied to the KMS key."
  type        = map(string)
  default     = {}
}
