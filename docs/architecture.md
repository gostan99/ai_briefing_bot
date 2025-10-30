# AI Briefing Bot Architecture

This document describes how a YouTube upload flows through the system—from webhook ingestion to the generated summary—plus the retry/backoff strategy and supporting data model.

## 1. High-Level Flow

```
YouTube → WebSub → FastAPI webhook → Postgres (video pending)
          ↓
   Transcript worker (fetch captions)
          ↓
   Metadata enrichment (scrape + clean)
          ↓
   Summariser worker (LLM)
          ↓
      Summary stored in Postgres
```

1. **Upload event**: WebSub notifies us; we upsert the channel/video record and mark the transcript job `pending`.
2. **Transcript fetch**: The transcript worker calls `youtube-transcript-api`. Captions are stored or retried with exponential backoff.
3. **Metadata enrichment**: Once captions exist, the metadata stage scrapes the public watch page for tags and the raw description, cleans it (LLM-assisted), and persists tags/hashtags/sponsors/URLs.
4. **Summary generation**: The summariser worker feeds the transcript + cleaned metadata into the OpenAI-compatible API and stores TL;DR/highlights/quote/topics.

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
- Read the full description and keywords from the page’s JavaScript objects (`ytInitialPlayerResponse`).
- Apply lightweight transforms: normalise tags, strip timestamp bullet lines, capture sponsor mentions, deduplicate hashtags/URLs.
- Persist results on the video row (`metadata_tags`, `metadata_clean_description`, `metadata_hashtags`, `metadata_sponsors`, `metadata_urls`, `metadata_fetched_at`).
- Retries/backoff mirror the transcript pattern (`metadata_status`, `metadata_retry_count`, etc.).

### 2.5 Summariser Worker
- Selects videos with `transcript_status='ready'` and `summary_status!='ready'`.
- Calls `generate_summary_via_openai()` (respecting `APP_OPENAI_BASE_URL` for OpenAI-compatible endpoints) using transcript + cleaned description/tags.
- **Success**: persists the summary (`tl_dr`, newline-joined highlights, `key_quote`, optional `topics`), marks `summary_status='ready'`, enqueues notification jobs for each subscribed user.
- **Failure**: logs the LLM snippet, retries with backoff, and marks the summary `failed` after `APP_SUMMARY_MAX_RETRY` attempts for manual follow-up.

## 3. Data Model Snapshot

| Table | Purpose |
|-------|---------|
| `channels` | Canonical YouTube channels (title, external ID, RSS URL, last polled timestamp) |
| `videos` | Video metadata, transcript status, metadata enrichment fields, summary timestamp |
| `summaries` | TL;DR, highlights, quote, topics, retry/error state (1:1 with `videos`) |
| `subscribers` | Subscriber emails (lowercased, unique) |
| `subscriber_channels` | Many-to-many link between subscribers and channels |

Retry-enabled tables share the schema pattern: `*_status`, `*_retry_count`, `*_next_retry_at`, `*_last_error`, guided by environment caps.

## 4. Configuration Overview

(Refer to `.env.example` for the complete list.)

- **Transcript worker**: `APP_TRANSCRIPT_MAX_RETRY`, `APP_TRANSCRIPT_BACKOFF_MINUTES`, `APP_TRANSCRIPT_MAX_CONCURRENCY`, `APP_TRANSCRIPT_MIN_INTERVAL_MS`
- **Metadata enrichment**: `APP_METADATA_MAX_RETRY`, `APP_METADATA_BACKOFF_MINUTES`
- **Summariser**: `APP_SUMMARY_MAX_RETRY`, `APP_OPENAI_API_KEY`, `APP_OPENAI_MODEL`, `APP_OPENAI_MAX_CHARS`, `APP_OPENAI_BASE_URL`
- **Webhook security**: `APP_WEBHOOK_SECRET`, `APP_WEBHOOK_CALLBACK_URL`

## 5. Operational Notes

- Workers start from FastAPI lifecycle hooks (`app/main.py`). For production, run them as separate processes or containers—the core logic lives in `app/services/*_worker.py` for easy extraction.
- Transcript fetches use shared semaphores + monotonic throttling; metadata/summariser stages use the same backoff pattern to avoid hammering external services.
- Logs include video IDs and trimmed error snippets (LLM responses, scraping results, transcript errors) for manual replay/debugging.
- Summaries rely on the LLM; repeated failures are logged and retried until the job is marked `failed` for manual follow-up.
- Metadata cleaning removes timestamps, extracts sponsors/hashtags/URLs, and stores structured JSON for the summariser prompt.

## 6. Future Enhancements

- Admin UI/CLI to requeue failed transcript/metadata/summary jobs.
- Integration smoke tests that push synthetic webhook payloads and verify summary generation end-to-end.
- Advanced analytics: dashboard for tag/topic frequency, channel performance, subscriber engagement.
- External metadata providers (e.g., official YouTube Data API) to replace HTML scraping if quota allows.

With this architecture, each new YouTube upload automatically progresses through transcript capture, metadata enrichment, and AI-generated summarisation—complete with retry/backoff safety nets at every stage.
