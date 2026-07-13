from __future__ import annotations

from yt_collector import scrapling_probe
from yt_collector.scrapling_probe import (
    DOM_TRANSCRIPT_SOURCE,
    collect_target_list_with_scrapling_transcripts,
    enrich_collection_with_scrapling_transcripts,
    extract_dom_transcript_segments,
    extract_transcript_from_scrapling_response,
    parse_transcript_timestamp,
    proxy_from_env,
)


class FakeResponse:
    def __init__(self, text: str, *, captured_xhr: list[object] | None = None) -> None:
        self.text = text
        self.captured_xhr = captured_xhr or []


MODERN_DOM = """
<html><body>
  <transcript-segment-view-model>
    <span class="ytwTranscriptSegmentViewModelTimestamp">0:01</span>
    <span class="ytAttributedStringHost">첫 번째 문장</span>
  </transcript-segment-view-model>
  <transcript-segment-view-model>
    <span class="ytwTranscriptSegmentViewModelTimestamp">1:02</span>
    <span class="ytAttributedStringHost">두 번째 문장</span>
  </transcript-segment-view-model>
</body></html>
"""

LEGACY_DOM = """
<html><body>
  <ytd-transcript-segment-renderer>
    <div class="segment-timestamp">0:03</div>
    <yt-formatted-string class="segment-text">legacy text</yt-formatted-string>
  </ytd-transcript-segment-renderer>
</body></html>
"""


def test_extract_transcript_from_scrapling_response_uses_modern_dom_segments() -> None:
    transcript = extract_transcript_from_scrapling_response("Tb6DhFy9N_A", FakeResponse(MODERN_DOM), preferred_language="ko")

    assert transcript["status"] == "found"
    assert transcript["source"] == DOM_TRANSCRIPT_SOURCE
    assert transcript["language_code"] == "ko"
    assert transcript["segment_count"] == 2
    assert transcript["segments"] == [
        {"start": "0:01", "start_seconds": 1.0, "text": "첫 번째 문장"},
        {"start": "1:02", "start_seconds": 62.0, "text": "두 번째 문장"},
    ]
    assert transcript["failure_class"] is None
    assert transcript["stage_evidence"]


def test_extract_transcript_from_scrapling_response_uses_legacy_dom_segments() -> None:
    transcript = extract_transcript_from_scrapling_response("legacy", FakeResponse(LEGACY_DOM), preferred_language="en")

    assert transcript["status"] == "found"
    assert transcript["source"] == DOM_TRANSCRIPT_SOURCE
    assert transcript["segments"] == [{"start": "0:03", "start_seconds": 3.0, "text": "legacy text"}]


def test_parse_transcript_timestamp_handles_seconds_minutes_and_hours() -> None:
    assert parse_transcript_timestamp("7") == 7.0
    assert parse_transcript_timestamp("1:02") == 62.0
    assert parse_transcript_timestamp("1:02:03") == 3723.0
    assert parse_transcript_timestamp("not a timestamp") is None


def test_empty_transcript_container_is_segments_empty() -> None:
    transcript = extract_transcript_from_scrapling_response("empty", FakeResponse("<div id='transcript'></div>"))

    assert transcript["status"] == "missing"
    assert transcript["source"] == DOM_TRANSCRIPT_SOURCE
    assert transcript["failure_class"] == "segments_empty"
    assert transcript["segments"] == []
    assert transcript["errors"][0]["code"] == "segments_empty"


def test_missing_dom_schema_is_selector_drift() -> None:
    transcript = extract_transcript_from_scrapling_response("missing", FakeResponse("<html><body>No useful schema</body></html>"))

    assert transcript["status"] == "missing"
    assert transcript["source"] == DOM_TRANSCRIPT_SOURCE
    assert transcript["failure_class"] == "selector_drift"


def test_caption_tracks_only_input_cannot_produce_found() -> None:
    html = '''before "captionTracks":[
      {"baseUrl":"https://www.youtube.com/api/timedtext?v=abc\\u0026lang=ko","languageCode":"ko","name":{"simpleText":"한국어"},"vssId":".ko"}
    ],"audioTracks" after'''

    transcript = extract_transcript_from_scrapling_response("captions", FakeResponse(html))

    assert transcript["status"] == "missing"
    assert transcript["source"] == DOM_TRANSCRIPT_SOURCE
    assert "captionTracks" not in transcript["source"]
    assert "timedtext" not in transcript["source"]


