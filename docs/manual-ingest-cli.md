# Aventi Manual Ingest CLI

Imports event rows from `JSON`, `NDJSON/JSONL`, or `CSV` into the backend ingest pipeline and writes normalized data to Supabase Postgres.

## Quick Start

From `/Users/ericswanson/code/gitHub/aventi`:

```bash
AVENTI_DATABASE_URL=postgresql+asyncpg://postgres:postgres@127.0.0.1:54332/postgres \
pnpm backend:ingest -- ./events.csv --city Austin --source-name manual:atx:first-batch
```

## What It Does

- loads rows from a file
- normalizes fields into manual-ingest payloads
- upserts `venues`, `events`, `event_occurrences`, `event_tags`
- records `ingest_sources` and `ingest_runs`
- enqueues `VERIFY_EVENT` jobs by default

## CLI Arguments

- `file` (required): input file path
- `--city` (required): default city used in normalization/ingest run
- `--source-name` (required): source identifier (upserted in `ingest_sources`)
- `--format` (optional): `auto` (default), `json`, `ndjson`, `csv`
- `--enqueue-verification` / `--no-enqueue-verification` (optional): default is enabled

## Supported Input Formats

## JSON

Accepted:
- array of event objects
- single event object
- object with `events` array

## NDJSON / JSONL

Each line must be a JSON object.

## CSV

Common supported columns:
- `title`
- `description`
- `category`
- `booking_url` -> `bookingUrl`
- `starts_at` / `ends_at` -> `startsAt` / `endsAt`
- `image_url`
- `price_label`
- `is_free` / `isFree` (boolean)
- `vibes` (comma or `|` separated)
- `tags` (comma or `|` separated)
- `metadata` (JSON object string)
- `venueMetadata` / `venue_metadata` (JSON object string)
- `venue_*` or `venue.*` fields (for example `venue_name`, `venue_city`, `venue_latitude`)

Example CSV:

```csv
title,booking_url,starts_at,category,is_free,vibes,tags,venue_name,venue_city,venue_state,venue_latitude,venue_longitude
Rooftop Set,https://example.com/rooftop,2026-03-01T03:00:00Z,nightlife,true,social|energetic,late-night|dj,Skylight,Austin,TX,30.2672,-97.7431
```

## Required Fields and Defaults

Required after normalization:
- `title`
- `bookingUrl`

Defaults (if omitted):
- `startsAt`: `now + 6h` (UTC)
- `timezone`: `UTC`
- `category`: `experiences`
- `country`: `US`
- `venue.name`: `<city> Spotlight`

## Idempotency / Dedupe

- `events` upsert by `booking_url`
- `event_occurrences` upsert by `(event_id, starts_at)`
- `event_tags` upsert by `(event_id, tag, tag_type)`

Re-importing the same event URL updates the event instead of creating a duplicate.

## Output (Success)

The CLI prints JSON like:

```json
{
  "ok": true,
  "source": "manual:atx:first-batch",
  "city": "Austin",
  "discovered": 12,
  "insertedEvents": 10,
  "updatedEvents": 2,
  "insertedOccurrences": 12,
  "verificationJobsEnqueued": 12
}
```

## Troubleshooting

- `AVENTI_DATABASE_URL is not configured`: set the env var before running the CLI.
- `Input file not found`: check the path (especially when running from repo root).
- `No events found`: file is empty, malformed, or contains only headers/blank rows.
- `Expected JSON object for metadata field`: CSV `metadata` fields must contain a JSON object string.

## Help

```bash
cd /Users/ericswanson/code/gitHub/aventi/services/backend
uv run aventi-manual-ingest --help
```

