from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import parse_qs, unquote, urlparse

from .errors import UrlParseError

VIDEO_ID_RE = re.compile(r"^[A-Za-z0-9_-]{11}$")


@dataclass(frozen=True, slots=True)
class ParsedYouTubeUrl:
    raw_url: str
    video_id: str
    is_shorts_url: bool
    canonical_watch_url: str
    canonical_shorts_url: str
    embed_url: str


def parse_youtube_url(raw_url: str) -> ParsedYouTubeUrl:
    """Extract a YouTube video id from public watch, shorts, and youtu.be URLs."""
    candidate_url = (raw_url or "").strip()
    if not candidate_url:
        raise UrlParseError("YouTube URL is empty.")

    if "://" not in candidate_url:
        candidate_url = f"https://{candidate_url}"

    parsed = urlparse(candidate_url)
    host = parsed.netloc.lower().split("@")[-1].split(":")[0]
    path_parts = [unquote(part) for part in parsed.path.split("/") if part]
    query = parse_qs(parsed.query)

    video_id: str | None = None
    is_shorts_url = False

    if host == "youtu.be":
        video_id = path_parts[0] if path_parts else None
    elif host == "youtube.com" or host.endswith(".youtube.com"):
        for value in query.get("v", []):
            if _is_valid_video_id(value):
                video_id = value
                break

        if video_id is None and len(path_parts) >= 2:
            section = path_parts[0].lower()
            if section == "shorts":
                is_shorts_url = True
                video_id = path_parts[1]
            elif section in {"embed", "live"}:
                video_id = path_parts[1]
    else:
        raise UrlParseError(f"Unsupported YouTube host: {host or '(missing host)'}.")

    if path_parts and path_parts[0].lower() == "shorts":
        is_shorts_url = True

    if not _is_valid_video_id(video_id):
        raise UrlParseError("Could not extract a valid 11-character YouTube videoId from the URL.")

    assert video_id is not None
    return ParsedYouTubeUrl(
        raw_url=raw_url,
        video_id=video_id,
        is_shorts_url=is_shorts_url,
        canonical_watch_url=f"https://www.youtube.com/watch?v={video_id}",
        canonical_shorts_url=f"https://www.youtube.com/shorts/{video_id}",
        embed_url=f"https://www.youtube.com/embed/{video_id}",
    )


def extract_video_id(raw_url: str) -> str:
    return parse_youtube_url(raw_url).video_id


def _is_valid_video_id(value: str | None) -> bool:
    return bool(value and VIDEO_ID_RE.fullmatch(value))
