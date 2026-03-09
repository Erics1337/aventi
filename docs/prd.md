# Aventi PRD and Implementation Plan

## Product Requirements Document (PRD)

### 1. Product Overview

**Aventi** is a highly immersive, Tinder-style discovery application for local events, nightlife, and experiences. It transforms the overwhelming process of finding something to do into an engaging, personalized swiping experience. By blending AI-driven event aggregation with a premium "dark luxury" aesthetic, Aventi curates the heartbeat of a city directly into the user's hands.

### 2. Core Mechanics and Features

#### 2.1 The Swiping Feed (Discovery)
- Users see a stack of full-screen, visually striking event cards.
- Swipe right or tap Heart to save to Favorites.
- Swipe left or tap X to pass and tune local preferences.
- Free users get 10 swipes per day.
- Users can review previously seen events within the same session.

#### 2.2 User Preferences and Personalization
- Users select categories (Nightlife, Wellness, Concerts, etc.).
- The app learns a taste profile (vibes like Chill, Energetic, Romantic).
- Client-side "vibe state machine" updates weights based on swipes.
- `useEventFeed` reorders remaining cards by affinity score.
- Filters include date, time of day, price, and radius.

#### 2.3 Premium Tier ("Unlimited Member")
- Unlimited swipes
- Advanced curation (age restrictions, deeper filtering)
- Travel mode (browse future destination cities)
- AI-generated match rationales, insider tips, and pairings

### 3. Event Sourcing and Feed Curation Engine

#### 3.1 Background City Aggregation ("The Scraper")
- Background service continuously scans cities in time segments.
- Search-grounded AI discovers real events with verifiable booking URLs.
- Anti-hallucination constraints reject generic aggregator pages.
- AI enriches missing metadata (vibes, dress code, crowd age, genre).

#### 3.2 On-Demand Personalized Discovery
- Live fallback search when the database lacks fresh matches.
- Multiple parallel AI agents with different search angles.
- Exclusions use prior rejected/mapped events to avoid duplicates.

#### 3.3 Visual Generation
- Missing event posters can be filled with AI-generated 9:16 cinematic imagery.

### 4. UI/UX and Aesthetic Guidelines

#### 4.1 Base Theming
- Pure black canvas (`#000000`)
- Glassmorphism panels, blur, translucent borders
- Bold uppercase headers with tight tracking

#### 4.2 Color System ("Gradient Glow")
- Nightlife: Violet to Indigo
- Dining: Orange to Red
- Concerts: Fuchsia to Rose
- Wellness: Teal to Cyan

#### 4.3 Components and Micro-interactions
- Full-bleed 9:16 cards with bottom text over steep black gradient
- Floating circular action buttons with shrink-on-tap
- Category-specific loading animations/placeholders

### 5. Security and Trust
- GPS location required to initialize feed
- Report flow hides invalid/nonexistent events after 3 unique reports
- Periodic event re-verification before display

## Aventi v1 Architecture and Bootstrap Plan

### Summary

Build **Aventi** as a **single Turborepo monorepo** in `/Users/ericswanson/code/gitHub/aventi` with:
- `Expo + NativeWind` mobile app
- `FastAPI` backend (API + worker entrypoints)
- `Supabase` for Auth + Postgres + Storage
- `AWS ECS/Fargate` for API/worker deployment
- Product-first MVP (seeded/manual events first), with scraper/LLM/image systems scaffolded as v1 stubs

This keeps mobile, API, Supabase schema, and shared contracts in sync while preserving deploy/runtime separation. Python is not a reason to split repos.

### Naming (Locked)
- App display name: `Aventi`
- Workspace package names: `@aventi/...`
- Env prefixes: `AVENTI_*`

### Repo Strategy Decision

Use **monorepo + Turborepo** now.

Why:
- Atomic changes across mobile, API, and shared contracts
- One place for Supabase migrations/seed data
- Easier onboarding and local dev
- Faster iteration on swipe UX + ranking logic

Split later only if:
- Team boundaries / permissions require separation
- Independent release cadences create CI friction
- Compliance/security boundaries require separate repos

### Planned Monorepo Layout

```text
/Users/ericswanson/code/gitHub/aventi/
  apps/
    mobile/                         # Expo app (Aventi)
  services/
    backend/                        # FastAPI API + worker (Python/uv)
  packages/
    contracts/                      # Shared TS contracts / schemas / constants
    api-client/                     # Typed mobile client for FastAPI
    design-tokens/                  # Tailwind + theme tokens
  supabase/
    migrations/                     # SQL schema + RLS + indexes
    seed/                           # Seed data/scripts
    config.toml
  infra/
    aws/
      terraform/                    # ECS/ECR/ALB/EventBridge/IAM/Secrets
  docs/
    architecture.md
    api.md
  turbo.json
  pnpm-workspace.yaml
  package.json
  .gitignore
  .editorconfig
  .env.example
```

### Technology Stack (Locked)

