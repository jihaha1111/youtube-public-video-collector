from __future__ import annotations

import argparse
import json
from pathlib import Path

from yt_collector.transcripts import PublicTranscriptFetcher


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Fetch one public YouTube transcript through the API/watch-page fallback path."
    )
    parser.add_argument("video_id")
    parser.add_argument("--language", default="ko")
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()

    transcript = PublicTranscriptFetcher(preferred_language=args.language).fetch_video_transcript(
        args.video_id
    )
    payload = {
        "schema_version": "public-transcript-probe-1",
        "source": "youtube-transcript-api-with-watch-page-fallback",
        "preferred_language": args.language,
        "video_id": args.video_id,
        "transcript": transcript,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"{args.video_id}: {transcript['status']} ({transcript.get('segment_count', 0)} segments)")


if __name__ == "__main__":
    main()
