# thes
THE-S Co.,Ltd

## Telegram Bot

간단한 텔레그램 봇입니다. `python-telegram-bot` 라이브러리를 사용합니다.

### Setup

1. 의존성 설치

   ```bash
   pip install -r requirements.txt
   ```

2. 환경변수 파일 준비

   ```bash
   cp .env.example .env
   ```

   그 후 `.env` 파일을 열어 `TELEGRAM_BOT_TOKEN` 값을 [@BotFather](https://t.me/BotFather)에서 발급받은 토큰으로 교체합니다.

3. 봇 실행

   ```bash
   python bot.py
   ```

### Commands

- `/start` - 봇을 시작합니다.
- `/help` - 사용 가능한 명령어를 표시합니다.
- 그 외 텍스트 메시지는 그대로 따라 말합니다(echo).
