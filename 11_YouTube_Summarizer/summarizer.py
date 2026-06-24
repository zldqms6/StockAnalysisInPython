"""추출한 자막/음성 텍스트를 Claude API로 한국어 요약하는 모듈."""

import anthropic

MODEL = "claude-opus-4-8"

SYSTEM_PROMPT = """당신은 유튜브 영상 자막을 한국어로 요약하는 전문가입니다.
자막에는 음성인식 오류나 구어체 반복이 섞여 있을 수 있으니 문맥으로 보정해서 이해하세요.
사실에 기반해 요약하고, 자막에 없는 내용을 지어내지 마세요."""

# 요약 결과의 형식을 지정한다.
USER_TEMPLATE = """다음은 유튜브 영상의 자막(또는 음성 변환 텍스트)입니다.

[영상 제목] {title}

[자막 내용]
{transcript}

위 내용을 아래 형식으로 한국어로 정리해 주세요.

## 한 줄 요약
(영상 핵심을 한 문장으로)

## 핵심 내용
- (중요한 포인트를 5~8개의 불릿으로)

## 상세 요약
(2~4개 문단으로 흐름에 맞게 정리)

## 키워드
(쉼표로 구분한 핵심 키워드 5~10개)"""


def summarize(transcript: str, title: str = "", api_key: str | None = None) -> str:
    """자막 텍스트를 받아 요약 결과 문자열을 반환한다.

    api_key를 주지 않으면 환경변수 ANTHROPIC_API_KEY를 사용한다.
    스트리밍으로 호출해 긴 출력에서도 타임아웃 없이 안전하게 받는다.
    """
    client = anthropic.Anthropic(api_key=api_key) if api_key else anthropic.Anthropic()

    user_message = USER_TEMPLATE.format(title=title or "(제목 정보 없음)", transcript=transcript)

    with client.messages.stream(
        model=MODEL,
        max_tokens=8000,
        system=SYSTEM_PROMPT,
        thinking={"type": "adaptive"},
        messages=[{"role": "user", "content": user_message}],
    ) as stream:
        message = stream.get_final_message()

    # 응답에서 텍스트 블록만 모은다 (thinking 블록은 제외).
    return "".join(block.text for block in message.content if block.type == "text").strip()
