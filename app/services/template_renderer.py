"""Email template rendering utilities."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from app.db.models import Summary, Video

_TEMPLATE_DIR = Path(__file__).resolve().parent.parent / "templates"

_env = Environment(
    loader=FileSystemLoader(str(_TEMPLATE_DIR)),
    autoescape=select_autoescape(disabled_extensions=("txt",)),
)


@dataclass(slots=True)
class RenderedEmail:
    """Represents a rendered email template."""

    subject: str
    body: str


def render_notification_email(*, video: Video, summary: Summary) -> RenderedEmail:
    """Render the notification email for a given video/summary pair."""

    template = _env.get_template("notification_email.txt.jinja")
    subject = f"New summary: {video.title}"
    body = template.render(video=video, summary=summary)
    return RenderedEmail(subject=subject, body=body)