def test_public_transcript_fetcher_fallback_is_not_invoked(monkeypatch) -> None:
    class FailingPublicTranscriptFetcher:
        def __init__(self, *args, **kwargs) -> None:
            raise AssertionError("PublicTranscriptFetcher must not be used by Scrapling DOM path")

    monkeypatch.setattr(scrapling_probe, "_fetch_watch_page", lambda *args, **kwargs: FakeResponse("no rendered transcript"))
    monkeypatch.setattr(scrapling_probe, "PublicTranscriptFetcher", FailingPublicTranscriptFetcher, raising=False)

    result = scrapling_probe.fetch_transcript_with_scrapling("https://www.youtube.com/watch?v=Tb6DhFy9N_A")

    assert result["transcript"]["status"] == "missing"
    assert result["transcript"]["source"] == DOM_TRANSCRIPT_SOURCE


def test_dom_payload_script_normalizes_to_schema() -> None:
    payload = {
        "segments": [{"start": "0:04", "text": "from browser"}],
        "evidence": [{"stage": "transcript_button", "ok": True}],
        "opened": True,
    }
    html = f'<script id="gjc-youtube-dom-transcript" type="application/json">{scrapling_probe.json.dumps(payload)}</script>'

    transcript = extract_transcript_from_scrapling_response("payload", FakeResponse(html))

    assert transcript["status"] == "found"
    assert transcript["segments"][0]["start_seconds"] == 4.0
    assert transcript["stage_evidence"] == payload["evidence"]


def test_dom_payload_classifies_panel_not_opened_after_button_click() -> None:
    payload = {
        "segments": [],
        "evidence": [{"stage": "transcript_button_direct", "ok": True}],
        "opened": True,
        "panel_opened": False,
    }
    html = f'<div id="gjc-youtube-dom-transcript">{scrapling_probe.json.dumps(payload)}</div>'

    transcript = extract_transcript_from_scrapling_response("panel", FakeResponse(html))

    assert transcript["status"] == "missing"
    assert transcript["failure_class"] == "panel_not_opened"
    assert transcript["errors"][0]["code"] == "panel_not_opened"


def test_dom_payload_classifies_page_action_exception() -> None:
    payload = {
        "segments": [],
        "evidence": [{"stage": "page_action", "ok": False, "error": "Error"}],
        "extractor_error": True,
        "opened": False,
    }
    html = f'<div id="gjc-youtube-dom-transcript">{scrapling_probe.json.dumps(payload)}</div>'

    transcript = extract_transcript_from_scrapling_response("error", FakeResponse(html))

    assert transcript["status"] == "missing"
    assert transcript["failure_class"] == "extractor_error"
    assert transcript["stage_evidence"] == payload["evidence"]


def test_extract_dom_transcript_segments_reports_evidence() -> None:
    segments, evidence = extract_dom_transcript_segments(MODERN_DOM)

    assert len(segments) == 2
    assert any(item["selector"] == "transcript-segment-view-model" for item in evidence)


def test_proxy_from_env_trims_blank_values(monkeypatch) -> None:
    monkeypatch.setenv("SCRAPLING_PROXY_URL", "  http://proxy.example:8080  ")
    assert proxy_from_env() == "http://proxy.example:8080"

    monkeypatch.setenv("SCRAPLING_PROXY_URL", "   ")
    assert proxy_from_env() is None


def test_enrich_collection_with_scrapling_transcripts_stops_after_block() -> None:
    collection = {
        "input": {"video_id": "seed", "collected_at": "2026-01-01T00:00:00Z"},
        "channel": {"normalized": {"channel_id": "channel", "channel_title": "테스트"}},
        "channel_videos": [
            {"normalized": {"video_id": "low", "title": "low", "view_count": 10, "is_probably_short": True}},
            {"normalized": {"video_id": "blocked", "title": "blocked", "view_count": 100, "is_probably_short": True}},
            {"normalized": {"video_id": "skipped", "title": "skipped", "view_count": 90, "is_probably_short": True}},
        ],
    }

    def fake_fetch_one(url: str):
        video_id = url.rsplit("=", 1)[-1]
        if video_id == "blocked":
            return {
                "transcript": {
                    "video_id": video_id,
                    "status": "missing",
                    "source": DOM_TRANSCRIPT_SOURCE,
                    "failure_class": "blocked_or_captcha",
                    "errors": [{"code": "blocked_or_captcha", "message": "captcha challenge"}],
                }
            }
        return {
            "transcript": {
                "video_id": video_id,
                "status": "found",
                "source": DOM_TRANSCRIPT_SOURCE,
                "language_code": "ko",
                "segment_count": 1,
                "text": f"script {video_id}",
                "segments": [{"start": "0:00", "start_seconds": 0.0, "text": f"script {video_id}"}],
                "errors": [],
                "failure_class": None,
                "stage_evidence": [],
            }
        }

    enriched = enrich_collection_with_scrapling_transcripts(collection, limit=3, fetch_one=fake_fetch_one)

    assert enriched["transcript_collection"]["attempted"] == 3
    assert enriched["transcript_collection"]["found"] == 0
    assert enriched["transcript_collection"]["stopped_by_block"] is True
    assert [item["video_id"] for item in enriched["videos"]] == ["blocked", "skipped", "low"]
    assert enriched["videos"][1]["transcript"]["errors"][0]["code"] == "skipped_after_block"


