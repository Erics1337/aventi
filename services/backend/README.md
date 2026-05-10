# Aventi Backend

FastAPI API and worker processes for Aventi.

## Run locally (after `uv sync`)

```bash
uv run --project services/backend python -m aventi_backend.main
uv run --project services/backend python -m aventi_backend.worker.main
```

Configure `.env` from `.env.example`. Job enqueue and the worker both require a reachable **`SQS_WORKER_QUEUE_URL`** (LocalStack is typical for local dev). See repository **`docs/backend_architecture.md`** for queue and worker context.

## Manual ingest (real event files)

Import JSON, NDJSON, or CSV event rows directly into Postgres via the backend ingest service.

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

The backend uses a job-driven ingest pipeline. Discovery is **source-adapter based**
(JSON/RSS/SerpAPI/Gemini/mock), not a browser crawler.

### 1) Event entry points

Events can enter the system through:

- Internal API endpoints (require `x-aventi-internal-key`):
  - `POST /internal/jobs/enqueue`
  - `POST /internal/ingest/manual`
  - `POST /internal/verification/run`
- CLI ingest:
  - `uv run --project services/backend aventi-manual-ingest ...`

### 2) Job processing and discovery

**Enqueue:** `JobQueueRepository.enqueue_job` sends a JSON message to **AWS SQS** (`SQS_WORKER_QUEUE_URL` via Boto3). Local development often uses LocalStack; the worker can auto-create the queue in dev if it is missing.

**Worker:** Long-polls SQS (`receive_message`), runs `process_job` in `worker/handlers.py`, and **deletes the message on success**. On failure, the message becomes visible again after the visibility timeout (SQS redelivery).

**Job types:**

| Type | Role |
|------|------|
| `MARKET_WARMUP` | Warmup orchestration for a market (structured sources + optional SerpAPI discovery scans). |
| `MARKET_SCAN` | Run `execute_market_scan`: discover candidates for a city/market, then `ManualIngestService.ingest_manual`. |
| `VERIFY_EVENT` | Verify one event (booking URL, etc.). |
| `ENRICH_EVENT` | Enrich description-derived metadata via Gemini when payload qualifies. |
| `GENERATE_IMAGE` | Build a Pollinations image URL, download the rendered image, upload to **Supabase Storage** (`event-images`), update `events.image_url`. |

For **`MARKET_SCAN`**, scraper selection is payload-driven (`build_market_scan_scraper`):

- `sourceType=json` (aliases: `structured-json`, `json-feed`): structured JSON
- `sourceType=rss` (aliases: `rss-feed`): RSS
- `sourceType=serpapi` or `google-events`: **SerpApi** Google Events API (`SerpApiEventScraper`; requires `SERPAPI_API_KEY`)
- `sourceType=gemini` or `ai`: Gemini-backed scraper
- Default: **`mock`** (deterministic test candidates)

Each discovery candidate is normalized to a manual ingest payload with defaults
(for example fallback category, fallback venue, fallback times), then sent through
the same ingest service as CLI/manual ingest. Ingest may enqueue **`GENERATE_IMAGE`**
when `should_generate_main_image` applies (for example replaceable SerpAPI thumbnails).

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

`VERIFY_EVENT` behavior depends on configured providers; the codebase includes patterns such as **`MockVerifier`** (e.g. treat `https://` booking URLs as active). Writes verification runs and can hide inactive events.

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
   - exclude saved event IDs
   - exclude saved normalized titles
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
