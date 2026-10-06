"""Validate release inputs; never print secret values or fabricate commercial terms."""
import json
import os
import sys
from urllib.parse import urlsplit

required=['AVENTI_PURCHASES_ENABLED','AVENTI_PAID_DISCOVERY_ENABLED','AVENTI_DATABASE_URL','AVENTI_SUPABASE_URL','AVENTI_SUPABASE_SECRET_KEY','EXPO_PUBLIC_WEB_URL','AVENTI_IOS_ASSOCIATED_APP_ID','AVENTI_ANDROID_PACKAGE','AVENTI_ANDROID_SHA256_FINGERPRINTS','DATABASE_URL','AVENTI_API_URL','AVENTI_INTERNAL_API_KEY','REVENUECAT_SECRET_KEY',
 'REVENUECAT_WEBHOOK_SECRET','REVENUECAT_MONTHLY_PRODUCT_ID','REVENUECAT_ANNUAL_PRODUCT_ID',
 'GOOGLE_GEOCODING_API_KEY','GOOGLE_TIMEZONE_API_KEY','GOOGLE_API_KEY','SERPAPI_API_KEY','POLLINATIONS_API_KEY',
 'AVENTI_PROVIDER_DAILY_BUDGETS','AVENTI_PROVIDER_MONTHLY_BUDGET_MICROUSD',
 'AVENTI_PROVIDER_MAX_COST_MICROUSD','AVENTI_CORS_ORIGINS','AVENTI_PRIVACY_URL','AVENTI_TERMS_URL',
 'AVENTI_SUPPORT_EMAIL','EXPO_PUBLIC_REVENUECAT_IOS_API_KEY','EXPO_PUBLIC_REVENUECAT_ANDROID_API_KEY',
 'NEXT_PUBLIC_IOS_APP_STORE_URL','NEXT_PUBLIC_PLAY_STORE_URL','TF_VAR_alert_emails','TF_VAR_cors_origins']
missing=[name for name in required if not os.environ.get(name)]
if missing:
    print('Release blocked: missing configuration names: '+', '.join(missing))
    sys.exit(1)
for name in ['AVENTI_API_URL','AVENTI_PRIVACY_URL','AVENTI_TERMS_URL','NEXT_PUBLIC_IOS_APP_STORE_URL','NEXT_PUBLIC_PLAY_STORE_URL']:
    if not os.environ[name].startswith('https://') or 'example.' in os.environ[name]:
        raise SystemExit(f'Release blocked: {name} must be an actual HTTPS URL')
for name in ['AVENTI_PURCHASES_ENABLED','AVENTI_PAID_DISCOVERY_ENABLED']:
    if os.environ[name].lower() not in {'true','false'}:
        raise SystemExit(f'Release blocked: {name} must be explicitly true or false')


def positive_integer_map(name):
    try:
        value = json.loads(os.environ[name])
    except (TypeError, json.JSONDecodeError) as exc:
        raise SystemExit(f'Release blocked: {name} must be a JSON object') from exc
    if not isinstance(value, dict) or any(
        not isinstance(provider, str)
        or not provider.strip()
        or type(limit) is not int
        or limit <= 0
        for provider, limit in value.items()
    ):
        raise SystemExit(
            f'Release blocked: {name} must map provider names to positive integers'
        )
    return {provider.strip().lower(): limit for provider, limit in value.items()}


try:
    monthly_budget_microusd = int(os.environ['AVENTI_PROVIDER_MONTHLY_BUDGET_MICROUSD'])
except ValueError as exc:
    raise SystemExit(
        'Release blocked: AVENTI_PROVIDER_MONTHLY_BUDGET_MICROUSD must be an integer'
    ) from exc
if not 1 <= monthly_budget_microusd <= 20_000_000:
    raise SystemExit(
        'Release blocked: AVENTI_PROVIDER_MONTHLY_BUDGET_MICROUSD must be between '
        '1 and 20000000 micro-USD ($20.00)'
    )

daily_budgets = positive_integer_map('AVENTI_PROVIDER_DAILY_BUDGETS')
max_costs = positive_integer_map('AVENTI_PROVIDER_MAX_COST_MICROUSD')
if os.environ['AVENTI_PAID_DISCOVERY_ENABLED'].lower() == 'true':
    required_providers = {'serpapi', 'gemini', 'geocoding', 'pollinations'}
    missing_daily = sorted(required_providers - daily_budgets.keys())
    missing_costs = sorted(required_providers - max_costs.keys())
    if missing_daily:
        raise SystemExit(
            'Release blocked: missing positive daily provider budgets for '
            + ', '.join(missing_daily)
        )
    if missing_costs:
        raise SystemExit(
            'Release blocked: missing verified maximum unit costs for '
            + ', '.join(missing_costs)
        )
    unaffordable = sorted(
        provider for provider in required_providers
        if max_costs[provider] > monthly_budget_microusd
    )
    if unaffordable:
        raise SystemExit(
            'Release blocked: one provider unit exceeds the monthly budget for '
            + ', '.join(unaffordable)
        )


def database_target(value):
    parsed = urlsplit(value.replace('postgresql+asyncpg://', 'postgresql://'))
    return (parsed.hostname, parsed.port or 5432, parsed.username, parsed.path)

if database_target(os.environ['DATABASE_URL']) != database_target(os.environ['AVENTI_DATABASE_URL']):
    raise SystemExit('Release blocked: migration and runtime database targets differ')

print('Required release inputs present. Store pricing, policies, physical-device and operational acceptance still require recorded evidence.')
