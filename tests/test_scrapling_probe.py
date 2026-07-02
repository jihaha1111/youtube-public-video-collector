from __future__ import annotations

from yt_collector import scrapling_probe
from yt_collector.scrapling_probe import enrich_collection_with_scrapling_transcripts, extract_transcript_from_scrapling_response, proxy_from_env


class FakeResponse:
    def __init__(self, text: str, *, captured_xhr: list[object] | None = None) -> None:
        self.text = text
        self.captured_xhr = captured_xhr or []


def test_extract_transcript_from_scrapling_response_uses_caption_tracks() -> None:
    html = '''before "captionTracks":[
      {"baseUrl":"https://www.youtube.com/api/timedtext?v=abc\\u0026lang=ko","languageCode":"ko","name":{"simpleText":"한국어 (자동 생성됨)"},"kind":"asr","vssId":"a.ko"}
    ],"audioTracks" after'''
    xml = '''<?xml version="1.0" encoding="utf-8" ?><transcript>
      <text start="0.0" dur="1.0">코스트코의</text>
      <text start="1.0" dur="1.2">실수</text>
    </transcript>'''

    transcript = extract_transcript_from_scrapling_response(
        "Tb6DhFy9N_A",
        FakeResponse(html),
        preferred_language="ko",
        caption_xml_fetcher=lambda base_url: xml,
    )

    assert transcript["status"] == "found"
    assert transcript["language_code"] == "ko"
    assert transcript["is_generated"] is True
    assert transcript["text"] == "코스트코의 실수"
    assert transcript["segment_count"] == 2


def test_extract_transcript_from_scrapling_response_checks_captured_xhr() -> None:
    xhr = FakeResponse('''before "captionTracks":[
      {"baseUrl":"https://www.youtube.com/api/timedtext?v=abc\\u0026lang=ko","languageCode":"ko","name":{"simpleText":"한국어"},"vssId":".ko"}
    ],"audioTracks" after''')
    xml = '<transcript><text start="0.0" dur="1.0">자막</text></transcript>'

    transcript = extract_transcript_from_scrapling_response(
        "Tb6DhFy9N_A",
        FakeResponse("no tracks", captured_xhr=[xhr]),
        caption_xml_fetcher=lambda base_url: xml,
    )

    assert transcript["status"] == "found"
    assert transcript["text"] == "자막"


def test_proxy_from_env_trims_blank_values(monkeypatch) -> None:
    monkeypatch.setenv("SCRAPLING_PROXY_URL", "  http://proxy.example:8080  ")
    assert proxy_from_env() == "http://proxy.example:8080"

    monkeypatch.setenv("SCRAPLING_PROXY_URL", "   ")
    assert proxy_from_env() is None



def test_fetch_transcript_with_scrapling_falls_back_to_transcript_api(monkeypatch) -> None:
    class FakePublicTranscriptFetcher:
        def __init__(self, *, preferred_language: str) -> None:
            self.preferred_language = preferred_language

        def fetch_video_transcript(self, video_id: str):
            return {
                "video_id": video_id,
                "status": "found",
                "language_code": self.preferred_language,
                "track_name": "한국어",
                "is_generated": True,
                "segment_count": 1,
                "text": "대체 자막",
                "segments": [{"start": 0.0, "duration": 1.0, "text": "대체 자막"}],
                "errors": [],
            }

    monkeypatch.setattr(scrapling_probe, "_fetch_watch_page", lambda *args, **kwargs: FakeResponse("no tracks"))
    monkeypatch.setattr(scrapling_probe, "PublicTranscriptFetcher", FakePublicTranscriptFetcher)

    result = scrapling_probe.fetch_transcript_with_scrapling("https://www.youtube.com/watch?v=Tb6DhFy9N_A")

    assert result["transcript"]["status"] == "found"
    assert result["transcript"]["text"] == "대체 자막"
    assert result["transcript"]["source"] == "youtube_transcript_api_after_scrapling_no_caption_tracks"

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
                    "errors": [{"code": "caption_fetch_error", "message": "429 too many requests"}],
                }
            }
        return {
            "transcript": {
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
        }

    enriched = enrich_collection_with_scrapling_transcripts(collection, limit=3, fetch_one=fake_fetch_one)

    assert enriched["transcript_collection"]["attempted"] == 3
    assert enriched["transcript_collection"]["found"] == 0
    assert enriched["transcript_collection"]["stopped_by_block"] is True
    assert [item["video_id"] for item in enriched["videos"]] == ["blocked", "skipped", "low"]
    assert enriched["videos"][1]["transcript"]["errors"][0]["code"] == "skipped_after_block"