#### Mobile (React Native)
- Expo
- Expo Router
- NativeWind
- React Native Reanimated
- React Native Gesture Handler
- Expo Blur / Expo Linear Gradient
- TanStack Query
- Zustand
- Zod
- Supabase JS (auth/session)
- Expo Location

#### Backend (Python)
- FastAPI
- Pydantic v2
- SQLAlchemy 2.x async
- Postgres driver (`asyncpg` or `psycopg`)
- `uv`
- `pytest`

#### Data / Auth / Storage
- Supabase Auth
- Supabase Postgres
- Supabase Storage

#### Jobs / Scheduling (v1)
- DB-backed job queue in Supabase Postgres
- Worker polling with `FOR UPDATE SKIP LOCKED`
- EventBridge schedules triggering ECS tasks

#### Infra / Deploy (v1)
- AWS ECR
- AWS ECS Fargate (API + worker)
- ALB for API
- CloudWatch Logs
- EventBridge Scheduler/Rules
- Secrets Manager or SSM Parameter Store
- Terraform

### Architecture (Decision-Complete)
- Mobile authenticates with Supabase Auth and stores session.
- Mobile calls FastAPI with Supabase JWT bearer token.
- FastAPI validates Supabase JWT (JWKS verification scaffolded; dev bypass allowed locally).
- FastAPI reads/writes domain data in Supabase Postgres using server credentials.
- `GET /v1/feed` applies filters and server-side ranking.
- Client `useEventFeed` applies local vibe-weight reordering for responsiveness.
- Client posts swipes/favorites/reports to FastAPI.
- Backend persists swipes and updates server-side vibe weights with same formula as client.
- Worker processes ingestion/verification/enrichment/image jobs from DB queue.
- Premium entitlements are server-authoritative.
- Stripe is deferred; premium is stubbed in v1.

### Public APIs / Interfaces / Types

#### FastAPI Public Endpoints (v1)
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

#### Private/Internal Endpoints (v1)
- `POST /internal/jobs/enqueue`
- `POST /internal/ingest/manual`
- `POST /internal/verification/run`

#### Shared Contracts
- `EventCard`
- `EventVibeTag`
- `FeedFilters`
- `FeedRequest`
- `FeedResponse`
- `SwipeAction`
- `SwipePayload`
- `UserPreferences`
- `VibeWeightMap`
- `MembershipEntitlements`
- `ReportReason`

#### Shared Ranking Constants
- `BASELINE_WEIGHT = 1.0`
- `LIKE_MULTIPLIER = 1.1`
- `LIKE_BONUS = 0.1`
- `PASS_MULTIPLIER = 0.95`
- Free swipe limit per day = `10`

### Supabase Schema Plan (v1)

Tables:
- `profiles`
- `user_preferences`
- `user_vibe_weights`
- `venues`
- `events`
- `event_occurrences`
- `event_tags`
- `swipe_actions`
- `favorites`
- `event_reports`
- `premium_entitlements`
- `feed_impressions`
- `ingest_sources`
- `ingest_runs`
- `verification_runs`
- `job_queue`
- `job_runs`

Recommended extensions (project support permitting):
- `postgis`
- `pg_trgm`
- `pgcrypto`
- `pgvector` (optional, unused initially)

### RLS / Access Model (v1)
- Mobile uses Supabase directly for auth only.
- Domain reads/writes go through FastAPI.
- RLS policies still added for user-owned tables for future flexibility.
- Backend service role bypasses RLS when appropriate.

### Product MVP Scope (Locked)

#### Implement First
- Auth + user bootstrap
- Location gate
- Preferences
- Swipe feed
- Favorites
- Basic filters (date/time/price/radius)
- Free swipe limit (10/day)
- Local vibe state machine + session reordering
- Event reporting + hide-after-3-reports behavior
- Premium entitlements + UI gating stubs
- Seeded/manual event supply
- Worker/job skeletons (no real scraping yet)

#### Defer to Phase 2+
- Stripe subscriptions/webhooks
- Production LLM scraping
- AI image generation integration
- Advanced travel mode behavior
- Premium rationales/tips/pairings

## Implementation Plan (Phased)

### Phase 0 — Bootstrap
- Initialize Git repo in `/Users/ericswanson/code/gitHub/aventi`
- Create root `package.json`, `pnpm-workspace.yaml`, `turbo.json`
- Create folder skeleton (`apps`, `services`, `packages`, `supabase`, `infra`, `docs`)
- Add root scripts (`dev`, `test`, `lint`, `typecheck`)
- Add `.gitignore`, `.editorconfig`, `.env.example`
- Add `docs/architecture.md`

### Phase 1 — App and Backend Scaffolds

#### Frontend
- Scaffold Expo app in `apps/mobile`
- Configure Expo Router, NativeWind, Reanimated, Gesture Handler
- Set app branding to `Aventi`
- Create black/glass/gradient theme shell

#### Backend
- Scaffold Python project in `services/backend` using `uv`
- Create FastAPI API and worker entrypoints
- Add config management (`.env`)
- Add Supabase JWT verification middleware scaffold
- Add `GET /v1/health`
- Add placeholder routers/models for feed/swipes/favorites

