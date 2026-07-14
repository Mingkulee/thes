"""Multi-agent orchestration using Google Gemini API (google-genai SDK).

The orchestrator classifies the user's message and routes it to the
appropriate specialist sub-agent (translator / coder / researcher),
or replies directly for general conversation.
"""

from __future__ import annotations

import json
import logging
import os
import re

from google import genai
from google.genai import types

from tools import describe_weather_code, fetch_gmail_messages, fetch_weather, geocode_location

logger = logging.getLogger(__name__)

MODEL = "gemini-2.0-flash"

_client: genai.Client | None = None


def _client_() -> genai.Client:
    global _client
    if _client is None:
        _client = genai.Client(api_key=os.environ["GOOGLE_API_KEY"])
    return _client


# ---------------------------------------------------------------------------
# Sub-agent definitions
# ---------------------------------------------------------------------------

SUBAGENTS: dict[str, str] = {
    "translator": (
        "You are a professional translator. Translate the user's text "
        "accurately while preserving tone and nuance. "
        "If no target language is specified, translate Korean<->English. "
        "Respond with only the translation, no commentary."
    ),
    "coder": (
        "You are an expert software engineer. Answer programming questions "
        "with correct, concise code examples and brief explanations. "
        "Always reply in the same language the user used."
    ),
    "researcher": (
        "You are a careful research analyst. Answer factual questions "
        "accurately and concisely. If you are uncertain, say so explicitly. "
        "Always reply in the same language the user used."
    ),
}

ORCHESTRATOR_SYSTEM = """\
You are the orchestrator of a multi-agent assistant.
Analyze the user's message and respond ONLY with valid JSON — no markdown, no explanation:

{"agent": "<agent>", "payload": "<text>"}

Rules:
- "agent" must be one of: "translator", "coder", "researcher", "weather", "gmail", "general"
- "translator"  → user wants text translated between languages
- "coder"       → programming, code, debugging, software questions
- "researcher"  → factual questions, concept explanations, summaries
- "weather"     → user is asking about current or forecast weather for a location
- "gmail"       → user wants to check, read, or summarize emails
- "general"     → greetings, small talk, anything that doesn't fit above
- "payload"     → for "general":  your direct friendly reply to the user
                  for "weather":  the user's original weather question (keep it intact)
                  for others:     the exact text/question to pass to the specialist
- Always use the same language the user used in the payload.\
"""

_LOCATION_EXTRACTION_SYSTEM = (
    "Extract ONLY the location name (city, region, or country) from the user's "
    "weather query. Respond with just the location name, no explanation, no "
    "punctuation. If no location is explicitly mentioned, respond with the "
    "single word: NONE"
)

