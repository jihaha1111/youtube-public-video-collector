from __future__ import annotations

import html
import json
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import httpx
from youtube_transcript_api import YouTubeTranscriptApi


@dataclass(frozen=True)
class TranscriptSegment:
    start: float
    duration: float | None
    text: str

    def to_dict(self) -> dict[str, Any]:
        return {"start": self.start, "duration": self.duration, "text": self.text}


@dataclass(frozen=True)
class CaptionTrack:
    base_url: str
    language_code: str | None
    name: str | None
    is_generated: bool


class PublicTranscriptFetcher:
    """Fetch public caption text exposed on normal YouTube watch pages.

    This does not use owner-only YouTube Analytics/Studio data. Some public
    videos expose no caption tracks, and YouTube can still withhold tracks by
    region, age restriction, or page changes.
    """

    def __init__(self, *, timeout: float = 20.0, preferred_language: str = "ko") -> None:
        self.timeout = timeout
        self.preferred_language = preferred_language
        self.headers = {
            "User-Agent": "Mozilla/5.0",
            "Accept-Language": f"{preferred_language},en;q=0.8",
        }
        self.transcript_api = YouTubeTranscriptApi()

    def fetch_video_transcript(self, video_id: str) -> dict[str, Any]:
        primary = self._fetch_with_transcript_api(video_id)
        if primary["status"] == "found":
            return primary

        fallback = self._fetch_from_watch_page(video_id)
        if fallback["status"] == "found":
            return fallback
        return {**fallback, "errors": [*primary["errors"], *fallback["errors"]]}

    def _fetch_with_transcript_api(self, video_id: str) -> dict[str, Any]:
        try:
            fetched = self.transcript_api.fetch(video_id, languages=[self.preferred_language])
            segments = [
                TranscriptSegment(start=float(snippet.start), duration=float(snippet.duration), text=snippet.text.strip())
                for snippet in fetched
                if snippet.text.strip()
            ]
            if not segments:
                return _missing(video_id, "empty_transcript", "Transcript API returned no text segments.")
            return {
                "video_id": video_id,
                "status": "found",
                "language_code": fetched.language_code,
                "track_name": fetched.language,
                "is_generated": fetched.is_generated,
                "segment_count": len(segments),
                "text": " ".join(segment.text for segment in segments if segment.text).strip(),
                "segments": [segment.to_dict() for segment in segments],
                "errors": [],
            }
        except Exception as exc:  # youtube-transcript-api has a broad public exception hierarchy.
            return _missing(video_id, "transcript_api_error", str(exc))

    def _fetch_from_watch_page(self, video_id: str) -> dict[str, Any]:
        watch_url = f"https://www.youtube.com/watch?v={video_id}"
        try:
            watch_response = httpx.get(watch_url, headers=self.headers, timeout=self.timeout, follow_redirects=True)
            watch_response.raise_for_status()
            tracks = extract_caption_tracks(watch_response.text)
            if not tracks:
                return _missing(video_id, "no_caption_tracks", "No public captionTracks were exposed on the watch page.")
            track = choose_caption_track(tracks, preferred_language=self.preferred_language)
            text_response = httpx.get(track.base_url, headers=self.headers, timeout=self.timeout, follow_redirects=True)
            text_response.raise_for_status()
            segments = parse_timedtext_xml(text_response.text)
            if not segments:
                return _missing(video_id, "empty_transcript", "Caption track returned no text segments.")
            return {
                "video_id": video_id,
                "status": "found",
                "language_code": track.language_code,
                "track_name": track.name,
                "is_generated": track.is_generated,
                "segment_count": len(segments),
                "text": " ".join(segment.text for segment in segments if segment.text).strip(),
                "segments": [segment.to_dict() for segment in segments],
                "errors": [],
            }
        except httpx.HTTPError as exc:
            return _missing(video_id, "network_error", str(exc))
        except ValueError as exc:
            return _missing(video_id, "parse_error", str(exc))


