"""Utilities for generating video summaries."""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from functools import lru_cache

from openai import OpenAI

from app.core.config import settings

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class SummaryResult:
    """Represents a generated summary."""

    tl_dr: str
    highlights: list[str]
    key_quote: str | None


def _split_sentences(text: str) -> list[str]:
    text = text.strip()
    if not text:
        return []
    sentences = re.split(r"(?<=[.!?])\s+", text)
    return [sentence.strip() for sentence in sentences if sentence.strip()]


def generate_summary_from_transcript(transcript: str, metadata: dict | None = None) -> SummaryResult:
    """Heuristic summariser used when no LLM is configured."""

    sentences = _split_sentences(transcript)
    if not sentences:
        raise ValueError("Transcript is empty")

    tl_dr = " ".join(sentences[:2]) if len(sentences) > 1 else sentences[0]

    highlights: list[str] = []
    for sentence in sentences:
        if len(highlights) >= 4:
            break
        highlights.append(sentence)

    key_quote = max(sentences, key=len)
    return SummaryResult(tl_dr=tl_dr, highlights=highlights, key_quote=key_quote)


@lru_cache
def _get_openai_client() -> OpenAI:
    if not settings.openai_api_key:
        raise ValueError("OpenAI API key is not configured")
    kwargs: dict[str, str] = {"api_key": settings.openai_api_key}
    if settings.openai_base_url:
        kwargs["base_url"] = settings.openai_base_url
    return OpenAI(**kwargs)


def generate_summary_via_openai(transcript: str, metadata: dict | None = None) -> SummaryResult:
    """Generate a summary using OpenAI Responses API."""

    if not settings.openai_api_key:
        raise ValueError("OpenAI API key is not configured")

    client = _get_openai_client()
    prompt = (
        "Summarise the following transcript."
        " Produce a concise tl_dr under 60 words, a list of 3-5 key highlights,"
        " and a single notable quote (or null if unavailable)."
        " Return JSON with keys tl_dr (string), highlights (array of strings), key_quote (string or null)."
        " Do not include text outside the JSON object."
    )
    clipped_transcript = transcript[: settings.openai_max_chars]

    metadata_context = ""
    if metadata:
        lines: list[str] = []
        tags = metadata.get("tags")
        if tags:
            tags_str = ", ".join(tags) if isinstance(tags, list) else str(tags)
            lines.append(f"Tags: {tags_str}")
        hashtags = metadata.get("hashtags")
        if hashtags:
            hashtags_str = ", ".join(hashtags) if isinstance(hashtags, list) else str(hashtags)
            lines.append(f"Hashtags: {hashtags_str}")
        sponsors = metadata.get("sponsors")
        if sponsors:
            sponsors_str = "; ".join(sponsors) if isinstance(sponsors, list) else str(sponsors)
            lines.append(f"Sponsor mentions: {sponsors_str}")
        clean_description = metadata.get("clean_description") or metadata.get("description")
        if clean_description:
            description = str(clean_description)
            if len(description) > 1000:
                description = description[:1000] + "…"
            lines.append(f"Description snippet: {description}")
        if lines:
            metadata_context = "\n".join(lines)

    response = client.responses.create(
        model=settings.openai_model,
        input=[
            {"role": "system", "content": "You are an expert executive briefing assistant."},
            {
                "role": "user",
                "content": (
                    f"{prompt}\n\nTranscript:\n{clipped_transcript}"
                    + (f"\n\nMetadata:\n{metadata_context}" if metadata_context else "")
                ),
            },
        ],
    )

    try:
        raw_text = getattr(response, "output_text", "") or ""
        if not raw_text:
            chunks: list[str] = []
            for item in getattr(response, "output", []) or []:
                for piece in getattr(item, "content", []) or []:
                    text = getattr(piece, "text", None)
                    if text:
                        chunks.append(text)
            raw_text = "".join(chunks)

        content = (raw_text or "").strip()
        if content.startswith("```"):
            # Handle responses wrapped in Markdown code fences
            content = content.strip("`\n")
            if content.startswith("json"):
                content = content[4:].strip()

        payload = json.loads(content)
    except Exception as exc:  # pragma: no cover - defensive guard
        logger.exception(
            "Failed to parse LLM summary response",
            extra={"snippet": content[:200] if 'content' in locals() else ""},
        )
        raise RuntimeError("Unable to parse LLM response") from exc

    highlights = payload.get("highlights") or []
    if not isinstance(highlights, list):
        highlights = [str(highlights)]

    return SummaryResult(
        tl_dr=str(payload.get("tl_dr", "")).strip(),
        highlights=[str(item).strip() for item in highlights if str(item).strip()],
        key_quote=(payload.get("key_quote") or None),
    )


__all__ = [
    "SummaryResult",
    "generate_summary_from_transcript",
    "generate_summary_via_openai",
    "_split_sentences",
]
