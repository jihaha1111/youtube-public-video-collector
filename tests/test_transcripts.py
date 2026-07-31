from __future__ import annotations

from yt_collector.transcripts import (
    choose_caption_track,
    enrich_collection_with_transcripts,
    extract_caption_tracks,
    fetch_public_transcript_list_file,
    parse_timedtext_xml,
)


def test_extract_caption_tracks_and_choose_preferred_language() -> None:
    html = '''before "captionTracks":[
      {"baseUrl":"https://www.youtube.com/api/timedtext?v=abc\\u0026lang=ko","languageCode":"ko","name":{"simpleText":"한국어 (자동 생성됨)"},"kind":"asr","vssId":"a.ko"},
      {"baseUrl":"https://www.youtube.com/api/timedtext?v=abc\\u0026lang=en","languageCode":"en","name":{"simpleText":"English"},"vssId":".en"}
    ],"audioTracks" after'''

    tracks = extract_caption_tracks(html)

    assert len(tracks) == 2
    assert tracks[0].base_url == "https://www.youtube.com/api/timedtext?v=abc&lang=ko"
    assert tracks[0].is_generated is True
    assert choose_caption_track(tracks, preferred_language="ko").language_code == "ko"


def test_parse_timedtext_xml_unescapes_segments() -> None:
    xml = '''<?xml version="1.0" encoding="utf-8" ?><transcript>
      <text start="0.0" dur="1.2">한국 코스트코가</text>
      <text start="1.2" dur="2.0">억울했던 &amp; 이유</text>
    </transcript>'''

    segments = parse_timedtext_xml(xml)

    assert [segment.text for segment in segments] == ["한국 코스트코가", "억울했던 & 이유"]
    assert segments[1].start == 1.2
    assert segments[1].duration == 2.0


class FakeFetcher:
    def fetch_video_transcript(self, video_id: str):
        return {
            "video_id": video_id,
            "status": "found",
            "language_code": "ko",
            "track_name": "한국어",
            "is_generated": True,
            "segment_count": 1,
            "text": f"script {video_id}",
            "segments": [{"start": 0.0, "duration": 1.0, "text": f"script {video_id}"}],
            "errors": [],
        }


def test_enrich_collection_ranks_shorts_by_views() -> None:
    collection = {
        "input": {"video_id": "seed", "collected_at": "2026-01-01T00:00:00Z"},
        "channel": {"normalized": {"channel_id": "channel", "channel_title": "테스트"}},
        "channel_videos": [
            {"normalized": {"video_id": "low", "title": "low", "view_count": 10, "is_probably_short": True}},
            {"normalized": {"video_id": "long", "title": "long", "view_count": 999, "is_probably_short": False}},
            {"normalized": {"video_id": "high", "title": "high", "view_count": 100, "is_probably_short": True}},
        ],
    }

    enriched = enrich_collection_with_transcripts(collection, limit=2, fetcher=FakeFetcher())

    assert enriched["transcript_collection"]["attempted"] == 2
    assert enriched["transcript_collection"]["found"] == 2
    assert [item["video_id"] for item in enriched["videos"]] == ["high", "low"]
    assert enriched["videos"][0]["transcript"]["text"] == "script high"

def test_enrich_collection_limit_zero_means_all_ranked_shorts() -> None:
    collection = {
        "input": {"video_id": "seed", "collected_at": "2026-01-01T00:00:00Z"},
        "channel": {"normalized": {"channel_id": "channel", "channel_title": "테스트"}},
        "channel_videos": [
            {"normalized": {"video_id": "low", "title": "low", "view_count": 10, "is_probably_short": True}},
            {"normalized": {"video_id": "long", "title": "long", "view_count": 999, "is_probably_short": False}},
            {"normalized": {"video_id": "mid", "title": "mid", "view_count": 50, "is_probably_short": True}},
            {"normalized": {"video_id": "high", "title": "high", "view_count": 100, "is_probably_short": True}},
        ],
    }

    enriched = enrich_collection_with_transcripts(collection, limit=0, fetcher=FakeFetcher())

    assert enriched["transcript_collection"]["requested_limit"] == 0
    assert enriched["transcript_collection"]["attempted"] == 3
    assert [item["video_id"] for item in enriched["videos"]] == ["high", "mid", "low"]


def test_fetch_public_transcript_list_preserves_order_and_deduplicates(tmp_path) -> None:
    targets = tmp_path / "targets.txt"
    targets.write_text(
        "Tb6DhFy9N_A\nhttps://www.youtube.com/shorts/onjVWrO2_5E\nTb6DhFy9N_A\n",
        encoding="utf-8",
    )
    output = tmp_path / "result.json"

    fetch_public_transcript_list_file(targets, output, fetcher=FakeFetcher())

    import json

    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["schema_version"] == "public-transcript-list-1"
    assert payload["transcript_collection"]["attempted"] == 2
    assert payload["transcript_collection"]["found"] == 2
    assert [video["video_id"] for video in payload["videos"]] == [
        "Tb6DhFy9N_A",
        "onjVWrO2_5E",
    ]


class BlockingFetcher:
    def fetch_video_transcript(self, video_id: str):
        return {
            "video_id": video_id,
            "status": "missing",
            "source": None,
            "segments": [],
            "text": "",
            "errors": [{"code": "transcript_api_error", "message": "Too many requests"}],
        }


def test_fetch_public_transcript_list_can_stop_after_ip_block(tmp_path) -> None:
    targets = tmp_path / "targets.txt"
    targets.write_text("Tb6DhFy9N_A\nonjVWrO2_5E\n", encoding="utf-8")
    output = tmp_path / "result.json"

    fetch_public_transcript_list_file(
        targets,
        output,
        fetcher=BlockingFetcher(),
        stop_on_ip_block=True,
    )

    import json

    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["transcript_collection"]["stopped_by_ip_block"] is True
    assert payload["videos"][0]["transcript"]["errors"][0]["code"] == "transcript_api_error"
    assert payload["videos"][1]["transcript"]["errors"][0]["code"] == "skipped_after_ip_block"
