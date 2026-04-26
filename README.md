# Aventi

Aventi is a premium, swipe-first discovery app for local events, nightlife, and experiences.

This repository is a Turborepo monorepo containing:

- `apps/mobile` (Expo + NativeWind mobile app)
- `services/backend` (FastAPI API + worker)
- `packages/*` shared contracts/client/design tokens
- `supabase` schema and seed data
- `infra/aws/terraform` Serverless AWS baseline using SQS queues and scalable Lambda containers (No expensive ECS required)

## Setup

### Prerequisites

- [Node.js](https://nodejs.org/) (LTS)
- [pnpm](https://pnpm.io/) — JS/TS package manager
- [uv](https://docs.astral.sh/uv/) — Python package manager

### Install Dependencies

From the **repo root**, install all JS/TS dependencies across the monorepo:

```bash
pnpm install
```

> **Note:** `pnpm install` must be run from the root. The `pnpm-workspace.yaml` file manages dependencies for `apps/*`, `packages/*`, and `services/*`.

Then install Python dependencies for the backend:

```bash
cd services/backend && uv sync
```

> **Note:** `uv sync` must be run inside `services/backend/` where the `pyproject.toml` lives. It will **not** work from the repo root.

### Run Services

Turborepo orchestrates mobile + backend API + worker in parallel:

```bash
pnpm dev          # mobile + backend API + worker (the 99% case)
pnpm dev:lite     # mobile + backend API only (no worker)
pnpm dev:full     # alias of pnpm dev — identical command, kept for backwards compat
```

**Note on the scheduler Lambda**: The weekly city-scan scheduler (`services/backend/src/aventi_backend/worker/scheduler.py`) only runs in production via AWS EventBridge. `pnpm dev` does **not** start it. To trigger fan-out manually in local dev:

```bash
uv run --project services/backend python -c "
import asyncio
from aventi_backend.worker.scheduler import _run
print(asyncio.run(_run(limit=5)))
"
```

That enqueues CITY_SCAN jobs onto your local SQS, which the already-running worker will pick up.

### Individual service commands

Use these if you need to run a single service in isolation (debugging, split terminals, etc.):

```bash
# Python deps for the backend
pnpm backend:sync

# Backend API only
pnpm backend:dev

# Worker only (SQS consumer)
pnpm backend:worker
# ...equivalent to:
uv run --project services/backend python -m aventi_backend.worker.main

# Mobile only
pnpm --filter @aventi/mobile dev

# Reset local Supabase DB
supabase db reset
```

## Deployment & Operations (`make`)

The root `Makefile` wraps every deploy and ops step into one-line commands. Run `make help` for the full list.

### Deploy prerequisites

- [Supabase CLI](https://supabase.com/docs/guides/cli) (`supabase`)
- [Terraform](https://developer.hashicorp.com/terraform/downloads) (for `tf-*` targets)
- [AWS CLI v2](https://docs.aws.amazon.com/cli/latest/userguide/getting-started-install.html) with `aws configure` pointed at the right account
- [Docker](https://docs.docker.com/get-docker/) (for `build` / `push`)
- `psql` (only needed for `migrate-psql` + `scan-report`)

### Config (override per-command)

```bash
# defaults:
#   PROJECT=aventi  ENV=dev  AWS_REGION=us-east-1
#   IMAGE_TAG=<current git short sha>
make deploy                                   # dev environment
make deploy ENV=prod AWS_REGION=us-west-2     # prod
make build IMAGE_TAG=hotfix-serpapi           # pinned tag
```

The Makefile auto-loads a root `.env` file, so you can persist values like `DATABASE_URL`, `SUPABASE_DB_PASSWORD`, or `AWS_REGION` there (already gitignored).

### Full pipelines

| command | does |
|---|---|
| `make deploy` | migrate DB → build image → push to ECR → `terraform apply` → smoke-test scheduler |
| `make deploy-quick` | code-only redeploy (skips migrations + smoke test) |

### Database migrations

| command | target | notes |
|---|---|---|
| `make migrate` | **local** | `supabase migration up --local` — applies pending migrations to your local dev stack. |
| `make migrate-reset` | **local** | ⚠️ `supabase db reset --local` — wipes local DB and replays all migrations from scratch. |
| `make migrate-remote` | **cloud** | `supabase db push` to the linked project. Requires `SUPABASE_DB_PASSWORD` (grab from Supabase dashboard → Project Settings → Database). |
| `make migrate-psql` | **either** | Raw `psql -f` of a specific migration file against `$DATABASE_URL`. Useful when the CLI is misbehaving. |

**Starting local Supabase**: `supabase start` before the first `make migrate`. Check status with `supabase status`.

### Backend image (Docker + ECR)

| command | does |
|---|---|
| `make build` | `docker build --platform linux/amd64` of `services/backend/Dockerfile`, tagged `:$IMAGE_TAG` and `:latest` |
| `make ecr-login` | `docker login` against your account's ECR registry |
| `make push` | `docker push` both tags (runs `ecr-login` first) |

### Terraform

| command | does |
|---|---|
| `make tf-plan` | `terraform init -upgrade` + `terraform plan` with the current `IMAGE_TAG`, saves to `tfplan` |
| `make tf-apply` | runs `tf-plan` then `terraform apply -auto-approve tfplan` |

Relevant variables (in `infra/aws/terraform/variables.tf`):
- `worker_reserved_concurrency` (default 5) — caps parallel SerpAPI calls
- `city_scan_cron_expression` (default `cron(0 9 ? * MON *)`) — weekly fan-out schedule
- `city_scan_max_markets` (default 200) — max markets per cron run

### Smoke tests + observability

| command | does |
|---|---|
| `make smoke` | Invokes the scheduler Lambda with `{"limit": 10}` and prints the response. Run after `tf-apply` to verify fan-out end-to-end. |
| `make logs` | Tails `/aws/lambda/aventi-$ENV-worker` logs (Ctrl-C to stop) |
| `make logs-api` | Tails `/aws/lambda/aventi-$ENV-api` logs (Ctrl-C to stop) |
| `make logs-scheduler` | Tails the scheduler Lambda's logs |
| `make scan-report` | Queries `ingest_runs` for the last hour: tier / scan_type / pages / candidates / dupes / exhausted / errors. Needs `$DATABASE_URL`. |

Live Lambda output commands (all functions):

```bash
make logs            # worker Lambda
make logs-api        # API Lambda
make logs-scheduler  # scheduler Lambda
```

### Cron management

| command | does |
|---|---|
| `make rule-status` | Shows whether the weekly EventBridge rule is `ENABLED` and its schedule |
| `make rule-disable` | Pauses the weekly cron (use during incidents or while debugging) |
| `make rule-enable` | Resumes the weekly cron |

### Rollback

```bash
make rollback-worker TAG=abc1234
```

Points the worker Lambda at a previous image tag without touching Terraform or SQS state. Useful for fast recovery from a bad deploy.

### Typical workflows

```bash
# First-time local setup after pulling main:
supabase start
make migrate

# Code-only redeploy to dev (after pushing a commit):
make deploy-quick

# Full dev deploy including DB schema changes:
make deploy

# Verify the cron fan-out worked:
make smoke
make scan-report    # confirm ingest_runs.metadata has heatTier/pages/etc.

# Incident response:
make rule-disable   # stop the bleeding
make rollback-worker TAG=<last-known-good>
make rule-enable    # resume once healthy
```
