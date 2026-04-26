locals {
  name_prefix = "${var.project_name}-${var.environment}"

  common_tags = {
    Project     = var.project_name
    Environment = var.environment
    ManagedBy   = "terraform"
  }

  runtime_secret_name = coalesce(var.runtime_secret_name, "${local.name_prefix}/backend/env")
  vpc_id              = coalesce(var.vpc_id, data.aws_vpc.default.id)
  app_subnet_ids      = length(var.subnet_ids) > 0 ? var.subnet_ids : data.aws_subnets.default.ids
  alb_subnet_ids      = length(var.load_balancer_subnet_ids) > 0 ? var.load_balancer_subnet_ids : local.app_subnet_ids

  api_environment = concat(
    [
      {
        name  = "AVENTI_ENV"
        value = var.environment
      },
    ],
    [for name, value in var.api_environment : { name = name, value = value }],
  )

  worker_environment = concat(
    [
      {
        name  = "AVENTI_ENV"
        value = var.environment
      },
    ],
    [for name, value in var.worker_environment : { name = name, value = value }],
  )
}
