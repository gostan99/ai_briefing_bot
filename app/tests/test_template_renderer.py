"""Tests for the notification email template renderer."""

from datetime import datetime, timezone

from app.db.models import Summary, Video
from app.services.template_renderer import render_notification_email


def test_render_notification_email():
    video = Video(
        id=1,
        channel_id=1,
        youtube_id="abc123",
        title="A Great Video",
        transcript_status="ready",
        created_at=datetime.now(timezone.utc),
    )
    summary = Summary(
        id=1,
        video_id=1,
        tl_dr="Quick takeaways",
        highlights="Point one.\nPoint two.",
        key_quote="Knowledge is power.",
        summary_status="ready",
        created_at=datetime.now(timezone.utc),
    )

    rendered = render_notification_email(video=video, summary=summary)

    assert rendered.subject == "New summary: A Great Video"
    assert "Quick takeaways" in rendered.body
    assert "- Point one." in rendered.body
    assert "Knowledge is power." in rendered.body
    assert "youtube.com/watch?v=abc123" in rendered.body
