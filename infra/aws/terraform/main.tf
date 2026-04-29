data "aws_vpc" "default" {
  default = true
}

data "aws_subnets" "default" {
  filter {
    name   = "vpc-id"
    values = [local.vpc_id]
  }
}



#
# One ECR repo serves all three Lambdas (api, worker, scheduler). The handler
# is chosen per-Lambda via image_config.command in Terraform rather than via
# separate images. Keeping a single repo halves storage + eliminates the risk
# of api/worker drifting to different image builds.
#
resource "aws_ecr_repository" "worker" {
  name                 = "${local.name_prefix}-worker"
  image_tag_mutability = var.environment == "prod" ? "IMMUTABLE" : "MUTABLE"
  force_delete         = var.environment == "prod" ? false : true

  image_scanning_configuration {
    scan_on_push = true
  }

  tags = local.common_tags
}

resource "aws_ecr_lifecycle_policy" "worker" {
  repository = aws_ecr_repository.worker.name
  policy = jsonencode({
    rules = [
      {
        rulePriority = 1
        description  = "Keep only the five most recent backend images"
        selection = {
          tagStatus   = "any"
          countType   = "imageCountMoreThan"
          countNumber = 5
        }
        action = {
          type = "expire"
        }
      },
    ]
  })
}

resource "aws_cloudwatch_log_group" "api" {
  name              = "/aws/lambda/${local.name_prefix}-api"
  retention_in_days = var.log_retention_days
  tags              = local.common_tags
}

resource "aws_cloudwatch_log_group" "worker" {
  name              = "/aws/lambda/${local.name_prefix}-worker"
  retention_in_days = var.log_retention_days
  tags              = local.common_tags
}



resource "aws_sqs_queue" "worker_jobs_dlq" {
  name = "${local.name_prefix}-worker-jobs-dlq"
  tags = local.common_tags
}

resource "aws_sqs_queue" "worker_jobs" {
  name = "${local.name_prefix}-worker-jobs"
  visibility_timeout_seconds = 900
  redrive_policy = jsonencode({
    deadLetterTargetArn = aws_sqs_queue.worker_jobs_dlq.arn
    maxReceiveCount     = 5
  })
  tags = local.common_tags
}

resource "aws_iam_role" "lambda_worker" {
  name               = "${local.name_prefix}-lambda-worker"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "lambda.amazonaws.com"
        }
      }
    ]
  })
  tags = local.common_tags
}

resource "aws_iam_role_policy_attachment" "lambda_worker_basic" {
  role       = aws_iam_role.lambda_worker.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

resource "aws_iam_role_policy" "lambda_sqs" {
  name = "sqs_permissions"
  role = aws_iam_role.lambda_worker.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = [
          "sqs:ReceiveMessage",
          "sqs:DeleteMessage",
          "sqs:GetQueueAttributes",
          "sqs:SendMessage"
        ]
        Effect   = "Allow"
        Resource = aws_sqs_queue.worker_jobs.arn
      }
    ]
  })
}

resource "aws_lambda_function" "worker" {
  function_name = "${local.name_prefix}-worker"
  role          = aws_iam_role.lambda_worker.arn
  package_type  = "Image"
  image_uri     = "${aws_ecr_repository.worker.repository_url}:${var.worker_image_tag}"
  timeout       = 900
  memory_size   = tonumber(var.worker_memory)

  # Cap concurrent MARKET_SCAN workers to protect the SerpAPI credit budget
  # and avoid DB contention. Tunable via var.worker_reserved_concurrency.
  reserved_concurrent_executions = var.worker_reserved_concurrency

  # Removed vpc_config to run in AWS default network for free outbound internet (no NAT Gateway needed)

  environment {
    variables = merge(
      {
        AVENTI_ENV           = var.environment
        SQS_WORKER_QUEUE_URL = aws_sqs_queue.worker_jobs.url
      },
      var.worker_environment
    )
  }

  depends_on = [
    aws_cloudwatch_log_group.worker,
    aws_iam_role_policy_attachment.lambda_worker_basic
  ]

  tags = local.common_tags
}

resource "aws_lambda_event_source_mapping" "worker_sqs" {
  event_source_arn = aws_sqs_queue.worker_jobs.arn
  function_name    = aws_lambda_function.worker.arn
  batch_size       = 1
}

resource "aws_iam_role" "lambda_api" {
  name               = "${local.name_prefix}-lambda-api"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "lambda.amazonaws.com"
        }
      }
    ]
  })
  tags = local.common_tags
}

