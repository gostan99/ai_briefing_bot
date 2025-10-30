# AI Briefing Bot

An event-driven FastAPI project that watches YouTube channels, harvests transcripts, enriches metadata, and generates AI summaries for downstream tools. It is built for portfolio/demo purposes, but mirrors a production-ready pipeline with retries and backoff at every stage.

## Highlights

- **Webhook ingest**: YouTube WebSub notifications land on `/webhooks/youtube`, upserting channels/videos and seeding transcript jobs.
- **Transcript worker**: Polls `videos.transcript_status='pending'`, calls `youtube-transcript-api`, and applies exponential backoff when YouTube throttles or captions lag.
- **Summariser worker**: Uses OpenAI (or any OpenAI-compatible endpoint) to produce TL;DR, highlights, and a quote. Requires an API key; errors are logged and retried with backoff.
- **Metadata worker**: Uses Playwright (Chromium) to pull full descriptions + tags, cleans them (timestamps, sponsor mentions, URLs), and feeds the summariser richer context.
- **Persistent state**: Postgres schema tracks channels, videos, metadata, and summaries so workers can recover after restarts.
- **React dashboard**: A lightweight Vite/React app visualises transcript, metadata, and summary status via the `/videos` API.

Architectural details and sequence diagrams live in [`docs/architecture.md`](docs/architecture.md).

## Prerequisites

- Python 3.11+
- Docker (Compose) for running Postgres or the full stack
- `uv` (optional but recommended) or plain `pip`

## Quick Start (local dev)

```bash
# 1. Configure environment
cp .env.example .env  # edit as needed (DB creds, API keys)

# If you set up the database before metadata support was added,
# re-run the init script after pulling:
#   uv run -- python -m app.db.init_db
#   # (If you still have legacy subscriber_* tables, drop them or recreate the DB.)

# 2. Install dependencies
uv sync --extra dev   # or: pip install -e .[dev]

# 3. Install Playwright browser binaries (for metadata scraping)
playwright install chromium

# 4. Bootstrap the database schema
uv run -- python -m app.db.init_db

# 5. Run the API + workers (workers start on FastAPI startup)
uv run -- uvicorn app.main:app --reload --port 8000
```

If you already had video rows before metadata support existed, requeue them once:

```
UPDATE videos
SET metadata_status = 'pending',
    metadata_retry_count = 0,
    metadata_next_retry_at = NOW(),
    metadata_last_error = NULL
WHERE metadata_fetched_at IS NULL;
```

## React Dashboard

```bash
cd frontend
npm install
npm run dev
```

Set `VITE_API_BASE` in a `.env` file inside `frontend/` if your API is not running on http://localhost:8000. The dashboard exposes a channel manager (list/add/remove) backed by `/channels`, polls the `/videos` API, exposes a delete action (`DELETE /videos/{id}`), and you can also prune entries via the CLI helper:

```bash
docker compose exec app python -m app.jobs.delete_video <YOUTUBE_ID>
```

The API exposes:
- `GET /channels` – list tracked YouTube channels
- `POST /channels` – add a channel by `UC…`, URL, or `@handle`
- `DELETE /channels/{id}` – remove a tracked channel (cascade to videos)
- `POST /webhooks/youtube` – endpoint for YouTube WebSub payloads
- `GET /healthz` – simple liveness probe

Channel handles (strings starting with `@`) are accepted when `APP_YOUTUBE_API_KEY` is configured; otherwise stick to canonical `UC…` IDs or feed URLs.

Summaries and metadata are stored in Postgres; email delivery is no longer part of this project. Use the React dashboard (`frontend/`) to monitor the pipeline in real time.

## Running with Docker Compose

A `docker-compose.yml` is included to spin up the FastAPI app and Postgres together:

```bash
docker compose up --build
```

- API available at `http://localhost:8000`
- Postgres exposed on `localhost:5432` with credentials from `.env`
- Environment variables come from `.env` via `env_file` and can be overridden per service

Stop the stack with `docker compose down` (add `--volumes` to drop the persistent database volume).

## Configuration Cheatsheet

| Purpose | Key(s) | Notes |
|---------|--------|-------|
| Database | `APP_DATABASE_URL` | Async Postgres DSN (default in `.env.example`) |
| Channel resolution | `APP_YOUTUBE_API_KEY` | Required to resolve channel `@handles` via the YouTube Data API |
| Transcript worker | `APP_TRANSCRIPT_MAX_RETRY`, `APP_TRANSCRIPT_BACKOFF_MINUTES`, `APP_TRANSCRIPT_MAX_CONCURRENCY`, `APP_TRANSCRIPT_MIN_INTERVAL_MS` | Control retry and rate limiting |
| Metadata worker | `APP_METADATA_MAX_RETRY`, `APP_METADATA_BACKOFF_MINUTES` | Retry/backoff for scraping & cleaning |
| Summaries | `APP_SUMMARY_MAX_RETRY` | Max LLM retries before marking `failed` |
| LLM (required for summaries) | `APP_OPENAI_API_KEY`, `APP_OPENAI_MODEL`, `APP_OPENAI_MAX_CHARS`, `APP_OPENAI_BASE_URL` | Provide an OpenAI-compatible key; summaries fail after retries if unavailable |
| Dashboard CORS | `APP_DASHBOARD_CORS_ORIGINS` | JSON array of origins (e.g. `["http://localhost:5173"]`) |
| Webhooks | `APP_WEBHOOK_SECRET`, `APP_WEBHOOK_CALLBACK_URL` | Secret validates inbound WebSub signatures |

### LLM Summaries (OpenAI-compatible)

```
APP_OPENAI_API_KEY=sk-...
APP_OPENAI_MODEL=gpt-4o-mini
APP_OPENAI_MAX_CHARS=12000
APP_OPENAI_BASE_URL=https://api.openai.com/v1  # override if using a compatible endpoint
```

The worker relies on the LLM. If the provider returns an error, the job logs a snippet and retries until `APP_SUMMARY_MAX_RETRY` is exceeded, then marks the summary `failed`.

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
  routers/         # FastAPI routers (/channels, /webhooks, /videos)
  services/
    transcript_worker.py
    metadata_worker.py
    summariser_worker.py
    summariser_utils.py  # LLM summary helpers
    template_renderer.py # Jinja rendering for future use
  templates/       # (reserved for future UI/email assets)
  tests/           # pytest suite covering workers + parsers
```
frontend/          # React/Vite dashboard
  src/             # dashboard source code
```

## Development Tips

- The workers run inside the FastAPI app in this repo; for production you’d probably split them into dedicated processes or Celery/Arq jobs but the logic is isolated in `app/services/*_worker.py`.
- `python -m pytest` exercises parser logic, retry helpers, and template rendering. Add integration tests when you introduce real I/O.
- Database state is safe to inspect directly (e.g. TablePlus). `videos.transcript_status` and `summaries.summary_status` tell you where each item sits in the pipeline.
- Logs surface LLM failures, metadata scrape errors, and transcript fetch issues with video IDs so you can replay or inspect manually.

## Next Ideas (Nice-to-haves)

- Integration smoke test that simulates a full upload → summary run
- Admin endpoints for retrying failed transcript/summary jobs
- UI for richer channel analytics and summary browsing

Enjoy hacking!
