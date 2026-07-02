from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

VIDEO_RAW_FIELD_PATHS = [
    "kind",
    "etag",
    "id",
    "snippet.publishedAt",
    "snippet.channelId",
    "snippet.title",
    "snippet.description",
    "snippet.thumbnails.default.url",
    "snippet.thumbnails.default.width",
    "snippet.thumbnails.default.height",
    "snippet.thumbnails.medium.url",
    "snippet.thumbnails.medium.width",
    "snippet.thumbnails.medium.height",
    "snippet.thumbnails.high.url",
    "snippet.thumbnails.high.width",
    "snippet.thumbnails.high.height",
    "snippet.thumbnails.standard.url",
    "snippet.thumbnails.standard.width",
    "snippet.thumbnails.standard.height",
    "snippet.thumbnails.maxres.url",
    "snippet.thumbnails.maxres.width",
    "snippet.thumbnails.maxres.height",
    "snippet.channelTitle",
    "snippet.tags",
    "snippet.categoryId",
    "snippet.liveBroadcastContent",
    "snippet.defaultLanguage",
    "snippet.localized.title",
    "snippet.localized.description",
    "snippet.defaultAudioLanguage",
    "contentDetails.duration",
    "contentDetails.dimension",
    "contentDetails.definition",
    "contentDetails.caption",
    "contentDetails.licensedContent",
    "contentDetails.regionRestriction.allowed",
    "contentDetails.regionRestriction.blocked",
    "contentDetails.contentRating",
    "contentDetails.projection",
    "status.uploadStatus",
    "status.failureReason",
    "status.rejectionReason",
    "status.privacyStatus",
    "status.publishAt",
    "status.license",
    "status.embeddable",
    "status.publicStatsViewable",
    "status.madeForKids",
    "status.containsSyntheticMedia",
    "statistics.viewCount",
    "statistics.likeCount",
    "statistics.favoriteCount",
    "statistics.commentCount",
    "paidProductPlacementDetails.hasPaidProductPlacement",
    "player.embedHtml",
    "player.embedHeight",
    "player.embedWidth",
    "topicDetails.topicIds",
    "topicDetails.relevantTopicIds",
    "topicDetails.topicCategories",
    "recordingDetails.locationDescription",
    "recordingDetails.location.latitude",
    "recordingDetails.location.longitude",
    "recordingDetails.location.altitude",
    "recordingDetails.recordingDate",
    "liveStreamingDetails.actualStartTime",
    "liveStreamingDetails.actualEndTime",
    "liveStreamingDetails.scheduledStartTime",
    "liveStreamingDetails.scheduledEndTime",
    "liveStreamingDetails.concurrentViewers",
    "liveStreamingDetails.activeLiveChatId",
    "localizations",
]

CHANNEL_RAW_FIELD_PATHS = [
    "kind",
    "etag",
    "id",
    "snippet.title",
    "snippet.description",
    "snippet.customUrl",
    "snippet.publishedAt",
    "snippet.thumbnails.default.url",
    "snippet.thumbnails.default.width",
    "snippet.thumbnails.default.height",
    "snippet.thumbnails.medium.url",
    "snippet.thumbnails.medium.width",
    "snippet.thumbnails.medium.height",
    "snippet.thumbnails.high.url",
    "snippet.thumbnails.high.width",
    "snippet.thumbnails.high.height",
    "snippet.defaultLanguage",
    "snippet.localized.title",
    "snippet.localized.description",
    "snippet.country",
    "contentDetails.relatedPlaylists.likes",
    "contentDetails.relatedPlaylists.favorites",
    "contentDetails.relatedPlaylists.uploads",
    "statistics.viewCount",
    "statistics.subscriberCount",
    "statistics.hiddenSubscriberCount",
    "statistics.videoCount",
    "topicDetails.topicIds",
    "topicDetails.topicCategories",
    "status.privacyStatus",
    "status.isLinked",
    "status.madeForKids",
    "brandingSettings.channel.title",
    "brandingSettings.channel.description",
    "brandingSettings.channel.keywords",
    "brandingSettings.channel.trackingAnalyticsAccountId",
    "brandingSettings.channel.unsubscribedTrailer",
    "brandingSettings.channel.defaultLanguage",
    "brandingSettings.channel.country",
    "brandingSettings.watch.textColor",
    "brandingSettings.watch.backgroundColor",
    "brandingSettings.watch.featuredPlaylistId",
    "brandingSettings.image.bannerExternalUrl",
    "brandingSettings.hints",
    "localizations",
]

