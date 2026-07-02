from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime, timezone
from typing import Any, Protocol

from .errors import UrlParseError, YouTubeApiError
from .models import (
    CHANNEL_RAW_FIELD_PATHS,
    PLAYLIST_ITEM_RAW_FIELD_PATHS,
    VIDEO_RAW_FIELD_PATHS,
    CollectionResult,
    InputInfo,
    RawNormalized,
    get_nested,
    normalize_channel,
    normalize_playlist_item,
    normalize_video,
    project_raw_fields,
)
from .url_parser import ParsedYouTubeUrl, parse_youtube_url


class YouTubeClientProtocol(Protocol):
    def list_videos(self, video_ids: Sequence[str]) -> list[dict[str, Any]]: ...

    def list_channels(self, channel_ids: Sequence[str]) -> list[dict[str, Any]]: ...

    def list_playlist_items(self, playlist_id: str, *, limit: int | None = None) -> list[dict[str, Any]]: ...


class YouTubeCollector:
    def __init__(self, client: YouTubeClientProtocol, *, mode: str):
        if mode not in {"mock", "real"}:
            raise ValueError("mode must be 'mock' or 'real'.")
        self.client = client
        self.mode = mode

    def collect(self, raw_url: str, *, limit: int | None = 3) -> CollectionResult:
        collected_at_dt = datetime.now(timezone.utc).astimezone()
        collected_at = collected_at_dt.isoformat(timespec="seconds")

        try:
            parsed = parse_youtube_url(raw_url)
        except UrlParseError as exc:
            return _empty_result(
                raw_url,
                None,
                self.mode,
                collected_at,
                errors=[_problem("invalid_url", str(exc))],
            )

        _seed_mock_client(self.client, parsed.video_id)

        try:
            return self._collect_parsed(parsed, collected_at_dt=collected_at_dt, collected_at=collected_at, limit=limit)
        except YouTubeApiError as exc:
            return _empty_result(
                parsed.raw_url,
                parsed.video_id,
                self.mode,
                collected_at,
                errors=[exc.as_problem()],
            )

    def _collect_parsed(
        self,
        parsed: ParsedYouTubeUrl,
        *,
        collected_at_dt: datetime,
        collected_at: str,
        limit: int | None,
    ) -> CollectionResult:
        warnings: list[dict[str, Any]] = []
        errors: list[dict[str, Any]] = []

        source_items = self.client.list_videos([parsed.video_id])
        if not source_items:
            warnings.append(_problem("not_found_or_not_public", "Source video was not found or is not public."))
            return _empty_result(parsed.raw_url, parsed.video_id, self.mode, collected_at, warnings=warnings)

        source_raw = project_raw_fields(source_items[0], VIDEO_RAW_FIELD_PATHS)
        source_normalized = normalize_video(source_raw, is_input_shorts_path=parsed.is_shorts_url)
        source_video = RawNormalized(raw=source_raw, normalized=source_normalized)

        channel_id = source_normalized.get("channel_id")
        if not channel_id:
            errors.append(_problem("missing_channel_id", "Source video response did not include snippet.channelId."))
            return _result(
                parsed.raw_url,
                parsed.video_id,
                self.mode,
                collected_at,
                source_video=source_video,
                warnings=warnings,
                errors=errors,
            )

        channel_items = self.client.list_channels([channel_id])
        if not channel_items:
            warnings.append(_problem("not_found_or_not_public", "Channel was not found or is not public."))
            return _result(
                parsed.raw_url,
                parsed.video_id,
                self.mode,
                collected_at,
                source_video=source_video,
                warnings=warnings,
                errors=errors,
            )

        channel_raw = project_raw_fields(channel_items[0], CHANNEL_RAW_FIELD_PATHS)
        channel = RawNormalized(raw=channel_raw, normalized=normalize_channel(channel_raw))
        uploads_playlist_id = channel.normalized.get("uploads_playlist_id")
        if not uploads_playlist_id:
            warnings.append(_problem("missing_uploads_playlist", "Channel response did not include contentDetails.relatedPlaylists.uploads."))
            return _result(
                parsed.raw_url,
                parsed.video_id,
                self.mode,
                collected_at,
                source_video=source_video,
                channel=channel,
                warnings=warnings,
                errors=errors,
            )

        playlist_limit = None if self.mode == "mock" else limit
        playlist_items_raw = self.client.list_playlist_items(uploads_playlist_id, limit=playlist_limit)
        upload_playlist_items = [
            RawNormalized(
                raw=project_raw_fields(item, PLAYLIST_ITEM_RAW_FIELD_PATHS),
                normalized=normalize_playlist_item(project_raw_fields(item, PLAYLIST_ITEM_RAW_FIELD_PATHS)),
            )
            for item in playlist_items_raw
        ]
        if not upload_playlist_items:
            warnings.append(_problem("not_found_or_not_public", "No public upload playlist items were returned."))

        video_ids = _playlist_video_ids(upload_playlist_items)
        video_items_by_id: dict[str, dict[str, Any]] = {}
        for batch in _chunks(video_ids, 50):
            for item in self.client.list_videos(batch):
                item_id = item.get("id")
                if isinstance(item_id, str):
                    video_items_by_id[item_id] = item

        missing_video_ids = [video_id for video_id in video_ids if video_id not in video_items_by_id]
        if missing_video_ids:
            warnings.append(
                _problem(
                    "not_found_or_not_public",
                    "Some playlist videos were not found or are not public.",
                    {"video_ids": missing_video_ids},
                )
            )

        channel_videos: list[RawNormalized] = []
        for video_id in video_ids:
            item = video_items_by_id.get(video_id)
            if item is None:
                continue
            raw = project_raw_fields(item, VIDEO_RAW_FIELD_PATHS)
            channel_videos.append(
                RawNormalized(
                    raw=raw,
                    normalized=normalize_video(
                        raw,
                        is_input_shorts_path=parsed.is_shorts_url and video_id == parsed.video_id,
                    ),
                )
            )

        _add_derived_metrics(channel_videos, collected_at_dt)
        source_from_channel = _find_video_normalized(channel_videos, parsed.video_id)
        if source_from_channel is not None:
            for key in _DERIVED_VIDEO_KEYS:
                source_video.normalized[key] = source_from_channel.get(key)

        derived_metrics = _source_derived_metrics(source_video.normalized, channel_videos)

        return _result(
            parsed.raw_url,
            parsed.video_id,
            self.mode,
            collected_at,
            source_video=source_video,
            channel=channel,
            upload_playlist_items=upload_playlist_items,
            channel_videos=channel_videos,
            derived_metrics=derived_metrics,
            warnings=warnings,
            errors=errors,
        )


