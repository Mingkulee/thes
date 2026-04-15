"""Telegram bot entry point for THE-S Co., Ltd.

Runs one or more bots concurrently. The main orchestrator bot routes user
messages through the orchestrator (agents.run_orchestrator). Optional
specialist bots skip orchestration and go directly to a single sub-agent
(agents.run_specialist).

Configure which bots to run via .env:

    TELEGRAM_BOT_TOKEN                  — orchestrator bot (required)
    TELEGRAM_BOT_TOKEN_TRANSLATOR       — translator specialist (optional)
    TELEGRAM_BOT_TOKEN_CODER            — coder specialist      (optional)
    TELEGRAM_BOT_TOKEN_RESEARCHER       — researcher specialist (optional)
"""

from __future__ import annotations

import asyncio
import logging
import os

from dotenv import load_dotenv
from telegram import Update
from telegram.constants import ChatAction
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from agents import run_orchestrator, run_specialist

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

TELEGRAM_MAX_MESSAGE = 4096


# Bot role definitions: env var name, agent name (None = orchestrator), start/help copy.
BOT_ROLES: list[dict[str, str | None]] = [
    {
        "env": "TELEGRAM_BOT_TOKEN",
        "agent": None,
        "label": "orchestrator",
        "start": (
            "안녕하세요 {user}님! THE-S 멀티에이전트 봇입니다.\n"
            "메시지를 보내시면 번역 / 코딩 / 리서치 전문가에게 자동으로 위임합니다."
        ),
        "help": (
            "Orchestrator bot\n"
            "일반 메시지는 자동으로 적절한 전문가에게 위임됩니다.\n"
            "• translator — 번역\n"
            "• coder — 코드/프로그래밍\n"
            "• researcher — 사실/개념"
        ),
    },
    {
        "env": "TELEGRAM_BOT_TOKEN_TRANSLATOR",
        "agent": "translator",
        "label": "translator",
        "start": (
            "안녕하세요 {user}님! 번역 전문 봇입니다.\n"
            "번역하고 싶은 텍스트를 보내주세요. 지정하지 않으면 한↔영 번역합니다."
        ),
        "help": "번역 전용 봇. 아무 텍스트나 보내면 바로 번역합니다.",
    },
    {
        "env": "TELEGRAM_BOT_TOKEN_CODER",
        "agent": "coder",
        "label": "coder",
        "start": (
            "안녕하세요 {user}님! 코딩 전문 봇입니다.\n"
            "프로그래밍 질문이나 디버깅할 코드를 보내주세요."
        ),
        "help": "코딩 전용 봇. 프로그래밍 질문을 받으면 코드 예시와 함께 답변합니다.",
    },
    {
        "env": "TELEGRAM_BOT_TOKEN_RESEARCHER",
        "agent": "researcher",
        "label": "researcher",
        "start": (
            "안녕하세요 {user}님! 리서치 전문 봇입니다.\n"
            "궁금한 개념이나 사실을 물어보세요."
        ),
        "help": "리서치 전용 봇. 사실 기반 질문에 정확히 답변합니다.",
    },
    {
        "env": "TELEGRAM_BOT_TOKEN_WEATHER",
        "agent": "weather",
        "label": "weather",
        "start": (
            "안녕하세요 {user}님! 날씨 전문 봇입니다.\n"
            "예) '서울 날씨 알려줘', '제주도 내일 비 와?'"
        ),
        "help": (
            "날씨 전용 봇. 지역명을 포함해 질문하시면 Open-Meteo API를 통해 "
            "현재 날씨와 3일 예보를 알려드립니다."
        ),
    },
]


def _make_application(token: str, role: dict[str, str | None]) -> Application:
    agent_name = role["agent"]
    start_copy = role["start"]
    help_copy = role["help"]
    label = role["label"]

    async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        user = update.effective_user
        await update.message.reply_html(
            start_copy.format(user=user.mention_html())
        )

    async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await update.message.reply_text(help_copy)

    async def handle_message(
        update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        user_text = update.message.text or ""
        chat_id = update.effective_chat.id
        await context.bot.send_chat_action(chat_id=chat_id, action=ChatAction.TYPING)

        try:
            if agent_name is None:
                reply = await run_orchestrator(user_text)
            else:
                reply = await run_specialist(agent_name, user_text)
        except Exception:
            logger.exception("[%s] agent failed", label)
            await update.message.reply_text(
                "죄송합니다. 답변 생성 중 오류가 발생했습니다. 잠시 후 다시 시도해주세요."
            )
            return

        if not reply:
            reply = "(응답이 비어 있습니다)"

        for chunk_start in range(0, len(reply), TELEGRAM_MAX_MESSAGE):
            await update.message.reply_text(
                reply[chunk_start : chunk_start + TELEGRAM_MAX_MESSAGE]
            )

    app = Application.builder().token(token).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    return app


async def _run_all(apps: list[tuple[str, Application]]) -> None:
    for label, app in apps:
        await app.initialize()
        await app.start()
        await app.updater.start_polling(allowed_updates=Update.ALL_TYPES)
        logger.info("[%s] bot started", label)

    stop_event = asyncio.Event()
    try:
        await stop_event.wait()
    finally:
        for label, app in apps:
            try:
                await app.updater.stop()
                await app.stop()
                await app.shutdown()
                logger.info("[%s] bot stopped", label)
            except Exception:
                logger.exception("[%s] shutdown error", label)


def main() -> None:
    load_dotenv()

    if not os.environ.get("GOOGLE_API_KEY"):
        raise RuntimeError(
            "GOOGLE_API_KEY is not set. Copy .env.example to .env and fill it in."
        )

    apps: list[tuple[str, Application]] = []
    for role in BOT_ROLES:
        token = os.environ.get(role["env"])
        if not token:
            continue
        app = _make_application(token, role)
        apps.append((role["label"], app))

    if not apps:
        raise RuntimeError(
            "No bot tokens found in .env. At least TELEGRAM_BOT_TOKEN must be set."
        )

    logger.info(
        "Starting %d bot(s): %s",
        len(apps),
        ", ".join(label for label, _ in apps),
    )

    try:
        asyncio.run(_run_all(apps))
    except KeyboardInterrupt:
        logger.info("shutdown requested")


if __name__ == "__main__":
    main()
