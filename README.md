# YouTube Public Video Collector

공개 YouTube watch/Shorts URL을 입력받아 쇼핑/제휴마케팅 콘텐츠 분석에 필요한 공개 메타데이터를 수집하는 Python 3.11 CLI MVP입니다. 대시보드나 웹앱 없이 데이터 수집 파이프라인, mock mode, JSON/CSV export에 집중합니다.

## 설치

이 프로젝트는 Python 3.11로 고정합니다. `.python-version`도 `3.11.15`로 추가되어 pyenv/asdf 환경에서 자동 선택됩니다.

```bash
python3.11 -m venv .venv
.venv/bin/python -m pip install -e ".[dev]"
.venv/bin/python --version
```

편의 명령도 제공합니다.

```bash
make install
make test
make mock
```

## `.env` 설정 / API key 전달

권장 방식은 프로젝트 루트에 `.env` 파일을 두는 것입니다. `.env`는 `.gitignore`에 포함되어 커밋되지 않습니다.

```bash
cp .env.example .env
# .env
YOUTUBE_API_KEY=your_public_youtube_data_api_key
```

일회성으로만 실행할 때는 환경변수로 직접 전달할 수도 있습니다.

```bash
YOUTUBE_API_KEY=your_public_youtube_data_api_key \
  .venv/bin/python -m yt_collector.cli collect \
  --url "https://youtu.be/onjVWrO2_5E" \
  --limit 3 \
  --format json \
  --out output/result.json
```

`YOUTUBE_API_KEY`가 없거나 `--mock`을 지정하면 mock mode로 동작합니다.

## Mock mode 실행

mock mode는 실제 API 없이도 최종 JSON 구조를 생성합니다. 입력 URL 1개 기준 해당 채널에 공개 영상이 정확히 3개 있다고 가정합니다.

```bash
.venv/bin/python -m yt_collector.cli collect \
  --url "https://www.youtube.com/watch?v=onjVWrO2_5E" \
  --limit 3 \
  --format json \
  --out output/result.json \
  --mock
```

여러 URL:

```bash
.venv/bin/python -m yt_collector.cli collect \
  --urls-file input_urls.txt \
  --limit 3 \
  --format json \
  --out output/result.json \
  --mock
```

## Real API mode 실행

```bash
.venv/bin/python -m yt_collector.cli collect \
  --url "https://youtu.be/onjVWrO2_5E" \
  --limit 3 \
  --format json \
  --out output/result.json
```

Real mode는 YouTube Data API v3의 `videos.list`, `channels.list`, `playlistItems.list`를 사용합니다. `collect` 명령은 댓글 본문이나 YouTube Studio/Analytics 내부 지표를 수집하지 않습니다.

`--limit 0`은 real API mode에서 업로드 플레이리스트를 페이지 끝까지 따라가며 public 후보 전체를 수집합니다. API quota를 쓰므로 먼저 작은 `--limit`로 샘플을 확인한 뒤 전체 실행에 사용하세요.

GitHub Actions의 `Channel Scrapling transcripts` 워크플로는 `url` 입력에 줄바꿈으로 여러 채널의 대표 watch/Shorts URL을 받을 수 있습니다. 여러 URL일 때는 내부에서 `--urls-file`로 일괄 수집하며 결과 JSON은 배열입니다. 대본 브라우저 작업 없이 메타데이터만 수집할 때는 `language` 입력을 `metadata-only`로 설정합니다. 단일 URL과 일반 언어 코드를 사용하는 기존 실행 방식은 그대로 유지됩니다.

## Public transcript enrichment

`collect`로 만든 단일 collection JSON에서 조회수 상위 Shorts의 공개 자막/자동자막 transcript를 보강할 수 있습니다.

```bash
.venv/bin/python -m yt_collector.cli transcripts \
  --collection output/result.json \
  --limit 20 \
  --language ko \
  --out output/top20_transcripts.json
```

