#!/usr/bin/env bash
set -euo pipefail

# Enqueue GENERATE_IMAGE jobs for events that still appear to be using
# replaceable discovery images (for example SerpAPI thumbnails).
#
# Usage examples:
#   DRY_RUN=true LIMIT=25 bash scripts/backfill_event_images.sh
#   LIMIT=100 CITY=Austin bash scripts/backfill_event_images.sh
#
# Required env:
#   AVENTI_DATABASE_URL or DATABASE_URL
#   SQS_WORKER_QUEUE_URL
# Optional env:
#   CITY
#   LIMIT (default: 50)
#   DRY_RUN (default: false)
#   AWS_REGION (default: us-east-1)

if [[ -f ./.env ]]; then
  set -a
  # shellcheck disable=SC1091
  . ./.env
  set +a
fi

DB_URL="${AVENTI_DATABASE_URL:-${DATABASE_URL:-}}"
QUEUE_URL="${SQS_WORKER_QUEUE_URL:-}"
CITY_FILTER="${CITY:-}"
LIMIT="${LIMIT:-50}"
DRY_RUN="${DRY_RUN:-false}"
AWS_REGION="${AWS_REGION:-us-east-1}"

if [[ -z "$DB_URL" ]]; then
  echo "Missing AVENTI_DATABASE_URL or DATABASE_URL" >&2
  exit 1
fi

if [[ -z "$QUEUE_URL" ]]; then
  echo "Missing SQS_WORKER_QUEUE_URL" >&2
  exit 1
fi

CITY_SQL=""
if [[ -n "$CITY_FILTER" ]]; then
  CITY_SQL="and e.city = '$CITY_FILTER'"
fi

EVENT_IDS=()
while IFS= read -r event_id; do
  [[ -n "$event_id" ]] || continue
  EVENT_IDS+=("$event_id")
done < <(
  psql "$DB_URL" -Atc "
    select e.id::text
    from public.events e
    left join public.venues v on v.id = e.venue_id
    where e.hidden = false
      and coalesce(e.metadata->>'imageSource', '') not in ('opengraph', 'supabase_storage')
      and (
        e.image_url is null
        or coalesce(e.metadata->>'imageSource', '') = 'pollinations'
        or coalesce(e.metadata->>'sourceType', '') in ('serpapi', 'google-events')
        or coalesce(e.metadata->>'imageSource', '') in ('serpapi', 'google-events')
        or e.image_url ilike '%thumbnail%'
        or e.image_url ilike '%thumb%'
        or e.image_url ilike '%eventbrite%'
        or e.image_url ilike '%fbcdn.net%'
      )
      ${CITY_SQL/e.city/v.city}
    order by e.updated_at desc
    limit ${LIMIT};
  "
)

echo "Selected ${#EVENT_IDS[@]} event(s) for image backfill"

if [[ "${#EVENT_IDS[@]}" -eq 0 ]]; then
  exit 0
fi

for event_id in "${EVENT_IDS[@]}"; do
  if [[ "$DRY_RUN" == "true" ]]; then
    echo "DRY_RUN: would enqueue GENERATE_IMAGE for ${event_id}"
    continue
  fi

  body=$(jq -nc --arg eid "$event_id" '{
    format: "v1",
    job_id: ("backfill-image-" + $eid),
    job_type: "GENERATE_IMAGE",
    payload: {eventId: $eid},
    attempts: 0,
    max_attempts: 3
  }')

  aws sqs send-message \
    --queue-url "$QUEUE_URL" \
    --region "$AWS_REGION" \
    --message-body "$body" \
    --query 'MessageId' \
    --output text >/dev/null

  echo "Enqueued GENERATE_IMAGE for ${event_id}"
done