PLAYLIST_ITEM_RAW_FIELD_PATHS = [
    "kind",
    "etag",
    "id",
    "snippet.publishedAt",
    "snippet.channelId",
    "snippet.title",
    "snippet.description",
    "snippet.thumbnails.default.url",
    "snippet.thumbnails.default.width",
    "snippet.thumbnails.default.height",
    "snippet.thumbnails.medium.url",
    "snippet.thumbnails.medium.width",
    "snippet.thumbnails.medium.height",
    "snippet.thumbnails.high.url",
    "snippet.thumbnails.high.width",
    "snippet.thumbnails.high.height",
    "snippet.thumbnails.standard.url",
    "snippet.thumbnails.standard.width",
    "snippet.thumbnails.standard.height",
    "snippet.thumbnails.maxres.url",
    "snippet.thumbnails.maxres.width",
    "snippet.thumbnails.maxres.height",
    "snippet.channelTitle",
    "snippet.videoOwnerChannelTitle",
    "snippet.videoOwnerChannelId",
    "snippet.playlistId",
    "snippet.position",
    "snippet.resourceId.kind",
    "snippet.resourceId.videoId",
    "contentDetails.videoId",
    "contentDetails.startAt",
    "contentDetails.endAt",
    "contentDetails.note",
    "contentDetails.videoPublishedAt",
    "status.privacyStatus",
]

_DURATION_RE = re.compile(
    r"^P(?:(?P<days>\d+(?:\.\d+)?)D)?"
    r"(?:T(?:(?P<hours>\d+(?:\.\d+)?)H)?(?:(?P<minutes>\d+(?:\.\d+)?)M)?(?:(?P<seconds>\d+(?:\.\d+)?)S)?)?$"
)
_HASHTAG_RE = re.compile(r"(?<![\w가-힣])#([\w가-힣_]+)")


class RawNormalized(BaseModel):
    model_config = ConfigDict(extra="forbid")

    raw: dict[str, Any] = Field(default_factory=dict)
    normalized: dict[str, Any] = Field(default_factory=dict)


class InputInfo(BaseModel):
    model_config = ConfigDict(extra="forbid")

    raw_url: str
    video_id: str | None = None
    collected_at: str
    mode: Literal["mock", "real"]


class CollectionResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    input: InputInfo
    source_video: RawNormalized = Field(default_factory=RawNormalized)
    channel: RawNormalized = Field(default_factory=RawNormalized)
    upload_playlist_items: list[RawNormalized] = Field(default_factory=list)
    channel_videos: list[RawNormalized] = Field(default_factory=list)
    derived_metrics: dict[str, Any] = Field(default_factory=dict)
    warnings: list[dict[str, Any]] = Field(default_factory=list)
    errors: list[dict[str, Any]] = Field(default_factory=list)


def get_nested(data: Mapping[str, Any] | None, path: str) -> Any:
    cursor: Any = data
    for part in path.split("."):
        if not isinstance(cursor, Mapping):
            return None
        cursor = cursor.get(part)
    return cursor


def project_raw_fields(item: Mapping[str, Any] | None, field_paths: list[str]) -> dict[str, Any]:
    """Return a raw-shaped dict containing every requested path, filling missing leaves with None."""
    source: Mapping[str, Any] = item or {}
    projected: dict[str, Any] = {}
    for path in field_paths:
        _set_nested(projected, path, get_nested(source, path))
    return projected


def safe_int(value: Any) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return None
        try:
            return int(stripped)
        except ValueError:
            return None
    return None


def iso8601_duration_to_seconds(duration: str | None) -> int | None:
    """Convert YouTube ISO 8601 durations such as PT1H2M3S to seconds."""
    if not duration:
        return None
    match = _DURATION_RE.fullmatch(duration)
    if match is None:
        return None
    days = float(match.group("days") or 0)
    hours = float(match.group("hours") or 0)
    minutes = float(match.group("minutes") or 0)
    seconds = float(match.group("seconds") or 0)
    return int(days * 86_400 + hours * 3_600 + minutes * 60 + seconds)


