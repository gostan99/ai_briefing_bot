# AI Briefing Bot (Event-Driven MVP)

Early scaffold for a briefing bot that reacts to YouTube uploads, collects transcripts, generates AI-powered summaries, and emails the highlights. The current codebase contains the shared plumbing (env config, Postgres models, RSS poller); the webhook-driven pipeline is defined in `docs/architecture.md` and will replace the poller as the primary trigger.

## Components

- **Webhook API (planned)**: FastAPI endpoint for YouTube WebSub notifications.
- **Subscription API (planned)**: single `POST /subscriptions` accepting an email + list of channels to monitor.
- **Transcript worker (planned)**: waits for captions to become available, retries with exponential backoff.
- **Summariser (planned)**: runs LangChain + OpenAI to create TL;DR + highlights once transcripts are ready.
- **Notifier (planned)**: emails the summary and tracks delivery retries.
- **RSS poller (proto)**: existing async worker useful for local testing or as a fallback.
- **Postgres**: stores channels, videos, transcripts, summaries, and retry metadata.

## Getting Started

1. Copy `.env.example` to `.env` and update database credentials plus any API/email keys.
2. Install dependencies with `poetry install` (or `uv sync`).
3. Create the schema via `python -m app.db.init_db`.
4. (Optional) Run the RSS poller prototype with `python -m app.services.poller` while the webhook flow is under construction.

Docker Compose, subscription/webhook handlers, and workers will be added as the event-driven pipeline solidifies. See `docs/architecture.md` for the detailed flow and retry strategy.
