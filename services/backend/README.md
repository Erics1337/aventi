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

## Event Discovery and Feed Algorithm (Current Implementation)

The backend uses a job-driven ingest pipeline. Today this is source-adapter based
(`json`, `rss`, `mock`) rather than a full browser/LLM crawler.

### 1) Event entry points

Events can enter the system through:

- Internal API endpoints (require `x-aventi-internal-key`):
  - `POST /internal/jobs/enqueue`
  - `POST /internal/ingest/manual`
  - `POST /internal/verification/run`
- CLI ingest:
  - `uv run --project services/backend aventi-manual-ingest ...`

### 2) Job processing and discovery

The worker continuously:

1. Claims due jobs from `job_queue` with row locking (`FOR UPDATE SKIP LOCKED`).
2. Marks jobs `running` and writes `job_runs`.
3. Processes by type:
   - `CITY_SCAN`: discover candidates and ingest them.
   - `VERIFY_EVENT`: verify one event.
   - `ENRICH_EVENT` / `GENERATE_IMAGE`: currently stubbed (`skipped`).
4. Marks complete, or marks failed with retry backoff until `max_attempts`.

For `CITY_SCAN`, source selection is payload-driven:

- `sourceType=json` (or aliases): pulls structured JSON
- `sourceType=rss` (or aliases): pulls/parses RSS
- default: `mock`

Each discovery candidate is normalized to a manual ingest payload with defaults
(for example fallback category, fallback venue, fallback times), then sent through
the same ingest service as CLI/manual ingest.

### 3) Ingest normalization + dedupe

`ManualIngestService` writes normalized data and run metrics:

- Upserts `ingest_sources` and records `ingest_runs`.
- Upserts venue, event, occurrence, and tags.
- Dedupe semantics:
  - events by `booking_url` (upsert conflict key)
  - occurrences by `(event_id, starts_at)`
  - tags by `(event_id, tag, tag_type)`

After ingest, verification jobs are typically enqueued for the affected event IDs.

### 4) Verification stage

`VERIFY_EVENT` currently uses `MockVerifier`:

- Event is considered active if `booking_url` starts with `https://`.
- Writes a row to `verification_runs`.
- If inactive, marks event `hidden=true`.

### 5) Feed assembly for users

`GET /v1/feed` returns the ranked page for a user and filter set.

Pipeline:

1. Select upcoming occurrence per event (`event_occurrences`) in requested date
   window and join latest verification data.
2. Apply hard filters:
   - event must not be hidden
   - optional `price` filter (`free`/`paid`)
   - verification freshness rules (max verification age and unverified grace window)
   - optional `radiusMiles` and `timeOfDay`
3. Apply per-user dedupe:
   - exclude recently passed event IDs
   - exclude recently passed normalized titles
4. Score each candidate:
   - `affinity = sum(user_vibe_weights[vibe] or 1.0)`
   - plus a small freshness tie-break favoring earlier events
5. Sort by score desc, paginate via offset cursor, and return:
   - `items`
   - `nextCursor`
   - `remainingFreeSwipes` / `remainingFreePreferenceActions`

### 6) Personalization feedback loop

`POST /v1/swipes` updates both behavior and ranking state:

- Inserts into `swipe_actions`.
- Updates `user_vibe_weights`:
  - `like`: `current * LIKE_MULTIPLIER + LIKE_BONUS`
  - `pass`: `current * PASS_MULTIPLIER`

`POST /v1/feed/impressions` records served events and filter context for analytics.

### 7) Local fallback behavior

If `AVENTI_DATABASE_URL` is not configured, repository deps fall back to an
in-memory implementation with seeded events. This keeps mobile/API flows working
for local scaffold development without Postgres.