이 명령은 `youtube-transcript-api`를 우선 사용하고, watch page의 공개 caption track 파싱을 fallback으로 둡니다. 공개 자막이 없거나 지역/연령/YouTube 응답 변경으로 막힌 영상은 `status: "missing"`과 error reason을 기록합니다. 자동 생성 자막은 인식 오류가 있을 수 있으므로 실제 프롬프트 seed로 쓰기 전 사람이 정리하는 것을 권장합니다.

## Scrapling/Patchright rendered DOM transcript

`youtube-transcript-api`/`timedtext` fallback을 성공으로 보지 않고, YouTube 페이지를 브라우저 렌더링한 뒤 DOM transcript 패널에서 가져온 결과만 `source: "scrapling_rendered_dom_transcript"`로 기록합니다. Transcript 버튼/메뉴와 `transcript-segment-view-model` 또는 `ytd-transcript-segment-renderer` 세그먼트 DOM이 나타나는 조건을 기다리며, `--wait-ms`는 고정 대기가 아니라 초기 DOM settle 조건의 최대 대기값입니다.

샘플 실행:

```bash
.venv/bin/python -m yt_collector.cli collect \
  --url "https://www.youtube.com/watch?v=Tb6DhFy9N_A" \
  --limit 3 \
  --format json \
  --out output/Tb6DhFy9N_A_sample_collection.json

.venv/bin/python -m yt_collector.cli scrapling-transcripts \
  --collection output/Tb6DhFy9N_A_sample_collection.json \
  --limit 3 \
  --language ko \
  --sleep-seconds 0 \
  --wait-ms 500 \
  --out output/Tb6DhFy9N_A_sample_dom_transcripts.json
```

전체 후보 실행은 `--limit 0`을 사용합니다.

```bash
.venv/bin/python -m yt_collector.cli collect \
  --url "https://www.youtube.com/watch?v=Tb6DhFy9N_A" \
  --limit 0 \
  --format json \
  --out output/Tb6DhFy9N_A_all_collection.json

.venv/bin/python -m yt_collector.cli scrapling-transcripts \
  --collection output/Tb6DhFy9N_A_all_collection.json \
  --limit 0 \
  --language ko \
  --sleep-seconds 0 \
  --wait-ms 500 \
  --stop-on-block \
  --out output/Tb6DhFy9N_A_all_dom_transcripts.json
```

채널 순위가 아니라 이미 선별한 영상 URL/ID 목록만 입력하려면 다음 명령을 사용합니다. 입력 순서를 유지하고 중복 video ID는 처음 한 번만 처리합니다.

```bash
.venv/bin/python -m yt_collector.cli scrapling-transcript-list \
  --targets-file input_video_targets.txt \
  --limit 0 \
  --language ko \
  --stop-on-block \
  --out output/video_list_scrapling_transcripts.json
```

`input_video_targets.txt`는 한 줄에 watch/Shorts/youtu.be URL 또는 11자리 video ID 하나를 넣습니다. GitHub Actions의 `Video list Scrapling transcripts` 워크플로도 같은 형식을 받으며, 실행 revision·run ID·입력 체크섬을 artifact manifest에 함께 기록합니다. 이 경로는 YouTube Data API channel 수집을 다시 실행하지 않습니다.

`targets`에 `food-story-expansion-v1`을 지정하면 저장된 6,768개 대본 대기열을 20개 균형 shard로 나눠 수집합니다. 1차 병렬 실행 뒤에는 `food-story-expansion-retry-v1`을 사용할 수 있습니다. 이 큐는 미확보 5,323편을 50편 이하 107개 shard로 나누고 최대 20개를 동시에 실행합니다. Google Sorry URL이나 HTTP 403·429는 즉시 `blocked_or_captcha`로 판정해 해당 shard를 끝내며, 명시 목록 결과는 영상마다 원자적으로 체크포인트됩니다. 한 라운드가 끝나면 병합 artifact의 `retry_targets.txt`로 성공분을 제외한 다음 라운드를 만든다는 전제입니다.

마지막 job은 원래 입력 순서로 결과를 합치고 `merge_summary.json`과 `retry_targets.txt`를 포함한 `video-list-scrapling-transcripts-sharded` artifact를 만듭니다. 같은 준비 큐의 중복 실행은 workflow concurrency group으로 직렬화됩니다.

