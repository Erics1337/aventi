#!/usr/bin/env bash
set -euo pipefail

PROJECT="${PROJECT:-aventi}"
ENV="${ENV:-dev}"
AWS_REGION="${AWS_REGION:-us-east-1}"
case "$ENV" in
  prod|production) RUNTIME_ENV_NAME=production ;;
  dev|development) RUNTIME_ENV_NAME=development ;;
  staging) RUNTIME_ENV_NAME=staging ;;
  *) echo "Unknown deployment environment" >&2; exit 1 ;;
esac
RUNTIME_ENV_FILE="${RUNTIME_ENV_FILE:-services/backend/.env.${RUNTIME_ENV_NAME}}"
SECRET_NAME="${AVENTI_RUNTIME_SECRET_NAME:-${PROJECT}-${ENV}/backend/env}"

KEYS=(
  AVENTI_ENV
  AVENTI_BACKEND_LOG_LEVEL
  AVENTI_DATABASE_URL
  AVENTI_SUPABASE_URL
  AVENTI_SUPABASE_JWKS_URL
  AVENTI_SUPABASE_JWT_AUDIENCE
  AVENTI_SUPABASE_JWT_SECRET
  AVENTI_SUPABASE_ISSUER
  AVENTI_SUPABASE_SECRET_KEY
  AVENTI_SUPABASE_SERVICE_ROLE_KEY
  AVENTI_INTERNAL_API_KEY
  AVENTI_FREE_SWIPE_LIMIT
  AVENTI_FEED_VERIFICATION_MAX_AGE_HOURS
  AVENTI_FEED_UNVERIFIED_GRACE_HOURS
  AVENTI_AUTH_DEV_BYPASS
  AVENTI_ENABLE_VERIFICATION
  AVENTI_SEEN_EVENTS_WINDOW_DAYS
  GOOGLE_API_KEY
  SERPAPI_API_KEY
  POLLINATIONS_API_KEY
  AVENTI_CORS_ORIGINS
  AVENTI_REQUEST_LIMIT_PER_MINUTE
  AVENTI_PURCHASES_ENABLED
  AVENTI_PAID_DISCOVERY_ENABLED
  AVENTI_PROVIDER_DAILY_BUDGETS
  AVENTI_PROVIDER_MONTHLY_BUDGET_MICROUSD
  AVENTI_PROVIDER_MAX_COST_MICROUSD
  REVENUECAT_SECRET_KEY
  REVENUECAT_WEBHOOK_SECRET
  REVENUECAT_MONTHLY_PRODUCT_ID
  REVENUECAT_ANNUAL_PRODUCT_ID
  REVENUECAT_ENTITLEMENT_ID
  GOOGLE_GEOCODING_API_KEY
  GOOGLE_TIMEZONE_API_KEY
)

if [[ ! -f "$RUNTIME_ENV_FILE" ]]; then
  echo "Runtime env file not found: $RUNTIME_ENV_FILE" >&2
  exit 1
fi

if ! aws secretsmanager describe-secret \
  --secret-id "$SECRET_NAME" \
  --region "$AWS_REGION" >/dev/null 2>&1; then
  echo "Secret not found: $SECRET_NAME" >&2
  echo "Run 'make tf-apply' first so Terraform creates the secret placeholder." >&2
  exit 1
fi

tmp_json="$(mktemp)"
trap 'rm -f "$tmp_json"' EXIT

python3 - "$RUNTIME_ENV_FILE" "$tmp_json" "$RUNTIME_ENV_NAME" "${KEYS[@]}" <<'PY'
import ast
import json
import re
import sys
from pathlib import Path

env_file = Path(sys.argv[1])
output_file = Path(sys.argv[2])
expected_environment = sys.argv[3]
allowed_keys = sys.argv[4:]
wanted = set(allowed_keys)
env = {}

key_pattern = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")

for raw_line in env_file.read_text().splitlines():
    line = raw_line.strip()
    if not line or line.startswith("#"):
        continue
    if line.startswith("export "):
        line = line[len("export "):].strip()
    if "=" not in line:
        continue

    key, value = line.split("=", 1)
    key = key.strip()
    value = value.strip()
    if not key_pattern.match(key) or key not in wanted:
        continue

    if value and value[0] in {"'", '"'}:
        try:
            value = ast.literal_eval(value)
        except (SyntaxError, ValueError):
            value = value.strip("'\"")

    if value != "":
        env[key] = str(value)

missing = [key for key in allowed_keys if key not in env]
if missing:
    print("Skipping missing or empty keys: " + ", ".join(missing), file=sys.stderr)

configured_environment = {"prod": "production", "dev": "development"}.get(env.get("AVENTI_ENV"), env.get("AVENTI_ENV"))
if configured_environment != expected_environment:
    raise SystemExit("Runtime secret file AVENTI_ENV must explicitly match the selected deployment environment")
output_file.write_text(json.dumps(env, indent=2, sort_keys=True) + "\n")
PY

aws secretsmanager put-secret-value \
  --secret-id "$SECRET_NAME" \
  --secret-string "file://$tmp_json" \
  --region "$AWS_REGION" >/dev/null

echo "Synced $(python3 -c 'import json,sys; print(len(json.load(open(sys.argv[1]))))' "$tmp_json") keys to $SECRET_NAME"
