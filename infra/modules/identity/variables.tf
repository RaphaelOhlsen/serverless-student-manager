variable "user_pool_name" {
  description = "Name of the Cognito User Pool."
  type        = string

  validation {
    condition     = length(trimspace(var.user_pool_name)) > 0
    error_message = "user_pool_name must not be empty."
  }
}

variable "user_pool_client_name" {
  description = "Name of the Cognito User Pool application client."
  type        = string

  validation {
    condition     = length(trimspace(var.user_pool_client_name)) > 0
    error_message = "user_pool_client_name must not be empty."
  }
}

variable "tags" {
  description = "Additional tags applied to the Cognito User Pool."
  type        = map(string)
  default     = {}
}
