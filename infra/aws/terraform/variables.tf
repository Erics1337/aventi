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
  description = "Container port exposed by the API task definition."
  default     = 8000
}

variable "log_retention_days" {
  type        = number
  description = "CloudWatch log retention for ECS logs."
  default     = 14
}

variable "api_image_tag" {
  type        = string
  description = "Image tag to use for the API task definition."
  default     = "latest"
}

variable "worker_image_tag" {
  type        = string
  description = "Image tag to use for the worker task definition."
  default     = "latest"
}

variable "api_cpu" {
  type        = number
  description = "API task CPU units."
  default     = 256
}

variable "api_memory" {
  type        = number
  description = "API task memory in MiB."
  default     = 512
}

variable "worker_cpu" {
  type        = number
  description = "Worker task CPU units."
  default     = 256
}

variable "worker_memory" {
  type        = number
  description = "Worker task memory in MiB."
  default     = 512
}

variable "api_command" {
  type        = list(string)
  description = "Optional command override for the API container."
  default     = []
}

variable "worker_command" {
  type        = list(string)
  description = "Command for the worker container."
  default     = ["python", "-m", "aventi_backend.worker.main"]
}

variable "api_environment" {
  type        = map(string)
  description = "Non-sensitive environment variables for the API container."
  default     = {}
}

variable "worker_environment" {
  type        = map(string)
  description = "Non-sensitive environment variables for the worker container."
  default     = {}
}

variable "vpc_id" {
  type        = string
  description = "VPC to use for optional ECS services. Defaults to the account default VPC."
  default     = null
}

variable "subnet_ids" {
  type        = list(string)
  description = "Subnet IDs for optional ECS services. Defaults to subnets in the selected/default VPC."
  default     = []
}

variable "assign_public_ip" {
  type        = bool
  description = "Whether optional ECS services should get a public IP."
  default     = true
}

variable "enable_api_service" {
  type        = bool
  description = "Whether to create a running ECS service for the API."
  default     = false
}

variable "api_desired_count" {
  type        = number
  description = "Desired task count for the optional API ECS service."
  default     = 0
}

variable "enable_load_balancer" {
  type        = bool
  description = "Whether to create an ALB in front of the optional API ECS service."
  default     = false
}

variable "load_balancer_subnet_ids" {
  type        = list(string)
  description = "Subnet IDs for the optional ALB. Defaults to the API service subnets."
  default     = []
}

variable "health_check_path" {
  type        = string
  description = "Health check path for the optional API target group."
  default     = "/health"
}

variable "create_runtime_secret" {
  type        = bool
  description = "Create an empty Secrets Manager secret placeholder for runtime configuration."
  default     = false
}

variable "runtime_secret_name" {
  type        = string
  description = "Name for the optional runtime secret. Defaults to <project>-<env>/backend/env."
  default     = null
}

variable "worker_reserved_concurrency" {
  type        = number
  description = "Max concurrent executions of the worker Lambda. Caps parallel SerpAPI calls."
  default     = 5
}

variable "market_scan_cron_expression" {
  type        = string
  description = "EventBridge schedule for the weekly market scan. Default: Mondays 09:00 UTC."
  default     = "cron(0 9 ? * MON *)"
}

variable "market_scan_max_markets" {
  type        = number
  description = "Max active markets the weekly scheduler will fan out per run."
  default     = 200
}
