# AI Briefing Bot (Event-Driven MVP)

A briefing bot that reacts to YouTube uploads, collects transcripts, generates AI-powered summaries, and emails the highlights. The current codebase contains the shared plumbing (env config, Postgres models) while the webhook-driven pipeline is captured in `docs/architecture.md`.

## Components

- **Subscription API (planned)**: single `POST /subscriptions` accepting an email + list of channels to monitor.
- **Webhook API (planned)**: FastAPI endpoint for YouTube WebSub notifications.
- **Transcript worker (planned)**: waits for captions to become available, retries with exponential backoff.
- **Summariser (planned)**: runs LangChain + OpenAI to create TL;DR + highlights once transcripts are ready.
- **Notifier (planned)**: emails the summary and tracks delivery retries.
- **Postgres**: stores channels, videos, transcripts, summaries, and retry metadata.

## Getting Started

1. Copy `.env.example` to `.env` and update database credentials plus any API/email keys.
2. Install dependencies with `uv sync --extra dev` (includes dev tooling).
3. Create the schema via `uv run -- python -m app.db.init_db`.
4. Launch the API locally with `uv run -- uvicorn app.main:app --reload --port 8000` to expose `POST /subscriptions` and `/healthz`.

### Optional: Configure Email Delivery (Mailjet example)

Set the following environment variables if you’d like the notification worker to send real email via Mailjet:

```
APP_EMAIL_SMTP_URL=smtp://<api_key>:<secret_key>@in-v3.mailjet.com:587
APP_EMAIL_FROM=briefing-bot@example.com
```

Leave `APP_EMAIL_SMTP_URL` blank to keep using the built-in dummy sender (no outbound email).

### Optional: Public URL via LocalTunnel

If you need a temporary public endpoint for the webhook (e.g., to demo the project), you can use [LocalTunnel](https://github.com/localtunnel/localtunnel):

```bash
npm install -g localtunnel
lt --port 8000 --subdomain briefing-bot-demo
```

The command prints a URL such as `https://briefing-bot-demo.loca.lt`; copy that into `APP_WEBHOOK_CALLBACK_URL` (append `/webhooks/youtube`). Leave out `--subdomain` to let LocalTunnel choose one automatically.

Docker Compose, subscription/webhook handlers, and workers will be added as the event-driven pipeline solidifies. See `docs/architecture.md` for the detailed flow and retry strategy.
