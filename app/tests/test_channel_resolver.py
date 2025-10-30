import httpx
import pytest

from app.services import channel_resolver


def test_extract_channel_id_passes_through_raw_id() -> None:
    channel_id = "UC" + "A" * 22
    assert channel_resolver.extract_channel_id(channel_id) == channel_id


def test_extract_channel_id_resolves_handle(monkeypatch: pytest.MonkeyPatch) -> None:
    channel_id = "UC" + "B" * 22

    def fake_get(url: str, *, params: dict[str, str] | None = None, timeout: int | None = None) -> httpx.Response:
        assert params is not None
        assert params["forHandle"] == "demo"
        assert params["part"] == "id"
        assert params["key"] == "dummy-key"
        return httpx.Response(
            200,
            json={"items": [{"id": channel_id}]},
            request=httpx.Request("GET", url),
        )

    monkeypatch.setattr(channel_resolver.settings, "youtube_api_key", "dummy-key")
    monkeypatch.setattr(channel_resolver.httpx, "get", fake_get)

    assert channel_resolver.extract_channel_id("@demo") == channel_id


def test_extract_channel_id_handle_requires_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(channel_resolver.settings, "youtube_api_key", None)

    with pytest.raises(channel_resolver.ChannelResolutionError, match="requires APP_YOUTUBE_API_KEY"):
        channel_resolver.extract_channel_id("@demo")


def test_extract_channel_id_handle_not_found(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_get(url: str, *, params: dict[str, str] | None = None, timeout: int | None = None) -> httpx.Response:
        return httpx.Response(
            200,
            json={"items": []},
            request=httpx.Request("GET", url),
        )

    monkeypatch.setattr(channel_resolver.settings, "youtube_api_key", "dummy-key")
    monkeypatch.setattr(channel_resolver.httpx, "get", fake_get)

    with pytest.raises(channel_resolver.ChannelResolutionError, match="not found"):
        channel_resolver.extract_channel_id("@missing")


def test_extract_channel_id_handle_http_error(monkeypatch: pytest.MonkeyPatch) -> None:
    request = httpx.Request("GET", "https://www.googleapis.com/youtube/v3/channels")

    def fake_get(url: str, *, params: dict[str, str] | None = None, timeout: int | None = None) -> httpx.Response:
        raise httpx.ConnectError("boom", request=request)

    monkeypatch.setattr(channel_resolver.settings, "youtube_api_key", "dummy-key")
    monkeypatch.setattr(channel_resolver.httpx, "get", fake_get)

    with pytest.raises(channel_resolver.ChannelResolutionError, match="Unable to contact YouTube Data API"):
        channel_resolver.extract_channel_id("@demo")
