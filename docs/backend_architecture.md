# Aventi Backend Architecture

This document provides a high-level overview of the Aventi Python backend, explaining how the different pieces fit together to power the AI-driven event discovery platform.

## Core Stack

- **Framework**: [FastAPI](https://fastapi.tiangolo.com/) (Python 3.12+)
- **Database**: PostgreSQL (hosted on [Supabase](https://supabase.com/))
- **ORM**: [SQLAlchemy](https://www.sqlalchemy.org/) (Async)
- **AI/LLM**: Google Gemini API (`google-genai` SDK)

---

## 1. The API Layer (`aventi_backend.api`)

This is the front door of the application. It exposes RESTful HTTP endpoints for the mobile/web clients. It leverages **Mangum** to deploy the `FastAPI` instance completely serverlessly inside an **AWS Lambda Function** via an HTTP Function URL.

- **Endpoints**: Defined in `src/aventi_backend/api/routes/`.
- **Feed (`feed.py`)**: The primary endpoint (`GET /v1/feed`). It requests events for a user's city. If the database doesn't have enough events, the API triggers background AI agents to go find some live.
- **Internal (`internal.py`)**: Secured endpoints used for manually triggering background jobs or forcing manual ingestion.

## 2. The Database Layer (`aventi_backend.db`)

We use the **Repository Pattern** to interact with the database. This abstracts away the raw SQL so the business logic stays clean.

- **`AventiRepository`**: The interface that defines all database interactions (getting feeds, swiping, updating profiles).
- **`PostgresAventiRepository`**: The actual implementation that executes async SQLAlchemy queries against the Supabase Postgres instance.
Local development and tests use the same Postgres-backed repository contract as production. Fast unit/contract tests use fakes at module seams; integration tests use local Supabase/Postgres.

## 3. The Background Job System (`aventi_backend.worker`)

Scraping the web and asking AI models to analyze text takes time. We can't do this while the user is waiting for an HTTP response. Instead, we use an event-driven, serverless background worker stack.

1.  **The Queue (`services/jobs.py`)**: Jobs (like "Scan Austin for events") are pushed to an **AWS SQS Queue** using Boto3. In production, the queue is provisioned by Terraform before the worker starts. In local development with LocalStack, the polling worker can auto-create the queue on startup if it doesn't exist.
2.  **The Worker (`worker/lambda_handler.py`)**: An **AWS Lambda Serverless Function** receives SQS batches and returns `batchItemFailures` so AWS retries only failed messages. Local development can also run `worker/main.py` as a long-polling worker against LocalStack.
3.  **The Scheduler (`worker/scheduler.py`)**: An EventBridge-triggered Lambda recomputes active market heat and enqueues weekly market scans.
4.  **The Handlers (`worker/handlers.py`)**: When the worker claims a job, it routes it to a specific function based on its type:
    - `MARKET_SCAN`: Triggers the scraper to search the web for events.
    - `ENRICH_EVENT`: Asks the AI to extract tags, vibes, and dress codes from a long event description.
    - `VERIFY_EVENT`: Checks if a booking URL is still active.
    - `GENERATE_IMAGE`: Creates an event poster using AI image generation.

## 4. The AI Engine (`aventi_backend.services`)

This is the brain of the event discovery platform, heavily relying on Google's Gemini models.

- **`SerpApiEventScraper`**: Given a city (e.g., "Austin") and an angle (e.g., "Hidden Gems"), this class queries the **SerpApi Google Events API** to discover real, upcoming events and return them as structured `DiscoveryCandidate` objects.
- **`GeminiEventScraper`** *(fallback)*: An AI-driven scraper using Google Gemini with Search Grounding. Available as a secondary option but no longer the default discovery engine.
- **`GeminiVerifier`**: Takes a URL and asks the AI to search the web to confirm if the event is real, active, and not cancelled.
- **`GeminiImageGenerator`**: Uses Google's Imagen 3 model to generate custom promotional posters for events based on their title and vibes.

## How it All Comes Together (The "Empty Feed" Flow)

1. A user opens the app in "Austin" and hits `GET /v1/feed`.
2. The `AventiRepository` queries Postgres. It realizes there are zero events for Austin.
3. The API immediately responds to the user with inventory status and asks the market warmup service to enqueue SQS work when the market needs discovery.
4. The Serverless **AWS Lambda Worker** is invoked by SQS to process these jobs in parallel and returns per-record retry failures when needed.
5. The worker fires up the `SerpApiEventScraper`, which queries the Google Events API, formats the results, and saves the new events to Postgres.
6. As those events are saved, the worker queues up follow-up jobs: `ENRICH_EVENT` to pull out specific vibes/tags, `GENERATE_IMAGE` to make posters, and `VERIFY_EVENT` to double-check the links.
7. The next time the user pulls to refresh, their feed is full of rich, verified, AI-generated content.
