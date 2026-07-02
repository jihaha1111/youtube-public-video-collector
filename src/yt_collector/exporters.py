from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any, Iterable

from pydantic import BaseModel

from .models import CollectionResult


def export_json(results: CollectionResult | list[CollectionResult], out_path: str | Path) -> Path:
    path = Path(out_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    result_list = _ensure_list(results)
    payload: Any = _jsonable(result_list[0]) if len(result_list) == 1 else [_jsonable(result) for result in result_list]
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def export_csv(results: CollectionResult | list[CollectionResult], out_path: str | Path) -> Path:
    path = Path(out_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = list(_csv_rows(_ensure_list(results)))
    fieldnames = [
        "input_raw_url",
        "input_video_id",
        "mode",
        "collected_at",
        "channel_id",
        "channel_title",
        "video_id",
        "title",
        "canonical_watch_url",
        "published_at",
        "duration_seconds",
        "is_probably_short",
        "view_count",
        "like_count",
        "comment_count",
        "like_rate",
        "comment_rate",
        "views_per_hour_since_published",
        "channel_relative_view_score",
        "rank_by_views_in_collected_channel_videos",
        "rank_by_likes_in_collected_channel_videos",
        "rank_by_comments_in_collected_channel_videos",
        "errors",
        "warnings",
    ]
    with path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    return path


def _ensure_list(results: CollectionResult | list[CollectionResult]) -> list[CollectionResult]:
    return results if isinstance(results, list) else [results]


def _jsonable(value: Any) -> Any:
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json")
    if isinstance(value, list):
        return [_jsonable(item) for item in value]
    if isinstance(value, dict):
        return {key: _jsonable(item) for key, item in value.items()}
    return value


def _csv_rows(results: Iterable[CollectionResult]) -> Iterable[dict[str, Any]]:
    for result in results:
        base = {
            "input_raw_url": result.input.raw_url,
            "input_video_id": result.input.video_id,
            "mode": result.input.mode,
            "collected_at": result.input.collected_at,
            "channel_id": result.channel.normalized.get("channel_id"),
            "channel_title": result.channel.normalized.get("channel_title"),
            "errors": json.dumps(result.errors, ensure_ascii=False),
            "warnings": json.dumps(result.warnings, ensure_ascii=False),
        }
        if not result.channel_videos:
            yield {**base}
            continue
        for video in result.channel_videos:
            normalized = video.normalized
            yield {
                **base,
                "video_id": normalized.get("video_id"),
                "title": normalized.get("title"),
                "canonical_watch_url": normalized.get("canonical_watch_url"),
                "published_at": normalized.get("published_at"),
                "duration_seconds": normalized.get("duration_seconds"),
                "is_probably_short": normalized.get("is_probably_short"),
                "view_count": normalized.get("view_count"),
                "like_count": normalized.get("like_count"),
                "comment_count": normalized.get("comment_count"),
                "like_rate": normalized.get("like_rate"),
                "comment_rate": normalized.get("comment_rate"),
                "views_per_hour_since_published": normalized.get("views_per_hour_since_published"),
                "channel_relative_view_score": normalized.get("channel_relative_view_score"),
                "rank_by_views_in_collected_channel_videos": normalized.get("rank_by_views_in_collected_channel_videos"),
                "rank_by_likes_in_collected_channel_videos": normalized.get("rank_by_likes_in_collected_channel_videos"),
                "rank_by_comments_in_collected_channel_videos": normalized.get("rank_by_comments_in_collected_channel_videos"),
            }
