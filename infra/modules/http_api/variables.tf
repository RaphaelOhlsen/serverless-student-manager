variable "api_name" {
  description = "Name of the API Gateway HTTP API."
  type        = string

  validation {
    condition     = length(trimspace(var.api_name)) > 0
    error_message = "api_name must not be empty."
  }
}

variable "jwt_issuer" {
  description = "OIDC issuer URL used by the JWT authorizer."
  type        = string

  validation {
    condition     = length(trimspace(var.jwt_issuer)) > 0
    error_message = "jwt_issuer must not be empty."
  }
}

variable "jwt_audience" {
  description = "Allowed audience values used by the JWT authorizer."
  type        = list(string)

  validation {
    condition = (
      length(var.jwt_audience) > 0 &&
      alltrue([
        for audience in var.jwt_audience :
        length(trimspace(audience)) > 0
      ])
    )
    error_message = "jwt_audience must contain at least one non-empty value."
  }
}

variable "integrations" {
  description = "Lambda alias integrations exposed by the HTTP API."

  type = map(object({
    invoke_arn    = string
    function_name = string
    alias_name    = string
  }))

  validation {
    condition = (
      length(var.integrations) > 0 &&
      alltrue([
        for integration in values(var.integrations) :
        length(trimspace(integration.invoke_arn)) > 0 &&
        length(trimspace(integration.function_name)) > 0 &&
        length(trimspace(integration.alias_name)) > 0
      ])
    )
    error_message = "integrations must contain at least one Lambda integration with non-empty invoke_arn, function_name and alias_name values."
  }
}

variable "routes" {
  description = "HTTP API routes and their Lambda integrations."

  type = map(object({
    route_key          = string
    integration_key    = string
    authorization_type = string
  }))

  validation {
    condition = (
      length(var.routes) > 0 &&
      alltrue([
        for route in values(var.routes) :
        length(trimspace(route.route_key)) > 0 &&
        length(trimspace(route.integration_key)) > 0 &&
        contains(["NONE", "JWT"], route.authorization_type)
      ])
    )
    error_message = "routes must contain at least one route with non-empty route_key and integration_key values, and authorization_type must be NONE or JWT."
  }
}

variable "cors_allow_origins" {
  description = "Origins allowed to make cross-origin requests to the HTTP API. An empty list disables API Gateway CORS configuration."
  type        = list(string)
  default     = []

  validation {
    condition = alltrue([
      for origin in var.cors_allow_origins :
      length(trimspace(origin)) > 0
    ])
    error_message = "cors_allow_origins must contain only non-empty values."
  }
}

variable "cors_allow_methods" {
  description = "HTTP methods allowed by the HTTP API CORS configuration."
  type        = list(string)

  default = [
    "GET",
    "POST",
    "PUT",
    "DELETE",
    "OPTIONS",
  ]

  validation {
    condition = (
      length(var.cors_allow_methods) > 0 &&
      alltrue([
        for method in var.cors_allow_methods :
        contains(
          ["DELETE", "GET", "HEAD", "OPTIONS", "PATCH", "POST", "PUT", "*"],
          upper(method),
        )
      ])
    )
    error_message = "cors_allow_methods must contain only valid HTTP methods or *."
  }
}

variable "cors_allow_headers" {
  description = "HTTP request headers allowed by the HTTP API CORS configuration."
  type        = list(string)

  default = [
    "Authorization",
    "Content-Type",
  ]

  validation {
    condition = alltrue([
      for header in var.cors_allow_headers :
      length(trimspace(header)) > 0
    ])
    error_message = "cors_allow_headers must contain only non-empty values."
  }
}

variable "cors_expose_headers" {
  description = "HTTP response headers exposed to browsers by the HTTP API CORS configuration."
  type        = list(string)
  default     = []

  validation {
    condition = alltrue([
      for header in var.cors_expose_headers :
      length(trimspace(header)) > 0
    ])
    error_message = "cors_expose_headers must contain only non-empty values."
  }
}

variable "cors_allow_credentials" {
  description = "Whether browser credentials are allowed in cross-origin requests."
  type        = bool
  default     = false
}

variable "cors_max_age" {
  description = "Maximum number of seconds browsers may cache CORS preflight responses."
  type        = number
  default     = 300

  validation {
    condition     = var.cors_max_age >= 0
    error_message = "cors_max_age must be greater than or equal to 0."
  }
}

variable "access_logging_enabled" {
  description = "Whether API Gateway access logging is enabled for the default stage."
  type        = bool
  default     = true
}

variable "access_log_retention_in_days" {
  description = "CloudWatch Logs retention period for HTTP API access logs."
  type        = number
  default     = 14

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
      var.access_log_retention_in_days,
    )
    error_message = "access_log_retention_in_days must be a value supported by CloudWatch Logs."
  }
}

variable "component" {
  description = "Component tag applied to resources."
  type        = string
  default     = "http-api"

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