output "api_ecr_repository_url" {
  value       = aws_ecr_repository.api.repository_url
  description = "ECR repo URL for Aventi API image"
}

output "worker_ecr_repository_url" {
  value       = aws_ecr_repository.worker.repository_url
  description = "ECR repo URL for Aventi worker image"
}
