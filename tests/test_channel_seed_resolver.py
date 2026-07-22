from __future__ import annotations

from yt_collector.channel_seed_resolver import resolve_channel_seeds
from yt_collector.mock_client import MockYouTubeClient


def test_resolve_channel_handle_to_official_identity_and_seed_video() -> None:
    payload = resolve_channel_seeds(
        ["https://www.youtube.com/@cookietime-l5w/shorts"],
        MockYouTubeClient(),
    )

    assert payload["input_count"] == 1
    assert payload["resolved_count"] == 1
    assert payload["error_count"] == 0
    result = payload["channels"][0]
    assert result["status"] == "resolved"
    assert result["requested_handle"] == "cookietime-l5w"
    assert result["channel"]["normalized"]["channel_id"].startswith("UC")
    assert result["seed_video"]["canonical_watch_url"].startswith("https://www.youtube.com/watch?v=")


def test_resolve_channel_id_input() -> None:
    payload = resolve_channel_seeds(
        ["https://www.youtube.com/channel/UC4Qd6YqA1slSltXRavnNtYw"],
        MockYouTubeClient(),
    )

    result = payload["channels"][0]
    assert result["status"] == "resolved"
    assert result["requested_channel_id"] == "UC4Qd6YqA1slSltXRavnNtYw"


def test_invalid_channel_input_is_preserved_as_error() -> None:
    payload = resolve_channel_seeds(["https://example.com/not-youtube"], MockYouTubeClient())

    assert payload["resolved_count"] == 0
    assert payload["error_count"] == 1
    assert payload["channels"][0]["errors"][0]["code"] == "invalid_channel_url"
