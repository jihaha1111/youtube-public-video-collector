from __future__ import annotations

import json
import re
import time
from collections import Counter
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

import httpx

VIDEO_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{11}$")


def parse_video_id(value: str) -> str:
    raw = value.strip()
    if VIDEO_ID_PATTERN.fullmatch(raw):
        return raw
    parsed = urlparse(raw)
    host = parsed.netloc.lower().removeprefix("www.")
    if host == "youtu.be":
        video_id = parsed.path.strip("/").split("/", 1)[0]
    elif host in {"youtube.com", "m.youtube.com"}:
        parts = [part for part in parsed.path.split("/") if part]
        if parts and parts[0] in {"shorts", "embed", "live"} and len(parts) >= 2:
            video_id = parts[1]
        else:
            video_id = (parse_qs(parsed.query).get("v") or [""])[0]
    else:
        video_id = ""
    if not VIDEO_ID_PATTERN.fullmatch(video_id):
        raise ValueError(f"Invalid public YouTube video target: {value!r}")
    return video_id


def classify_short_path_response(status_code: int, location: str | None) -> str:
    if status_code == 200:
        return "shorts_path_accepted"
    if status_code in {301, 302, 303, 307, 308}:
        parsed = urlparse(location or "")
        if parsed.path == "/watch":
            return "redirected_to_watch_longform"
        return "redirected_unknown"
    if status_code in {403, 429}:
        return "blocked"
    if status_code == 404:
        return "not_found"
    return "unexpected_response"


class ShortsPathAuditor:
    def __init__(self, *, timeout: float = 20.0, client: httpx.Client | None = None) -> None:
        self._owned_client = client is None
        self.client = client or httpx.Client(
            timeout=timeout,
            follow_redirects=False,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
                ),
                "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
            },
        )

    def close(self) -> None:
        if self._owned_client:
            self.client.close()

    def audit(self, video_id: str) -> dict[str, Any]:
        requested_url = f"https://www.youtube.com/shorts/{video_id}"
        try:
            response = self.client.head(requested_url)
            location = response.headers.get("location")
            return {
                "video_id": video_id,
                "requested_url": requested_url,
                "status_code": response.status_code,
                "location": location,
                "classification": classify_short_path_response(response.status_code, location),
                "error": None,
            }
        except httpx.HTTPError as exc:
            return {
                "video_id": video_id,
                "requested_url": requested_url,
                "status_code": None,
                "location": None,
                "classification": "request_error",
                "error": f"{type(exc).__name__}: {exc}",
            }


def audit_short_path_list_file(
    targets_path: Path,
    output_path: Path,
    *,
    limit: int = 0,
    timeout: float = 20.0,
    sleep_seconds: float = 0.0,
    auditor: ShortsPathAuditor | None = None,
) -> Path:
    targets: list[str] = []
    seen: set[str] = set()
    for line in targets_path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        video_id = parse_video_id(stripped)
        if video_id in seen:
            continue
        seen.add(video_id)
        targets.append(video_id)
    if limit > 0:
        targets = targets[:limit]
    if not targets:
        raise ValueError("Target list must contain at least one public YouTube video")

    active_auditor = auditor or ShortsPathAuditor(timeout=timeout)
    records: list[dict[str, Any]] = []
    try:
        for index, video_id in enumerate(targets):
            records.append(active_auditor.audit(video_id))
            if sleep_seconds > 0 and index + 1 < len(targets):
                time.sleep(sleep_seconds)
    finally:
        if auditor is None:
            active_auditor.close()

    counts = Counter(record["classification"] for record in records)
    payload = {
        "schema_version": "youtube-shorts-path-audit-1",
        "shorts_path_audit": {
            "requested": len(targets),
            "attempted": len(records),
            "classification_counts": dict(sorted(counts.items())),
            "source": "youtube-public-shorts-path-head-response",
        },
        "videos": records,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return output_path
