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

from tools import describe_weather_code, fetch_weather, geocode_location

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
- "agent" must be one of: "translator", "coder", "researcher", "weather", "general"
- "translator"  → user wants text translated between languages
- "coder"       → programming, code, debugging, software questions
- "researcher"  → factual questions, concept explanations, summaries
- "weather"     → user is asking about current or forecast weather for a location
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

    system_prompt = SUBAGENTS.get(agent)
    if not system_prompt:
        logger.warning("unknown agent '%s', returning payload", agent)
        return payload

    logger.info("delegating to %s_agent", agent)
    return await _gemini(system_prompt, payload)


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
