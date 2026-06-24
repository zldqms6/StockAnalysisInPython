"""유튜브 영상에서 텍스트(자막/음성)를 추출하는 모듈.

여러 가지 방법을 순서대로 시도하는 폴백(fallback) 체인 구조다.
  1) youtube-transcript-api : 유튜브가 제공하는 (자동)자막을 바로 가져옴 - 가장 빠름
  2) yt-dlp 자막 다운로드   : 1번이 실패할 때 자막 파일(vtt)을 직접 받아 파싱
  3) yt-dlp 오디오 + Whisper: 자막이 아예 없으면 오디오를 받아 음성인식으로 변환

각 단계는 실패하면 다음 단계로 넘어가고, 어디서 성공했는지 source 문자열로 알려준다.
"""

import os
import re
import glob
import tempfile

# 한국어 우선, 그다음 영어 자막을 찾는다.
PREFERRED_LANGS = ["ko", "en"]


def extract_video_id(url: str) -> str:
    """다양한 형태의 유튜브 URL에서 11자리 영상 ID를 추출한다."""
    patterns = [
        r"(?:v=|/v/|youtu\.be/|/embed/|/shorts/)([0-9A-Za-z_-]{11})",
        r"^([0-9A-Za-z_-]{11})$",  # 이미 ID만 넘어온 경우
    ]
    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1)
    raise ValueError(f"유튜브 영상 ID를 찾을 수 없습니다: {url}")


def _clean_subtitle_text(raw: str) -> str:
    """vtt/srt 자막에서 타임스탬프·태그·중복 줄을 걷어내고 본문만 남긴다."""
    lines = []
    last_line = None
    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue
        if line.startswith("WEBVTT") or line.startswith("Kind:") or line.startswith("Language:"):
            continue
        if "-->" in line:  # 타임스탬프 줄
            continue
        if line.isdigit():  # srt 순번
            continue
        # <00:00:00.000><c> 같은 인라인 타이밍 태그 제거
        line = re.sub(r"<[^>]+>", "", line).strip()
        if not line or line == last_line:  # 자동자막 특유의 중복 줄 제거
            continue
        lines.append(line)
        last_line = line
    return " ".join(lines)


# ---------------------------------------------------------------------------
# 1) youtube-transcript-api
# ---------------------------------------------------------------------------
def _from_transcript_api(video_id: str):
    """youtube-transcript-api로 자막을 가져온다. 버전별 API 차이를 흡수한다."""
    try:
        from youtube_transcript_api import YouTubeTranscriptApi
    except ImportError:
        return None

    def _join(entries) -> str:
        texts = []
        for e in entries:
            # 1.x는 객체(.text), 0.x는 dict({"text": ...})를 반환
            texts.append(getattr(e, "text", None) if not isinstance(e, dict) else e.get("text"))
        return " ".join(t for t in texts if t).strip()

    # 신버전(1.x): 인스턴스 메서드 fetch/list
    try:
        api = YouTubeTranscriptApi()
        try:
            fetched = api.fetch(video_id, languages=PREFERRED_LANGS)
            text = _join(fetched)
            if text:
                return text
        except Exception:
            pass
    except Exception:
        pass

    # 구버전(0.x): 클래스 메서드 get_transcript
    try:
        entries = YouTubeTranscriptApi.get_transcript(video_id, languages=PREFERRED_LANGS)
        text = _join(entries)
        if text:
            return text
    except Exception:
        pass

    return None


# ---------------------------------------------------------------------------
# 2) yt-dlp 자막 파일 다운로드
# ---------------------------------------------------------------------------
def _from_ytdlp_subtitles(url: str):
    """yt-dlp로 (자동)자막 파일을 받아 텍스트로 변환한다."""
    try:
        import yt_dlp
    except ImportError:
        return None

    with tempfile.TemporaryDirectory() as tmp:
        outtmpl = os.path.join(tmp, "%(id)s.%(ext)s")
        opts = {
            "skip_download": True,
            "writesubtitles": True,
            "writeautomaticsub": True,
            "subtitleslangs": PREFERRED_LANGS + ["ko-orig", "en-orig"],
            "subtitlesformat": "vtt",
            "outtmpl": outtmpl,
            "quiet": True,
            "no_warnings": True,
        }
        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                ydl.download([url])
        except Exception:
            return None

        # 선호 언어 순으로 받아진 자막 파일을 찾는다.
        sub_files = glob.glob(os.path.join(tmp, "*.vtt"))
        if not sub_files:
            return None

        def _lang_rank(path: str) -> int:
            for i, lang in enumerate(PREFERRED_LANGS):
                if f".{lang}" in os.path.basename(path):
                    return i
            return len(PREFERRED_LANGS)

        sub_files.sort(key=_lang_rank)
        with open(sub_files[0], encoding="utf-8") as f:
            text = _clean_subtitle_text(f.read())
        return text or None