def enrich_collection_with_transcripts(
    collection: dict[str, Any],
    *,
    limit: int = 20,
    preferred_language: str = "ko",
    include_non_shorts: bool = False,
    fetcher: PublicTranscriptFetcher | None = None,
    existing_items: dict[str, dict[str, Any]] | None = None,
    sleep_seconds: float = 0.0,
    stop_on_ip_block: bool = False,
) -> dict[str, Any]:
    fetcher = fetcher or PublicTranscriptFetcher(preferred_language=preferred_language)
    videos = _limit_ranked_videos(collection, include_non_shorts=include_non_shorts, limit=limit)
    transcript_items = []
    stopped_by_ip_block = False
    for index, video in enumerate(videos):
        normalized = video.get("normalized") or {}
        video_id = normalized.get("video_id")
        if not isinstance(video_id, str) or not video_id:
            continue
        cached = existing_items.get(video_id) if existing_items else None
        if cached and (cached.get("transcript") or {}).get("status") == "found":
            transcript = cached["transcript"]
        elif stopped_by_ip_block:
            transcript = _missing(video_id, "skipped_after_ip_block", "Skipped because an earlier transcript request in this run hit an IP-block response.")
        else:
            transcript = fetcher.fetch_video_transcript(video_id)
            if stop_on_ip_block and _looks_like_ip_block(transcript):
                stopped_by_ip_block = True
        transcript_items.append(_video_transcript_item(normalized, transcript))
        if sleep_seconds > 0 and index < len(videos) - 1 and not stopped_by_ip_block:
            time.sleep(sleep_seconds)
    found_count = sum(1 for item in transcript_items if item["transcript"].get("status") == "found")
    return {
        "source_collection": {
            "input_video_id": (collection.get("input") or {}).get("video_id"),
            "collected_at": (collection.get("input") or {}).get("collected_at"),
            "channel": (collection.get("channel") or {}).get("normalized", {}),
            "total_channel_videos": len(collection.get("channel_videos") or []),
        },
        "transcript_collection": {
            "preferred_language": preferred_language,
            "requested_limit": limit,
            "include_non_shorts": include_non_shorts,
            "attempted": len(transcript_items),
            "found": found_count,
            "missing": len(transcript_items) - found_count,
            "reused_from_existing": sum(
                1
                for item in transcript_items
                if (existing_items or {}).get(item["video_id"], {}).get("transcript", {}).get("status") == "found"
                and item["transcript"].get("status") == "found"
            ),
            "stopped_by_ip_block": stopped_by_ip_block,
        },
        "videos": transcript_items,
    }


