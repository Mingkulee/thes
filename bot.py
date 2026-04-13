"""Telegram bot entry point for THE-S Co., Ltd."""

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

from agents import run_orchestrator

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

TELEGRAM_MAX_MESSAGE = 4096


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    await update.message.reply_html(
        f"안녕하세요 {user.mention_html()}님! THE-S 멀티에이전트 봇입니다.\n"
        "메시지를 보내시면 번역 / 코딩 / 리서치 전문 에이전트가 자동으로 "
        "답변을 준비합니다. /help 로 사용법을 확인하세요."
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "사용 가능한 명령어:\n"
        "/start - 봇 시작\n"
        "/help - 도움말 보기\n\n"
        "일반 메시지는 오케스트레이터가 분석해 적절한 전문가에게 위임합니다:\n"
        "• translator_agent - 번역 요청\n"
        "• coder_agent - 코드/프로그래밍 질문\n"
        "• researcher_agent - 사실/개념 질문\n"
        "그 외 일반 대화는 오케스트레이터가 직접 응답합니다."
    )


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_text = update.message.text or ""
    chat_id = update.effective_chat.id

    await context.bot.send_chat_action(chat_id=chat_id, action=ChatAction.TYPING)

    try:
        reply = await run_orchestrator(user_text)
    except Exception:
        logger.exception("orchestrator failed")
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


def main() -> None:
    load_dotenv()
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not token:
        raise RuntimeError(
            "TELEGRAM_BOT_TOKEN is not set. Copy .env.example to .env and fill it in."
        )
    if not os.environ.get("ANTHROPIC_API_KEY"):
        raise RuntimeError(
            "ANTHROPIC_API_KEY is not set. Copy .env.example to .env and fill it in."
        )

    application = Application.builder().token(token).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message)
    )

    logger.info("Starting Telegram bot (multi-agent mode)...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
