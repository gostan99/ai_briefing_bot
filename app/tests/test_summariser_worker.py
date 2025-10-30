"""Unit tests for summariser utilities."""

from __future__ import annotations

import pytest

from app.services.summariser_utils import SummaryResult, generate_summary_via_openai


def test_generate_summary_raises_without_api_key(monkeypatch):
    monkeypatch.setattr("app.services.summariser_utils.settings.openai_api_key", None)
    with pytest.raises(ValueError):
        generate_summary_via_openai("Sample transcript")


def test_summary_result_dataclass():
    result = SummaryResult(tl_dr="Summary", highlights=["Point"], key_quote="Quote")
    assert result.tl_dr == "Summary"
    assert result.highlights == ["Point"]
    assert result.key_quote == "Quote"
