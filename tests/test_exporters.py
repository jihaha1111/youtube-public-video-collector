from __future__ import annotations

import csv
import json

from yt_collector.collector import YouTubeCollector
from yt_collector.exporters import export_csv, export_json
from yt_collector.mock_client import MockYouTubeClient


def _mock_result():
    return YouTubeCollector(MockYouTubeClient(), mode="mock").collect(
        "https://www.youtube.com/watch?v=onjVWrO2_5E",
        limit=3,
    )


def test_export_json_writes_single_result_object(tmp_path) -> None:
    result = _mock_result()
    out = tmp_path / "result.json"

    export_json(result, out)

    payload = json.loads(out.read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    assert payload["input"]["video_id"] == "onjVWrO2_5E"
    assert payload["input"]["mode"] == "mock"
    assert len(payload["channel_videos"]) == 3
    assert payload["source_video"]["raw"]["status"]["failureReason"] is None
    assert payload["source_video"]["normalized"]["comment_count"] == 20


def test_export_json_writes_multiple_results_as_array(tmp_path) -> None:
    result = _mock_result()
    out = tmp_path / "results.json"

    export_json([result, result], out)

    payload = json.loads(out.read_text(encoding="utf-8"))
    assert isinstance(payload, list)
    assert len(payload) == 2
    assert payload[0]["derived_metrics"]["channel_video_count_collected"] == 3


def test_export_csv_writes_channel_video_rows(tmp_path) -> None:
    result = _mock_result()
    out = tmp_path / "result.csv"

    export_csv(result, out)

    with out.open(encoding="utf-8", newline="") as file:
        rows = list(csv.DictReader(file))

    assert len(rows) == 3
    assert rows[0]["mode"] == "mock"
    assert rows[1]["video_id"] == "onjVWrO2_5E"
    assert rows[1]["comment_count"] == "20"
