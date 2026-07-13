from __future__ import annotations

import html
import json
import os
import re
import time
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, Callable

from .transcripts import _limit_ranked_videos, _video_transcript_item
from .url_parser import parse_youtube_url

DOM_TRANSCRIPT_SOURCE = "scrapling_rendered_dom_transcript"
DOM_FAILURE_CLASSES = {
    "consent_required",
    "panel_button_not_found",
    "panel_not_opened",
    "segments_empty",
    "selector_drift",
    "blocked_or_captcha",
    "network_or_timeout",
    "actions_environment_blocked",
    "extractor_error",
    "unknown",
}
DOM_EVIDENCE_SCRIPT_ID = "gjc-youtube-dom-transcript"

ScraplingTranscriptFetcher = Callable[[str], dict[str, Any]]


def fetch_transcript_with_scrapling(
    raw_url: str,
    *,
    preferred_language: str = "ko",
    timeout_ms: int = 90_000,
    wait_ms: int = 500,
    headless: bool = True,
    proxy: str | None = None,
) -> dict[str, Any]:
    """Fetch one rendered YouTube transcript panel through Scrapling's browser fetcher."""
    parsed_url = parse_youtube_url(raw_url)
    try:
        response = _fetch_watch_page(
            parsed_url.canonical_watch_url,
            preferred_language=preferred_language,
            timeout_ms=timeout_ms,
            wait_ms=wait_ms,
            headless=headless,
            proxy=proxy,
        )
        transcript = extract_transcript_from_scrapling_response(
            parsed_url.video_id,
            response,
            preferred_language=preferred_language,
        )
    except Exception as exc:
        transcript = _missing(
            parsed_url.video_id,
            "network_or_timeout" if _looks_like_timeout(exc) else "extractor_error",
            str(exc),
            stage_evidence=[{"stage": "fetch_watch_page", "ok": False, "error": type(exc).__name__}],
        )
    return {
        "input": {
            "url": raw_url,
            "canonical_watch_url": parsed_url.canonical_watch_url,
            "video_id": parsed_url.video_id,
            "preferred_language": preferred_language,
            "fetcher": "scrapling.StealthyFetcher",
            "timeout_ms": timeout_ms,
            "wait_ms": wait_ms,
            "headless": headless,
            "used_proxy": bool(proxy),
        },
        "transcript": transcript,
    }


