"""Utilities for normalising YouTube channel identifiers."""

from __future__ import annotations

import re
from urllib.parse import parse_qs, urlparse

CHANNEL_ID_REGEX = re.compile(r"^UC[0-9A-Za-z_-]{22}$")


class ChannelResolutionError(ValueError):
    """Raised when a channel identifier cannot be normalised."""


def extract_channel_id(raw: str) -> str:
    """Normalise user-supplied channel identifiers into canonical YouTube channel IDs.

    Supports:
      * Raw channel IDs (starting with UC)
      * YouTube feed URLs containing `channel_id`
      * Standard channel URLs (`/channel/UC...`)

    Channel handles (`@name`) and custom vanity URLs require a Data API lookup and
    are not handled yet; callers should surface a validation error to the user.
    """

    identifier = raw.strip()
    if not identifier:
        raise ChannelResolutionError("Empty channel identifier")

    if CHANNEL_ID_REGEX.match(identifier):
        return identifier

    if identifier.startswith("@"):  # TODO: resolve via YouTube Data API
        raise ChannelResolutionError("Channel handles are not supported yet")  # TODO(@future): support handles

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
