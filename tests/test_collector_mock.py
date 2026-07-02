from __future__ import annotations

from yt_collector.collector import YouTubeCollector
from yt_collector.mock_client import MockYouTubeClient
from yt_collector.models import VIDEO_RAW_FIELD_PATHS, iso8601_duration_to_seconds, normalize_video, project_raw_fields


def test_mock_collector_returns_complete_three_video_result() -> None:
    collector = YouTubeCollector(MockYouTubeClient(), mode="mock")

    result = collector.collect("https://www.youtube.com/watch?v=onjVWrO2_5E", limit=1)

    assert result.input.mode == "mock"
    assert result.input.video_id == "onjVWrO2_5E"
    assert result.errors == []
    assert len(result.upload_playlist_items) == 3
    assert len(result.channel_videos) == 3
    assert result.derived_metrics["channel_video_count_collected"] == 3
    assert result.derived_metrics["source_video_rank_by_views_in_collected_channel_videos"] == 2
    assert result.derived_metrics["source_video_rank_by_likes_in_collected_channel_videos"] == 2
    assert result.derived_metrics["source_video_rank_by_comments_in_collected_channel_videos"] == 2

    source = result.source_video.normalized
    assert source["video_id"] == "onjVWrO2_5E"
    assert source["view_count"] == 3000
    assert source["like_count"] == 300
    assert source["favorite_count"] == 0
    assert source["comment_count"] == 20
    assert source["duration_seconds"] == 45
    assert source["is_probably_short"] is True
    assert "#shopping" in source["hashtags"]
    assert "comment_body" not in source

    assert result.channel.normalized["uploads_playlist_id"].startswith("UU")
    assert result.channel.normalized["video_count"] == 3
    assert result.source_video.raw["status"]["failureReason"] is None


def test_short_url_marks_source_as_probably_short_even_without_duration_rule() -> None:
    collector = YouTubeCollector(MockYouTubeClient(), mode="mock")

    result = collector.collect("https://www.youtube.com/shorts/onjVWrO2_5E", limit=3)

    assert result.source_video.normalized["is_probably_short"] is True


def test_iso8601_duration_to_seconds() -> None:
    assert iso8601_duration_to_seconds("PT45S") == 45
    assert iso8601_duration_to_seconds("PT1M1S") == 61
    assert iso8601_duration_to_seconds("PT1H2M3S") == 3723
    assert iso8601_duration_to_seconds("P1DT2H") == 93600
    assert iso8601_duration_to_seconds(None) is None
    assert iso8601_duration_to_seconds("not-duration") is None


def test_normalized_video_fields_handle_strings_and_missing_values() -> None:
    raw = project_raw_fields(
        {
            "kind": "youtube#video",
            "id": "onjVWrO2_5E",
            "snippet": {
                "publishedAt": "2024-01-01T00:00:00Z",
                "title": "테스트 제목 #Deal",
                "description": "설명 #쇼핑",
                "thumbnails": {"default": {"url": "https://example.com/default.jpg"}},
                "liveBroadcastContent": "none",
            },
            "contentDetails": {"duration": "PT1M1S", "caption": "true"},
            "statistics": {"viewCount": "12", "likeCount": "", "favoriteCount": "0", "commentCount": "3"},
        },
        VIDEO_RAW_FIELD_PATHS,
    )

    normalized = normalize_video(raw)

    assert normalized["duration_seconds"] == 61
    assert normalized["is_probably_short"] is False
    assert normalized["caption_available"] is True
    assert normalized["view_count"] == 12
    assert normalized["like_count"] is None
    assert normalized["favorite_count"] == 0
    assert normalized["comment_count"] == 3
    assert normalized["thumbnail_default_url"] == "https://example.com/default.jpg"
    assert normalized["thumbnail_medium_url"] is None
    assert normalized["hashtags"] == ["#Deal", "#쇼핑"]
