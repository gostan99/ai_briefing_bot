# AI Briefing Bot Architecture

This document describes how a single YouTube upload flows through the system—from webhook ingestion to the final email—together with the retry/backoff strategy and supporting data model.

## 1. High-Level Flow

```
YouTube → WebSub → FastAPI webhook → Postgres (video pending)
          ↓
   Transcript worker (fetch captions)
          ↓
   Metadata enrichment (scrape + clean)
          ↓
   Summariser worker (LLM or heuristic)
          ↓
   Notification worker (SMTP)
          ↓
      Subscriber inbox
```

1. **Upload event**: WebSub notifies us; we upsert the channel/video record and mark the transcript job `pending`.
2. **Transcript fetch**: The transcript worker calls `youtube-transcript-api`. Captions are stored or retried with exponential backoff.
3. **Metadata enrichment**: Once captions exist, the metadata stage scrapes the public watch page for tags and the raw description, cleans it (LLM-assisted), and persists tags/hashtags/sponsors/URLs.
4. **Summary generation**: The summariser worker feeds the transcript + cleaned metadata into the OpenAI-compatible API (with a heuristic fallback) and stores TL;DR/highlights/quote/topics.
5. **Email dispatch**: The notification worker fans out per-subscriber jobs, renders a Jinja template, and delivers via SMTP with retry/backoff.

## 2. Detailed Stages

### 2.1 Subscription API (`POST /subscriptions`)
- Normalises channel identifiers (`UC…`, `/channel/…`, `@handles`, etc.).
- Upserts the subscriber + `subscriber_channels` links.
- Subscribes to WebSub for any new channels we are not already following.

### 2.2 YouTube Webhook (`/webhooks/youtube`)
- `GET` handles the WebSub challenge handshake.
- `POST` parses Atom XML, writing/merging rows in `channels` and `videos`:
  - Sets `transcript_status='pending'`
  - Resets transcript retry counters (`retry_count=0`, `next_retry_at=NOW()`)
  - Stores provided metadata (title, short description, published timestamp)

### 2.3 Transcript Worker
- Queries `videos` where `transcript_status='pending'` **and** `next_retry_at <= NOW()`.
- Calls `youtube-transcript-api` with shared semaphore + monotonic throttle (`APP_TRANSCRIPT_MAX_CONCURRENCY`, `APP_TRANSCRIPT_MIN_INTERVAL_MS`).
- **Success**: stores transcript text/lang, marks `transcript_status='ready'`, clears `last_error`, stamps `fetched_transcript_at`.
- **Failure**: increments `retry_count`, schedules `next_retry_at = NOW() + base * 2^(retry_count-1)`. After `APP_TRANSCRIPT_MAX_RETRY` attempts the status becomes `failed`.

### 2.4 Metadata Enrichment
- Once transcripts are ready we load the watch page (`https://www.youtube.com/watch?v={id}`) via Playwright (Chromium).
- Read the full description and keywords from the page’s JavaScript objects (`ytInitialPlayerResponse`); fall back to `httpx + BeautifulSoup` when Playwright is unavailable.
- Apply lightweight transforms: normalise tags, strip timestamp bullet lines, capture sponsor mentions, deduplicate hashtags/URLs.
- Persist results on the video row (`metadata_tags`, `metadata_clean_description`, `metadata_hashtags`, `metadata_sponsors`, `metadata_urls`, `metadata_fetched_at`).
- Retries/backoff mirror the transcript pattern (`metadata_status`, `metadata_retry_count`, etc.).

### 2.5 Summariser Worker
- Selects videos with `transcript_status='ready'` and `summary_status!='ready'`.
- Chooses the generator:
  - If `APP_OPENAI_API_KEY` is set, call `generate_summary_via_openai()` (respecting `APP_OPENAI_BASE_URL` for OpenAI-compatible endpoints).
  - Otherwise fall back to `generate_summary_from_transcript()` (sentence-based heuristic).
- Prompt includes transcript plus cleaned description/tags to enrich the TL;DR/highlights/topics.
- **Success**: persists the summary (`tl_dr`, newline-joined highlights, `key_quote`, optional `topics`), marks `summary_status='ready'`, enqueues notification jobs for each subscribed user.
- **Failure**: logs the LLM snippet, retries with backoff, and automatically falls back to the heuristic summariser when the LLM step throws.

