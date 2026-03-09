# Aventi Backend Architecture

This document provides a high-level overview of the Aventi Python backend, explaining how the different pieces fit together to power the AI-driven event discovery platform.

## Core Stack

- **Framework**: [FastAPI](https://fastapi.tiangolo.com/) (Python 3.12+)
- **Database**: PostgreSQL (hosted on [Supabase](https://supabase.com/))
- **ORM**: [SQLAlchemy](https://www.sqlalchemy.org/) (Async)
- **AI/LLM**: Google Gemini API (`google-genai` SDK)

---

## 1. The API Layer (`aventi_backend.api`)

This is the front door of the application. It exposes RESTful HTTP endpoints for the mobile/web clients.

- **Endpoints**: Defined in `src/aventi_backend/api/routes/`.
- **Feed (`feed.py`)**: The primary endpoint (`GET /v1/feed`). It requests events for a user's city. If the database doesn't have enough events, the API triggers background AI agents to go find some live.
- **Internal (`internal.py`)**: Secured endpoints used for manually triggering background jobs or forcing manual ingestion.

## 2. The Database Layer (`aventi_backend.db`)

We use the **Repository Pattern** to interact with the database. This abstracts away the raw SQL so the business logic stays clean.

- **`AventiRepository`**: The interface that defines all database interactions (getting feeds, swiping, updating profiles).
- **`PostgresAventiRepository`**: The actual implementation that executes async SQLAlchemy queries against the Supabase Postgres instance.
- **`InMemoryAventiRepository`**: A lightweight, in-memory version used as a fallback or for local testing before the database is fully seeded.

## 3. The Background Job System (`aventi_backend.worker`)

Scraping the web and asking AI models to analyze text takes time. We can't do this while the user is waiting for an HTTP response. Instead, we use a custom, Postgres-backed background job queue.

1.  **The Queue (`services/jobs.py`)**: Jobs (like "Scan Austin for events") are inserted into a `job_queue` table in Postgres.
2.  **The Worker (`worker/main.py`)**: A completely separate python process that constantly polls the `job_queue` table. It uses `SELECT ... FOR UPDATE SKIP LOCKED` to safely claim jobs without colliding with other workers.
3.  **The Handlers (`worker/handlers.py`)**: When the worker claims a job, it routes it to a specific function based on its type:
    - `CITY_SCAN`: Triggers the AI to search the web for events.
    - `ENRICH_EVENT`: Asks the AI to extract tags, vibes, and dress codes from a long event description.
    - `VERIFY_EVENT`: Checks if a booking URL is still active.
    - `GENERATE_IMAGE`: Creates an event poster using AI image generation.

## 4. The AI Engine (`aventi_backend.services`)

This is the brain of the event discovery platform, heavily relying on Google's Gemini models.

- **`GeminiEventScraper`**: Given a city (e.g., "Austin") and an angle (e.g., "Hidden Gems"), this class asks Gemini 2.5 Flash to use **Google Search Grounding** to scour the web for exactly matching events and return them as structured JSON.
- **`GeminiVerifier`**: Takes a URL and asks the AI to search the web to confirm if the event is real, active, and not cancelled.
- **`GeminiImageGenerator`**: Uses Google's Imagen 3 model to generate custom promotional posters for events based on their title and vibes.

## How it All Comes Together (The "Empty Feed" Flow)

1. A user opens the app in "Austin" and hits `GET /v1/feed`.
2. The `AventiRepository` queries Postgres. It realizes there are zero events for Austin.
3. The API immediately responds to the user (perhaps showing a loading state or a fallback) AND injects three new `CITY_SCAN` jobs into the `job_queue` database table for "Austin" (covering angles like "Trending", "Hidden Gems", and "Weekend Vibes").
4. Seconds later, the Background Worker picks up these three jobs in parallel.
5. The worker fires up the `GeminiEventScraper`, which searches the web, formats the results, and saves the new events to Postgres.
6. As those events are saved, the worker queues up follow-up jobs: `ENRICH_EVENT` to pull out specific vibes/tags, `GENERATE_IMAGE` to make posters, and `VERIFY_EVENT` to double-check the links.
7. The next time the user pulls to refresh, their feed is full of rich, verified, AI-generated content.
