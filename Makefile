SHELL := /bin/bash
.ONESHELL:
.SHELLFLAGS := -eu -o pipefail -c

# -------- Config (override on CLI: `make deploy ENV=prod`) ------------------
PROJECT       ?= aventi
ENV           ?= dev
AWS_REGION    ?= us-east-1
IMAGE_TAG     ?= $(shell git rev-parse --short HEAD)

# Derived
AWS_ACCOUNT_ID := $(shell aws sts get-caller-identity --query Account --output text 2>/dev/null)
ECR_BASE       := $(AWS_ACCOUNT_ID).dkr.ecr.$(AWS_REGION).amazonaws.com
# Single consolidated repo — serves api, worker, and scheduler Lambdas.
# Keeping the -worker suffix preserves the existing ECR + avoids a migration.
ECR_BACKEND    := $(ECR_BASE)/$(PROJECT)-$(ENV)-worker
WORKER_FN      := $(PROJECT)-$(ENV)-worker
API_FN         := $(PROJECT)-$(ENV)-api
SCHEDULER_FN   := $(PROJECT)-$(ENV)-scheduler
RULE_NAME      := $(PROJECT)-$(ENV)-weekly-city-scan

TF_DIR := infra/aws/terraform

# Load local .env so DATABASE_URL etc. are available (non-fatal if missing)
-include .env
export

.PHONY: help deploy deploy-quick migrate migrate-reset migrate-remote migrate-psql \
        ecr-login build push tf-plan tf-apply runtime-secret-sync \
        smoke logs logs-api logs-scheduler scan-report rule-status rule-disable rule-enable \
        rollback-worker rollback-api

## ------- Meta --------------------------------------------------------------
help: ## show available targets
	@awk 'BEGIN {FS = ":.*##"; printf "Targets:\n"} \
	  /^[a-zA-Z_-]+:.*?##/ { printf "  \033[36m%-18s\033[0m %s\n", $$1, $$2 }' \
	  $(MAKEFILE_LIST)

## ------- Full pipelines ----------------------------------------------------
deploy: migrate build push tf-apply smoke ## full deploy: migrate DB -> build -> push -> terraform -> smoke test
	@echo "✅ deploy complete (tag=$(IMAGE_TAG))"

deploy-quick: build push tf-apply ## skip migrate + smoke (just redeploy code)

## ------- Step 1: Supabase migrations ---------------------------------------
migrate: ## apply pending migrations to LOCAL supabase stack
	supabase migration up --local
	@echo "✅ local migrations up-to-date"

migrate-reset: ## ⚠️  WIPES local db + re-applies ALL migrations from scratch
	supabase db reset --local
	@echo "✅ local db reset from migrations"

migrate-remote: ## push migrations to remote Supabase using DATABASE_URL
	@test -n "$$DATABASE_URL" || (echo "❌ DATABASE_URL not set"; exit 1)
	supabase db push --db-url "$$DATABASE_URL" --yes

migrate-psql: ## apply migration 0008 directly via psql (uses DATABASE_URL)
	@test -n "$$DATABASE_URL" || (echo "❌ DATABASE_URL not set"; exit 1)
	psql "$$DATABASE_URL" -f supabase/migrations/0008_market_heat_and_scan_metrics.sql
	@echo "✅ migration 0008 applied via psql"

## ------- Step 2: Docker build + push ---------------------------------------
ecr-login: ## authenticate Docker with ECR
	aws ecr get-login-password --region $(AWS_REGION) \
	  | docker login --username AWS --password-stdin $(ECR_BASE)

build: ## build the shared backend container image (linux/amd64 for Lambda)
	test -f services/backend/Dockerfile || (echo "❌ services/backend/Dockerfile missing — create one first"; exit 1)
	docker build \
	  --platform linux/amd64 \
	  -t $(ECR_BACKEND):$(IMAGE_TAG) \
	  -t $(ECR_BACKEND):latest \
	  -f services/backend/Dockerfile \
	  services/backend

push: ecr-login ## push backend image to the consolidated ECR
	docker push $(ECR_BACKEND):$(IMAGE_TAG)
	docker push $(ECR_BACKEND):latest
	@echo "✅ pushed $(ECR_BACKEND):$(IMAGE_TAG) (serves api, worker, scheduler)"