# ---------------------------------------------------------------------------
# 3) yt-dlp 오디오 다운로드 + faster-whisper 음성인식
# ---------------------------------------------------------------------------
def _from_audio_whisper(url: str, whisper_model: str = "base"):
    """오디오를 받아 faster-whisper로 음성→텍스트 변환한다 (자막이 전혀 없을 때)."""
    try:
        import yt_dlp
        from faster_whisper import WhisperModel
    except ImportError:
        return None

    with tempfile.TemporaryDirectory() as tmp:
        outtmpl = os.path.join(tmp, "audio.%(ext)s")
        opts = {
            "format": "bestaudio/best",
            "outtmpl": outtmpl,
            "quiet": True,
            "no_warnings": True,
            # ffmpeg가 있으면 mp3로 변환, 없으면 원본 오디오를 그대로 사용
            "postprocessors": [
                {"key": "FFmpegExtractAudio", "preferredcodec": "mp3", "preferredquality": "128"}
            ],
        }
        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                ydl.download([url])
        except Exception:
            # ffmpeg가 없을 수 있으니 후처리 없이 한 번 더 시도
            opts.pop("postprocessors", None)
            try:
                with yt_dlp.YoutubeDL(opts) as ydl:
                    ydl.download([url])
            except Exception:
                return None

        audio_files = glob.glob(os.path.join(tmp, "audio.*"))
        if not audio_files:
            return None

        print(f"  [Whisper] '{whisper_model}' 모델로 음성을 인식하는 중... (시간이 걸릴 수 있습니다)")
        model = WhisperModel(whisper_model, device="cpu", compute_type="int8")
        segments, _info = model.transcribe(audio_files[0], language=None)
        text = " ".join(seg.text.strip() for seg in segments).strip()
        return text or None


def get_video_title(url: str) -> str:
    """yt-dlp 메타데이터에서 영상 제목을 가져온다 (요약 품질 향상용 컨텍스트)."""
    try:
        import yt_dlp
    except ImportError:
        return ""
    try:
        with yt_dlp.YoutubeDL({"quiet": True, "no_warnings": True, "skip_download": True}) as ydl:
            info = ydl.extract_info(url, download=False)
            return info.get("title", "") or ""
    except Exception:
        return ""


def get_transcript(url: str, whisper_model: str = "base", allow_whisper: bool = True):
    """폴백 체인을 순서대로 실행해 (텍스트, 추출방법) 튜플을 반환한다.

    실패 시 RuntimeError를 던진다.
    """
    video_id = extract_video_id(url)

    print("[1/3] youtube-transcript-api로 자막 확인 중...")
    text = _from_transcript_api(video_id)
    if text:
        return text, "youtube-transcript-api (자막)"

    print("[2/3] yt-dlp로 자막 파일 다운로드 시도 중...")
    text = _from_ytdlp_subtitles(url)
    if text:
        return text, "yt-dlp (자막 파일)"

    if allow_whisper:
        print("[3/3] 자막이 없어 오디오를 내려받아 음성인식(Whisper)을 시도합니다...")
        text = _from_audio_whisper(url, whisper_model=whisper_model)
        if text:
            return text, f"faster-whisper ({whisper_model} 음성인식)"

    raise RuntimeError(
        "자막/음성 어느 방법으로도 텍스트를 추출하지 못했습니다.\n"
        "  - 영상에 자막이 없고 Whisper 의존성(faster-whisper, ffmpeg)이 없을 수 있습니다.\n"
        "  - requirements.txt를 설치했는지, 영상이 비공개/지역제한은 아닌지 확인해 주세요."
    )