def _seed_mock_client(client: YouTubeClientProtocol, video_id: str) -> None:
    setter = getattr(client, "set_source_video_id", None)
    if callable(setter):
        setter(video_id)


def _playlist_video_ids(items: list[RawNormalized]) -> list[str]:
    seen: set[str] = set()
    video_ids: list[str] = []
    for item in items:
        video_id = item.normalized.get("video_id")
        if isinstance(video_id, str) and video_id and video_id not in seen:
            seen.add(video_id)
            video_ids.append(video_id)
    return video_ids


def _chunks(values: list[str], size: int) -> list[list[str]]:
    return [values[index : index + size] for index in range(0, len(values), size)]


_DERIVED_VIDEO_KEYS = [
    "like_rate",
    "comment_rate",
    "views_per_hour_since_published",
    "channel_relative_view_score",
    "rank_by_views_in_collected_channel_videos",
    "rank_by_likes_in_collected_channel_videos",
    "rank_by_comments_in_collected_channel_videos",
]


def _add_derived_metrics(channel_videos: list[RawNormalized], collected_at_dt: datetime) -> None:
    norms = [video.normalized for video in channel_videos]
    view_values = [value for value in (video.get("view_count") for video in norms) if isinstance(value, int)]
    average_views = sum(view_values) / len(view_values) if view_values else None

    for norm in norms:
        view_count = norm.get("view_count")
        like_count = norm.get("like_count")
        comment_count = norm.get("comment_count")
        norm["like_rate"] = _safe_div(like_count, view_count)
        norm["comment_rate"] = _safe_div(comment_count, view_count)
        norm["views_per_hour_since_published"] = _views_per_hour(view_count, norm.get("published_at"), collected_at_dt)
        norm["channel_relative_view_score"] = _safe_div(view_count, average_views)
        norm["rank_by_views_in_collected_channel_videos"] = _rank(view_count, [video.get("view_count") for video in norms])
        norm["rank_by_likes_in_collected_channel_videos"] = _rank(like_count, [video.get("like_count") for video in norms])
        norm["rank_by_comments_in_collected_channel_videos"] = _rank(comment_count, [video.get("comment_count") for video in norms])


