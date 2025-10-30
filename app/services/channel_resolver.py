"""Utilities for normalising YouTube channel identifiers."""

from __future__ import annotations

import re
from urllib.parse import parse_qs, urlparse

import httpx

from app.core.config import settings

CHANNEL_ID_REGEX = re.compile(r"^UC[0-9A-Za-z_-]{22}$")
YOUTUBE_API_BASE = "https://www.googleapis.com/youtube/v3"


class ChannelResolutionError(ValueError):
    """Raised when a channel identifier cannot be normalised."""


def _fetch_channel_id_for_handle(handle: str) -> str:
    """Resolve a YouTube `@handle` into a canonical channel ID via the Data API."""

    api_key = settings.youtube_api_key
    if not api_key:
        raise ChannelResolutionError("Channel handle resolution requires APP_YOUTUBE_API_KEY")

    normalised_handle = handle.lstrip("@").strip()
    if not normalised_handle:
        raise ChannelResolutionError("Invalid YouTube channel handle")

    url = f"{YOUTUBE_API_BASE}/channels"
    params = {
        "part": "id",
        "forHandle": normalised_handle,
        "key": api_key,
    }

    try:
        response = httpx.get(url, params=params, timeout=10)
        response.raise_for_status()
    except httpx.HTTPError as exc:
        raise ChannelResolutionError("Unable to contact YouTube Data API") from exc

    try:
        payload = response.json()
    except ValueError as exc:  # pragma: no cover - defensive for invalid JSON
        raise ChannelResolutionError("Invalid response from YouTube Data API") from exc

    for item in payload.get("items", []):
        channel_id = item.get("id")
        if channel_id and CHANNEL_ID_REGEX.match(channel_id):
            return channel_id

    raise ChannelResolutionError("Channel handle not found")


def extract_channel_id(raw: str) -> str:
    """Normalise user-supplied channel identifiers into canonical YouTube channel IDs.

    Supports:
      * Raw channel IDs (starting with UC)
      * YouTube feed URLs containing `channel_id`
      * Standard channel URLs (`/channel/UC...`)
      * Channel handles (`@name`) via the YouTube Data API (requires APP_YOUTUBE_API_KEY)

    """

    identifier = raw.strip()
    if not identifier:
        raise ChannelResolutionError("Empty channel identifier")

    if CHANNEL_ID_REGEX.match(identifier):
        return identifier

    if identifier.startswith("@"):
        return _fetch_channel_id_for_handle(identifier)

    if identifier.startswith("http://") or identifier.startswith("https://"):
        parsed = urlparse(identifier)
        # Check query param first (feed URLs)
        channel_ids = parse_qs(parsed.query).get("channel_id")
        if channel_ids:
            candidate = channel_ids[-1]
            if CHANNEL_ID_REGEX.match(candidate):
                return candidate

        # Fallback: /channel/UC...
        parts = [part for part in parsed.path.split("/") if part]
        if len(parts) >= 2 and parts[-2] == "channel" and CHANNEL_ID_REGEX.match(parts[-1]):
            return parts[-1]

        raise ChannelResolutionError("Unsupported YouTube URL format")

    raise ChannelResolutionError("Unsupported channel identifier format")