resource "aws_iam_role_policy_attachment" "lambda_api_basic" {
  role       = aws_iam_role.lambda_api.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

resource "aws_iam_role_policy" "lambda_api_sqs" {
  name = "sqs_producer_permissions"
  role = aws_iam_role.lambda_api.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = [
          "sqs:GetQueueAttributes",
          "sqs:GetQueueUrl",
          "sqs:SendMessage"
        ]
        Effect   = "Allow"
        Resource = aws_sqs_queue.worker_jobs.arn
      }
    ]
  })
}

resource "aws_lambda_function" "api" {
  function_name = "${local.name_prefix}-api"
  role          = aws_iam_role.lambda_api.arn
  package_type  = "Image"
  # Uses the same shared backend image as the worker + scheduler. Handler
  # selected via image_config.command below.
  image_uri    = "${aws_ecr_repository.worker.repository_url}:${var.api_image_tag}"
  timeout      = 30
  memory_size  = tonumber(var.api_memory)

  image_config {
    command = ["aventi_backend.api.lambda_handler.handler"]
  }

  environment {
    variables = merge(
      {
        AVENTI_ENV           = var.environment
        SQS_WORKER_QUEUE_URL = aws_sqs_queue.worker_jobs.url
      },
      var.api_environment
    )
  }

  depends_on = [
    aws_cloudwatch_log_group.api,
    aws_iam_role_policy_attachment.lambda_api_basic
  ]

  tags = local.common_tags
}

resource "aws_lambda_function_url" "api" {
  function_name      = aws_lambda_function.api.function_name
  authorization_type = "AWS_IAM"
  cors {
    allow_credentials = true
    allow_origins     = ["*"]
    allow_methods     = ["GET", "POST", "PUT", "DELETE", "OPTIONS"]
    allow_headers     = ["content-type", "authorization", "x-api-key", "date", "keep-alive"]
    expose_headers    = ["keep-alive", "date"]
    max_age           = 86400
  }
}

resource "aws_secretsmanager_secret" "runtime" {
  count = var.create_runtime_secret ? 1 : 0

  name                    = local.runtime_secret_name
  description             = "Runtime configuration for ${local.name_prefix}"
  recovery_window_in_days = var.environment == "prod" ? 30 : 7
  tags                    = local.common_tags
}

############################################################
# Weekly market-scan scheduler (EventBridge -> scheduler Lambda
# -> SQS -> worker Lambda). Fans out one MARKET_SCAN job per
# (active market x scan window). Reuses the worker container
# image with an overridden handler.
############################################################

resource "aws_cloudwatch_log_group" "scheduler" {
  name              = "/aws/lambda/${local.name_prefix}-scheduler"
  retention_in_days = var.log_retention_days
  tags              = local.common_tags
}

resource "aws_lambda_function" "scheduler" {
  function_name = "${local.name_prefix}-scheduler"
  # Reuse the worker IAM role — it already grants SQS:SendMessage + VPC basic exec.
  role         = aws_iam_role.lambda_worker.arn
  package_type = "Image"
  image_uri    = "${aws_ecr_repository.worker.repository_url}:${var.worker_image_tag}"
  timeout      = 300
  memory_size  = 512

  # Override the container CMD to point at the scheduler handler instead of
  # the SQS-consuming worker handler. Both live in the same image.
  image_config {
    command = ["aventi_backend.worker.scheduler.handler"]
  }

  environment {
    variables = merge(
      {
        AVENTI_ENV           = var.environment
        SQS_WORKER_QUEUE_URL = aws_sqs_queue.worker_jobs.url
      },
      var.worker_environment
    )
  }

  depends_on = [
    aws_cloudwatch_log_group.scheduler,
    aws_iam_role_policy_attachment.lambda_worker_basic
  ]

  tags = local.common_tags
}

resource "aws_cloudwatch_event_rule" "weekly_market_scan" {
  name                = "${local.name_prefix}-weekly-market-scan"
  description         = "Trigger weekly heat-aware market scan fan-out"
  schedule_expression = var.market_scan_cron_expression
  tags                = local.common_tags
}

resource "aws_cloudwatch_event_target" "weekly_market_scan" {
  rule      = aws_cloudwatch_event_rule.weekly_market_scan.name
  target_id = "scheduler-lambda"
  arn       = aws_lambda_function.scheduler.arn

  input = jsonencode({
    limit = var.market_scan_max_markets
  })
}

resource "aws_lambda_permission" "allow_eventbridge_scheduler" {
  statement_id  = "AllowEventBridgeInvokeScheduler"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.scheduler.function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.weekly_market_scan.arn
}