def write_scrapling_transcript_probe(
    raw_url: str,
    out_path: str | Path,
    *,
    preferred_language: str = "ko",
    timeout_ms: int = 90_000,
    wait_ms: int = 500,
    headless: bool = True,
    proxy: str | None = None,
) -> Path:
    result = fetch_transcript_with_scrapling(
        raw_url,
        preferred_language=preferred_language,
        timeout_ms=timeout_ms,
        wait_ms=wait_ms,
        headless=headless,
        proxy=proxy,
    )
    output = Path(out_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return output


def enrich_collection_with_scrapling_transcripts(
    collection: dict[str, Any],
    *,
    limit: int = 20,
    preferred_language: str = "ko",
    include_non_shorts: bool = False,
    timeout_ms: int = 90_000,
    wait_ms: int = 500,
    headless: bool = True,
    proxy: str | None = None,
    sleep_seconds: float = 0.0,
    stop_on_block: bool = True,
    fetch_one: ScraplingTranscriptFetcher | None = None,
) -> dict[str, Any]:
    videos = _limit_ranked_videos(collection, include_non_shorts=include_non_shorts, limit=limit)
    transcript_items = []
    stopped_by_block = False
    for index, video in enumerate(videos):
        normalized = video.get("normalized") or {}
        video_id = normalized.get("video_id")
        if not isinstance(video_id, str) or not video_id:
            continue
        if stopped_by_block:
            transcript = _missing(video_id, "blocked_or_captcha", "Skipped because an earlier Scrapling transcript request looked blocked.")
            transcript["errors"][0]["code"] = "skipped_after_block"
        else:
            watch_url = normalized.get("canonical_watch_url") or f"https://www.youtube.com/watch?v={video_id}"
            result = (
                fetch_one(watch_url)
                if fetch_one
                else fetch_transcript_with_scrapling(
                    watch_url,
                    preferred_language=preferred_language,
                    timeout_ms=timeout_ms,
                    wait_ms=wait_ms,
                    headless=headless,
                    proxy=proxy,
                )
            )
            transcript = result.get("transcript") if isinstance(result, dict) else None
            if not isinstance(transcript, dict):
                transcript = _missing(video_id, "extractor_error", "Scrapling fetcher returned an invalid result payload.")
            if stop_on_block and _looks_like_block(transcript):
                stopped_by_block = True
        transcript_items.append(_video_transcript_item(normalized, transcript))
        if sleep_seconds > 0 and index < len(videos) - 1 and not stopped_by_block:
            time.sleep(sleep_seconds)

    found_count = sum(1 for item in transcript_items if item["transcript"].get("status") == "found")
    return {
        "source_collection": {
            "input_video_id": (collection.get("input") or {}).get("video_id"),
            "collected_at": (collection.get("input") or {}).get("collected_at"),
            "channel": (collection.get("channel") or {}).get("normalized", {}),
            "total_channel_videos": len(collection.get("channel_videos") or []),
        },
        "transcript_collection": {
            "preferred_language": preferred_language,
            "requested_limit": limit,
            "include_non_shorts": include_non_shorts,
            "attempted": len(transcript_items),
            "found": found_count,
            "missing": len(transcript_items) - found_count,
            "fetcher": "scrapling.StealthyFetcher",
            "timeout_ms": timeout_ms,
            "wait_ms": wait_ms,
            "headless": headless,
            "used_proxy": bool(proxy),
            "sleep_seconds": sleep_seconds,
            "stopped_by_block": stopped_by_block,
        },
        "videos": transcript_items,
    }


def write_scrapling_collection_transcripts(
    collection_path: str | Path,
    out_path: str | Path,
    *,
    limit: int = 20,
    preferred_language: str = "ko",
    include_non_shorts: bool = False,
    timeout_ms: int = 90_000,
    wait_ms: int = 500,
    headless: bool = True,
    proxy: str | None = None,
    sleep_seconds: float = 0.0,
    stop_on_block: bool = True,
) -> Path:
    collection = json.loads(Path(collection_path).read_text(encoding="utf-8"))
    if isinstance(collection, list):
        if len(collection) != 1:
            raise ValueError("Scrapling transcript enrichment expects a single collection result object")
        collection = collection[0]
    if not isinstance(collection, dict):
        raise ValueError("collection JSON must be an object")
    result = enrich_collection_with_scrapling_transcripts(
        collection,
        limit=limit,
        preferred_language=preferred_language,
        include_non_shorts=include_non_shorts,
        timeout_ms=timeout_ms,
        wait_ms=wait_ms,
        headless=headless,
        proxy=proxy,
        sleep_seconds=sleep_seconds,
        stop_on_block=stop_on_block,
    )
    output = Path(out_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return output


def collect_target_list_with_scrapling_transcripts(
    raw_targets: list[str],
    *,
    limit: int = 0,
    preferred_language: str = "ko",
    timeout_ms: int = 90_000,
    wait_ms: int = 500,
    headless: bool = True,
    proxy: str | None = None,
    sleep_seconds: float = 0.0,
    stop_on_block: bool = True,
    fetch_one: ScraplingTranscriptFetcher | None = None,
) -> dict[str, Any]:
    """Fetch rendered DOM transcripts for an explicit ordered URL/video-ID list."""
    if limit < 0:
        raise ValueError("limit must be 0 or greater")

    targets: list[dict[str, str]] = []
    seen_video_ids: set[str] = set()
    for raw_target in raw_targets:
        target = raw_target.strip()
        if not target or target.startswith("#"):
            continue
        raw_url = (
            f"https://www.youtube.com/watch?v={target}"
            if re.fullmatch(r"[A-Za-z0-9_-]{11}", target)
            else target
        )
        parsed = parse_youtube_url(raw_url)
        if parsed.video_id in seen_video_ids:
            continue
        seen_video_ids.add(parsed.video_id)
        targets.append(
            {
                "raw_target": target,
                "video_id": parsed.video_id,
                "canonical_watch_url": parsed.canonical_watch_url,
                "canonical_shorts_url": parsed.canonical_shorts_url,
            }
        )

    if not targets:
        raise ValueError("target list must contain at least one YouTube URL or video ID")
    selected_targets = targets if limit == 0 else targets[:limit]

    transcript_items: list[dict[str, Any]] = []
    stopped_by_block = False
    for index, target in enumerate(selected_targets):
        video_id = target["video_id"]
        if stopped_by_block:
            transcript = _missing(
                video_id,
                "blocked_or_captcha",
                "Skipped because an earlier Scrapling transcript request looked blocked.",
            )
            transcript["errors"][0]["code"] = "skipped_after_block"
        else:
            result = (
                fetch_one(target["canonical_watch_url"])
                if fetch_one
                else fetch_transcript_with_scrapling(
                    target["canonical_watch_url"],
                    preferred_language=preferred_language,
                    timeout_ms=timeout_ms,
                    wait_ms=wait_ms,
                    headless=headless,
                    proxy=proxy,
                )
            )
            transcript = result.get("transcript") if isinstance(result, dict) else None
            if not isinstance(transcript, dict):
                transcript = _missing(
                    video_id,
                    "extractor_error",
                    "Scrapling fetcher returned an invalid result payload.",
                )
            if stop_on_block and _looks_like_block(transcript):
                stopped_by_block = True

        transcript_items.append(
            {
                "raw_target": target["raw_target"],
                **_video_transcript_item(
                    {
                        "video_id": video_id,
                        "canonical_watch_url": target["canonical_watch_url"],
                        "canonical_shorts_url": target["canonical_shorts_url"],
                    },
                    transcript,
                ),
            }
        )
        if sleep_seconds > 0 and index < len(selected_targets) - 1 and not stopped_by_block:
            time.sleep(sleep_seconds)

    found_count = sum(
        1 for item in transcript_items if item["transcript"].get("status") == "found"
    )
    failure_counts: dict[str, int] = {}
    for item in transcript_items:
        transcript = item["transcript"]
        if transcript.get("status") == "found":
            continue
        failure_class = transcript.get("failure_class") or "unknown"
        failure_counts[failure_class] = failure_counts.get(failure_class, 0) + 1

    return {
        "source_target_list": {
            "requested_nonblank_targets": len(
                [target for target in raw_targets if target.strip() and not target.strip().startswith("#")]
            ),
            "unique_video_ids": len(targets),
            "selected_video_ids": [target["video_id"] for target in selected_targets],
            "duplicates_removed": len(
                [target for target in raw_targets if target.strip() and not target.strip().startswith("#")]
            )
            - len(targets),
        },
        "transcript_collection": {
            "preferred_language": preferred_language,
            "requested_limit": limit,
            "attempted": len(transcript_items),
            "found": found_count,
            "missing": len(transcript_items) - found_count,
            "failure_counts": dict(sorted(failure_counts.items())),
            "fetcher": "scrapling.StealthyFetcher",
            "source": DOM_TRANSCRIPT_SOURCE,
            "timeout_ms": timeout_ms,
            "wait_ms": wait_ms,
            "headless": headless,
            "used_proxy": bool(proxy),
            "sleep_seconds": sleep_seconds,
            "stopped_by_block": stopped_by_block,
        },
        "videos": transcript_items,
    }


def write_scrapling_target_list_transcripts(
    targets_path: str | Path,
    out_path: str | Path,
    *,
    limit: int = 0,
    preferred_language: str = "ko",
    timeout_ms: int = 90_000,
    wait_ms: int = 500,
    headless: bool = True,
    proxy: str | None = None,
    sleep_seconds: float = 0.0,
    stop_on_block: bool = True,
) -> Path:
    targets = Path(targets_path).read_text(encoding="utf-8").splitlines()
    result = collect_target_list_with_scrapling_transcripts(
        targets,
        limit=limit,
        preferred_language=preferred_language,
        timeout_ms=timeout_ms,
        wait_ms=wait_ms,
        headless=headless,
        proxy=proxy,
        sleep_seconds=sleep_seconds,
        stop_on_block=stop_on_block,
    )
    output = Path(out_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return output


def extract_transcript_from_scrapling_response(
    video_id: str,
    response: Any,
    *,
    preferred_language: str = "ko",
    **_: Any,
) -> dict[str, Any]:
    """Normalize rendered transcript-panel DOM evidence into the Scrapling transcript schema."""
    text = _response_text(response)
    payload = _extract_dom_payload(text)
    if isinstance(payload, dict):
        return _transcript_from_dom_payload(video_id, payload, preferred_language=preferred_language)

    stage_evidence = [{"stage": "response_html", "ok": True, "text_length": len(text)}]
    if _looks_like_block_text(text):
        return _missing(video_id, "blocked_or_captcha", "Rendered page appears blocked or challenged.", stage_evidence=stage_evidence)
    segments, evidence = extract_dom_transcript_segments(text)
    stage_evidence.extend(evidence)
    if segments:
        return _found(video_id, preferred_language, segments, stage_evidence)
    failure_class = "segments_empty" if _has_transcript_container(text) else "selector_drift"
    return _missing(video_id, failure_class, "Rendered transcript DOM segments were not found.", stage_evidence=stage_evidence)


def extract_dom_transcript_segments(markup: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    modern = _extract_modern_dom_segments(markup)
    legacy = _extract_legacy_dom_segments(markup)
    evidence = [
        {"stage": "parse_modern_segments", "ok": bool(modern), "selector": "transcript-segment-view-model", "count": len(modern)},
        {"stage": "parse_legacy_segments", "ok": bool(legacy), "selector": "ytd-transcript-segment-renderer", "count": len(legacy)},
    ]
    return (modern or legacy), evidence


def parse_transcript_timestamp(value: str) -> float | None:
    parts = [part.strip() for part in value.strip().split(":")]
    if not parts or any(not part for part in parts):
        return None
    try:
        numbers = [int(part) for part in parts]
    except ValueError:
        return None
    if len(numbers) == 1:
        return float(numbers[0])
    if len(numbers) == 2:
        minutes, seconds = numbers
        return float(minutes * 60 + seconds)
    if len(numbers) == 3:
        hours, minutes, seconds = numbers
        return float(hours * 3600 + minutes * 60 + seconds)
    return None


def proxy_from_env() -> str | None:
    value = os.getenv("SCRAPLING_PROXY_URL", "").strip()
    return value or None


def _fetch_watch_page(
    watch_url: str,
    *,
    preferred_language: str,
    timeout_ms: int,
    wait_ms: int,
    headless: bool,
    proxy: str | None,
) -> Any:
    try:
        from scrapling.fetchers import StealthyFetcher
    except ImportError as exc:  # pragma: no cover - exercised only without optional dependency installed.
        raise RuntimeError("Install Scrapling support with `python -m pip install -e '.[scrapling]'`.") from exc

    page_action = lambda page: _capture_rendered_dom_transcript(page, timeout_ms=timeout_ms, settle_ms=wait_ms)
    kwargs: dict[str, Any] = {
        "headless": headless,
        "network_idle": True,
        "timeout": timeout_ms,
        "wait": 0,
        "block_webrtc": True,
        "locale": "ko-KR" if preferred_language.startswith("ko") else "en-US",
        "timezone_id": "Asia/Seoul" if preferred_language.startswith("ko") else "UTC",
        "page_action": page_action,
        "extra_headers": {"Accept-Language": f"{preferred_language},en;q=0.8"},
    }
    if proxy:
        kwargs["proxy"] = proxy
    return StealthyFetcher.fetch(watch_url, **kwargs)


def _capture_rendered_dom_transcript(page: Any, *, timeout_ms: int, settle_ms: int) -> None:
    action_timeout_ms = max(1_000, timeout_ms - 1_000)
    poll_interval_ms = max(50, min(250, action_timeout_ms // 300))
    script = r"""
async () => {
    const evidence = [];
    const actionTimeoutMs = __ACTION_TIMEOUT_MS__;
    const settleMaxMs = __SETTLE_MAX_MS__;
    const pollIntervalMs = __POLL_INTERVAL_MS__;
    const deadline = Date.now() + actionTimeoutMs;
    const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
    const textOf = (node) => (node && (node.innerText || node.textContent || '') || '').replace(/\s+/g, ' ').trim();
    const record = (stage, data = {}) => evidence.push(Object.assign({stage, elapsed_ms: Date.now() - (deadline - actionTimeoutMs)}, data));
    const labelOf = (node) => [textOf(node), node?.getAttribute?.('aria-label') || '', node?.getAttribute?.('title') || ''].join(' ').toLowerCase();
    const isVisible = (el) => !!el && (el.offsetParent !== null || el.getClientRects().length > 0);
    const visibleFor = (selectors, keywords = []) => {
      for (const selector of selectors) {
        const candidates = Array.from(document.querySelectorAll(selector)).filter(isVisible);
        const filtered = keywords.length ? candidates.filter((el) => keywords.some((keyword) => labelOf(el).includes(keyword))) : candidates;
        if (filtered.length) {
          return {selector, candidates: candidates.length, matched: filtered.length, element: filtered[0]};
        }
      }
      return null;
    };
    const clickElement = (stage, match) => {
      if (!match?.element) return false;
      try {
        match.element.scrollIntoView({block: 'center', inline: 'center'});
        match.element.click();
        record(stage, {ok: true, selector: match.selector, candidates: match.candidates, matched: match.matched, text: textOf(match.element), label: labelOf(match.element)});
        return true;
      } catch (error) {
        record(stage, {ok: false, selector: match.selector, error: String(error)});
        return false;
      }
    };
    const countSegments = () => ({
      modern: document.querySelectorAll('transcript-segment-view-model').length,
      legacy: document.querySelectorAll('ytd-transcript-segment-renderer').length
    });
    const panelCount = () => document.querySelectorAll('ytd-engagement-panel-section-list-renderer[target-id="engagement-panel-searchable-transcript"], ytd-transcript-renderer, ytd-transcript-search-panel-renderer').length;
    const waitUntil = async (stage, predicate, maxMs) => {
      const localDeadline = Date.now() + Math.max(0, maxMs);
      let iterations = 0;
      while (Date.now() <= localDeadline && Date.now() <= deadline) {
        const value = predicate();
        if (value) {
          record(stage, {ok: true, iterations, value});
          return value;
        }
        iterations += 1;
        await sleep(pollIntervalMs);
      }
      record(stage, {ok: false, iterations, timeout_ms: maxMs});
      return null;
    };
    const transcriptKeywords = ['transcript', '스크립트', '스크립트 표시'];
    const transcriptSelectors = ['button', 'yt-button-view-model button', 'ytd-menu-service-item-renderer', 'tp-yt-paper-item', '[role="menuitem"]'];
    const expandSelectors = ['tp-yt-paper-button#expand', '#description-inline-expander #expand', 'ytd-text-inline-expander tp-yt-paper-button', 'button[aria-label*="more" i]', 'button[aria-label*="더보기"]'];
    const overflowSelectors = ['button[aria-label*="more" i]', 'button[aria-label*="추가 작업"]', 'button[aria-label*="더보기"]', 'button[title*="more" i]'];
    const consentSelectors = ['button[aria-label*="Accept" i]', 'button[aria-label*="동의"]', 'button[aria-label*="모두 수락"]', 'tp-yt-paper-dialog button', 'ytd-consent-bump-v2-lightbox button', 'button.yt-spec-button-shape-next'];

    await waitUntil('body_ready', () => document.body && textOf(document.body).length > 0, settleMaxMs);
    const bodyText = textOf(document.body).toLowerCase();
    const blocked = /captcha|unusual traffic|confirm you're not a bot|robot|429|403/.test(bodyText);
    const consent = /accept all|reject all|i agree|동의|모두 수락/.test(bodyText);
    record('initial_page', {url: location.href, bodyTextLength: bodyText.length, blocked, consent, actionTimeoutMs, settleMaxMs, pollIntervalMs});

    const consentMatch = visibleFor(consentSelectors);
    if (consentMatch) clickElement('consent_or_overlay', consentMatch);

    let opened = false;
    let expandClicked = false;
    let overflowClicked = false;
    let segmentsState = countSegments();

    while (Date.now() <= deadline) {
      segmentsState = countSegments();
      if (segmentsState.modern || segmentsState.legacy) {
        record('segments_ready', segmentsState);
        break;
      }

      const transcriptMatch = visibleFor(transcriptSelectors, transcriptKeywords);
      if (transcriptMatch) {
        opened = clickElement(opened ? 'transcript_menu_item' : 'transcript_button_direct', transcriptMatch) || opened;
        await waitUntil('segments_after_click', () => {
          const counts = countSegments();
          return (counts.modern || counts.legacy) ? counts : null;
        }, Math.max(0, deadline - Date.now()));
        segmentsState = countSegments();
        break;
      }

      if (!expandClicked) {
        const expandMatch = visibleFor(expandSelectors, ['more', '더보기']);
        if (expandMatch && clickElement('description_expand', expandMatch)) {
          expandClicked = true;
          continue;
        }
      }

      if (!overflowClicked) {
        const overflowMatch = visibleFor(overflowSelectors, ['more', '추가 작업', '더보기']);
        if (overflowMatch && clickElement('overflow_menu', overflowMatch)) {
          overflowClicked = true;
          continue;
        }
      }

      await sleep(pollIntervalMs);
    }

    segmentsState = countSegments();
    if (!segmentsState.modern && !segmentsState.legacy) {
      record('condition_timeout', {opened, panelCount: panelCount(), modern: segmentsState.modern, legacy: segmentsState.legacy});
    }

    const segments = [];
    for (const node of document.querySelectorAll('transcript-segment-view-model')) {
      const start = textOf(node.querySelector('.ytwTranscriptSegmentViewModelTimestamp, [class*="Timestamp"]'));
      const text = textOf(node.querySelector('.ytAttributedStringHost, [class*="ytAttributedStringHost"]'));
      if (start || text) segments.push({start, text});
    }
    for (const node of document.querySelectorAll('ytd-transcript-segment-renderer')) {
      const start = textOf(node.querySelector('.segment-timestamp, [class*="timestamp"]'));
      const text = textOf(node.querySelector('.segment-text, yt-formatted-string, [class*="segment-text"]'));
      if (start || text) segments.push({start, text});
    }
    const currentPanelCount = panelCount();
    record('panel_state', {opened, panelCount: currentPanelCount, modern: segmentsState.modern, legacy: segmentsState.legacy});
    const payload = {segments, evidence, blocked, consent, opened, panel_opened: currentPanelCount > 0, url: location.href};
    const old = document.getElementById('__DOM_EVIDENCE_SCRIPT_ID__');
    if (old) old.remove();
    const node = document.createElement('div');
    node.id = '__DOM_EVIDENCE_SCRIPT_ID__';
    node.hidden = true;
    node.setAttribute('data-gjc-json', 'dom-transcript');
    node.textContent = JSON.stringify(payload);
    document.documentElement.appendChild(node);
}
"""
    script = (
        script.replace("__DOM_EVIDENCE_SCRIPT_ID__", DOM_EVIDENCE_SCRIPT_ID)
        .replace("__ACTION_TIMEOUT_MS__", str(action_timeout_ms))
        .replace("__SETTLE_MAX_MS__", str(max(0, settle_ms)))
        .replace("__POLL_INTERVAL_MS__", str(poll_interval_ms))
    )
    try:
        page.evaluate(script)
    except Exception as exc:
        error_payload = {
            "segments": [],
            "evidence": [
                {
                    "stage": "page_action",
                    "ok": False,
                    "error": type(exc).__name__,
                    "message": str(exc),
                    "timeout_ms": timeout_ms,
                    "settle_ms": settle_ms,
                }
            ],
            "extractor_error": True,
            "opened": False,
        }
        try:
            page.evaluate(
                f"""payload => {{
                    const old = document.getElementById('{DOM_EVIDENCE_SCRIPT_ID}');
                    if (old) old.remove();
                    const node = document.createElement('div');
                    node.id = '{DOM_EVIDENCE_SCRIPT_ID}';
                    node.hidden = true;
                    node.setAttribute('data-gjc-json', 'dom-transcript');
                    node.textContent = payload;
                    document.documentElement.appendChild(node);
                }}""",
                json.dumps(error_payload, ensure_ascii=False),
            )
        except Exception:
            return


def _extract_dom_payload(markup: str) -> dict[str, Any] | None:
    pattern = rf'<(?:script|template|div)[^>]+id=["\']{re.escape(DOM_EVIDENCE_SCRIPT_ID)}["\'][^>]*>(.*?)</(?:script|template|div)>'
    match = re.search(pattern, markup, flags=re.IGNORECASE | re.DOTALL)
    if not match:
        return None
    try:
        payload = json.loads(html.unescape(match.group(1)).strip())
    except json.JSONDecodeError:
        return None
    return payload if isinstance(payload, dict) else None


def _transcript_from_dom_payload(video_id: str, payload: dict[str, Any], *, preferred_language: str) -> dict[str, Any]:
    stage_evidence = payload.get("evidence") if isinstance(payload.get("evidence"), list) else []
    raw_segments = payload.get("segments") if isinstance(payload.get("segments"), list) else []
    segments = _normalize_dom_segments(raw_segments)
    if segments:
        return _found(video_id, preferred_language, segments, stage_evidence)
    if payload.get("extractor_error"):
        failure_class = "extractor_error"
    elif payload.get("blocked"):
        failure_class = "blocked_or_captcha"
    elif payload.get("consent") and not payload.get("opened"):
        failure_class = "consent_required"
    elif payload.get("opened") is False:
        failure_class = "panel_button_not_found"
    elif payload.get("opened") and not payload.get("panel_opened"):
        failure_class = "panel_not_opened"
    else:
        failure_class = "segments_empty"
    return _missing(video_id, failure_class, "Rendered transcript DOM segments were not found.", stage_evidence=stage_evidence)


def _normalize_dom_segments(raw_segments: list[Any]) -> list[dict[str, Any]]:
    segments = []
    for item in raw_segments:
        if not isinstance(item, dict):
            continue
        start = str(item.get("start") or "").strip()
        text = str(item.get("text") or "").strip()
        start_seconds = parse_transcript_timestamp(start)
        if start and text and start_seconds is not None:
            segments.append({"start": start, "start_seconds": start_seconds, "text": text})
    return segments


def _extract_modern_dom_segments(markup: str) -> list[dict[str, Any]]:
    parser = _TranscriptHtmlParser("transcript-segment-view-model")
    parser.feed(markup)
    return _normalize_dom_segments(parser.segments)


def _extract_legacy_dom_segments(markup: str) -> list[dict[str, Any]]:
    parser = _TranscriptHtmlParser("ytd-transcript-segment-renderer")
    parser.feed(markup)
    return _normalize_dom_segments(parser.segments)


class _TranscriptHtmlParser(HTMLParser):
    def __init__(self, segment_tag: str) -> None:
        super().__init__(convert_charrefs=True)
        self.segment_tag = segment_tag
        self.segments: list[dict[str, str]] = []
        self._depth = 0
        self._current: dict[str, list[str]] | None = None
        self._capture: str | None = None
        self._capture_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attrs_dict = {name: value or "" for name, value in attrs}
        tag = tag.lower()
        if tag == self.segment_tag:
            self._depth = 1
            self._current = {"start": [], "text": []}
            return
        if self._depth:
            self._depth += 1
            classes = attrs_dict.get("class", "")
            if self.segment_tag == "transcript-segment-view-model":
                if tag == "ytwtranscriptsegmentviewmodeltimestamp" or "ytwTranscriptSegmentViewModelTimestamp" in classes:
                    self._capture = "start"
                    self._capture_depth = self._depth
                elif tag == "ytattributedstringhost" or "ytAttributedStringHost" in classes:
                    self._capture = "text"
                    self._capture_depth = self._depth
            else:
                if "segment-timestamp" in classes or "timestamp" in classes:
                    self._capture = "start"
                    self._capture_depth = self._depth
                elif "segment-text" in classes or tag == "yt-formatted-string":
                    self._capture = "text"
                    self._capture_depth = self._depth

    def handle_endtag(self, tag: str) -> None:
        if not self._depth:
            return
        if self._capture and self._depth == self._capture_depth:
            self._capture = None
        if tag.lower() == self.segment_tag and self._current is not None:
            self.segments.append({key: " ".join(value).strip() for key, value in self._current.items()})
            self._current = None
            self._depth = 0
            self._capture = None
            return
        self._depth -= 1

    def handle_data(self, data: str) -> None:
        if self._current is not None and self._capture:
            value = " ".join(data.split())
            if value:
                self._current[self._capture].append(value)


def _found(video_id: str, language_code: str, segments: list[dict[str, Any]], stage_evidence: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "video_id": video_id,
        "status": "found",
        "source": DOM_TRANSCRIPT_SOURCE,
        "language_code": language_code,
        "track_name": None,
        "is_generated": None,
        "segment_count": len(segments),
        "text": " ".join(segment["text"] for segment in segments if segment.get("text")).strip(),
        "segments": segments,
        "errors": [],
        "failure_class": None,
        "stage_evidence": stage_evidence,
    }


def _missing(video_id: str, failure_class: str, message: str, *, stage_evidence: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    normalized_failure = failure_class if failure_class in DOM_FAILURE_CLASSES else "unknown"
    return {
        "video_id": video_id,
        "status": "missing",
        "source": DOM_TRANSCRIPT_SOURCE,
        "language_code": None,
        "track_name": None,
        "is_generated": None,
        "segment_count": 0,
        "text": "",
        "segments": [],
        "errors": [{"code": normalized_failure, "message": message}],
        "failure_class": normalized_failure,
        "stage_evidence": stage_evidence or [],
    }


def _response_text(response: Any) -> str:
    text_value = getattr(response, "text", None)
    if isinstance(text_value, str) and text_value:
        return text_value
    if callable(text_value):
        try:
            called = text_value()
        except TypeError:
            called = None
        if isinstance(called, str):
            return called

    body = getattr(response, "body", b"")
    if isinstance(body, bytes):
        encoding = getattr(response, "encoding", None) or "utf-8"
        return body.decode(encoding, errors="replace")
    if isinstance(body, str):
        return body
    return str(response)


def _looks_like_block(transcript: dict[str, Any]) -> bool:
    if transcript.get("status") == "found":
        return False
    if transcript.get("failure_class") in {"blocked_or_captcha", "actions_environment_blocked", "network_or_timeout"}:
        return True
    errors = transcript.get("errors")
    if not isinstance(errors, list):
        return False
    text = " ".join(
        str(error.get("message", "")) + " " + str(error.get("code", ""))
        for error in errors
        if isinstance(error, dict)
    ).lower()
    return _looks_like_block_text(text)


def _looks_like_block_text(text: str) -> bool:
    lowered = text.lower()
    block_markers = (
        "429",
        "403",
        "blocked",
        "too many requests",
        "unusual traffic",
        "confirm you're not a bot",
        "captcha",
        "robot",
    )
    return any(marker in lowered for marker in block_markers)


def _looks_like_timeout(exc: Exception) -> bool:
    text = f"{type(exc).__name__} {exc}".lower()
    return "timeout" in text or "network" in text


def _has_transcript_container(markup: str) -> bool:
    lowered = markup.lower()
    return "transcript" in lowered or "스크립트" in lowered or "ytd-transcript" in lowered