def normalize_video(raw: Mapping[str, Any], *, is_input_shorts_path: bool = False) -> dict[str, Any]:
    video_id = get_nested(raw, "id")
    duration_iso8601 = get_nested(raw, "contentDetails.duration")
    duration_seconds = iso8601_duration_to_seconds(duration_iso8601)
    live_broadcast_content = get_nested(raw, "snippet.liveBroadcastContent")
    localizations = get_nested(raw, "localizations")
    tags = _list_or_none(get_nested(raw, "snippet.tags"))
    title = get_nested(raw, "snippet.title")
    description = get_nested(raw, "snippet.description")

    return {
        "video_id": video_id,
        "canonical_watch_url": f"https://www.youtube.com/watch?v={video_id}" if video_id else None,
        "canonical_shorts_url": f"https://www.youtube.com/shorts/{video_id}" if video_id else None,
        "embed_url": f"https://www.youtube.com/embed/{video_id}" if video_id else None,
        "channel_id": get_nested(raw, "snippet.channelId"),
        "channel_title": get_nested(raw, "snippet.channelTitle"),
        "title": title,
        "description": description,
        "published_at": get_nested(raw, "snippet.publishedAt"),
        "duration_iso8601": duration_iso8601,
        "duration_seconds": duration_seconds,
        "is_probably_short": bool(is_input_shorts_path or (duration_seconds is not None and duration_seconds <= 60)),
        "tags": tags,
        "hashtags": _extract_hashtags(title, description, tags),
        "category_id": get_nested(raw, "snippet.categoryId"),
        "default_language": get_nested(raw, "snippet.defaultLanguage"),
        "default_audio_language": get_nested(raw, "snippet.defaultAudioLanguage"),
        "thumbnail_default_url": get_nested(raw, "snippet.thumbnails.default.url"),
        "thumbnail_medium_url": get_nested(raw, "snippet.thumbnails.medium.url"),
        "thumbnail_high_url": get_nested(raw, "snippet.thumbnails.high.url"),
        "thumbnail_standard_url": get_nested(raw, "snippet.thumbnails.standard.url"),
        "thumbnail_maxres_url": get_nested(raw, "snippet.thumbnails.maxres.url"),
        "definition": get_nested(raw, "contentDetails.definition"),
        "caption_available": _caption_available(get_nested(raw, "contentDetails.caption")),
        "licensed_content": get_nested(raw, "contentDetails.licensedContent"),
        "projection": get_nested(raw, "contentDetails.projection"),
        "privacy_status": get_nested(raw, "status.privacyStatus"),
        "license": get_nested(raw, "status.license"),
        "embeddable": get_nested(raw, "status.embeddable"),
        "public_stats_viewable": get_nested(raw, "status.publicStatsViewable"),
        "made_for_kids": get_nested(raw, "status.madeForKids"),
        "contains_synthetic_media": get_nested(raw, "status.containsSyntheticMedia"),
        "view_count": safe_int(get_nested(raw, "statistics.viewCount")),
        "like_count": safe_int(get_nested(raw, "statistics.likeCount")),
        "favorite_count": safe_int(get_nested(raw, "statistics.favoriteCount")),
        "comment_count": safe_int(get_nested(raw, "statistics.commentCount")),
        "has_paid_product_placement": get_nested(raw, "paidProductPlacementDetails.hasPaidProductPlacement"),
        "topic_categories": _list_or_none(get_nested(raw, "topicDetails.topicCategories")),
        "recording_date": get_nested(raw, "recordingDetails.recordingDate"),
        "recording_location": _recording_location(raw),
        "live_broadcast_content": live_broadcast_content,
        "is_live": bool(
            live_broadcast_content == "live"
            or get_nested(raw, "liveStreamingDetails.activeLiveChatId")
            or get_nested(raw, "liveStreamingDetails.concurrentViewers")
        ),
        "localization_languages": sorted(localizations.keys()) if isinstance(localizations, Mapping) else None,
    }


