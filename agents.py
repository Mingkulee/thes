"""Multi-agent orchestration layer backed by the Claude API.

An orchestrator agent receives the user's message and either answers directly
or delegates to one of several specialist sub-agents via tool use. Each
sub-agent is a separate Claude call with its own system prompt.
"""

from __future__ import annotations

import logging
from typing import Any

from anthropic import AsyncAnthropic

logger = logging.getLogger(__name__)

MODEL = "claude-sonnet-4-6"
MAX_TOKENS = 2048

_client: AsyncAnthropic | None = None


def _client_() -> AsyncAnthropic:
    global _client
    if _client is None:
        _client = AsyncAnthropic()
    return _client


# ---------------------------------------------------------------------------
# Sub-agent definitions
# ---------------------------------------------------------------------------

SUBAGENTS: dict[str, dict[str, str]] = {
    "translator_agent": {
        "system": (
            "You are a professional translator. Translate the user's text "
            "accurately while preserving tone and nuance. If no target language "
            "is given, translate Korean<->English. Respond with only the "
            "translation, no commentary."
        ),
        "input_key": "text",
    },
    "coder_agent": {
        "system": (
            "You are an expert software engineer. Answer programming questions "
            "with correct, concise code examples and short explanations. "
            "Match the language the user is writing in."
        ),
        "input_key": "question",
    },
    "researcher_agent": {
        "system": (
            "You are a careful research analyst. Answer factual questions "
            "accurately and concisely. If you are not certain, say so "
            "explicitly. Match the language the user is writing in."
        ),
        "input_key": "question",
    },
}

ORCHESTRATOR_TOOLS: list[dict[str, Any]] = [
    {
        "name": "translator_agent",
        "description": (
            "Delegate to the translation specialist. Use when the user asks "
            "to translate text between languages."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "text": {
                    "type": "string",
                    "description": (
                        "The text to translate, including any target language hint "
                        "(e.g. 'to English: 안녕하세요')."
                    ),
                },
            },
            "required": ["text"],
        },
    },
    {
        "name": "coder_agent",
        "description": (
            "Delegate to the programming specialist. Use for code, debugging, "
            "software design, or language-specific technical questions."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "question": {"type": "string"},
            },
            "required": ["question"],
        },
    },
    {
        "name": "researcher_agent",
        "description": (
            "Delegate to the research specialist. Use for factual questions, "
            "explanations of concepts, or summaries of topics."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "question": {"type": "string"},
            },
            "required": ["question"],
        },
    },
]

ORCHESTRATOR_SYSTEM = (
    "You are the orchestrator of a multi-agent assistant. For each user "
    "message, decide whether to delegate to a specialist tool or to answer "
    "directly. Delegate whenever a specialist clearly fits; answer directly "
    "for greetings, chit-chat, or requests that don't fit any specialist. "
    "Always reply in the same language the user used."
)


# ---------------------------------------------------------------------------
# Sub-agent execution
# ---------------------------------------------------------------------------


async def _run_subagent(name: str, tool_input: dict[str, Any]) -> str:
    spec = SUBAGENTS.get(name)
    if spec is None:
        return f"[orchestrator error: unknown agent '{name}']"

    user_text = tool_input.get(spec["input_key"], "")
    if not user_text:
        user_text = next(iter(tool_input.values()), "")

    logger.info("sub-agent %s invoked", name)
    resp = await _client_().messages.create(
        model=MODEL,
        max_tokens=MAX_TOKENS,
        system=spec["system"],
        messages=[{"role": "user", "content": user_text}],
    )
    return "".join(block.text for block in resp.content if block.type == "text")


# ---------------------------------------------------------------------------
# Orchestrator entrypoint
# ---------------------------------------------------------------------------


async def run_orchestrator(user_message: str) -> str:
    """Send a user message through the orchestrator and return the final reply."""
    messages: list[dict[str, Any]] = [
        {"role": "user", "content": user_message},
    ]

    first = await _client_().messages.create(
        model=MODEL,
        max_tokens=MAX_TOKENS,
        system=ORCHESTRATOR_SYSTEM,
        tools=ORCHESTRATOR_TOOLS,
        messages=messages,
    )

    if first.stop_reason != "tool_use":
        return "".join(b.text for b in first.content if b.type == "text").strip()

    messages.append({"role": "assistant", "content": first.content})

    tool_results: list[dict[str, Any]] = []
    for block in first.content:
        if block.type != "tool_use":
            continue
        result = await _run_subagent(block.name, block.input or {})
        tool_results.append(
            {
                "type": "tool_result",
                "tool_use_id": block.id,
                "content": result,
            }
        )

    messages.append({"role": "user", "content": tool_results})

    final = await _client_().messages.create(
        model=MODEL,
        max_tokens=MAX_TOKENS,
        system=ORCHESTRATOR_SYSTEM,
        tools=ORCHESTRATOR_TOOLS,
        messages=messages,
    )
    return "".join(b.text for b in final.content if b.type == "text").strip()
