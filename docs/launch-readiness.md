# Public mobile release

Aventi targets iOS and Android in the United States. Free accounts have 10 preference actions per UTC day and a 10-mile radius. Premium supports unlimited actions, configurable radius, source-supported admission filters, travel dates, and grounded event insights. Monthly/annual prices are owned by the store product configuration, not application source.

## Local verification

No development server is started by the verification commands.

```sh
pnpm install --frozen-lockfile
uv sync --project services/backend --extra dev --frozen
pnpm exec turbo run typecheck lint test --filter='!@aventi/backend'
uv run --project services/backend ruff check services/backend/src services/backend/tests
uv run --project services/backend mypy --config-file services/backend/pyproject.toml services/backend/src
AVENTI_ENV=test uv run --project services/backend pytest services/backend/tests
pnpm --filter @aventi/web build
pnpm --filter @aventi/mobile exec expo export --platform ios
pnpm --filter @aventi/mobile exec expo export --platform android
terraform -chdir=infra/aws/terraform init -backend=false -lockfile=readonly
terraform -chdir=infra/aws/terraform validate
```

Public HTTPS Supabase/API configuration is required for bundle builds. Placeholder public configuration only proves compilation; it does not validate a live deployment. Native purchases require a development/store build; Expo Go is not acceptance evidence.

Database integration tests require `AVENTI_TEST_DATABASE_URL` pointing to a disposable migrated Postgres/PostGIS database. Do not point tests at a real application database. CI creates the managed-schema fixture in `services/backend/tests/database_bootstrap.sql` and applies all migrations; the fixture must never be applied to hosted Supabase. It approximates Supabase-managed schemas and is not a substitute for checking hosted grants and Auth/Storage behavior.

## Implementation verification record (2026-09-26)

- Backend: 83 tests pass against a disposable Postgres/PostGIS database, including database grants/RLS, atomic actions, feed sessions, budgets, billing, deletion concurrency and job recovery. Ruff passes; mypy passes for 48 source files.
- Frontend: TypeScript, lint and package checks pass; 15 mobile, 4 API-client and 1 web tests pass. The web production build and native bundle exports pass with test public configuration.
- All forward migrations through `0014_monthly_provider_budget.sql` applied successfully. The Android native configuration introspection check confirms the purchase-compatible activity mode.
- Terraform validation/format checks and frozen dependency installs pass. None of these checks deploys resources or substitutes for the unchecked release gates below.

## Required configuration

Backend production requires database and Supabase credentials, an internal API key, and explicit HTTPS CORS origins. Authentication bypass is prohibited. `AVENTI_PURCHASES_ENABLED` and `AVENTI_PAID_DISCOVERY_ENABLED` independently control new purchases and paid discovery. Start with both disabled while configuring staging.

- RevenueCat: secret API key, webhook authorization secret, monthly and annual product IDs, and entitlement ID `premium`. Map both products to this entitlement. Set restore/transfer behavior to retain the original app user ID; never automatically transfer between Aventi accounts. Configure the webhook at `/v1/membership/webhooks/revenuecat` and its Authorization value to match the backend secret. Mobile uses separate public SDK keys for Apple and Google.
- Geocoding: separate Google Geocoding and Time Zone API keys with appropriate API restrictions. These are not the Gemini key.
- Provider budgets: paid processing stays disabled until `AVENTI_PROVIDER_DAILY_BUDGETS` and `AVENTI_PROVIDER_MAX_COST_MICROUSD` contain verified positive integers for `serpapi`, `gemini`, `geocoding`, and `pollinations`. Daily values cap provider reservation units. Each unit also reserves its configured conservative maximum cost from one aggregate UTC calendar-month ledger shared by discovery, verification, maps, images, and AI. `AVENTI_PROVIDER_MONTHLY_BUDGET_MICROUSD` defaults to and can never exceed `20000000` micro-USD ($20.00). Reservations remain consumed when external requests fail. Daily unit caps reset at 00:00 UTC each day; the monetary cap resets at 00:00 UTC on the first day of each month.
- Web: real store listing URLs, `AVENTI_PRIVACY_URL`, `AVENTI_TERMS_URL`, and `AVENTI_SUPPORT_EMAIL`. Approved policy content is served directly by the web app at the configured HTTPS origin.
- Mobile links: configure the actual web domain/redirect URLs with Supabase and native association files. Do not use a guessed domain or unverified deep link association.
- AWS: `TF_VAR_cors_origins` and `TF_VAR_alert_emails`; recipients must confirm SNS subscriptions. Use isolated staging and production Supabase projects/secrets.

