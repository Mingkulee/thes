#!/usr/bin/env bash
# Friendly welcome message shown every time the Codespace is attached.

set -e

cat <<'BANNER'

╔══════════════════════════════════════════════════════════════╗
║  thes — Telegram Multi-Agent Bot (Codespaces)                ║
╚══════════════════════════════════════════════════════════════╝

BANNER

echo "환경 변수 상태:"
for var in GOOGLE_API_KEY TELEGRAM_BOT_TOKEN TELEGRAM_BOT_TOKEN_TRANSLATOR \
           TELEGRAM_BOT_TOKEN_CODER TELEGRAM_BOT_TOKEN_RESEARCHER TELEGRAM_BOT_TOKEN_WEATHER \
           TELEGRAM_BOT_TOKEN_DOCANALYST TELEGRAM_BOT_TOKEN_GMAIL; do
    if [ -n "${!var}" ]; then
        printf "  ✓ %s\n" "$var"
    else
        printf "  ✗ %s (not set)\n" "$var"
    fi
done

echo ""
if [ -z "$GOOGLE_API_KEY" ] || [ -z "$TELEGRAM_BOT_TOKEN" ]; then
    cat <<'HELP'
⚠️  필수 환경변수가 비어 있습니다.

두 가지 방법 중 하나로 설정하세요:

1) Codespaces Secrets (권장)
   - 모바일: github.com/settings/codespaces 에서 Secret 추가
   - 이 Codespace에 접근 허용 → Codespace 재시작

2) 로컬 .env 파일
   cp .env.example .env
   # 그 후 .env 파일을 열어 값을 채우세요

HELP
else
    echo "✅ 준비 완료! 아래 명령으로 봇을 시작하세요:"
    echo ""
    echo "   python bot.py"
    echo ""
fi
