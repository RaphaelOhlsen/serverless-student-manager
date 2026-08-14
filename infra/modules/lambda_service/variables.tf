variable "function_name" {
  description = "Name of the Lambda function."
  type        = string

  validation {
    condition     = length(trimspace(var.function_name)) > 0
    error_message = "function_name must not be empty."
  }
}

variable "description" {
  description = "Description of the Lambda function."
  type        = string
  default     = ""
}

variable "runtime" {
  description = "Lambda runtime."
  type        = string
}

variable "handler" {
  description = "Lambda function handler."
  type        = string

  validation {
    condition     = length(trimspace(var.handler)) > 0
    error_message = "handler must not be empty."
  }
}

variable "architectures" {
  description = "Instruction set architecture used by the Lambda function."
  type        = list(string)
  default     = ["x86_64"]

  validation {
    condition = (
      length(var.architectures) == 1 &&
      contains(["x86_64", "arm64"], var.architectures[0])
    )
    error_message = "architectures must contain exactly one value: x86_64 or arm64."
  }
}

variable "memory_size" {
  description = "Memory allocated to the Lambda function in MB."
  type        = number
  default     = 512

  validation {
    condition     = var.memory_size >= 128 && var.memory_size <= 10240
    error_message = "memory_size must be between 128 and 10240 MB."
  }
}

variable "timeout" {
  description = "Lambda function timeout in seconds."
  type        = number
  default     = 10

  validation {
    condition     = var.timeout >= 1 && var.timeout <= 900
    error_message = "timeout must be between 1 and 900 seconds."
  }
}

variable "environment_variables" {
  description = "Environment variables configured on the Lambda function."
  type        = map(string)
  default     = {}
}

variable "bootstrap_package_filename" {
  description = "Path to the Lambda deployment package used only to bootstrap the function."
  type        = string

  validation {
    condition     = length(trimspace(var.bootstrap_package_filename)) > 0
    error_message = "bootstrap_package_filename must not be empty."
  }
}

variable "log_retention_in_days" {
  description = "CloudWatch Logs retention period in days."
  type        = number

  validation {
    condition = contains(
      [
        1,
        3,
        5,
        7,
        14,
        30,
        60,
        90,
        120,
        150,
        180,
        365,
        400,
        545,
        731,
        1096,
        1827,
        2192,
        2557,
        2922,
        3288,
        3653,
      ],
      var.log_retention_in_days,
    )
    error_message = "log_retention_in_days must be a value supported by CloudWatch Logs."
  }
}

variable "additional_iam_policy_json" {
  description = "Optional IAM policy document containing service-specific permissions."
  type        = string
  default     = null
  nullable    = true
}

variable "alias_name" {
  description = "Stable Lambda alias managed structurally by Terraform."
  type        = string
  default     = "live"

  validation {
    condition     = length(trimspace(var.alias_name)) > 0
    error_message = "alias_name must not be empty."
  }
}

variable "component" {
  description = "Component tag applied to resources."
  type        = string

  validation {
    condition     = length(trimspace(var.component)) > 0
    error_message = "component must not be empty."
  }
}

variable "data_classification" {
  description = "Data classification tag applied to resources."
  type        = string
  default     = "confidential"

  validation {
    condition     = length(trimspace(var.data_classification)) > 0
    error_message = "data_classification must not be empty."
  }
}

variable "tags" {
  description = "Additional tags applied to resources."
  type        = map(string)
  default     = {}
}
