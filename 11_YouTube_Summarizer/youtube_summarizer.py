"""유튜브 링크를 넣으면 자막/음성을 추출해 한국어로 요약해 주는 CLI 도구.

사용 예시:
    python youtube_summarizer.py "https://www.youtube.com/watch?v=VIDEO_ID"
    python youtube_summarizer.py "https://youtu.be/VIDEO_ID" -o summary.md
    python youtube_summarizer.py URL --whisper-model small   # 음성인식 정확도 ↑
    python youtube_summarizer.py URL --no-whisper            # 자막 없으면 그냥 종료
    python youtube_summarizer.py URL --transcript-only       # 요약 없이 원문만 출력

요약에는 Claude API가 필요합니다. 환경변수로 API 키를 설정하세요:
    export ANTHROPIC_API_KEY="sk-ant-..."
"""

import os
import sys
import argparse

import transcript as transcript_mod


def main():
    parser = argparse.ArgumentParser(
        description="유튜브 링크 → 자막/음성 추출 → 한국어 요약",
    )
    parser.add_argument("url", help="유튜브 영상 URL 또는 영상 ID")
    parser.add_argument("-o", "--output", help="요약 결과를 저장할 파일 경로 (예: summary.md)")
    parser.add_argument(
        "--whisper-model",
        default="base",
        help="음성인식에 쓸 faster-whisper 모델 (tiny/base/small/medium/large-v3). 기본: base",
    )
    parser.add_argument(
        "--no-whisper",
        action="store_true",
        help="자막이 없을 때 음성인식(Whisper)을 시도하지 않음",
    )
    parser.add_argument(
        "--transcript-only",
        action="store_true",
        help="요약하지 않고 추출한 원문 텍스트만 출력 (Claude API 불필요)",
    )
    args = parser.parse_args()

    # 1) 텍스트 추출
    try:
        title = transcript_mod.get_video_title(args.url)
        if title:
            print(f"영상 제목: {title}\n")
        text, source = transcript_mod.get_transcript(
            args.url,
            whisper_model=args.whisper_model,
            allow_whisper=not args.no_whisper,
        )
    except (ValueError, RuntimeError) as e:
        print(f"\n[오류] {e}", file=sys.stderr)
        sys.exit(1)

    print(f"\n✓ 텍스트 추출 완료 (방법: {source}, 길이: {len(text):,}자)\n")

    # 원문만 원하면 여기서 끝낸다.
    if args.transcript_only:
        _output(text, args.output)
        return

    # 2) 요약 (Claude API)
    if not os.environ.get("ANTHROPIC_API_KEY"):
        print(
            "[오류] ANTHROPIC_API_KEY 환경변수가 없습니다.\n"
            '  export ANTHROPIC_API_KEY="sk-ant-..." 로 설정하거나\n'
            "  --transcript-only 옵션으로 원문만 출력할 수 있습니다.",
            file=sys.stderr,
        )
        sys.exit(1)

    print("Claude로 요약 중...\n")
    try:
        import summarizer as summarizer_mod  # 요약할 때만 anthropic 의존성을 로드
        summary = summarizer_mod.summarize(text, title=title)
    except Exception as e:
        print(f"[오류] 요약 중 문제가 발생했습니다: {e}", file=sys.stderr)
        sys.exit(1)

    _output(summary, args.output)


def _output(content: str, output_path: str | None):
    """결과를 화면에 출력하고, 경로가 주어지면 파일로도 저장한다."""
    print("=" * 60)
    print(content)
    print("=" * 60)
    if output_path:
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(content)
        print(f"\n✓ 결과를 '{output_path}'에 저장했습니다.")


if __name__ == "__main__":
    main()
