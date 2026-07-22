from __future__ import annotations

from collections.abc import Sequence
from typing import Any

import httpx

from .errors import YouTubeApiError

VIDEO_PARTS = [
    "snippet",
    "contentDetails",
    "status",
    "statistics",
    "player",
    "topicDetails",
    "recordingDetails",
    "liveStreamingDetails",
    "localizations",
    "paidProductPlacementDetails",
]

CHANNEL_PARTS = [
    "snippet",
    "contentDetails",
    "statistics",
    "status",
    "topicDetails",
    "brandingSettings",
    "localizations",
]

PLAYLIST_ITEM_PARTS = ["snippet", "contentDetails", "status"]


class YouTubeDataApiClient:
    """Thin official YouTube Data API v3 client; no scraping and no comments endpoints."""

    def __init__(self, api_key: str, *, base_url: str = "https://www.googleapis.com/youtube/v3", timeout: float = 20.0):
        if not api_key:
            raise YouTubeApiError("missing_api_key", "YOUTUBE_API_KEY is required for real API mode.")
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def list_videos(self, video_ids: Sequence[str]) -> list[dict[str, Any]]:
        if not video_ids:
            return []
        payload = self._get(
            "videos",
            {
                "part": ",".join(VIDEO_PARTS),
                "id": ",".join(video_ids),
                "maxResults": min(len(video_ids), 50),
            },
        )
        return list(payload.get("items") or [])

    def list_channels(self, channel_ids: Sequence[str]) -> list[dict[str, Any]]:
        if not channel_ids:
            return []
        payload = self._get(
            "channels",
            {
                "part": ",".join(CHANNEL_PARTS),
                "id": ",".join(channel_ids),
                "maxResults": min(len(channel_ids), 50),
            },
        )
        return list(payload.get("items") or [])

    def list_channels_by_handle(self, handle: str) -> list[dict[str, Any]]:
        normalized_handle = handle.strip().removeprefix("@")
        if not normalized_handle:
            return []
        payload = self._get(
            "channels",
            {
                "part": ",".join(CHANNEL_PARTS),
                "forHandle": normalized_handle,
                "maxResults": 1,
            },
        )
        return list(payload.get("items") or [])

    def list_playlist_items(self, playlist_id: str, *, limit: int | None = None) -> list[dict[str, Any]]:
        if not playlist_id:
            return []
        collected: list[dict[str, Any]] = []
        page_token: str | None = None

        while True:
            remaining = None if limit is None else max(limit - len(collected), 0)
            if remaining == 0:
                break
            payload = self._get(
                "playlistItems",
                {
                    "part": ",".join(PLAYLIST_ITEM_PARTS),
                    "playlistId": playlist_id,
                    "maxResults": min(remaining or 50, 50),
                    **({"pageToken": page_token} if page_token else {}),
                },
            )
            items = list(payload.get("items") or [])
            collected.extend(items)
            page_token = payload.get("nextPageToken")
            if not page_token or not items:
                break

        return collected

    def _get(self, resource: str, params: dict[str, Any]) -> dict[str, Any]:
        request_params = {**params, "key": self.api_key}
        try:
            with httpx.Client(timeout=self.timeout) as client:
                response = client.get(f"{self.base_url}/{resource}", params=request_params)
        except httpx.HTTPError as exc:
            raise YouTubeApiError("network_error", str(exc)) from exc

        if response.status_code >= 400:
            raise _api_error_from_response(response)

        try:
            data = response.json()
        except ValueError as exc:
            raise YouTubeApiError("invalid_api_response", "YouTube API returned non-JSON response.") from exc

        if not isinstance(data, dict):
            raise YouTubeApiError("invalid_api_response", "YouTube API returned an unexpected response shape.")
        return data


def _api_error_from_response(response: httpx.Response) -> YouTubeApiError:
    message = response.text
    reason = None
    details: dict[str, Any] = {}
    try:
        payload = response.json()
    except ValueError:
        payload = None

    if isinstance(payload, dict):
        error = payload.get("error")
        if isinstance(error, dict):
            message = str(error.get("message") or message)
            errors = error.get("errors")
            if isinstance(errors, list) and errors and isinstance(errors[0], dict):
                reason = errors[0].get("reason")
                details = errors[0]

    status = response.status_code
    if status in {403, 429} and reason in {"quotaExceeded", "dailyLimitExceeded", "rateLimitExceeded", "userRateLimitExceeded"}:
        code = "quota_or_rate_limited"
    elif status == 403:
        code = "forbidden"
    elif status == 404:
        code = "not_found"
    elif status == 400:
        code = "bad_request"
    else:
        code = "youtube_api_error"

    return YouTubeApiError(code, message, status_code=status, details=details or {"reason": reason})
