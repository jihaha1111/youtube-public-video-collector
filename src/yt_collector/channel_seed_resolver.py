from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime, timezone
from typing import Any, Protocol

from .channel_url_parser import parse_youtube_channel_url
from .errors import UrlParseError, YouTubeApiError
from .models import CHANNEL_RAW_FIELD_PATHS, normalize_channel, project_raw_fields


class ChannelSeedClientProtocol(Protocol):
    def list_channels(self, channel_ids: Sequence[str]) -> list[dict[str, Any]]: ...

    def list_channels_by_handle(self, handle: str) -> list[dict[str, Any]]: ...

    def list_playlist_items(self, playlist_id: str, *, limit: int | None = None) -> list[dict[str, Any]]: ...

    def list_videos(self, video_ids: Sequence[str]) -> list[dict[str, Any]]: ...


def resolve_channel_seeds(
    raw_urls: list[str],
    client: ChannelSeedClientProtocol,
    *,
    probe_uploads: int = 10,
) -> dict[str, Any]:
    collected_at = datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")
    channels = [_resolve_one(raw_url, client, probe_uploads=probe_uploads) for raw_url in raw_urls]
    resolved = [item for item in channels if item["status"] == "resolved"]
    return {
        "schema_version": 1,
        "collected_at": collected_at,
        "input_count": len(raw_urls),
        "resolved_count": len(resolved),
        "error_count": len(raw_urls) - len(resolved),
        "channels": channels,
    }


def _resolve_one(raw_url: str, client: ChannelSeedClientProtocol, *, probe_uploads: int) -> dict[str, Any]:
    try:
        parsed = parse_youtube_channel_url(raw_url)
    except UrlParseError as exc:
        return _error_result(raw_url, "invalid_channel_url", str(exc))

    try:
        channel_items = (
            client.list_channels([parsed.channel_id])
            if parsed.channel_id
            else client.list_channels_by_handle(parsed.handle or "")
        )
        if not channel_items:
            return _error_result(raw_url, "channel_not_found", "Channel was not found or is not public.")

        channel_raw = project_raw_fields(channel_items[0], CHANNEL_RAW_FIELD_PATHS)
        channel = normalize_channel(channel_raw)
        uploads_playlist_id = channel.get("uploads_playlist_id")
        if not uploads_playlist_id:
            return _error_result(raw_url, "missing_uploads_playlist", "Channel has no public uploads playlist.")

        playlist_items = client.list_playlist_items(uploads_playlist_id, limit=probe_uploads)
        ordered_video_ids = _playlist_video_ids(playlist_items)
        public_videos = {
            item.get("id"): item
            for item in client.list_videos(ordered_video_ids)
            if isinstance(item.get("id"), str)
        }
        seed_video_id = next((video_id for video_id in ordered_video_ids if video_id in public_videos), None)
        if not seed_video_id:
            return _error_result(raw_url, "missing_public_seed_video", "No public seed video was found in recent uploads.")

        return {
            "input_url": raw_url,
            "canonical_input_url": parsed.canonical_channel_url,
            "requested_channel_id": parsed.channel_id,
            "requested_handle": parsed.handle,
            "status": "resolved",
            "channel": {"raw": channel_raw, "normalized": channel},
            "seed_video": {
                "video_id": seed_video_id,
                "canonical_watch_url": f"https://www.youtube.com/watch?v={seed_video_id}",
            },
            "errors": [],
        }
    except YouTubeApiError as exc:
        return {
            **_error_result(raw_url, exc.code, exc.message),
            "errors": [exc.as_problem()],
        }


def _playlist_video_ids(items: list[dict[str, Any]]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        content_details = item.get("contentDetails") or {}
        snippet = item.get("snippet") or {}
        resource = snippet.get("resourceId") or {}
        video_id = content_details.get("videoId") or resource.get("videoId")
        if isinstance(video_id, str) and video_id and video_id not in seen:
            seen.add(video_id)
            result.append(video_id)
    return result


def _error_result(raw_url: str, code: str, message: str) -> dict[str, Any]:
    return {
        "input_url": raw_url,
        "canonical_input_url": None,
        "requested_channel_id": None,
        "requested_handle": None,
        "status": "error",
        "channel": {"raw": {}, "normalized": {}},
        "seed_video": None,
        "errors": [{"code": code, "message": message, "details": None}],
    }
