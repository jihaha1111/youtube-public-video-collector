from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any, Callable

from .transcripts import (
    CaptionTrack,
    PublicTranscriptFetcher,
    _ranked_videos,
    _video_transcript_item,
    choose_caption_track,
    extract_caption_tracks,
    parse_timedtext_xml,
)
from .url_parser import parse_youtube_url

CaptionXmlFetcher = Callable[[str], str]
ScraplingTranscriptFetcher = Callable[[str], dict[str, Any]]


def fetch_transcript_with_scrapling(
    raw_url: str,
    *,
    preferred_language: str = "ko",
    timeout_ms: int = 90_000,
    wait_ms: int = 5_000,
    headless: bool = True,
    proxy: str | None = None,
) -> dict[str, Any]:
    """Fetch one public YouTube transcript through Scrapling's browser fetcher."""
    parsed_url = parse_youtube_url(raw_url)
    response = _fetch_watch_page(
        parsed_url.canonical_watch_url,
        preferred_language=preferred_language,
        timeout_ms=timeout_ms,
        wait_ms=wait_ms,
        headless=headless,
        proxy=proxy,
    )
    transcript = extract_transcript_from_scrapling_response(
        parsed_url.video_id,
        response,
        preferred_language=preferred_language,
        proxy=proxy,
    )
    if transcript.get("status") != "found" and _has_error_code(transcript, "no_caption_tracks"):
        fallback = PublicTranscriptFetcher(preferred_language=preferred_language).fetch_video_transcript(parsed_url.video_id)
        if fallback.get("status") == "found":
            transcript = {**fallback, "source": "youtube_transcript_api_after_scrapling_no_caption_tracks"}
        else:
            transcript = {
                **fallback,
                "source": "youtube_transcript_api_after_scrapling_no_caption_tracks",
                "errors": [*transcript.get("errors", []), *fallback.get("errors", [])],
            }
    return {
        "input": {
            "url": raw_url,
            "canonical_watch_url": parsed_url.canonical_watch_url,
            "video_id": parsed_url.video_id,
            "preferred_language": preferred_language,
            "fetcher": "scrapling.StealthyFetcher",
            "timeout_ms": timeout_ms,
            "wait_ms": wait_ms,
            "headless": headless,
            "used_proxy": bool(proxy),
        },
        "transcript": transcript,
    }


def write_scrapling_transcript_probe(
    raw_url: str,
    out_path: str | Path,
    *,
    preferred_language: str = "ko",
    timeout_ms: int = 90_000,
    wait_ms: int = 5_000,
    headless: bool = True,
    proxy: str | None = None,
) -> Path:
    result = fetch_transcript_with_scrapling(
        raw_url,
        preferred_language=preferred_language,
        timeout_ms=timeout_ms,
        wait_ms=wait_ms,
        headless=headless,
        proxy=proxy,
    )
    output = Path(out_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return output
def enrich_collection_with_scrapling_transcripts(
    collection: dict[str, Any],
    *,
    limit: int = 20,
    preferred_language: str = "ko",
    include_non_shorts: bool = False,
    timeout_ms: int = 90_000,
    wait_ms: int = 5_000,
    headless: bool = True,
    proxy: str | None = None,
    sleep_seconds: float = 0.0,
    stop_on_block: bool = True,
    fetch_one: ScraplingTranscriptFetcher | None = None,
) -> dict[str, Any]:
    videos = _ranked_videos(collection, include_non_shorts=include_non_shorts)[:limit]
    transcript_items = []
    stopped_by_block = False
    for index, video in enumerate(videos):
        normalized = video.get("normalized") or {}
        video_id = normalized.get("video_id")
        if not isinstance(video_id, str) or not video_id:
            continue
        if stopped_by_block:
            transcript = _missing(video_id, "skipped_after_block", "Skipped because an earlier Scrapling transcript request looked blocked.")
        else:
            watch_url = normalized.get("canonical_watch_url") or f"https://www.youtube.com/watch?v={video_id}"
            result = (
                fetch_one(watch_url)
                if fetch_one
                else fetch_transcript_with_scrapling(
                    watch_url,
                    preferred_language=preferred_language,
                    timeout_ms=timeout_ms,
                    wait_ms=wait_ms,
                    headless=headless,
                    proxy=proxy,
                )
            )
            transcript = result.get("transcript") if isinstance(result, dict) else None
            if not isinstance(transcript, dict):
                transcript = _missing(video_id, "invalid_scrapling_result", "Scrapling fetcher returned an invalid result payload.")
            if stop_on_block and _looks_like_block(transcript):
                stopped_by_block = True
        transcript_items.append(_video_transcript_item(normalized, transcript))
        if sleep_seconds > 0 and index < len(videos) - 1 and not stopped_by_block:
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
            "fetcher": "scrapling.StealthyFetcher",
            "timeout_ms": timeout_ms,
            "wait_ms": wait_ms,
            "headless": headless,
            "used_proxy": bool(proxy),
            "sleep_seconds": sleep_seconds,
            "stopped_by_block": stopped_by_block,
        },
        "videos": transcript_items,
    }


