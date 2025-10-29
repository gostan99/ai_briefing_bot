"""Background worker that dispatches email notifications."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
import smtplib
import ssl
from typing import Awaitable, Callable
from urllib.parse import unquote, urlparse

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import settings
from app.services.template_renderer import render_notification_email
from app.db.models import NotificationJob, Summary, Subscriber, Video
from app.db.session import SessionLocal

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class EmailPayload:
    """Represents an outbound email message."""

    to: str
    subject: str
    body: str


async def dummy_email_sender(payload: EmailPayload) -> None:
    """Placeholder email sender that just logs the payload."""

    logger.info("Sending email (dummy)", extra={"to": payload.to, "subject": payload.subject})


def _build_smtp_sender(url: str, from_address: str) -> Callable[[EmailPayload], Awaitable[None]]:
    parsed = urlparse(url)
    if not parsed.hostname:
        raise ValueError("SMTP URL missing hostname")

    scheme = (parsed.scheme or "smtp").lower()
    host = parsed.hostname
    port = parsed.port or (465 if scheme == "smtps" else 587)
    username = unquote(parsed.username) if parsed.username else None
    password = unquote(parsed.password) if parsed.password else None

    use_ssl = scheme == "smtps"
    use_starttls = scheme in {"smtp", "submission"} and not use_ssl

    def _send(payload: EmailPayload) -> None:
        message = EmailMessage()
        message["From"] = from_address
        message["To"] = payload.to
        message["Subject"] = payload.subject
        message.set_content(payload.body)

        if use_ssl:
            context = ssl.create_default_context()
            with smtplib.SMTP_SSL(host, port, context=context) as smtp:
                if username:
                    smtp.login(username, password or "")
                smtp.send_message(message)
        else:
            with smtplib.SMTP(host, port) as smtp:
                smtp.ehlo()
                if use_starttls:
                    context = ssl.create_default_context()
                    smtp.starttls(context=context)
                    smtp.ehlo()
                if username:
                    smtp.login(username, password or "")
                smtp.send_message(message)

    async def _async_send(payload: EmailPayload) -> None:
        await asyncio.to_thread(_send, payload)

    return _async_send


def _compute_backoff(base_minutes: int, retry_count: int) -> timedelta:
    base_minutes = max(base_minutes, 1)
    exponent = max(retry_count - 1, 0)
    return timedelta(minutes=base_minutes * (2**exponent))


def _apply_delivery_success(job: NotificationJob) -> None:
    now = datetime.now(timezone.utc)
    job.status = "delivered"
    job.retry_count = 0
    job.next_retry_at = None
    job.last_error = None
    job.delivered_at = now


def _apply_delivery_failure(job: NotificationJob, error: Exception) -> None:
    job.retry_count += 1
    job.last_error = str(error)

    if job.retry_count >= settings.notify_max_retry:
        job.status = "failed"
        job.next_retry_at = None
        return

    job.status = "pending"
    delay = _compute_backoff(settings.notify_backoff_minutes, job.retry_count)
    job.next_retry_at = datetime.now(timezone.utc) + delay


async def process_pending_notifications(
    session: AsyncSession,
    *,
    batch_size: int = 10,
    sender: Callable[[EmailPayload], Awaitable[None]] | None = None,
) -> list[NotificationJob]:
    """Send email notifications for pending jobs."""

    now = datetime.now(timezone.utc)
    stmt = (
        select(NotificationJob)
        .options(
            selectinload(NotificationJob.subscriber),
            selectinload(NotificationJob.video).selectinload(Video.summary),
        )
        .where(
            NotificationJob.status == "pending",
            or_(NotificationJob.next_retry_at == None, NotificationJob.next_retry_at <= now),
        )
        .order_by(NotificationJob.next_retry_at, NotificationJob.id)
        .limit(batch_size)
    )

    result = await session.execute(stmt)
    jobs = list(result.scalars())

    processed: list[NotificationJob] = []
    active_sender = sender or dummy_email_sender

    for job in jobs:
        if not job.video or not job.subscriber:
            logger.warning(
                "Notification job missing relations", extra={"job_id": job.id}
            )
            _apply_delivery_failure(job, RuntimeError("Missing related data"))
            processed.append(job)
            continue

        summary: Summary | None = job.video.summary
        if summary is None or summary.summary_status != "ready":
            logger.info(
                "Summary not ready; skipping notification",
                extra={"job_id": job.id, "video_id": job.video.youtube_id},
            )
            continue

        if not job.subscriber.email:
            _apply_delivery_failure(job, RuntimeError("Subscriber email missing"))
            processed.append(job)
            continue

        rendered = render_notification_email(video=job.video, summary=summary)
        payload = EmailPayload(
            to=job.subscriber.email,
            subject=rendered.subject,
            body=rendered.body,
        )

        try:
            await active_sender(payload)
            _apply_delivery_success(job)
        except Exception as exc:  # pragma: no cover - network dependent
            logger.exception(
                "Failed to send email",
                extra={"job_id": job.id, "video_id": job.video.youtube_id},
            )
            _apply_delivery_failure(job, exc)

        processed.append(job)

    await session.flush()
    return processed


class NotificationWorker:
    """Background loop that dispatches notification emails."""

    def __init__(self) -> None:
        self._task: asyncio.Task | None = None
        self._stop_event = asyncio.Event()
        self._sender: Callable[[EmailPayload], Awaitable[None]] | None = None

    def configure_sender(self) -> None:
        if settings.email_smtp_url and settings.email_from:
            try:
                self._sender = _build_smtp_sender(settings.email_smtp_url, settings.email_from)
                logger.info(
                    "Notification worker configured SMTP sender",
                    extra={"host": urlparse(settings.email_smtp_url).hostname},
                )
                return
            except Exception as exc:  # pragma: no cover - configuration guard
                logger.exception("Failed to configure SMTP sender", extra={"error": str(exc)})
        else:
            if not settings.email_smtp_url:
                logger.info("No SMTP URL configured; using dummy sender")
            elif not settings.email_from:
                logger.info("No email from address configured; using dummy sender")
        self._sender = dummy_email_sender

    async def _run(self) -> None:
        idle_sleep = 30
        active_sleep = 5

        while not self._stop_event.is_set():
            try:
                async with SessionLocal() as session:
                    jobs = await process_pending_notifications(session, sender=self._sender)
                    if jobs:
                        await session.commit()
                    else:
                        await session.rollback()
            except Exception:  # pragma: no cover - defensive guard
                logger.exception("Notification worker iteration failed")
                await asyncio.sleep(idle_sleep)
                continue

            await asyncio.sleep(active_sleep if jobs else idle_sleep)

    def start(self) -> None:
        if self._task is not None and not self._task.done():
            return
        self._stop_event.clear()
        self._task = asyncio.create_task(self._run())

    async def stop(self) -> None:
        if self._task is None:
            return
        self._stop_event.set()
        self._task.cancel()
        try:
            await self._task
        except asyncio.CancelledError:  # pragma: no cover - event loop behaviour
            pass
        finally:
            self._task = None


notification_worker = NotificationWorker()


def start_notification_worker() -> None:
    """Start the notification worker."""

    notification_worker.configure_sender()
    notification_worker.start()


async def stop_notification_worker() -> None:
    """Stop the notification worker."""

    await notification_worker.stop()
