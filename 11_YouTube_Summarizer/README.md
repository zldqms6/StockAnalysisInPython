# 유튜브 자막 요약기 (YouTube Summarizer)

유튜브 링크를 넣으면 **자막(또는 음성)을 추출**해서 **Claude API로 한국어 요약**을 만들어 주는 CLI 도구입니다.

## 동작 방식 (폴백 체인)

자막을 가져오기 위해 아래 방법을 **순서대로** 시도하고, 먼저 성공하는 것을 사용합니다.

1. **`youtube-transcript-api`** — 유튜브가 제공하는 (자동)자막을 바로 가져옴 · 가장 빠름
2. **`yt-dlp` 자막 다운로드** — 1번이 막히면 자막 파일(vtt)을 직접 받아 파싱
3. **`yt-dlp` 오디오 + `faster-whisper`** — 자막이 아예 없으면 오디오를 받아 음성인식으로 변환

추출한 텍스트는 `claude-opus-4-8` 모델로 한 줄 요약 · 핵심 내용 · 상세 요약 · 키워드 형태로 정리됩니다.

## 설치

```bash
pip install -r requirements.txt

# 음성인식(Whisper) 폴백을 쓰려면 ffmpeg도 필요합니다.
#   macOS:  brew install ffmpeg
#   Ubuntu: sudo apt install ffmpeg
```

## API 키 설정

요약에는 Anthropic(Claude) API 키가 필요합니다.

```bash
export ANTHROPIC_API_KEY="sk-ant-..."
```

> 키 없이 추출된 원문만 보고 싶다면 `--transcript-only` 옵션을 쓰면 됩니다.

## 사용법

```bash
# 기본: 자막 추출 후 요약
python youtube_summarizer.py "https://www.youtube.com/watch?v=VIDEO_ID"

# 요약 결과를 파일로 저장
python youtube_summarizer.py "https://youtu.be/VIDEO_ID" -o summary.md

# 음성인식 정확도를 높이고 싶을 때 (모델이 클수록 정확하지만 느림)
python youtube_summarizer.py URL --whisper-model small

# 자막이 없으면 음성인식 없이 그냥 종료
python youtube_summarizer.py URL --no-whisper

# 요약 없이 추출된 원문만 출력 (Claude API 불필요)
python youtube_summarizer.py URL --transcript-only

# 회원전용·비공개·연령제한 영상 (로그인 쿠키 필요)
python youtube_summarizer.py URL --cookies-from-browser chrome
python youtube_summarizer.py URL --cookies cookies.txt
```

## 회원전용 / 비공개 / 연령제한 영상

이런 영상은 로그인이 없으면 자막·오디오 접근이 막혀서 추출이 실패합니다.
**본인이 로그인한 계정의 쿠키**를 넘겨주면, 그 계정으로 볼 수 있는 영상은 처리할 수 있습니다.

- `--cookies-from-browser chrome` : 설치된 브라우저(chrome/firefox/edge/safari 등)에서 쿠키를 자동으로 꺼내 씁니다. 가장 편합니다.
- `--cookies cookies.txt` : Netscape 형식 쿠키 파일을 직접 지정합니다. (브라우저 확장 프로그램 "Get cookies.txt" 등으로 내보낼 수 있음)

> ⚠️ 쿠키는 곧 로그인 자격 증명입니다. 파일을 공유하거나 깃에 커밋하지 마세요. 본인이 볼 권한이 있는 영상에만 사용하세요.

## 옵션

| 옵션 | 설명 |
|------|------|
| `url` | 유튜브 영상 URL 또는 11자리 영상 ID (필수) |
| `-o`, `--output` | 결과를 저장할 파일 경로 |
| `--whisper-model` | `tiny`/`base`/`small`/`medium`/`large-v3` 중 선택 (기본 `base`) |
| `--no-whisper` | 자막 없을 때 음성인식 생략 |
| `--transcript-only` | 요약 없이 원문 텍스트만 출력 |
| `--cookies-from-browser` | 브라우저에서 쿠키 자동 추출 (회원전용·비공개 영상용) |
| `--cookies` | Netscape 형식 쿠키 파일 경로 (회원전용·비공개 영상용) |

## 파일 구성

| 파일 | 역할 |
|------|------|
| `youtube_summarizer.py` | CLI 진입점 · 전체 흐름 조율 |
| `transcript.py` | 자막/음성 추출 폴백 체인 |
| `summarizer.py` | Claude API 요약 |
| `requirements.txt` | 의존성 목록 |

## 참고

- 일부 영상은 비공개·지역제한·자막 비활성화로 추출이 안 될 수 있습니다.
- `faster-whisper`의 `base` 모델은 CPU에서도 동작하지만 영상이 길면 시간이 걸립니다. 정확도가 더 필요하면 `--whisper-model small` 이상을 권장합니다.