`scripts/release_check.py` checks required configuration names without printing values. Presence checks do not certify prices, legal text, store permissions, or native credentials.

## Deployment and operations

`make deploy ENV=staging` validates configuration, migrates the remote database identified by `DATABASE_URL`, builds/pushes a Git-tagged image, applies Terraform for the selected environment, synchronizes the explicitly matching environment secret file, recycles API/worker/scheduler environments, and runs `scripts/smoke.py`. The smoke test requires `AVENTI_API_URL` and the internal key, and checks API health plus actual `HEALTH_CHECK` job completion through the outbox and SQS worker. It does not spend discovery credits.

The minute maintenance schedule dispatches committed outbox entries and performs bounded housekeeping. The weekly schedule discovers active markets. SQS uses partial-batch failure reporting and a dead-letter queue. Monitor queue age, dead letters, provider/budget failures, API errors, and subscription synchronization.

When paid processing pauses, existing eligible inventory remains available. Do not bypass configured caps through manual refreshes. Investigate dead jobs and reconcile their state before replay; automatic retries must retain idempotency and lease ownership.

Roll back application image tags using the API and worker rollback targets. Database migrations are forward-only: restore into an isolated database to prove recovery, and use a corrective migration for production. Never run `migrate-reset` against production.

## Public launch acceptance record

These require real accounts/devices/configuration and must be recorded before submission:

- [ ] Production configuration, approved policy content, support contact, store prices and receipt-transfer behavior reviewed.
- [ ] Hosted Supabase anonymous/authenticated grants checked; domain mutations and event-image uploads rejected directly.
- [ ] Guest conversion, confirmation, recovery, logout/account switch, and resumable deletion tested through Supabase.
- [ ] Apple and Google sandbox purchase, pending/cancelled purchase, restore, renewal, expiry, refund and grace scenarios passed.
- [ ] Physical iOS and Android journeys completed, including VoiceOver/TalkBack, text scaling, reduced motion, denied permissions and interrupted networks.
- [ ] Destination dates and DST boundaries verified across US timezones; low-inventory/cold locations show truthful states.
- [ ] Fifty concurrent cached-feed users: p95 under two seconds, less than 1% server errors on staging infrastructure.
- [ ] At least 100 events across five US markets manually audited; at least 95% accurate title, venue, date and booking destination.
- [ ] Worker retry/dead-letter path and paused-provider behavior exercised on actual AWS resources.
- [ ] Backup restored into isolation; API and worker rollback rehearsed.
- [ ] Signed builds, screenshots, privacy/data disclosures, reviewer account and review notes supplied to both stores.

Store submission and public rollout are separate release actions. A green local test run is not public-launch approval.

Verified links are served by the web app at `/.well-known/apple-app-site-association`
and `/.well-known/assetlinks.json`. Configure `AVENTI_IOS_ASSOCIATED_APP_ID`
(Apple team ID plus bundle ID), `AVENTI_ANDROID_PACKAGE`, and comma-separated
`AVENTI_ANDROID_SHA256_FINGERPRINTS` using the actual store signing certificates.
Missing configuration returns 503, not a placeholder association. Set the same
HTTPS origin in `EXPO_PUBLIC_WEB_URL` and Supabase redirect allowlists.

Runtime secret sync selects `services/backend/.env.staging`, `.env.production`, or `.env.development` from `ENV`. The file must declare the matching `AVENTI_ENV`; mismatches fail closed. A custom `RUNTIME_ENV_FILE` still requires the matching declaration. Runtime secrets are synchronized after infrastructure exists, then all three Lambda configurations receive a fresh revision to avoid stale warm-container settings.

Cold-market discovery admission is bounded to six new warmup requests per account and thirty per source IP per UTC day, in addition to the shared market cooldown and provider caps. Cached browsing is unaffected. Activity pings only touch existing profile-matching markets and never create jobs.

The staging load harness is `uv run --project services/backend python scripts/loadtest.py`.
It requires `AVENTI_STAGING_API_URL` and `AVENTI_LOAD_TEST_ACCOUNTS`, a JSON array of
50 distinct staging-only `{userId, token, latitude, longitude}` accounts with
populated cached feeds. It makes four waves of 50 requests, prints aggregate timing
only, and fails the stated latency/error gate. Keep credentials out of source control.
Use the store handoff draft in [store-release.md](store-release.md) for listing copy,
reviewer steps and owner-supplied assets/disclosures.