def _source_derived_metrics(source: dict[str, Any], channel_videos: list[RawNormalized]) -> dict[str, Any]:
    return {
        "channel_video_count_collected": len(channel_videos),
        "view_count": source.get("view_count"),
        "like_count": source.get("like_count"),
        "comment_count": source.get("comment_count"),
        "like_rate": source.get("like_rate"),
        "comment_rate": source.get("comment_rate"),
        "views_per_hour_since_published": source.get("views_per_hour_since_published"),
        "channel_relative_view_score": source.get("channel_relative_view_score"),
        "source_video_rank_by_views_in_collected_channel_videos": source.get("rank_by_views_in_collected_channel_videos"),
        "source_video_rank_by_likes_in_collected_channel_videos": source.get("rank_by_likes_in_collected_channel_videos"),
        "source_video_rank_by_comments_in_collected_channel_videos": source.get("rank_by_comments_in_collected_channel_videos"),
    }


def _find_video_normalized(channel_videos: list[RawNormalized], video_id: str) -> dict[str, Any] | None:
    for video in channel_videos:
        if video.normalized.get("video_id") == video_id:
            return video.normalized
    return None


def _rank(value: Any, values: list[Any]) -> int | None:
    if not isinstance(value, int):
        return None
    return 1 + sum(1 for other in values if isinstance(other, int) and other > value)


def _safe_div(numerator: Any, denominator: Any) -> float | None:
    if not isinstance(numerator, (int, float)) or not isinstance(denominator, (int, float)) or denominator == 0:
        return None
    return round(float(numerator) / float(denominator), 8)


def _views_per_hour(view_count: Any, published_at: Any, collected_at_dt: datetime) -> float | None:
    if not isinstance(view_count, int) or not isinstance(published_at, str):
        return None
    published_dt = _parse_datetime(published_at)
    if published_dt is None:
        return None
    hours = (collected_at_dt - published_dt).total_seconds() / 3600
    if hours <= 0:
        return None
    return round(view_count / hours, 8)


def _parse_datetime(value: str) -> datetime | None:
    try:
        normalized = value.replace("Z", "+00:00") if value.endswith("Z") else value
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed


def _empty_result(
    raw_url: str,
    video_id: str | None,
    mode: str,
    collected_at: str,
    *,
    warnings: list[dict[str, Any]] | None = None,
    errors: list[dict[str, Any]] | None = None,
) -> CollectionResult:
    return _result(raw_url, video_id, mode, collected_at, warnings=warnings or [], errors=errors or [])


def _result(
    raw_url: str,
    video_id: str | None,
    mode: str,
    collected_at: str,
    *,
    source_video: RawNormalized | None = None,
    channel: RawNormalized | None = None,
    upload_playlist_items: list[RawNormalized] | None = None,
    channel_videos: list[RawNormalized] | None = None,
    derived_metrics: dict[str, Any] | None = None,
    warnings: list[dict[str, Any]] | None = None,
    errors: list[dict[str, Any]] | None = None,
) -> CollectionResult:
    return CollectionResult(
        input=InputInfo(raw_url=raw_url, video_id=video_id, collected_at=collected_at, mode=mode),
        source_video=source_video or RawNormalized(),
        channel=channel or RawNormalized(),
        upload_playlist_items=upload_playlist_items or [],
        channel_videos=channel_videos or [],
        derived_metrics=derived_metrics or {},
        warnings=warnings or [],
        errors=errors or [],
    )


def _problem(code: str, message: str, details: dict[str, Any] | None = None) -> dict[str, Any]:
    return {"code": code, "message": message, "details": details}
