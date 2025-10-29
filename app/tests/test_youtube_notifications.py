"""Unit tests for YouTube WebSub notification parsing."""

from __future__ import annotations

import pytest

from app.services.youtube_notifications import WebhookParseError, parse_notifications


def test_parse_notifications_extracts_entry():
    payload = (
        """
        <feed xmlns="http://www.w3.org/2005/Atom"
              xmlns:yt="http://www.youtube.com/xml/schemas/2015"
              xmlns:media="http://search.yahoo.com/mrss/">
          <title>YouTube channel title</title>
          <entry>
            <id>tag:youtube.com,2008:video:VIDEO123</id>
            <yt:videoId>VIDEO123</yt:videoId>
            <yt:channelId>UCTESTCHANNEL</yt:channelId>
            <title>Sample Video</title>
            <author>
              <name>Sample Channel</name>
            </author>
            <media:group>
              <media:description>Example description</media:description>
            </media:group>
            <published>2024-07-16T12:00:00Z</published>
            <updated>2024-07-16T12:05:00Z</updated>
          </entry>
        </feed>
        """
    ).strip()

    notifications = parse_notifications(payload.encode())

    assert len(notifications) == 1
    note = notifications[0]
    assert note.channel_id == "UCTESTCHANNEL"
    assert note.video_id == "VIDEO123"
    assert note.channel_title == "Sample Channel"
    assert note.video_title == "Sample Video"
    assert note.description == "Example description"
    assert note.published_at.isoformat() == "2024-07-16T12:00:00+00:00"
    assert note.updated_at.isoformat() == "2024-07-16T12:05:00+00:00"


def test_parse_notifications_invalid_xml():
    with pytest.raises(WebhookParseError):
        parse_notifications(b"<not-xml>")

