resource "aws_ecr_repository" "api" {
  name = "${local.name_prefix}-api"
  tags = local.common_tags
}

resource "aws_ecr_repository" "worker" {
  name = "${local.name_prefix}-worker"
  tags = local.common_tags
}

resource "aws_cloudwatch_log_group" "api" {
  name              = "/ecs/${local.name_prefix}/api"
  retention_in_days = 14
  tags              = local.common_tags
}

resource "aws_cloudwatch_log_group" "worker" {
  name              = "/ecs/${local.name_prefix}/worker"
  retention_in_days = 14
  tags              = local.common_tags
}

# Placeholder network and ECS resources.
# TODO: add VPC/subnet/security groups or integrate existing network module.
# TODO: add ECS cluster, task definitions, services, ALB, target groups, IAM roles.
# TODO: add EventBridge schedules for worker verification and city scan jobs.
# TODO: add Secrets Manager parameters and task env var wiring for Supabase credentials.