def test_enrich_collection_with_scrapling_transcripts_limit_zero_means_all() -> None:
    collection = {
        "input": {"video_id": "seed", "collected_at": "2026-01-01T00:00:00Z"},
        "channel": {"normalized": {"channel_id": "channel", "channel_title": "테스트"}},
        "channel_videos": [
            {"normalized": {"video_id": "low", "title": "low", "view_count": 10, "is_probably_short": True}},
            {"normalized": {"video_id": "mid", "title": "mid", "view_count": 90, "is_probably_short": True}},
            {"normalized": {"video_id": "high", "title": "high", "view_count": 100, "is_probably_short": True}},
        ],
    }

    def fake_fetch_one(url: str):
        video_id = url.rsplit("=", 1)[-1]
        return {
            "transcript": {
                "video_id": video_id,
                "status": "found",
                "source": DOM_TRANSCRIPT_SOURCE,
                "language_code": "ko",
                "segment_count": 1,
                "text": f"script {video_id}",
                "segments": [{"start": "0:00", "start_seconds": 0.0, "text": f"script {video_id}"}],
                "errors": [],
                "failure_class": None,
                "stage_evidence": [],
            }
        }

    enriched = enrich_collection_with_scrapling_transcripts(collection, limit=0, fetch_one=fake_fetch_one)

    assert enriched["transcript_collection"]["requested_limit"] == 0
    assert enriched["transcript_collection"]["attempted"] == 3
    assert [item["video_id"] for item in enriched["videos"]] == ["high", "mid", "low"]


def test_collect_target_list_preserves_order_deduplicates_and_accepts_video_ids() -> None:
    requested_urls: list[str] = []

    def fake_fetch_one(url: str):
        requested_urls.append(url)
        video_id = url.rsplit("=", 1)[-1]
        return {
            "transcript": {
                "video_id": video_id,
                "status": "found",
                "source": DOM_TRANSCRIPT_SOURCE,
                "language_code": "ko",
                "segment_count": 1,
                "text": f"script {video_id}",
                "segments": [
                    {"start": "0:00", "start_seconds": 0.0, "text": f"script {video_id}"}
                ],
                "errors": [],
                "failure_class": None,
                "stage_evidence": [],
            }
        }

    result = collect_target_list_with_scrapling_transcripts(
        [
            "# keep input order",
            "Tb6DhFy9N_A",
            "https://www.youtube.com/shorts/rGFXQlS9Cp4",
            "https://youtu.be/Tb6DhFy9N_A",
            "",
        ],
        limit=0,
        fetch_one=fake_fetch_one,
    )

    assert result["source_target_list"] == {
        "requested_nonblank_targets": 3,
        "unique_video_ids": 2,
        "selected_video_ids": ["Tb6DhFy9N_A", "rGFXQlS9Cp4"],
        "duplicates_removed": 1,
    }
    assert result["transcript_collection"]["attempted"] == 2
    assert result["transcript_collection"]["found"] == 2
    assert requested_urls == [
        "https://www.youtube.com/watch?v=Tb6DhFy9N_A",
        "https://www.youtube.com/watch?v=rGFXQlS9Cp4",
    ]


def test_collect_target_list_limit_and_stop_on_block() -> None:
    def fake_fetch_one(url: str):
        video_id = url.rsplit("=", 1)[-1]
        if video_id == "Tb6DhFy9N_A":
            return {
                "transcript": {
                    "video_id": video_id,
                    "status": "missing",
                    "source": DOM_TRANSCRIPT_SOURCE,
                    "failure_class": "blocked_or_captcha",
                    "errors": [{"code": "blocked_or_captcha", "message": "blocked"}],
                }
            }
        raise AssertionError("Later targets must be skipped after a block")

    result = collect_target_list_with_scrapling_transcripts(
        ["Tb6DhFy9N_A", "rGFXQlS9Cp4", "PFvCfu1ECK4"],
        limit=2,
        fetch_one=fake_fetch_one,
    )

    assert result["source_target_list"]["selected_video_ids"] == [
        "Tb6DhFy9N_A",
        "rGFXQlS9Cp4",
    ]
    assert result["transcript_collection"]["attempted"] == 2
    assert result["transcript_collection"]["found"] == 0
    assert result["transcript_collection"]["stopped_by_block"] is True
    assert result["videos"][1]["transcript"]["errors"][0]["code"] == "skipped_after_block"