def normalize_channel(raw: Mapping[str, Any]) -> dict[str, Any]:
    localizations = get_nested(raw, "localizations")
    return {
        "channel_id": get_nested(raw, "id"),
        "channel_title": get_nested(raw, "snippet.title"),
        "description": get_nested(raw, "snippet.description"),
        "custom_url": get_nested(raw, "snippet.customUrl"),
        "published_at": get_nested(raw, "snippet.publishedAt"),
        "country": get_nested(raw, "snippet.country"),
        "default_language": get_nested(raw, "snippet.defaultLanguage"),
        "thumbnail_default_url": get_nested(raw, "snippet.thumbnails.default.url"),
        "thumbnail_medium_url": get_nested(raw, "snippet.thumbnails.medium.url"),
        "thumbnail_high_url": get_nested(raw, "snippet.thumbnails.high.url"),
        "uploads_playlist_id": get_nested(raw, "contentDetails.relatedPlaylists.uploads"),
        "view_count": safe_int(get_nested(raw, "statistics.viewCount")),
        "subscriber_count": safe_int(get_nested(raw, "statistics.subscriberCount")),
        "hidden_subscriber_count": get_nested(raw, "statistics.hiddenSubscriberCount"),
        "video_count": safe_int(get_nested(raw, "statistics.videoCount")),
        "privacy_status": get_nested(raw, "status.privacyStatus"),
        "is_linked": get_nested(raw, "status.isLinked"),
        "made_for_kids": get_nested(raw, "status.madeForKids"),
        "branding_keywords": get_nested(raw, "brandingSettings.channel.keywords"),
        "banner_external_url": get_nested(raw, "brandingSettings.image.bannerExternalUrl"),
        "topic_categories": _list_or_none(get_nested(raw, "topicDetails.topicCategories")),
        "localization_languages": sorted(localizations.keys()) if isinstance(localizations, Mapping) else None,
    }


def normalize_playlist_item(raw: Mapping[str, Any]) -> dict[str, Any]:
    video_id = get_nested(raw, "contentDetails.videoId") or get_nested(raw, "snippet.resourceId.videoId")
    return {
        "playlist_item_id": get_nested(raw, "id"),
        "video_id": video_id,
        "canonical_watch_url": f"https://www.youtube.com/watch?v={video_id}" if video_id else None,
        "channel_id": get_nested(raw, "snippet.channelId"),
        "channel_title": get_nested(raw, "snippet.channelTitle"),
        "video_owner_channel_id": get_nested(raw, "snippet.videoOwnerChannelId"),
        "video_owner_channel_title": get_nested(raw, "snippet.videoOwnerChannelTitle"),
        "playlist_id": get_nested(raw, "snippet.playlistId"),
        "position": get_nested(raw, "snippet.position"),
        "title": get_nested(raw, "snippet.title"),
        "description": get_nested(raw, "snippet.description"),
        "published_at": get_nested(raw, "snippet.publishedAt"),
        "video_published_at": get_nested(raw, "contentDetails.videoPublishedAt"),
        "privacy_status": get_nested(raw, "status.privacyStatus"),
        "thumbnail_default_url": get_nested(raw, "snippet.thumbnails.default.url"),
        "thumbnail_medium_url": get_nested(raw, "snippet.thumbnails.medium.url"),
        "thumbnail_high_url": get_nested(raw, "snippet.thumbnails.high.url"),
        "thumbnail_standard_url": get_nested(raw, "snippet.thumbnails.standard.url"),
        "thumbnail_maxres_url": get_nested(raw, "snippet.thumbnails.maxres.url"),
    }


def _set_nested(target: dict[str, Any], path: str, value: Any) -> None:
    cursor = target
    parts = path.split(".")
    for part in parts[:-1]:
        next_cursor = cursor.get(part)
        if not isinstance(next_cursor, dict):
            next_cursor = {}
            cursor[part] = next_cursor
        cursor = next_cursor
    cursor[parts[-1]] = value


def _list_or_none(value: Any) -> list[Any] | None:
    if value is None:
        return None
    if isinstance(value, list):
        return value
    return [value]


def _caption_available(value: Any) -> bool | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered == "true":
            return True
        if lowered == "false":
            return False
    return None


def _extract_hashtags(title: Any, description: Any, tags: list[Any] | None) -> list[str] | None:
    text_parts = [part for part in [title, description] if isinstance(part, str)]
    if tags:
        text_parts.extend(str(tag) for tag in tags)
    seen: set[str] = set()
    hashtags: list[str] = []
    for match in _HASHTAG_RE.finditer("\n".join(text_parts)):
        hashtag = f"#{match.group(1)}"
        lowered = hashtag.lower()
        if lowered not in seen:
            seen.add(lowered)
            hashtags.append(hashtag)
    return hashtags or None


def _recording_location(raw: Mapping[str, Any]) -> dict[str, Any] | None:
    location = {
        "description": get_nested(raw, "recordingDetails.locationDescription"),
        "latitude": get_nested(raw, "recordingDetails.location.latitude"),
        "longitude": get_nested(raw, "recordingDetails.location.longitude"),
        "altitude": get_nested(raw, "recordingDetails.location.altitude"),
    }
    return location if any(value is not None for value in location.values()) else None
