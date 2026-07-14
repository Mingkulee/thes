# thes
THE-S Co.,Ltd

## Telegram × Gemini Multi-Agent Bot

Google Gemini API 기반 멀티에이전트 텔레그램 봇입니다. 하나의 프로세스가
여러 개의 전용 텔레그램 봇을 동시에 폴링하며, 오케스트레이터가 사용자의
메시지를 적절한 전문가 에이전트에게 위임합니다.

## Architecture

```
python bot.py (단일 프로세스)
  ├── Application #1 → @Orchestrator    → 자동 라우팅
  ├── Application #2 → @Translator      → translator 직결
  ├── Application #3 → @Coder           → coder 직결
  ├── Application #4 → @Researcher      → researcher 직결
  └── Application #5 → @Weather         → weather 직결 (Open-Meteo API)
```

전문가 에이전트:
- **translator** — 번역 (Gemini)
- **coder** — 프로그래밍 Q&A (Gemini)
- **researcher** — 사실/개념 질문 (Gemini)
- **weather** — Open-Meteo API 호출 후 Gemini가 한국어로 포맷

## 실행 방법 (3가지)

### 방법 1: GitHub Codespaces (모바일 사용자 권장)

모바일 브라우저에서 바로 실행 가능한 방법입니다.

1. 모바일 브라우저에서 [github.com/settings/codespaces](https://github.com/settings/codespaces) 접속
2. **"New secret"** 클릭해서 아래 Secret들을 등록하고 이 저장소에 접근 허용:
   - `GOOGLE_API_KEY` — [aistudio.google.com/app/apikey](https://aistudio.google.com/app/apikey) 에서 발급
   - `TELEGRAM_BOT_TOKEN` — [@BotFather](https://t.me/BotFather)에서 발급
   - `TELEGRAM_BOT_TOKEN_TRANSLATOR` (선택)
   - `TELEGRAM_BOT_TOKEN_CODER` (선택)
   - `TELEGRAM_BOT_TOKEN_RESEARCHER` (선택)
   - `TELEGRAM_BOT_TOKEN_WEATHER` (선택)
3. 이 저장소 페이지에서 **Code → Codespaces → Create codespace** 클릭
4. 터미널이 열리면 아래 명령 한 줄:
   ```bash
   python bot.py
   ```

### 방법 2: 로컬 실행

```bash
git clone https://github.com/Mingkulee/thes.git
cd thes
git checkout claude/add-telegram-integration-mWMOO
pip install -r requirements.txt
cp .env.example .env
# .env 파일을 편집기로 열어 값 채우기
python bot.py
```

### 방법 3: 클라우드 배포 (Railway 등)

`python bot.py` 를 start command로 지정하고 환경변수를 등록하면 어떤 PaaS에서든 동작합니다.

## Commands (텔레그램 채팅)

- `/start` — 봇 소개 메시지
- `/help` — 사용 가능한 에이전트 목록
- 일반 메시지 — 오케스트레이터가 자동으로 분류해 전문가에게 위임

### 사용 예시

```
"Hello world 를 한국어로 번역해줘"     → translator
"파이썬으로 퀵소트 짜줘"                → coder
"양자역학이 뭐야?"                      → researcher
"서울 날씨 알려줘"                      → weather (Open-Meteo)
"안녕 오늘 뭐해?"                       → orchestrator 직접 응답
```

## 환경변수

| 이름 | 필수 | 설명 |
|---|---|---|
| `GOOGLE_API_KEY` | ✅ | Gemini API 키 |
| `TELEGRAM_BOT_TOKEN` | ⚠️ | 오케스트레이터 봇 토큰 (최소 1개 봇 필요) |
| `TELEGRAM_BOT_TOKEN_TRANSLATOR` | | 번역 전용 봇 토큰 |
| `TELEGRAM_BOT_TOKEN_CODER` | | 코더 전용 봇 토큰 |
| `TELEGRAM_BOT_TOKEN_RESEARCHER` | | 리서치 전용 봇 토큰 |
| `TELEGRAM_BOT_TOKEN_WEATHER` | | 날씨 전용 봇 토큰 |

## Extending

### 새 전문가 에이전트 추가 (LLM only)
`agents.py` 의 `SUBAGENTS` 딕셔너리에 `{"이름": "system prompt"}` 를 추가하고,
`ORCHESTRATOR_SYSTEM` 의 라우팅 규칙에 해당 이름을 포함시키면 됩니다.

### 새 도구 기반 에이전트 추가
`tools.py` 에 헬퍼 함수를 정의한 뒤, `agents.py` 에서 `run_weather()` 를 참고해
별도 함수를 만들고, `run_orchestrator()` 와 `run_specialist()` 에 분기를 추가합니다.