Device coordinates are client reported, not proof of physical presence. Explicit travel destinations and premium filters are authorized by the API; deliberate GPS spoofing remains a trust assumption. Per-account/IP warmup limits and provider budgets bound discovery abuse.

Android prebuild sets the purchase activity to `singleTop` to preserve external bank-verification flows, as required by [RevenueCat Android installation guidance](https://www.revenuecat.com/docs/getting-started/installation/android). Verify interrupted purchases on physical devices before release.

Current external billing setup and the delegated initial pricing decision are recorded in [revenuecat-setup.md](revenuecat-setup.md). Test Store configuration is not completion of the real-store billing gate.

## Owner budget and Pollinations follow-up verification (2026-09-27 UTC)

The owner capped combined provider spend at $20/month and requested Pollinations. Migration `0014` adds the shared UTC-calendar-month reservation ledger. Paid processing remains disabled pending deployment, verified conservative cost bounds, and provider-level budget configuration. Current Pollinations insight and image clients use authenticated fixed-model requests with bounded inputs/responses, no HTTP generation retries, and no generation-URL fallback. The existing provider key was validated read-only; no paid generation was exercised.

After these changes: backend tests **83 passed, 20 skipped**, Ruff passed, mypy passed across **49 source files**, and `git diff --check` passed. The skipped tests require a disposable migrated PostgreSQL/PostGIS database; the new cross-provider concurrency test has not run. A new independent reviewer could not be spawned because the session's agent-thread limit was reached. The earlier launch review predates this monetary-budget/Pollinations delta and does not cover it. Obtain a fresh read-only review and run all database tests before accepting this delta for deployment.

The owner does not own `aventi.app`; that marketing URL was removed from the Apple draft. The selected Aventi web origin is the existing stock Vercel domain `https://aventi-web.vercel.app`; no custom DNS is required. Apple release mode is now manual. Apple subscriptions are drafts at $7.99/month and $49.99/year and are mapped into RevenueCat; Google requires a billing-capable build before subscription creation. Both native RevenueCat public SDK keys are configured in Expo. See `revenuecat-setup.md` for remaining store setup items.

## Owner approval and hosting check (2026-09-28)

The owner accepted Apple's updated developer agreement. App Store Connect now shows both the Free Apps and Paid Apps agreements as Active. The owner selected Aventi's stock Vercel domain for its own privacy, terms, support, and account-deletion pages. PR #14 merged on 2026-09-29 and the Vercel production deployment succeeded. The live privacy, terms, support, deletion, and download routes returned 200; feed and saved routes redirected to download. The Apple draft's support, privacy, and user privacy choices URLs were updated and read back from App Store Connect. Its app privacy data questionnaire has not been completed.

The signed-in Vercel team contains `crestcodecreative.com`, and Route 53 hosted zone `Z064752935D7KBXD6DB54` is authoritative for that unrelated domain. Aventi uses `aventi-web.vercel.app`. The owner confirmed `admin@crestcodecreative.com` as the Aventi support email. The Aventi Vercel project's Production `AVENTI_PRIVACY_URL` and `AVENTI_TERMS_URL` point to the stock-domain paths; `AVENTI_SUPPORT_EMAIL` is set. The direct policy pages do not depend on redirect variables.

Google Play's Aventi draft is in Crest Code developer account `7404641502830463153`. Its store contact email was updated to `admin@crestcodecreative.com` and website to `https://aventi-web.vercel.app/support`; both values were read back after reloading the store settings page. The app remains a draft, and the Play privacy/deletion disclosures have not been completed.

## Fresh CI database verification (2026-09-29 UTC)

PR #15 contains the remaining launch implementation and is undergoing review. CI applied every forward migration to disposable PostgreSQL 17/PostGIS with a Supabase-schema fixture. Backend verification passed **103 tests**, including provider-budget concurrency and feed/job/database integration; Ruff and mypy passed. Frontend typecheck, lint, tests, and web/iOS/Android bundle builds passed. Terraform initialization, validation, and format checks passed with checksums for both Linux and macOS. These checks do not verify deployed Supabase grants, store billing, AWS worker delivery, or the device and operational acceptance list above.
