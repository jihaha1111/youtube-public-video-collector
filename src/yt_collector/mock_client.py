from __future__ import annotations

import hashlib
from collections.abc import Sequence
from typing import Any


class MockYouTubeClient:
    """Deterministic mock client that returns one public channel with exactly 3 public videos."""

    def __init__(self, source_video_id: str | None = None):
        self.source_video_id: str | None = None
        self.channel_video_ids: list[str] = []
        self.channel_id: str | None = None
        self.uploads_playlist_id: str | None = None
        if source_video_id:
            self.set_source_video_id(source_video_id)

    def set_source_video_id(self, source_video_id: str) -> None:
        self.source_video_id = source_video_id
        high_video_id = _derived_id(source_video_id, "high")
        low_video_id = _derived_id(source_video_id, "low")
        self.channel_video_ids = [high_video_id, source_video_id, low_video_id]
        suffix = hashlib.sha1(source_video_id.encode("utf-8")).hexdigest()[:18]
        self.channel_id = f"UC{suffix}"
        self.uploads_playlist_id = f"UU{suffix}"

    def list_videos(self, video_ids: Sequence[str]) -> list[dict[str, Any]]:
        if not video_ids:
            return []
        if self.source_video_id is None:
            self.set_source_video_id(video_ids[0])

        return [self._video_item(video_id) for video_id in video_ids]

    def list_channels(self, channel_ids: Sequence[str]) -> list[dict[str, Any]]:
        if self.source_video_id is None:
            self.set_source_video_id("mockVideo01")
        if not channel_ids:
            return []
        return [self._channel_item()]

    def list_channels_by_handle(self, handle: str) -> list[dict[str, Any]]:
        if self.source_video_id is None:
            seed = _derived_id(handle or "mock-handle", "seed")
            self.set_source_video_id(seed)
        return [self._channel_item()]

    def list_playlist_items(self, playlist_id: str, *, limit: int | None = None) -> list[dict[str, Any]]:
        if self.source_video_id is None:
            self.set_source_video_id("mockVideo01")
        return [self._playlist_item(video_id, position) for position, video_id in enumerate(self.channel_video_ids)]

    def _video_item(self, video_id: str) -> dict[str, Any]:
        assert self.channel_id is not None
        stats_by_id = self._stats_by_video_id()
        stats = stats_by_id.get(video_id, stats_by_id[self.source_video_id])  # type: ignore[index]
        title = stats["title"]
        published_at = stats["published_at"]
        duration = stats["duration"]
        return {
            "kind": "youtube#video",
            "etag": f"mock-video-{video_id}",
            "id": video_id,
            "snippet": {
                "publishedAt": published_at,
                "channelId": self.channel_id,
                "title": title,
                "description": f"Mock description for {title}. #shopping #affiliate",
                "thumbnails": _thumbnails(video_id),
                "channelTitle": "Mock Shopping Shorts Channel",
                "tags": ["shopping", "affiliate", "shorts", "#deal"],
                "categoryId": "22",
                "liveBroadcastContent": "none",
                "defaultLanguage": "ko",
                "localized": {
                    "title": title,
                    "description": f"Localized mock description for {title}.",
                },
                "defaultAudioLanguage": "ko",
            },
            "contentDetails": {
                "duration": duration,
                "dimension": "2d",
                "definition": "hd",
                "caption": "false",
                "licensedContent": True,
                "regionRestriction": {"allowed": None, "blocked": None},
                "contentRating": {},
                "projection": "rectangular",
            },
            "status": {
                "uploadStatus": "processed",
                "failureReason": None,
                "rejectionReason": None,
                "privacyStatus": "public",
                "publishAt": None,
                "license": "youtube",
                "embeddable": True,
                "publicStatsViewable": True,
                "madeForKids": False,
                "containsSyntheticMedia": False,
            },
            "statistics": {
                "viewCount": str(stats["view_count"]),
                "likeCount": str(stats["like_count"]),
                "favoriteCount": "0",
                "commentCount": str(stats["comment_count"]),
            },
            "paidProductPlacementDetails": {"hasPaidProductPlacement": True},
            "player": {
                "embedHtml": f'<iframe src="https://www.youtube.com/embed/{video_id}"></iframe>',
                "embedHeight": 360,
                "embedWidth": 640,
            },
            "topicDetails": {
                "topicIds": ["/m/0bzvm2"],
                "relevantTopicIds": ["/m/01j61q"],
                "topicCategories": ["https://en.wikipedia.org/wiki/Lifestyle_(sociology)"],
            },
            "recordingDetails": {
                "locationDescription": None,
                "location": {"latitude": None, "longitude": None, "altitude": None},
                "recordingDate": published_at[:10],
            },
            "liveStreamingDetails": {
                "actualStartTime": None,
                "actualEndTime": None,
                "scheduledStartTime": None,
                "scheduledEndTime": None,
                "concurrentViewers": None,
                "activeLiveChatId": None,
            },
            "localizations": {
                "ko": {"title": title, "description": f"한국어 설명: {title}"},
                "en": {"title": f"EN {title}", "description": f"English mock description for {title}."},
            },
        }

    def _channel_item(self) -> dict[str, Any]:
        assert self.channel_id is not None
        assert self.uploads_playlist_id is not None
        return {
            "kind": "youtube#channel",
            "etag": f"mock-channel-{self.channel_id}",
            "id": self.channel_id,
            "snippet": {
                "title": "Mock Shopping Shorts Channel",
                "description": "Mock public channel for shopping and affiliate video analysis.",
                "customUrl": "@mock-shopping-shorts",
                "publishedAt": "2023-01-01T00:00:00Z",
                "thumbnails": _thumbnails(self.channel_id),
                "defaultLanguage": "ko",
                "localized": {
                    "title": "Mock Shopping Shorts Channel",
                    "description": "Localized mock channel description.",
                },
                "country": "KR",
            },
            "contentDetails": {
                "relatedPlaylists": {
                    "likes": None,
                    "favorites": None,
                    "uploads": self.uploads_playlist_id,
                }
            },
            "statistics": {
                "viewCount": "9000",
                "subscriberCount": "12345",
                "hiddenSubscriberCount": False,
                "videoCount": "3",
            },
            "topicDetails": {
                "topicIds": ["/m/0bzvm2"],
                "topicCategories": ["https://en.wikipedia.org/wiki/Shopping"],
            },
            "status": {"privacyStatus": "public", "isLinked": True, "madeForKids": False},
            "brandingSettings": {
                "channel": {
                    "title": "Mock Shopping Shorts Channel",
                    "description": "Branding description for mock mode.",
                    "keywords": "shopping affiliate shorts deals",
                    "trackingAnalyticsAccountId": None,
                    "unsubscribedTrailer": self.source_video_id,
                    "defaultLanguage": "ko",
                    "country": "KR",
                },
                "watch": {
                    "textColor": None,
                    "backgroundColor": None,
                    "featuredPlaylistId": self.uploads_playlist_id,
                },
                "image": {"bannerExternalUrl": "https://img.youtube.com/mock/banner.jpg"},
                "hints": [{"property": "channel.modules.show_comments", "value": "False"}],
            },
            "localizations": {
                "ko": {"title": "Mock Shopping Shorts Channel", "description": "한국어 채널 설명"},
                "en": {"title": "Mock Shopping Shorts Channel", "description": "English channel description"},
            },
        }

    def _playlist_item(self, video_id: str, position: int) -> dict[str, Any]:
        assert self.channel_id is not None
        assert self.uploads_playlist_id is not None
        video = self._video_item(video_id)
        return {
            "kind": "youtube#playlistItem",
            "etag": f"mock-playlist-item-{video_id}",
            "id": f"PLI{position}-{video_id}",
            "snippet": {
                "publishedAt": video["snippet"]["publishedAt"],
                "channelId": self.channel_id,
                "title": video["snippet"]["title"],
                "description": video["snippet"]["description"],
                "thumbnails": video["snippet"]["thumbnails"],
                "channelTitle": video["snippet"]["channelTitle"],
                "videoOwnerChannelTitle": video["snippet"]["channelTitle"],
                "videoOwnerChannelId": self.channel_id,
                "playlistId": self.uploads_playlist_id,
                "position": position,
                "resourceId": {"kind": "youtube#video", "videoId": video_id},
            },
            "contentDetails": {
                "videoId": video_id,
                "startAt": None,
                "endAt": None,
                "note": None,
                "videoPublishedAt": video["snippet"]["publishedAt"],
            },
            "status": {"privacyStatus": "public"},
        }

    def _stats_by_video_id(self) -> dict[str, dict[str, Any]]:
        assert self.source_video_id is not None
        high_video_id, source_video_id, low_video_id = self.channel_video_ids
        return {
            high_video_id: {
                "title": "Mock viral shopping comparison #deal",
                "published_at": "2024-06-01T09:00:00Z",
                "duration": "PT2M10S",
                "view_count": 5000,
                "like_count": 500,
                "comment_count": 50,
            },
            source_video_id: {
                "title": "Mock source affiliate short #shopping",
                "published_at": "2024-06-02T09:00:00Z",
                "duration": "PT45S",
                "view_count": 3000,
                "like_count": 300,
                "comment_count": 20,
            },
            low_video_id: {
                "title": "Mock quiet product hook #shorts",
                "published_at": "2024-06-03T09:00:00Z",
                "duration": "PT59S",
                "view_count": 1000,
                "like_count": 75,
                "comment_count": 5,
            },
        }


def _derived_id(seed: str, label: str) -> str:
    return hashlib.sha1(f"{seed}:{label}".encode("utf-8")).hexdigest()[:11]


def _thumbnails(seed: str) -> dict[str, dict[str, Any]]:
    slug = seed.replace("_", "-")
    return {
        "default": {"url": f"https://img.youtube.com/vi/{slug}/default.jpg", "width": 120, "height": 90},
        "medium": {"url": f"https://img.youtube.com/vi/{slug}/mqdefault.jpg", "width": 320, "height": 180},
        "high": {"url": f"https://img.youtube.com/vi/{slug}/hqdefault.jpg", "width": 480, "height": 360},
        "standard": {"url": f"https://img.youtube.com/vi/{slug}/sddefault.jpg", "width": 640, "height": 480},
        "maxres": {"url": f"https://img.youtube.com/vi/{slug}/maxresdefault.jpg", "width": 1280, "height": 720},
    }
