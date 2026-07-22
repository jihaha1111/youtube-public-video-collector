from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import unquote, urlparse

from .errors import UrlParseError


CHANNEL_ID_RE = re.compile(r"^UC[A-Za-z0-9_-]{22}$")


@dataclass(frozen=True, slots=True)
class ParsedYouTubeChannelUrl:
    raw_url: str
    channel_id: str | None
    handle: str | None
    canonical_channel_url: str


def parse_youtube_channel_url(raw_url: str) -> ParsedYouTubeChannelUrl:
    """Parse public YouTube /channel/UC... and /@handle channel URLs."""
    candidate = (raw_url or "").strip()
    if not candidate:
        raise UrlParseError("YouTube channel URL is empty.")

    if CHANNEL_ID_RE.fullmatch(candidate):
        return _from_channel_id(raw_url, candidate)
    if candidate.startswith("@") and len(candidate) > 1:
        return _from_handle(raw_url, candidate[1:])

    if "://" not in candidate:
        candidate = f"https://{candidate}"

    parsed = urlparse(candidate)
    host = parsed.netloc.lower().split("@")[-1].split(":")[0]
    if not (host == "youtube.com" or host.endswith(".youtube.com")):
        raise UrlParseError(f"Unsupported YouTube host: {host or '(missing host)'}.")

    path_parts = [unquote(part) for part in parsed.path.split("/") if part]
    if not path_parts:
        raise UrlParseError("Could not extract a YouTube channel ID or handle from the URL.")

    first = path_parts[0]
    if first.startswith("@") and len(first) > 1:
        return _from_handle(raw_url, first[1:])
    if first.lower() == "channel" and len(path_parts) >= 2 and CHANNEL_ID_RE.fullmatch(path_parts[1]):
        return _from_channel_id(raw_url, path_parts[1])

    raise UrlParseError("Only public YouTube /channel/UC... and /@handle channel URLs are supported.")


def _from_channel_id(raw_url: str, channel_id: str) -> ParsedYouTubeChannelUrl:
    return ParsedYouTubeChannelUrl(
        raw_url=raw_url,
        channel_id=channel_id,
        handle=None,
        canonical_channel_url=f"https://www.youtube.com/channel/{channel_id}",
    )


def _from_handle(raw_url: str, handle: str) -> ParsedYouTubeChannelUrl:
    normalized = handle.strip().strip("/")
    if not normalized or any(character.isspace() for character in normalized):
        raise UrlParseError("YouTube channel handle is empty or contains whitespace.")
    return ParsedYouTubeChannelUrl(
        raw_url=raw_url,
        channel_id=None,
        handle=normalized,
        canonical_channel_url=f"https://www.youtube.com/@{normalized}",
    )