렌더링 DOM에 세그먼트가 없지만 공개 caption API에는 자막이 있는지 한 영상만 확인할 때는 별도 원자료로 저장합니다. 기존 DOM 수집 artifact를 덮어쓰지 않습니다.

```bash
.venv/bin/python scripts/fetch_public_transcript.py VIDEO_ID \
  --language ko \
  --out output/VIDEO_ID_public_transcript.json
```


## 입력 URL 형식

지원 예시:

- `https://www.youtube.com/watch?v=onjVWrO2_5E`
- `https://youtube.com/watch?v=onjVWrO2_5E`
- `https://www.youtube.com/shorts/onjVWrO2_5E`
- `https://youtu.be/onjVWrO2_5E`

watch URL은 query parameter가 여러 개 있어도 `v`에서 videoId를 추출합니다. Shorts와 youtu.be URL은 path에서 videoId를 추출합니다.

## 출력 JSON 구조

단일 URL이면 JSON object, 여러 URL이면 object 배열을 씁니다.

```json
{
  "input": {"raw_url": "...", "video_id": "...", "collected_at": "...", "mode": "mock"},
  "source_video": {"raw": {}, "normalized": {}},
  "channel": {"raw": {}, "normalized": {}},
  "upload_playlist_items": [{"raw": {}, "normalized": {}}],
  "channel_videos": [{"raw": {}, "normalized": {}}],
  "derived_metrics": {},
  "warnings": [],
  "errors": []
}
```

`raw`는 YouTube API 공개 응답 구조를 최대한 보존하며 MVP에서 요구한 raw field path를 누락 시 `null`로 채웁니다. `normalized`는 분석하기 쉬운 snake_case 필드와 파생 지표를 담습니다.

## 댓글 제외 정책

댓글 본문, 댓글 작성자, 댓글 좋아요 수 등 댓글 상세 데이터는 MVP 수집 대상이 아닙니다. `commentThreads.list`도 호출하지 않습니다. 단, `videos.statistics.commentCount`는 공개 통계 필드이므로 저장합니다.

## 공개 API key로 얻는 값

- 영상: `snippet`, `contentDetails`, `status`, `statistics`, `player`, `topicDetails`, `recordingDetails`, `liveStreamingDetails`, `localizations`, `paidProductPlacementDetails`
- 채널: `snippet`, `contentDetails`, `statistics`, `status`, `topicDetails`, `brandingSettings`, `localizations`
- 업로드 목록: `playlistItems.list`의 `snippet`, `contentDetails`, `status`

`viewCount`, `likeCount`, `favoriteCount`, `commentCount`는 API에서 문자열로 오는 경우가 있어 안전하게 정수 변환합니다. 값이 없거나 숨김/비공개이면 `null`로 둡니다. `favoriteCount`는 YouTube API에서 일반적으로 `0`으로 옵니다. 싫어요 수는 수집하지 않습니다.

## 소유자 권한이 필요한 값

다음은 공개 API key만으로 수집하지 않습니다.

- `fileDetails`, `processingDetails`, `suggestions`
- YouTube Studio/Analytics 내부 지표: 노출수, CTR, 평균 시청 시간, 유지율, 트래픽 소스, 수익, 성별/연령 등

이 값들은 영상 소유자 OAuth/Analytics 권한이 필요합니다.

## Shorts 판별

YouTube Data API의 공개 응답만으로 Shorts 여부를 확정하지 않습니다. 이 MVP의 `is_probably_short`는 추정값입니다.

- 입력 URL path가 `/shorts/`이면 `true`
- 또는 영상 길이가 60초 이하이면 `true`

## 테스트

```bash
pytest
```

## 향후 확장 아이디어

- SQLite 저장
- 스냅샷 누적
- 시간별 조회수 증가량 추적
- 여러 채널 비교
- 쇼핑/제품 키워드 추출
- 제목/설명/태그 기반 훅 패턴 분석
- FastAPI 대시보드
- CSV/Parquet export
