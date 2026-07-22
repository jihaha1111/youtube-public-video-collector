from __future__ import annotations

import pytest

from yt_collector.channel_url_parser import parse_youtube_channel_url
from yt_collector.errors import UrlParseError


@pytest.mark.parametrize(
    ("raw_url", "channel_id", "handle"),
    [
        ("https://www.youtube.com/channel/UC4Qd6YqA1slSltXRavnNtYw", "UC4Qd6YqA1slSltXRavnNtYw", None),
        ("https://www.youtube.com/@cookietime-l5w/shorts", None, "cookietime-l5w"),
        ("https://www.youtube.com/@%EB%A7%9B%EB%B3%B4%EB%9D%BC1/shorts", None, "맛보라1"),
        ("@Fooddogam", None, "Fooddogam"),
        ("UCY1UjUS4zg2Eh6AmHt48wJw", "UCY1UjUS4zg2Eh6AmHt48wJw", None),
    ],
)
def test_parse_supported_channel_urls(raw_url: str, channel_id: str | None, handle: str | None) -> None:
    parsed = parse_youtube_channel_url(raw_url)

    assert parsed.channel_id == channel_id
    assert parsed.handle == handle


@pytest.mark.parametrize(
    "raw_url",
    [
        "",
        "https://example.com/@Fooddogam",
        "https://www.youtube.com/c/legacy-custom-url",
        "https://www.youtube.com/watch?v=onjVWrO2_5E",
        "@bad handle",
    ],
)
def test_parse_invalid_channel_urls(raw_url: str) -> None:
    with pytest.raises(UrlParseError):
        parse_youtube_channel_url(raw_url)
