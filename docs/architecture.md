# AI Briefing Bot Architecture

This document outlines the end-to-end flow that turns a YouTube upload into a summarised email, plus the core data model and retry strategy.

## 1. High-Level Flow

```
YouTube → WebSub → FastAPI webhook → Postgres (video:pending)
          ↓
   Transcript worker (polls videos)
          ↓
   Summariser worker (LLM or heuristic)
          ↓
   Notification worker (SMTP)
          ↓
      Subscriber inbox
```

1. **Upload event**: YouTube notifies the app via WebSub; we upsert the channel/video row and mark the transcript job `pending`.
2. **Transcript fetch**: A background worker calls `youtube-transcript-api`, storing the transcript (or scheduling a retry with exponential backoff).
3. **Summary generation**: Once a transcript is ready, the summariser worker invokes the OpenAI-compatible API (with fallback to a heuristic summariser) and persists TL;DR + highlights + quote.
4. **Email dispatch**: The notification worker fan-outs `notification_jobs` for each subscriber, renders a Jinja template, and delivers via SMTP. Retries use the same exponential backoff pattern.

## 2. Detailed Stages

### 2.1 Subscription API (`POST /subscriptions`)
- Normalises channel identifiers (UC IDs, channel URLs, etc.).
- Upserts the subscriber and the `subscriber_channels` links.
- Initiates/refreshes WebSub subscriptions for any new channels.

### 2.2 YouTube Webhook (`/webhooks/youtube`)
- `GET` handles the WebSub challenge handshake.
- `POST` parses Atom XML, writes/updates `channels` + `videos`, and seeds transcript state:
  - `transcript_status='pending'`
  - `retry_count=0`
  - `next_retry_at=NOW()`
  - video metadata (title, description, published timestamp)

### 2.3 Transcript Worker
- Queries `videos` where `transcript_status='pending'` and `next_retry_at <= NOW()`.
- Calls `youtube-transcript-api` with rate limiting (`transcript_max_concurrency`, `transcript_min_interval_ms`).
- On success: stores transcript text/lang, marks `transcript_status='ready'`, clears error fields, sets `fetched_transcript_at`.
- On failure: increments `retry_count`, schedules the next attempt via `transcript_backoff_minutes * 2^(retry_count-1)`. Once retries exceed `APP_TRANSCRIPT_MAX_RETRY`, the video is marked `failed`.

### 2.4 Summariser Worker
- Finds videos with `transcript_status='ready'` and `summary_status!='ready'`.
- Picks a summariser function:
  - If `APP_OPENAI_API_KEY` is present, use `generate_summary_via_openai()` with optional `APP_OPENAI_BASE_URL` (OpenAI-compatible providers).
  - Otherwise use the built-in sentence-based heuristic.
- Persists the summary (`tl_dr`, newline-joined highlights, optional `key_quote`) and sets `summary_status='ready'`.
- If the LLM step fails, logs the error snippet and falls back to the heuristic; repeated failures trigger retry/backoff similar to transcripts.
- When a summary succeeds, the worker enqueues notification jobs for every subscriber tied to the channel (unique `(video_id, subscriber_id)` constraint prevents dupes).

### 2.5 Notification Worker
- Selects `notification_jobs` with `status='pending'` and `next_retry_at` due (NULL allowed).
- Ensures the related `video` and `summary` exist; if data is missing it records a failure.
- Renders the email using Jinja (`app/templates/notification_email.txt.jinja`).
- Sends via SMTP:
  - If `APP_EMAIL_SMTP_URL` + `APP_EMAIL_FROM` are set, a real SMTP client is initialised (supports SSL/STARTTLS via URL scheme).
  - Otherwise a dummy sender logs the payload for local testing.
- On success: sets `status='delivered'`, clears error fields, records `delivered_at`.
- On failure: increments `retry_count`, schedules `next_retry_at` using `APP_NOTIFY_BACKOFF_MINUTES`, and stops after `APP_NOTIFY_MAX_RETRY` attempts.

## 3. Data Model Snapshot

| Table | Purpose |
|-------|---------|
| `channels` | Canonical YouTube channels (title, external ID, RSS URL, last polled timestamp) |
| `videos` | Videos per channel, transcript metadata, retry counters, summary timestamps |
| `summaries` | TL;DR, highlights, quote, retry/error state; one-to-one with `videos` |
| `subscribers` | Subscriber emails (lowercased, unique) |
| `subscriber_channels` | Many-to-many join table between subscribers and channels |
| `notification_jobs` | Pending/delivered/failed email jobs per subscriber/video |

All retry-enabled tables share the same pattern: `status`, `retry_count`, `next_retry_at`, `last_error`, plus a hard cap from environment settings.

## 4. Configuration Overview

Key environment variables (see `.env.example` for the full list):

- Transcript worker: `APP_TRANSCRIPT_MAX_RETRY`, `APP_TRANSCRIPT_BACKOFF_MINUTES`, `APP_TRANSCRIPT_MAX_CONCURRENCY`, `APP_TRANSCRIPT_MIN_INTERVAL_MS`
- Summariser: `APP_SUMMARY_MAX_RETRY`, `APP_OPENAI_API_KEY`, `APP_OPENAI_MODEL`, `APP_OPENAI_MAX_CHARS`, `APP_OPENAI_BASE_URL`
- Notifications: `APP_NOTIFY_MAX_RETRY`, `APP_NOTIFY_BACKOFF_MINUTES`, `APP_EMAIL_SMTP_URL`, `APP_EMAIL_FROM`
- Webhook security: `APP_WEBHOOK_SECRET`, `APP_WEBHOOK_CALLBACK_URL`

## 5. Operational Notes

- **Startup/shutdown**: All workers start from FastAPI’s lifecycle hooks in `app/main.py`; for production you can split them into separate processes (e.g., using a supervisor or container per worker).
- **Rate limiting**: Transcript fetches use a shared semaphore + monotonic throttle to avoid hammering YouTube; configure via env vars.
- **Logging**: Workers log failures with video IDs and snippets (LLM responses, SMTP errors) to simplify manual inspection.
- **Fallback behaviour**: Summaries revert to heuristic generation whenever the LLM errors; notification delivery falls back to dummy sender when SMTP is misconfigured.
- **Extensibility**: swap the heuristic summariser for other models, plug in HTML templates, or add UI endpoints without touching the core pipeline.

## 6. Future Enhancements

- HTML or multi-part email templates
- Admin UI/CLI to requeue failed items and view pipeline status
- Integration tests that publish a synthetic webhook payload and verify email delivery
- Scaling the workers via separate deployments or task queues when moving beyond portfolio usage

With these components in place, a single YouTube upload now propagates automatically to subscribers with AI-generated highlights and resilient retries at every stage.