_WEATHER_REPORT_SYSTEM = (
    "You are a friendly Korean weather reporter. Given raw Open-Meteo weather "
    "data, write a concise, easy-to-read forecast in Korean using appropriate "
    "emojis. Keep it under 10 short lines. Always reply in Korean unless the "
    "user wrote in another language."
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _extract_json(text: str) -> str:
    """Strip markdown code fences if Gemini wraps JSON in them."""
    match = re.search(r"```(?:json)?\s*([\s\S]+?)\s*```", text)
    if match:
        return match.group(1)
    return text.strip()


async def _gemini(system: str, user_text: str) -> str:
    response = await _client_().aio.models.generate_content(
        model=MODEL,
        contents=user_text,
        config=types.GenerateContentConfig(
            system_instruction=system,
        ),
    )
    return response.text.strip()


# ---------------------------------------------------------------------------
# Weather agent (uses Open-Meteo as a tool)
# ---------------------------------------------------------------------------


async def run_weather(user_message: str) -> str:
    """Answer a weather question by calling Open-Meteo and summarizing."""
    # 1. Extract location from the user's message
    location = await _gemini(_LOCATION_EXTRACTION_SYSTEM, user_message)
    location = location.strip().strip(".").strip()
    logger.info("weather: extracted location %r", location)

    if not location or location.upper() == "NONE":
        return "어느 지역의 날씨를 알려드릴까요? 도시 이름을 함께 보내주세요."

    # 2. Geocode
    try:
        geo = await geocode_location(location)
    except Exception:
        logger.exception("weather: geocoding failed")
        return "위치 검색 중 오류가 발생했습니다. 잠시 후 다시 시도해주세요."

    if geo is None:
        return f"'{location}' 위치를 찾을 수 없습니다. 다른 지역명을 시도해주세요."

    lat, lon, display_name, country = geo

    # 3. Fetch weather
    try:
        data = await fetch_weather(lat, lon)
    except Exception:
        logger.exception("weather: forecast fetch failed")
        return "날씨 정보 조회 중 오류가 발생했습니다. 잠시 후 다시 시도해주세요."

    # 4. Pre-decode weather codes to Korean and hand to Gemini for formatting
    current = data.get("current", {}) or {}
    daily = data.get("daily", {}) or {}
    current_code = current.get("weather_code")
    daily_codes = daily.get("weather_code", []) or []

    enriched = {
        "location": {
            "name": display_name,
            "country": country,
            "latitude": lat,
            "longitude": lon,
        },
        "current": {
            **current,
            "weather_description_ko": (
                describe_weather_code(int(current_code))
                if current_code is not None
                else None
            ),
        },
        "daily": {
            **daily,
            "weather_description_ko": [
                describe_weather_code(int(c)) for c in daily_codes
            ],
        },
    }

    summary_input = (
        f"사용자 질문: {user_message}\n\n"
        f"Open-Meteo 날씨 데이터 (JSON):\n"
        f"{json.dumps(enriched, ensure_ascii=False, indent=2)}"
    )
    return await _gemini(_WEATHER_REPORT_SYSTEM, summary_input)


# ---------------------------------------------------------------------------
# Orchestrator entry point
# ---------------------------------------------------------------------------


async def run_orchestrator(user_message: str) -> str:
    """Route the user message through the orchestrator and return a reply."""
    raw = await _gemini(ORCHESTRATOR_SYSTEM, user_message)
    logger.info("orchestrator raw: %s", raw)

    try:
        data = json.loads(_extract_json(raw))
        agent: str = data.get("agent", "general")
        payload: str = data.get("payload", user_message)
    except (json.JSONDecodeError, AttributeError):
        logger.warning("orchestrator JSON parse failed, returning raw response")
        return raw

    if agent == "general":
        return payload

    if agent == "weather":
        logger.info("delegating to weather_agent")
        return await run_weather(payload)

    if agent == "gmail":
        logger.info("delegating to gmail_agent")
        try:
            msgs = await fetch_gmail_messages(max_results=5, query="is:unread")
            return await run_gmail_analyst(msgs, payload)
        except FileNotFoundError:
            return (
                "⚠️ Gmail 인증이 필요합니다.\n"
                "터미널에서 아래 명령을 먼저 실행하세요:\n"
                "`python gmail_auth.py`"
            )

    system_prompt = SUBAGENTS.get(agent)
    if not system_prompt:
        logger.warning("unknown agent '%s', returning payload", agent)
        return payload

    logger.info("delegating to %s_agent", agent)
    return await _gemini(system_prompt, payload)


_DOCUMENT_ANALYSIS_SYSTEM = """\
당신은 한국 사업계획서 전문 분석가입니다.
아래 문서 내용을 분석하여 다음을 마크다운 형식으로 체계적으로 정리하세요:

1. **문서 개요** — 제목 추정, 전체 구조 요약
2. **핵심 사업 내용** — 목적, 비전, 전략, 타겟 시장
3. **표 데이터 요약** — 각 표의 의미 해석
4. **주요 수치·일정** — 예산, 매출 목표, KPI, 일정
5. **특이사항** — 이미지/도표 개수, 주목할 내용

사용자 질문이 있으면 마지막에 **[질문 답변]** 섹션으로 별도 답변하세요.
항상 한국어로 답변하세요.
"""


async def run_document_analyst(extracted: dict, user_question: str = "") -> str:
    """Analyse extracted HWP/HWPX content with Gemini."""
    parts: list[str] = [f"[문서 형식: {extracted.get('format', '알 수 없음')}]"]

    text = (extracted.get("text") or "").strip()
    if text:
        if len(text) > 15_000:
            text = text[:15_000] + "\n...(이하 생략)"
        parts.append(f"## 본문\n{text}")
    else:
        parts.append("## 본문\n(추출된 텍스트 없음)")

    for i, tbl in enumerate(extracted.get("tables") or [], 1):
        lines = [f"## 표 {i}"]
        for row in tbl:
            lines.append(" | ".join(str(c) for c in row))
        parts.append("\n".join(lines))

    image_count = extracted.get("image_count", 0)
    if image_count:
        parts.append(f"## 이미지/그림: {image_count}개 포함 (텍스트 분석만 가능)")

    if user_question.strip():
        parts.append(f"## 사용자 질문\n{user_question.strip()}")

    return await _gemini(_DOCUMENT_ANALYSIS_SYSTEM, "\n\n".join(parts))


_GMAIL_ANALYSIS_SYSTEM = """\
당신은 이메일 비서입니다. 제공된 Gmail 메일 목록을 한국어로 분석하여 아래 형식으로 정리하세요.

각 메일마다:
• **[번호] 제목** (발신자 | 날짜)
  - 핵심 내용 1-3줄 요약
  - 필요한 액션: (답장 필요 / 처리 필요 / 참고만 / 없음)
  - 중요도: 🔴 높음 / 🟡 보통 / 🟢 낮음

마지막에 전체 요약 한 줄을 추가하세요.
"""


async def run_gmail_analyst(messages: list[dict], user_question: str = "") -> str:
    """Analyse Gmail messages with Gemini."""
    if not messages:
        return "📭 조건에 맞는 메일이 없습니다."

    parts: list[str] = [f"[총 {len(messages)}개 메일]"]
    for i, m in enumerate(messages, 1):
        parts.append(
            f"## 메일 {i}\n"
            f"발신자: {m['from']}\n"
            f"제목: {m['subject']}\n"
            f"날짜: {m['date']}\n"
            f"본문:\n{m['body'] or m['snippet']}"
        )

    if user_question.strip():
        parts.append(f"## 사용자 질문\n{user_question.strip()}")

    return await _gemini(_GMAIL_ANALYSIS_SYSTEM, "\n\n".join(parts))


async def run_specialist(agent_name: str, user_message: str) -> str:
    """Run a single specialist sub-agent directly, bypassing the orchestrator."""
    if agent_name == "weather":
        logger.info("specialist weather_agent invoked directly")
        return await run_weather(user_message)

    system_prompt = SUBAGENTS.get(agent_name)
    if not system_prompt:
        return f"[error: unknown agent '{agent_name}']"
    logger.info("specialist %s_agent invoked directly", agent_name)
    return await _gemini(system_prompt, user_message)
