# thes
THE-S Co.,Ltd

## Telegram × Claude Multi-Agent Bot

Claude API 기반 멀티에이전트가 백엔드로 붙은 텔레그램 봇입니다.
`python-telegram-bot` 으로 메시지를 받고, `anthropic` SDK로 오케스트레이터 +
전문가 서브에이전트를 실행합니다.

### Architecture

```
Telegram user
     │
     ▼
 bot.py (python-telegram-bot, polling)
     │
     ▼
 agents.run_orchestrator()
     │
     ▼
 Orchestrator (Claude, tool_use)
     ├── translator_agent   (번역 전문)
     ├── coder_agent        (코드/프로그래밍 전문)
     └── researcher_agent   (사실/개념 전문)
```

Orchestrator는 사용자의 메시지를 보고 어떤 서브에이전트에게 위임할지 결정하거나,
일반 대화는 직접 응답합니다. 각 서브에이전트는 독립된 system prompt를 가진
별개의 Claude 호출입니다.

### Setup

1. 의존성 설치

   ```bash
   pip install -r requirements.txt
   ```

2. 환경변수 파일 준비

   ```bash
   cp .env.example .env
   ```

   `.env` 를 열어 두 값을 채웁니다.
   - `TELEGRAM_BOT_TOKEN` — [@BotFather](https://t.me/BotFather) 에서 발급
   - `ANTHROPIC_API_KEY` — <https://console.anthropic.com/> 에서 발급

3. 봇 실행

   ```bash
   python bot.py
   ```

### Commands

- `/start` — 봇을 시작합니다.
- `/help` — 사용 가능한 명령어와 에이전트 목록을 표시합니다.
- 그 외 텍스트 메시지는 오케스트레이터가 받아 적절한 전문 에이전트에 위임하거나
  직접 응답합니다.

### Extending

새 전문가 에이전트를 추가하려면 `agents.py` 에서:
1. `SUBAGENTS` 에 `system` 프롬프트와 `input_key` 를 정의합니다.
2. `ORCHESTRATOR_TOOLS` 에 같은 이름의 tool 스펙을 추가합니다.
