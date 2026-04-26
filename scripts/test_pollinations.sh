#!/usr/bin/env bash
# Force a Pollinations → Supabase Storage round-trip against an existing event.
# Usage: bash scripts/test_pollinations.sh
set -euo pipefail

set -a; . ./.env; set +a

ENCODED_PW=$(python3 -c "import urllib.parse, os; print(urllib.parse.quote(os.environ['SUPABASE_DB_PASSWORD'], safe=''))")
REMOTE_DB="postgresql://postgres.mkwvqzgngiclybvklorr:${ENCODED_PW}@aws-0-us-west-2.pooler.supabase.com:5432/postgres"
QUEUE="https://sqs.us-east-1.amazonaws.com/989438951744/aventi-dev-worker-jobs"

echo "--- picking + prepping a random Austin event ---"
EVENT_ID=$(psql "$REMOTE_DB" -tAc "
  update public.events
     set image_url = null,
         booking_url = 'https://example.invalid/no-og/' || id
   where id = (select id from public.events where city = 'Austin' order by random() limit 1)
   returning id;
" | tr -d ' ')
echo "Target event: $EVENT_ID"

echo "--- enqueuing GENERATE_IMAGE job on SQS ---"
BODY=$(jq -nc --arg eid "$EVENT_ID" '{
  format: "v1",
  job_id: ("manual-test-" + $eid),
  job_type: "GENERATE_IMAGE",
  payload: {eventId: $eid},
  attempts: 0,
  max_attempts: 3
}')
aws sqs send-message \
  --queue-url "$QUEUE" \
  --region us-east-1 \
  --message-body "$BODY" \
  --query 'MessageId' --output text

echo
echo "Waiting 60s for Pollinations + Supabase Storage upload..."
sleep 60

echo
echo "=== Event image status ==="
psql "$REMOTE_DB" -c "
  select substr(id::text, 1, 8) as id, image_url
    from public.events where id = '$EVENT_ID';
"
