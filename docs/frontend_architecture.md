# Aventi Architecture (v1 scaffold)

## Runtime Components
- `apps/mobile`: Expo + NativeWind React Native client
- `services/backend`: FastAPI API and Python worker entrypoints
- `supabase`: Auth + Postgres + Storage (hosted)
- `infra/aws/terraform`: AWS deployment config with a near-zero-cost dev baseline

## Request Flow
1. Mobile authenticates with Supabase Auth.
2. Mobile sends Supabase bearer token to FastAPI.
3. FastAPI verifies JWT (JWKS verification scaffolded; dev bypass available for local work).
4. FastAPI serves feed, swipes, favorites, reports, and entitlements.
5. Worker processes SQS-backed ingest/verification tasks through Lambda, with a local polling worker available for LocalStack development.

## Personalization Split
- Server: candidate filtering and base ranking
- Client: in-session vibe state machine and deck reordering
- Server: persisted vibe weight updates after swipe submit

## Deployment Targets
- API, worker, and scheduler: AWS Lambda functions built from the backend container image
- Worker jobs: AWS SQS queue with Lambda event source mapping
- Scheduler: EventBridge rule invoking the scheduler Lambda
- Supabase remains hosted externally
