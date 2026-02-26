variable "project_name" {
  type        = string
  description = "Project identifier"
  default     = "aventi"
}

variable "environment" {
  type        = string
  description = "Deployment environment"
  default     = "dev"
}

variable "aws_region" {
  type        = string
  description = "AWS region"
  default     = "us-east-1"
}

variable "api_container_port" {
  type        = number
  default     = 8000
}

variable "supabase_url" {
  type      = string
  sensitive = true
}

variable "supabase_service_role_key" {
  type      = string
  sensitive = true
}

variable "supabase_jwks_url" {
  type      = string
  sensitive = true
}

variable "internal_api_key" {
  type      = string
  sensitive = true
}
