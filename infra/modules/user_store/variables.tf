variable "table_name" {
  description = "Name of the DynamoDB table used by the users domain."
  type        = string

  validation {
    condition     = length(trimspace(var.table_name)) > 0
    error_message = "table_name must not be empty."
  }
}

variable "point_in_time_recovery_enabled" {
  description = "Whether point-in-time recovery is enabled for the table."
  type        = bool
  default     = false
}

variable "deletion_protection_enabled" {
  description = "Whether deletion protection is enabled for the table."
  type        = bool
  default     = false
}

variable "tags" {
  description = "Additional tags applied to the DynamoDB table."
  type        = map(string)
  default     = {}
}
