# Aventi Backend

FastAPI API and worker processes for Aventi.

## Run locally (after `uv sync`)

```bash
uv run --project services/backend python -m aventi_backend.main
uv run --project services/backend python -m aventi_backend.worker.main
```

## Manual ingest (real event files)

Import JSON, NDJSON, or CSV event rows directly into Supabase via the backend ingest service.

See the full guide: `/Users/ericswanson/code/gitHub/aventi/docs/manual-ingest-cli.md`

```bash
AVENTI_DATABASE_URL=postgresql+asyncpg://postgres:postgres@127.0.0.1:54332/postgres \
uv run --project services/backend aventi-manual-ingest ./events.json \
  --city Austin \
  --source-name manual:atx:seed-import
```

CSV supports common columns like `title`, `booking_url`, `starts_at`, `category`, `is_free`,
`vibes`, `tags`, and `venue_*` fields (for example `venue_name`, `venue_city`,
`venue_latitude`, `venue_longitude`).
