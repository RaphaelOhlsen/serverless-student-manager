variable "bucket_name" {
  description = "Globally unique name of the private frontend S3 bucket."
  type        = string

  validation {
    condition     = length(trimspace(var.bucket_name)) >= 3 && length(var.bucket_name) <= 63
    error_message = "bucket_name must contain between 3 and 63 characters."
  }
}

variable "distribution_name" {
  description = "Name used for the CloudFront distribution and related resources."
  type        = string

  validation {
    condition     = length(trimspace(var.distribution_name)) > 0
    error_message = "distribution_name must not be empty."
  }
}

variable "data_classification" {
  description = "Data classification tag applied to frontend hosting resources."
  type        = string
  default     = "public"

  validation {
    condition     = length(trimspace(var.data_classification)) > 0
    error_message = "data_classification must not be empty."
  }
}

variable "tags" {
  description = "Additional tags applied to frontend hosting resources."
  type        = map(string)
  default     = {}
}
