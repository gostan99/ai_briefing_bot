"""Tests for metadata scraping helpers."""

from app.services.metadata_worker import _clean_description, _normalise_tags


def test_normalise_tags_deduplicates_and_lowercases():
    raw = "Python, AI ,python , Data Science"
    assert _normalise_tags(raw) == ["ai", "data science", "python"]


def test_clean_description_strips_timestamps_urls_hashtags():
    raw = """
00:00 Intro
Check the sponsor Acme Corp at https://example.com #Coding
Real content line.
"""
    cleaned, hashtags, urls, sponsors = _clean_description(raw)
    assert "Intro" not in cleaned
    assert "Real content line." in cleaned
    assert hashtags == ["coding"]
    assert urls == ["https://example.com"]
    assert sponsors == ["Check the sponsor Acme Corp at https://example.com #Coding"]