def write_scrapling_collection_transcripts(
    collection_path: str | Path,
    out_path: str | Path,
    *,
    limit: int = 20,
    preferred_language: str = "ko",
    include_non_shorts: bool = False,
    timeout_ms: int = 90_000,
    wait_ms: int = 5_000,
    headless: bool = True,
    proxy: str | None = None,
    sleep_seconds: float = 0.0,
    stop_on_block: bool = True,
) -> Path:
    collection = json.loads(Path(collection_path).read_text(encoding="utf-8"))
    if isinstance(collection, list):
        if len(collection) != 1:
            raise ValueError("Scrapling transcript enrichment expects a single collection result object")
        collection = collection[0]
    if not isinstance(collection, dict):
        raise ValueError("collection JSON must be an object")
    result = enrich_collection_with_scrapling_transcripts(
        collection,
        limit=limit,
        preferred_language=preferred_language,
        include_non_shorts=include_non_shorts,
        timeout_ms=timeout_ms,
        wait_ms=wait_ms,
        headless=headless,
        proxy=proxy,
        sleep_seconds=sleep_seconds,
        stop_on_block=stop_on_block,
    )
    output = Path(out_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return output



def extract_transcript_from_scrapling_response(
    video_id: str,
    response: Any,
    *,
    preferred_language: str = "ko",
    proxy: str | None = None,
    caption_xml_fetcher: CaptionXmlFetcher | None = None,
) -> dict[str, Any]:
    tracks = _caption_tracks_from_response(response)
    if not tracks:
        return _missing(video_id, "no_caption_tracks", "Scrapling loaded the watch page, but no captionTracks were found.")

    track = choose_caption_track(tracks, preferred_language=preferred_language)
    fetch_caption_xml = caption_xml_fetcher or (lambda base_url: _fetch_caption_xml(base_url, proxy=proxy))
    try:
        xml_text = fetch_caption_xml(track.base_url)
        segments = parse_timedtext_xml(xml_text)
    except Exception as exc:
        return _missing(video_id, "caption_fetch_error", str(exc))

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
        "source": "scrapling_watch_page_caption_tracks",
    }


def proxy_from_env() -> str | None:
    value = os.getenv("SCRAPLING_PROXY_URL", "").strip()
    return value or None


def _fetch_watch_page(
    watch_url: str,
    *,
    preferred_language: str,
    timeout_ms: int,
    wait_ms: int,
    headless: bool,
    proxy: str | None,
) -> Any:
    try:
        from scrapling.fetchers import StealthyFetcher
    except ImportError as exc:  # pragma: no cover - exercised only without optional dependency installed.
        raise RuntimeError("Install Scrapling support with `python -m pip install -e '.[scrapling]'`.") from exc
    def capture_player_response(page: Any) -> None:
        try:
            page.wait_for_timeout(1_000)
            payload = page.evaluate(
                """() => JSON.stringify(
                    window.ytInitialPlayerResponse
                    || (window.ytplayer && window.ytplayer.config && window.ytplayer.config.args && window.ytplayer.config.args.raw_player_response)
                    || {}
                )"""
            )
            if isinstance(payload, str) and payload and payload != "{}":
                page.evaluate(
                    """payload => {
                        const node = document.createElement('script');
                        node.id = 'gjc-youtube-player-response';
                        node.type = 'application/json';
                        node.textContent = payload;
                        document.documentElement.appendChild(node);
                    }""",
                    payload,
                )
        except Exception:
            return


    kwargs: dict[str, Any] = {
        "headless": headless,
        "network_idle": True,
        "timeout": timeout_ms,
        "wait": wait_ms,
        "block_webrtc": True,
        "locale": "ko-KR" if preferred_language.startswith("ko") else "en-US",
        "timezone_id": "Asia/Seoul" if preferred_language.startswith("ko") else "UTC",
        "capture_xhr": r"(youtube\.com/api/timedtext|/api/timedtext|/youtubei/v1/player)",
        "page_action": capture_player_response,
        "extra_headers": {"Accept-Language": f"{preferred_language},en;q=0.8"},
    }
    if proxy:
        kwargs["proxy"] = proxy
    return StealthyFetcher.fetch(watch_url, **kwargs)


def _fetch_caption_xml(base_url: str, *, proxy: str | None = None) -> str:
    try:
        from scrapling.fetchers import Fetcher
    except ImportError as exc:  # pragma: no cover - exercised only without optional dependency installed.
        raise RuntimeError("Install Scrapling support with `python -m pip install -e '.[scrapling]'`.") from exc

    kwargs: dict[str, Any] = {"timeout": 30, "stealthy_headers": True, "impersonate": "chrome"}
    if proxy:
        kwargs["proxy"] = proxy
    response = Fetcher.get(base_url, **kwargs)
    return _response_text(response)


def _caption_tracks_from_response(response: Any) -> list[CaptionTrack]:
    tracks = extract_caption_tracks(_response_text(response))
    if tracks:
        return tracks
    for captured in getattr(response, "captured_xhr", None) or []:
        tracks = extract_caption_tracks(_response_text(captured))
        if tracks:
            return tracks
    return []


def _response_text(response: Any) -> str:
    text_value = getattr(response, "text", None)
    if isinstance(text_value, str):
        return text_value
    if callable(text_value):
        try:
            called = text_value()
        except TypeError:
            called = None
        if isinstance(called, str):
            return called

    body = getattr(response, "body", b"")
    if isinstance(body, bytes):
        encoding = getattr(response, "encoding", None) or "utf-8"
        return body.decode(encoding, errors="replace")
    if isinstance(body, str):
        return body
    return str(response)


def _has_error_code(transcript: dict[str, Any], code: str) -> bool:
    errors = transcript.get("errors")
    return isinstance(errors, list) and any(isinstance(error, dict) and error.get("code") == code for error in errors)


def _looks_like_block(transcript: dict[str, Any]) -> bool:
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
    block_markers = (
        "429",
        "403",
        "blocked",
        "too many requests",
        "unusual traffic",
        "confirm you're not a bot",
        "captcha",
        "robot",
    )
    return any(marker in text for marker in block_markers)



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
        "source": "scrapling_watch_page_caption_tracks",
    }
