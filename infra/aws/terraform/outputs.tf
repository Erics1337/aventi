output "backend_ecr_repository_url" {
  value       = aws_ecr_repository.worker.repository_url
  description = "ECR repo URL for the consolidated Aventi backend image (serves api, worker, scheduler)"
}

output "api_lambda_arn" {
  value       = aws_lambda_function.api.arn
  description = "API Lambda Function ARN"
}

output "worker_lambda_arn" {
  value       = aws_lambda_function.worker.arn
  description = "Worker Lambda Function ARN"
}

output "api_lambda_url" {
  value       = aws_lambda_function_url.api.function_url
  description = "Public HTTP Endpoint for the API Lambda"
}

output "runtime_secret_name" {
  value       = one(aws_secretsmanager_secret.runtime[*].name)
  description = "Secrets Manager placeholder name when create_runtime_secret=true"
}

output "scheduler_lambda_arn" {
  value       = aws_lambda_function.scheduler.arn
  description = "Weekly market-scan scheduler Lambda ARN"
}

output "weekly_market_scan_rule_name" {
  value       = aws_cloudwatch_event_rule.weekly_market_scan.name
  description = "EventBridge rule driving the weekly market scan"
}

output "weekly_city_scan_rule_name" {
  value       = aws_cloudwatch_event_rule.weekly_market_scan.name
  description = "Deprecated: renamed to weekly_market_scan_rule_name"
}
