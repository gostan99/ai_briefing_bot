# AI Briefing Bot (Event-Driven MVP)

Early scaffold for a briefing bot that reacts to YouTube uploads, collects transcripts, generates AI-powered summaries, and emails the highlights. The current codebase contains the shared plumbing (env config, Postgres models) while the webhook-driven pipeline is captured in `docs/architecture.md`.

## Components

- **Subscription API (planned)**: single `POST /subscriptions` accepting an email + list of channels to monitor.
- **Webhook API (planned)**: FastAPI endpoint for YouTube WebSub notifications.
- **Transcript worker (planned)**: waits for captions to become available, retries with exponential backoff.
- **Summariser (planned)**: runs LangChain + OpenAI to create TL;DR + highlights once transcripts are ready.
- **Notifier (planned)**: emails the summary and tracks delivery retries.
- **Postgres**: stores channels, videos, transcripts, summaries, and retry metadata.

## Getting Started

1. Copy `.env.example` to `.env` and update database credentials plus any API/email keys.
2. Install dependencies with `poetry install` (or `uv sync`).
3. Create the schema via `python -m app.db.init_db`.

Docker Compose, subscription/webhook handlers, and workers will be added as the event-driven pipeline solidifies. See `docs/architecture.md` for the detailed flow and retry strategy.