### 2.6 Notification Worker
- Selects `notification_jobs` with `status='pending'` and `next_retry_at` due (NULL allowed).
- Loads the associated `video`, `summary`, and `subscriber`:
  - Missing relations mark the job failed with the retry/backoff pattern.
  - If summary isn’t ready yet the job stays pending for the next cycle.
- Renders `app/templates/notification_email.txt.jinja` via Jinja (`render_notification_email`), inserting TL;DR, highlights, quote, topics, tags, and watch URL.
- Sends mail via SMTP:
  - Real delivery if `APP_EMAIL_SMTP_URL` + `APP_EMAIL_FROM` are set (supports `smtp://` + STARTTLS or `smtps://`).
  - Otherwise a dummy sender logs the payload for local testing.
- **Success**: sets `delivered`, clears errors, records `delivered_at`.
- **Failure**: increments `retry_count`, schedules `next_retry_at = NOW() + base * 2^(retry_count-1)`. After `APP_NOTIFY_MAX_RETRY` attempts the job becomes `failed`.

## 3. Data Model Snapshot

| Table | Purpose |
|-------|---------|
| `channels` | Canonical YouTube channels (title, external ID, RSS URL, last polled timestamp) |
| `videos` | Video metadata, transcript status, metadata enrichment fields, summary timestamp |
| `summaries` | TL;DR, highlights, quote, topics, retry/error state (1:1 with `videos`) |
| `subscribers` | Subscriber emails (lowercased, unique) |
| `subscriber_channels` | Many-to-many link between subscribers and channels |
| `notification_jobs` | Pending/delivered/failed email jobs per subscriber/video |

Retry-enabled tables share the schema pattern: `*_status`, `*_retry_count`, `*_next_retry_at`, `*_last_error`, guided by environment caps.

## 4. Configuration Overview

(Refer to `.env.example` for the complete list.)

- **Transcript worker**: `APP_TRANSCRIPT_MAX_RETRY`, `APP_TRANSCRIPT_BACKOFF_MINUTES`, `APP_TRANSCRIPT_MAX_CONCURRENCY`, `APP_TRANSCRIPT_MIN_INTERVAL_MS`
- **Metadata enrichment**: (planned) `APP_METADATA_MAX_RETRY`, `APP_METADATA_BACKOFF_MINUTES` (default mirrors transcript values)
- **Summariser**: `APP_SUMMARY_MAX_RETRY`, `APP_OPENAI_API_KEY`, `APP_OPENAI_MODEL`, `APP_OPENAI_MAX_CHARS`, `APP_OPENAI_BASE_URL`
- **Notification**: `APP_NOTIFY_MAX_RETRY`, `APP_NOTIFY_BACKOFF_MINUTES`, `APP_EMAIL_SMTP_URL`, `APP_EMAIL_FROM`
- **Webhook security**: `APP_WEBHOOK_SECRET`, `APP_WEBHOOK_CALLBACK_URL`

## 5. Operational Notes

- Workers start from FastAPI lifecycle hooks (`app/main.py`). For production, run them as separate processes or containers—the core logic lives in `app/services/*_worker.py` for easy extraction.
- Transcript fetches use shared semaphores + monotonic throttling; metadata and email workers use the same backoff pattern to avoid hammering external services.
- Logs include video IDs and trimmed error snippets (LLM responses, SMTP issues, scraping results) for manual replay/debugging.
- LLM summary fallback ensures deliveries keep flowing even when the AI provider throttles or returns malformed JSON.
- Metadata cleaning leverages the same LLM to remove timestamps, extract sponsors/hashtags, and provide structured JSON; a lightweight regex fallback ensures resilience.

## 6. Future Enhancements

- HTML or multi-part email templates with responsive styling.
- Admin UI/CLI to requeue failed transcript/metadata/summary/notification jobs.
- Integration smoke tests that push synthetic webhook payloads and verify email delivery end-to-end.
- Advanced analytics: dashboard for tag/topic frequency, channel performance, subscriber engagement.
- External metadata providers (e.g., official YouTube Data API) to replace HTML scraping if quota allows.

With this architecture, each new YouTube upload automatically progresses through transcript capture, metadata enrichment, AI-generated summarisation, and reliable email delivery—complete with retry/backoff safety nets at every stage.