def enrich_collection_file(
    collection_path: str | Path,
    out_path: str | Path,
    *,
    limit: int = 20,
    preferred_language: str = "ko",
    include_non_shorts: bool = False,
    existing_path: str | Path | None = None,
    sleep_seconds: float = 0.0,
    stop_on_ip_block: bool = False,
) -> Path:
    collection = json.loads(Path(collection_path).read_text(encoding="utf-8"))
    if isinstance(collection, list):
        if len(collection) != 1:
            raise ValueError("transcript enrichment expects a single collection result object")
        collection = collection[0]
    if not isinstance(collection, dict):
        raise ValueError("collection JSON must be an object")
    existing_items = _load_existing_items(existing_path) if existing_path else None
    enriched = enrich_collection_with_transcripts(
        collection,
        limit=limit,
        preferred_language=preferred_language,
        include_non_shorts=include_non_shorts,
        existing_items=existing_items,
        sleep_seconds=sleep_seconds,
        stop_on_ip_block=stop_on_ip_block,
    )
    output = Path(out_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(enriched, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return output


def extract_caption_tracks(html_text: str) -> list[CaptionTrack]:
    marker = '"captionTracks":'
    marker_index = html_text.find(marker)
    if marker_index < 0:
        return []
    start_index = marker_index + len(marker)
    try:
        tracks_payload, _end = json.JSONDecoder().raw_decode(html_text[start_index:])
    except json.JSONDecodeError as exc:
        raise ValueError(f"could not decode captionTracks JSON: {exc}") from exc
    if not isinstance(tracks_payload, list):
        return []
    tracks: list[CaptionTrack] = []
    for item in tracks_payload:
        if not isinstance(item, dict):
            continue
        base_url = item.get("baseUrl")
        if not isinstance(base_url, str) or not _is_youtube_timedtext_url(base_url):
            continue
        name = _caption_name(item.get("name"))
        language_code = item.get("languageCode") if isinstance(item.get("languageCode"), str) else None
        vss_id = item.get("vssId") if isinstance(item.get("vssId"), str) else ""
        kind = item.get("kind") if isinstance(item.get("kind"), str) else ""
        tracks.append(
            CaptionTrack(
                base_url=html.unescape(base_url),
                language_code=language_code,
                name=name,
                is_generated=kind == "asr" or vss_id.startswith("a."),
            )
        )
    return tracks


def choose_caption_track(tracks: list[CaptionTrack], *, preferred_language: str = "ko") -> CaptionTrack:
    if not tracks:
        raise ValueError("no caption tracks available")
    for track in tracks:
        if track.language_code == preferred_language:
            return track
    for track in tracks:
        if (track.language_code or "").split("-")[0] == preferred_language.split("-")[0]:
            return track
    return tracks[0]


def parse_timedtext_xml(xml_text: str) -> list[TranscriptSegment]:
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as exc:
        raise ValueError(f"could not parse timedtext XML: {exc}") from exc
    segments: list[TranscriptSegment] = []
    for node in root.iter("text"):
        text = "".join(node.itertext()).strip()
        if not text:
            continue
        start = _float_attr(node, "start")
        if start is None:
            continue
        segments.append(
            TranscriptSegment(
                start=start,
                duration=_float_attr(node, "dur"),
                text=html.unescape(text),
            )
        )
    return segments


def _video_transcript_item(normalized: dict[str, Any], transcript: dict[str, Any]) -> dict[str, Any]:
    return {
        "video_id": normalized.get("video_id"),
        "title": normalized.get("title"),
        "canonical_watch_url": normalized.get("canonical_watch_url"),
        "canonical_shorts_url": normalized.get("canonical_shorts_url"),
        "view_count": normalized.get("view_count"),
        "like_count": normalized.get("like_count"),
        "comment_count": normalized.get("comment_count"),
        "published_at": normalized.get("published_at"),
        "duration_seconds": normalized.get("duration_seconds"),
        "rank_by_views_in_collected_channel_videos": normalized.get("rank_by_views_in_collected_channel_videos"),
        "transcript": transcript,
    }


def _load_existing_items(existing_path: str | Path) -> dict[str, dict[str, Any]]:
    payload = json.loads(Path(existing_path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("existing transcript JSON must be an object")
    items = payload.get("videos")
    if not isinstance(items, list):
        raise ValueError("existing transcript JSON must contain a videos array")
    return {
        item["video_id"]: item
        for item in items
        if isinstance(item, dict) and isinstance(item.get("video_id"), str)
    }


def _looks_like_ip_block(transcript: dict[str, Any]) -> bool:
    if transcript.get("status") == "found":
        return False
    errors = transcript.get("errors")
    if not isinstance(errors, list):
        return False
    text = " ".join(
        str(error.get("message", "")) + " " + str(error.get("code", ""))
        for error in errors
        if isinstance(error, dict)
    ).lower()
    return "blocking requests from your ip" in text or "ip has been blocked" in text or "too many requests" in text


def _limit_ranked_videos(collection: dict[str, Any], *, include_non_shorts: bool, limit: int) -> list[dict[str, Any]]:
    videos = _ranked_videos(collection, include_non_shorts=include_non_shorts)
    return videos if limit == 0 else videos[:limit]


def _ranked_videos(collection: dict[str, Any], *, include_non_shorts: bool) -> list[dict[str, Any]]:
    videos = list(collection.get("channel_videos") or [])
    if not include_non_shorts:
        videos = [video for video in videos if (video.get("normalized") or {}).get("is_probably_short")]
    return sorted(videos, key=lambda video: ((video.get("normalized") or {}).get("view_count") or 0), reverse=True)


def _caption_name(value: Any) -> str | None:
    if isinstance(value, dict):
        if isinstance(value.get("simpleText"), str):
            return value["simpleText"]
        runs = value.get("runs")
        if isinstance(runs, list):
            text = "".join(run.get("text", "") for run in runs if isinstance(run, dict))
            return text or None
    return None


def _float_attr(node: ET.Element, name: str) -> float | None:
    value = node.attrib.get(name)
    if value is None:
        return None
    try:
        return float(value)
    except ValueError:
        return None


def _is_youtube_timedtext_url(value: str) -> bool:
    host = urlparse(value).netloc.lower()
    return host.endswith("youtube.com") and "/api/timedtext" in value


def _missing(video_id: str, code: str, message: str) -> dict[str, Any]:
    return {
        "video_id": video_id,
        "status": "missing",
        "language_code": None,
        "track_name": None,
        "is_generated": None,
        "segment_count": 0,
        "text": "",
        "segments": [],
        "errors": [{"code": code, "message": message}],
    }
