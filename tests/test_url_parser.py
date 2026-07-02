from __future__ import annotations

import pytest

from yt_collector.errors import UrlParseError
from yt_collector.url_parser import extract_video_id, parse_youtube_url


@pytest.mark.parametrize(
    ("raw_url", "is_shorts"),
    [
        ("https://www.youtube.com/watch?v=onjVWrO2_5E", False),
        ("https://youtube.com/watch?feature=share&v=onjVWrO2_5E&t=12", False),
        ("https://www.youtube.com/shorts/onjVWrO2_5E", True),
        ("https://youtu.be/onjVWrO2_5E?si=mock", False),
        ("youtube.com/watch?v=onjVWrO2_5E", False),
    ],
)
def test_parse_supported_urls(raw_url: str, is_shorts: bool) -> None:
    parsed = parse_youtube_url(raw_url)

    assert parsed.video_id == "onjVWrO2_5E"
    assert parsed.is_shorts_url is is_shorts
    assert parsed.canonical_watch_url == "https://www.youtube.com/watch?v=onjVWrO2_5E"
    assert parsed.canonical_shorts_url == "https://www.youtube.com/shorts/onjVWrO2_5E"
    assert parsed.embed_url == "https://www.youtube.com/embed/onjVWrO2_5E"
    assert extract_video_id(raw_url) == "onjVWrO2_5E"


@pytest.mark.parametrize(
    "raw_url",
    [
        "",
        "https://example.com/watch?v=onjVWrO2_5E",
        "https://www.youtube.com/watch?feature=share",
        "https://www.youtube.com/watch?v=short",
        "https://youtu.be/not-a-valid-video-id",
    ],
)
def test_parse_invalid_urls(raw_url: str) -> None:
    with pytest.raises(UrlParseError):
        parse_youtube_url(raw_url)
