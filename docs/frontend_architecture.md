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
5. Worker polls DB-backed job queue for ingest/verification tasks.

## Personalization Split
- Server: candidate filtering and base ranking
- Client: in-session vibe state machine and deck reordering
- Server: persisted vibe weight updates after swipe submit

## Deployment Targets
- API + worker: AWS ECS/Fargate task definitions managed in Terraform
- Optional ECS service for the API, disabled by default in dev
- Optional ALB for the API, disabled by default in dev
- Supabase remains hosted externally