## ------- Step 3: Terraform -------------------------------------------------
tf-plan: ## terraform plan (uses current IMAGE_TAG)
	cd $(TF_DIR) && terraform init -upgrade && \
	  terraform plan \
	    -var "worker_image_tag=$(IMAGE_TAG)" \
	    -var "api_image_tag=$(IMAGE_TAG)" \
	    -out=tfplan

tf-apply: tf-plan ## terraform apply (auto-plan first)
	cd $(TF_DIR) && terraform apply -auto-approve tfplan

runtime-secret-sync: ## sync backend runtime config from local env file into AWS Secrets Manager
	bash scripts/sync-runtime-secret.sh

## ------- Step 4: Smoke test + observability --------------------------------
smoke: ## invoke scheduler Lambda with limit=10 and print the response
	aws lambda invoke \
	  --function-name $(SCHEDULER_FN) \
	  --region $(AWS_REGION) \
	  --cli-binary-format raw-in-base64-out \
	  --payload '{"limit": 10}' \
	  /tmp/$(SCHEDULER_FN)-out.json >/dev/null
	@echo "--- scheduler response ---"
	@cat /tmp/$(SCHEDULER_FN)-out.json && echo

logs: ## tail worker Lambda logs (Ctrl-C to stop)
	aws logs tail /aws/lambda/$(WORKER_FN) --follow --region $(AWS_REGION)
logs-api: ## tail API Lambda logs (Ctrl-C to stop)
	aws logs tail /aws/lambda/$(API_FN) --follow --region $(AWS_REGION)

logs-scheduler: ## tail scheduler Lambda logs
	aws logs tail /aws/lambda/$(SCHEDULER_FN) --follow --region $(AWS_REGION)

scan-report: ## show last hour of ingest_runs metadata (requires DATABASE_URL)
	test -n "$$DATABASE_URL" || (echo "DATABASE_URL not set"; exit 1)
	psql "$$DATABASE_URL" -c "\
	  select started_at, \
	         metadata->>'heatTier' as tier, \
	         metadata->>'scanType' as scan_type, \
	         (metadata->>'pagesExecuted')::int as pages, \
	         (metadata->>'candidatesReturned')::int as found, \
	         (metadata->>'nearDuplicatesSkipped')::int as dupes, \
	         inserted_count, \
	         metadata->>'windowExhausted' as exhausted, \
	         error_message \
	    from public.ingest_runs \
	   where started_at > now() - interval '1 hour' \
	   order by started_at desc;"

## ------- Cron management ---------------------------------------------------
rule-status: ## show the EventBridge rule's current state + next schedule
	aws events describe-rule --name $(RULE_NAME) --region $(AWS_REGION) \
	  --query '{State:State,Schedule:ScheduleExpression}'

rule-disable: ## pause the weekly cron (use during incidents)
	aws events disable-rule --name $(RULE_NAME) --region $(AWS_REGION)
	@echo "⏸  cron disabled"

rule-enable: ## re-enable the weekly cron
	aws events enable-rule --name $(RULE_NAME) --region $(AWS_REGION)
	@echo "▶️  cron enabled"

## ------- Rollback ----------------------------------------------------------
rollback-worker: ## point worker Lambda at a previous image tag (TAG=<sha>)
	test -n "$(TAG)" || (echo "Usage: make rollback-worker TAG=<sha>"; exit 1)
	aws lambda update-function-code \
	  --function-name $(WORKER_FN) \
	  --image-uri $(ECR_BACKEND):$(TAG) \
	  --region $(AWS_REGION)
	@echo "⏪ worker rolled back to $(TAG)"

rollback-api: ## point api Lambda at a previous image tag (TAG=<sha>)
	test -n "$(TAG)" || (echo "Usage: make rollback-api TAG=<sha>"; exit 1)
	aws lambda update-function-code \
	  --function-name $(API_FN) \
	  --image-uri $(ECR_BACKEND):$(TAG) \
	  --region $(AWS_REGION)
	@echo "⏪ api rolled back to $(TAG)"