#### Shared
- Create `@aventi/contracts`
- Create `@aventi/design-tokens`
- Create `@aventi/api-client`

### Phase 2 — Supabase Schema + Seed Data
- Initialize Supabase local config
- Add SQL migrations for core tables/indexes/RLS
- Add seed data for one city (30–50 events target)
- Add radius/geospatial query support and indexes
- Add report-threshold logic support

### Phase 3 — Core Product MVP

#### Backend
- Implement `me`, `preferences`, `feed`, `swipes`, `favorites`, `reports`, `entitlements`
- Enforce free swipe limit
- Persist and update `user_vibe_weights`
- Server-side feed filtering + ranking + dedupe

#### Mobile
- Onboarding/auth flow
- Location permission gate
- Preferences selection
- Swipe deck UI
- Session history review
- Favorites list
- Filters UI
- Premium lock states and CTA stubs

### Phase 4 — Worker + Ingestion Skeleton
- DB job queue polling worker
- Job types: `CITY_SCAN`, `VERIFY_EVENT`, `ENRICH_EVENT`, `GENERATE_IMAGE`
- Manual ingest endpoint/script
- Verification stub (URL active/inactive)
- Provider interfaces + mock adapters (scraper/LLM/image)

### Phase 5 — AWS Deployment
- Terraform for ECR/ECS/ALB/IAM/CloudWatch/EventBridge/Secrets
- Dockerfiles for backend API and worker
- ECS task/service definitions
- EventBridge schedules
- CI pipeline for test/build/push/deploy

### Phase 6 — Hardening and Polish
- Structured logging and request IDs
- Retries/backoff for jobs
- Rate limiting / abuse protection
- Monitoring + alerts
- Second-city seed set and tuning

## Mobile UI/UX Implementation Rules (Aventi Aesthetic)
- Pure black base canvas
- Glassmorphism overlays via blur + translucent borders
- Category gradients:
  - Nightlife = violet/indigo
  - Dining = orange/red
  - Concerts = fuchsia/rose
  - Wellness = teal/cyan
- Full-bleed 9:16 event cards with bottom gradient text anchoring
- Floating circular action buttons with shrink-on-tap
- Category-specific loading placeholders (RN animation equivalents)

## Feed Ranking / Personalization (Locked v1 Behavior)
- Server handles hard filtering and base candidate ranking.
- Client updates local vibe weights instantly on swipe.
- Client reorders remaining session deck using local weights.
- Backend applies same update rules on persisted weights after swipe submission.
- If strict filters produce no results, API returns relaxed suggestions plus `fallback_status`.

## Test Cases and Scenarios

### Backend/API Tests
- Valid Supabase JWT accepted
- Invalid/expired JWT rejected (`401`)
- Feed filtering respects radius/date/time/price
- Hidden/reported events excluded
- Free user blocked after 10 swipes/day
- Premium user bypasses swipe limit
- Swipe updates vibe weights deterministically
- Favorites save is idempotent
- Report threshold (3 unique users) hides event
- Dedupe excludes recent rejects (normalized title matching in v1)

### Worker Tests
- Worker claims jobs without double-processing
- Retries and error recording work
- Verification stub updates event status
- Manual ingest normalizes and dedupes records

### Mobile Tests
- Location permission gate blocks feed before approval
- Swipe right updates favorites + counter
- Swipe left updates local vibe model + reorders deck
- Session history review restores previous cards
- Premium-locked controls render safely
- Empty feed shows fallback state

### End-to-End Acceptance Scenarios
- New user signs in, grants location, sets preferences, sees feed, swipes 10 times, hits limit
- Returning user sees favorites and personalized feed changes
- 3 unique reports hide invalid event
- Worker verification marks stale event hidden
- API and worker deploy to ECS and connect to Supabase

## Assumptions and Defaults (Explicit)
- Turborepo monorepo is the v1 repo strategy.
- AWS deployment is required now (`ECS/Fargate`), with Supabase hosted separately.
- Supabase is source of truth for auth + DB + storage.
- Mobile is Expo + NativeWind.
- Product MVP is prioritized over full scraper/Stripe implementations.
- Premium is entitlement/gating only in v1; Stripe deferred.
- One Python codebase provides API and worker entrypoints.
- Terraform is the IaC standard.
- Initial event supply is seeded/manual for one city.
- Swipe-limit day window uses stored user timezone when available, fallback UTC initially.
- FastAPI is the primary domain API; direct client DB access is minimized.

## Split-Later Path (If Needed)
- Extract `/Users/ericswanson/code/gitHub/aventi/services/backend`
- Extract `/Users/ericswanson/code/gitHub/aventi/supabase`
- Extract `/Users/ericswanson/code/gitHub/aventi/infra/aws`
- Keep shared contracts/design tokens reusable (`@aventi/contracts`, `@aventi/design-tokens`)

## Developer Note

If running Python sync from the repo root, use:

```bash
uv sync --project services/backend --extra dev
```

Or change directories first:

```bash
cd services/backend
uv sync --extra dev
```
