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
- "agent" must be one of: "translator", "coder", "researcher", "general"
- "translator"  → user wants text translated between languages
- "coder"       → programming, code, debugging, software questions
- "researcher"  → factual questions, concept explanations, summaries
- "general"     → greetings, small talk, anything that doesn't fit above
- "payload"     → for "general": your direct friendly reply to the user
                  for others: the exact text/question to pass to the specialist
- Always use the same language the user used in the payload.\
"""


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

    system_prompt = SUBAGENTS.get(agent)
    if not system_prompt:
        logger.warning("unknown agent '%s', returning payload", agent)
        return payload

    logger.info("delegating to %s_agent", agent)
    return await _gemini(system_prompt, payload)
