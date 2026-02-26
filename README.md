# Aventi

Aventi is a premium, swipe-first discovery app for local events, nightlife, and experiences.

This repository is a Turborepo monorepo containing:

- `apps/mobile` (Expo + NativeWind mobile app)
- `services/backend` (FastAPI API + worker)
- `packages/*` shared contracts/client/design tokens
- `supabase` schema and seed data
- `infra/aws/terraform` infrastructure scaffolding for ECS/Fargate

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

Start the mobile app and any JS/TS tasks via Turborepo:

```bash
pnpm dev
```

In separate terminals, start the backend API and worker:

```bash
uv run --project services/backend python -m aventi_backend.main
uv run --project services/backend python -m aventi_backend.worker.main
```

## Useful run commands

```bash
# Sync backend deps
pnpm backend:sync

# Start backend
pnpm backend:dev

# Start worker
pnpm backend:worker

# Import events from JSON/CSV/NDJSON into Supabase
pnpm backend:ingest -- ./events.csv --city Austin --source-name manual:atx:first-batch

# Reset local Supabase DB
supabase db reset

# Start mobile
pnpm --filter @aventi/mobile dev
```

Manual ingest CLI docs: `/Users/ericswanson/code/gitHub/aventi/docs/manual-ingest-cli.md`
