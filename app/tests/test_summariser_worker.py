"""Unit tests for summariser helper functions."""

from __future__ import annotations

import pytest

from app.services.summariser_utils import _split_sentences, generate_summary_from_transcript


def test_split_sentences_handles_basic_punctuation():
    sentences = _split_sentences("Hello world. This is a test! Are you sure?")
    assert sentences == ["Hello world.", "This is a test!", "Are you sure?"]


def test_generate_summary_returns_key_fields():
    transcript = "One. Two. Three. Four."
    result = generate_summary_from_transcript(transcript)
    assert result.tl_dr.startswith("One.")
    assert len(result.highlights) >= 1
    assert result.key_quote


def test_generate_summary_raises_for_empty_transcript():
    with pytest.raises(ValueError):
        generate_summary_from_transcript("\n   \n")
