from __future__ import annotations

import json

import httpx

from yt_collector.shorts_path import (
    ShortsPathAuditor,
    audit_short_path_list_file,
    classify_short_path_response,
    parse_video_id,
)


def test_parse_video_id_accepts_public_youtube_forms() -> None:
    assert parse_video_id("Tb6DhFy9N_A") == "Tb6DhFy9N_A"
    assert parse_video_id("https://www.youtube.com/shorts/Tb6DhFy9N_A") == "Tb6DhFy9N_A"
    assert parse_video_id("https://www.youtube.com/watch?v=Tb6DhFy9N_A") == "Tb6DhFy9N_A"
    assert parse_video_id("https://youtu.be/Tb6DhFy9N_A") == "Tb6DhFy9N_A"


def test_classify_short_path_response() -> None:
    assert classify_short_path_response(200, None) == "shorts_path_accepted"
    assert (
        classify_short_path_response(303, "https://www.youtube.com/watch?v=Tb6DhFy9N_A")
        == "redirected_to_watch_longform"
    )
    assert classify_short_path_response(429, None) == "blocked"


def test_audit_short_path_list_preserves_order_and_evidence(tmp_path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("Tb6DhFy9N_A"):
            return httpx.Response(200, request=request)
        return httpx.Response(
            303,
            headers={"location": "https://www.youtube.com/watch?v=onjVWrO2_5E"},
            request=request,
        )

    targets = tmp_path / "targets.txt"
    targets.write_text("Tb6DhFy9N_A\nonjVWrO2_5E\nTb6DhFy9N_A\n", encoding="utf-8")
    output = tmp_path / "result.json"
    client = httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=False)
    auditor = ShortsPathAuditor(client=client)

    audit_short_path_list_file(targets, output, auditor=auditor)

    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["schema_version"] == "youtube-shorts-path-audit-1"
    assert payload["shorts_path_audit"]["attempted"] == 2
    assert payload["shorts_path_audit"]["classification_counts"] == {
        "redirected_to_watch_longform": 1,
        "shorts_path_accepted": 1,
    }
    assert [record["video_id"] for record in payload["videos"]] == [
        "Tb6DhFy9N_A",
        "onjVWrO2_5E",
    ]
