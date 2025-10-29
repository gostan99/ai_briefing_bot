# AI Briefing Bot

An event-driven FastAPI project that watches YouTube channels, harvests transcripts, generates AI summaries, and emails subscribers. It is built for portfolio/demo purposes, but mirrors a production-ready pipeline with retries, backoff, and templated emails.

## Highlights

- **Webhook ingest**: YouTube WebSub notifications land on `/webhooks/youtube`, upserting channels/videos and seeding transcript jobs.
- **Transcript worker**: Polls `videos.transcript_status='pending'`, calls `youtube-transcript-api`, and applies exponential backoff when YouTube throttles or captions lag.
- **Summariser worker**: Uses OpenAI (or any OpenAI-compatible endpoint) to produce TL;DR, highlights, and a quote; automatically falls back to a heuristic summary when the LLM fails or is disabled.
- **Notification worker**: Creates per-subscriber jobs, renders a Jinja template, and delivers mail via SMTP (Mailjet-ready). Retries obey configurable backoff before marking jobs failed.
- **Persistent state**: Postgres schema tracks channels, subscribers, videos, summaries, and notification jobs so workers can recover after restarts.

Architectural details and sequence diagrams live in [`docs/architecture.md`](docs/architecture.md).

## Prerequisites

- Python 3.11+
- Postgres (local `docker compose up postgres` works)
- `uv` (optional but recommended) or plain `pip`

## Quick Start

```bash
# 1. Configure environment
cp .env.example .env  # edit as needed (DB creds, API keys, SMTP)

# 2. Install dependencies
uv sync --extra dev   # or: pip install -e .[dev]

# 3. Bootstrap the database schema
uv run -- python -m app.db.init_db

# 4. Run the API + workers (workers start on FastAPI startup)
uv run -- uvicorn app.main:app --reload --port 8000
```

The API exposes:
- `POST /subscriptions` – register an email + list of channel IDs/URLs
- `POST /webhooks/youtube` – endpoint for YouTube WebSub payloads
- `GET /healthz` – simple liveness probe

## Configuration Cheatsheet

| Purpose | Key(s) | Notes |
|---------|--------|-------|
| Database | `APP_DATABASE_URL` | Async Postgres DSN (default in `.env.example`) |
| Transcript worker | `APP_TRANSCRIPT_MAX_RETRY`, `APP_TRANSCRIPT_BACKOFF_MINUTES`, `APP_TRANSCRIPT_MAX_CONCURRENCY`, `APP_TRANSCRIPT_MIN_INTERVAL_MS` | Control retry and rate limiting |
| Summaries | `APP_SUMMARY_MAX_RETRY` | Max LLM/heuristic retries before marking `failed` |
| LLM (optional) | `APP_OPENAI_API_KEY`, `APP_OPENAI_MODEL`, `APP_OPENAI_MAX_CHARS`, `APP_OPENAI_BASE_URL` | Leave blank to use heuristic summariser; set base URL for compatible providers such as Moonshot/Kimi |
| Email (optional) | `APP_EMAIL_SMTP_URL`, `APP_EMAIL_FROM` | Example: `smtp://<api_key>:<secret>@in-v3.mailjet.com:587` |
| Webhooks | `APP_WEBHOOK_SECRET`, `APP_WEBHOOK_CALLBACK_URL` | Secret validates inbound WebSub signatures |

### LLM Summaries (OpenAI-compatible)

```
APP_OPENAI_API_KEY=sk-...
APP_OPENAI_MODEL=gpt-4o-mini
APP_OPENAI_MAX_CHARS=12000
APP_OPENAI_BASE_URL=https://api.openai.com/v1  # override if using a compatible endpoint
```

The worker first tries the LLM. If the provider returns anything non-JSON (or errors), it logs a snippet and falls back to the built-in heuristic summariser so delivery keeps flowing.

### Email Delivery (Mailjet example)

```
APP_EMAIL_SMTP_URL=smtp://<api_key>:<secret_key>@in-v3.mailjet.com:587
APP_EMAIL_FROM=briefing-bot@example.com
```

If `APP_EMAIL_SMTP_URL` is blank, the notification worker uses a dummy sender that only logs payloads—perfect for local testing.

### Exposing a Public Webhook (Optional)

```bash
npm install -g localtunnel
lt --port 8000 --subdomain briefing-bot-demo
# Use https://briefing-bot-demo.loca.lt/webhooks/youtube as APP_WEBHOOK_CALLBACK_URL
```

## Project Layout

```
app/
  core/            # configuration loading
  db/              # SQLAlchemy models + init script
  routers/         # FastAPI routers (/subscriptions, /webhooks)
  services/
    transcript_worker.py
    summariser_worker.py
    notification_worker.py
    summariser_utils.py  # heuristic + LLM summary helpers
    template_renderer.py # Jinja email rendering
  templates/       # notification_email.txt.jinja (plain text template)
  tests/           # pytest suite covering workers + parsers
```

## Development Tips

- The workers run inside the FastAPI app in this repo; for production you’d probably split them into dedicated processes or Celery/Arq jobs but the logic is isolated in `app/services/*_worker.py`.
- `python -m pytest` exercises parser logic, retry helpers, and template rendering. Add integration tests when you introduce real I/O.
- Database state is safe to inspect directly (e.g. TablePlus). `videos.transcript_status` and `summaries.summary_status` tell you where each item sits in the pipeline.
- Logs surface LLM failures, email retries, and transcript fetch issues with video IDs so you can replay or inspect manually.

## Next Ideas (Nice-to-haves)

- HTML email template with responsive styling
- Integration smoke test that simulates a full upload → email run
- Admin endpoints for retrying failed transcript/summary/notification jobs
- UI for subscriber management and summary browsing

Enjoy hacking!
