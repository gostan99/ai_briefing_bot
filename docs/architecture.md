# AI Briefing Bot – Event-Driven Flow

## Overview
Reacts to YouTube upload notifications, a webhook stores new uploads, a worker waits for transcripts to appear, an LLM produces a brief, and an email service delivers the summary.

## Flow Breakdown
1. **Subscription API**
   - FastAPI exposes `POST /subscriptions` with payload:
     ```json
     {
       "email": "user@example.com",
       "channels": ["UC123...", "https://www.youtube.com/@channel"]
     }
     ```
   - Handler normalises channel identifiers (accepts IDs, `@handles`, or feed URLs) and deduplicates the list.
   - Upsert subscriber record (`subscribers` table) and associated channels (`subscriber_channels`).
   - For any new channel we are not yet following, issue/refresh a WebSub subscription.

2. **YouTube Push Notification**
   - FastAPI exposes `GET/POST /webhooks/youtube`.
   - GET handles WebSub subscription challenge.
   - POST parses the new upload payload, extracts `channel_id` + `video_id`.
   - DB upsert into `channels`; insert/update `videos` with:
     - `transcript_status = 'pending'`
     - `retry_count = 0`
     - `next_retry_at = NOW()`
     - metadata (title if provided, timestamps, etc.)

3. **Transcript Worker**
   - Background loop (APScheduler job or standalone worker) selects rows where:
     - `transcript_status = 'pending'`
     - `next_retry_at <= NOW()`
   - For each candidate:
     - Call `youtube-transcript-api`.
     - **Success**: store transcript text/language, set `transcript_status = 'ready'`, reset `retry_count`, clear `last_error`.
     - **Failure**: increment `retry_count`, set `next_retry_at = NOW() + backoff(retry_count)`, record error.
     - When `retry_count >= MAX_RETRY`, mark `transcript_status = 'failed'` and stop retrying.

4. **Summariser**
   - Worker scans for `videos` where `transcript_status = 'ready'` and summary status is `pending`.
   - Fetch transcript, run LangChain + OpenAI (or chosen LLM) to produce:
     - `tl_dr` paragraph
     - Bullet highlights (JSON array/string)
     - Key quote
   - Persist into `summaries` table, set `summary_status = 'ready'`, and reset `summary_retry_count`.
   - On failure, increment `summary_retry_count`, schedule another attempt, and capture the error message. After `summary_retry_count >= APP_SUMMARY_MAX_RETRY`, mark `summary_status = 'failed'` for manual follow-up.

5. **Notification Dispatcher**
   - Once a summary is ready, load all subscribers linked to the video’s channel via `subscriber_channels`.
   - For each subscriber, upsert a `notification_jobs` row with status `pending` and capture the email address plus any preferences (timezone, format, etc.).
   - Worker dequeues pending jobs, renders the Jinja email template, and sends via SMTP/SendGrid.
   - Successful sends mark the job `delivered` with `delivered_at = NOW()`; failures increment `retry_count`, store `last_error`, and set `next_retry_at` using exponential backoff.
   - After `retry_count >= APP_NOTIFY_MAX_RETRY`, mark the job `failed` so it appears in dashboards for manual follow-up without retrying forever.

6. **Observability & Recovery**
   - Structured logging for each stage (video id, channel, attempt counts, durations).
   - Metrics counters (processed, retries, failures) for quick health checks.
   - Admin endpoint or CLI script to list rows with `transcript_status='failed'` or stuck retries.

## Schema Additions (relative to MVP)
- **`videos` table**
  - `transcript_status VARCHAR(16)` (default `'pending'`, values: `pending|ready|failed`).
  - `retry_count INT DEFAULT 0`.
  - `next_retry_at TIMESTAMPTZ NULL`.
  - `last_error TEXT NULL`.
  - `summary_ready_at TIMESTAMPTZ NULL` (timestamp when LLM succeeded).
- **`summaries` table**
  - `summary_status VARCHAR(16)` (values: `pending|ready|failed`).
  - `summary_retry_count INT DEFAULT 0`.
  - `summary_last_error TEXT NULL`.
  - Existing summary payload columns (`tl_dr`, `highlights`, `key_quote`, `created_at`).
- **`subscribers` table**
  - `id SERIAL PRIMARY KEY`.
  - `email VARCHAR(320)` (unique, lower-cased).
  - `created_at TIMESTAMPTZ NOT NULL`.
  - Optional metadata (name, last_notified).
- **`subscriber_channels` table**
  - `subscriber_id` FK → `subscribers.id`.
  - `channel_id` FK → `channels.id`.
  - `created_at TIMESTAMPTZ NOT NULL`.
  - Composite unique key on `(subscriber_id, channel_id)`.
- **`notification_jobs` table**
  - `id SERIAL PRIMARY KEY`.
  - `video_id` FK → `videos.id`.
  - `subscriber_id` FK → `subscribers.id`.
  - `status VARCHAR(16)` (values: `pending|delivered|failed`).
  - `retry_count INT DEFAULT 0`.
  - `next_retry_at TIMESTAMPTZ NULL`.
  - `last_error TEXT NULL`.
  - `delivered_at TIMESTAMPTZ NULL`.
  - Composite unique key `(video_id, subscriber_id)` to prevent duplicates.

## Configuration Keys
- `APP_TRANSCRIPT_MAX_RETRY` (default 6).
- `APP_TRANSCRIPT_BACKOFF_MINUTES` (base interval for exponential backoff).
- `APP_NOTIFY_MAX_RETRY` (default 5).
- `APP_SUMMARY_MAX_RETRY` (default 5).
- `APP_EMAIL_SMTP_URL`, `APP_EMAIL_FROM`, `APP_EMAIL_TO`.
- `APP_WEBHOOK_SECRET` for validating requests (optional but recommended behind a proxy).

## Worker Implementation Notes
- Use FastAPI startup event to spawn async loops, or split into separate processes (API + worker) coordinated via Docker Compose.
- Backoff example: `delay = base * (2 ** retry_count)` capped at e.g. 6 hours.
- Protect against duplicate notifications by unique constraint on `(channel_id, youtube_id)`.
