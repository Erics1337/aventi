# Aventi API (v1 scaffold)

## Public endpoints
- `GET /v1/health`
- `POST /v1/me/bootstrap`
- `GET /v1/me`
- `PUT /v1/me/preferences`
- `GET /v1/feed`
- `POST /v1/swipes`
- `GET /v1/favorites`
- `PUT /v1/favorites/{event_id}`
- `DELETE /v1/favorites/{event_id}`
- `POST /v1/events/{event_id}/report`
- `GET /v1/membership/entitlements`

## Internal endpoints (require `x-aventi-internal-key`)
- `POST /internal/jobs/enqueue`
- `POST /internal/ingest/manual`
- `POST /internal/verification/run`

## Notes
- Current scaffold returns seeded feed data and in-memory favorites/swipe counters.
- Replace in-memory stores with Supabase Postgres-backed repositories in the next implementation pass.
