"""Gmail OAuth 2.0 인증 헬퍼.

환경변수 방식 (Codespaces 권장):
  GMAIL_CLIENT_ID, GMAIL_CLIENT_SECRET 설정 후 python gmail_auth.py

파일 방식:
  gmail_credentials.json 을 프로젝트 루트에 두고 python gmail_auth.py
"""

from __future__ import annotations

import json
import os
import sys

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]

CREDENTIALS_FILE = os.environ.get("GMAIL_CREDENTIALS_FILE", "gmail_credentials.json")
TOKEN_FILE = os.environ.get("GMAIL_TOKEN_FILE", "gmail_token.json")


def _build_client_config() -> dict | None:
    """환경변수에서 OAuth 클라이언트 설정을 구성합니다."""
    client_id = os.environ.get("GMAIL_CLIENT_ID")
    client_secret = os.environ.get("GMAIL_CLIENT_SECRET")
    if client_id and client_secret:
        return {
            "installed": {
                "client_id": client_id,
                "client_secret": client_secret,
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
                "redirect_uris": ["http://localhost"],
            }
        }
    return None


def get_gmail_credentials() -> Credentials:
    """저장된 토큰을 불러오거나, 없으면 OAuth 인증 흐름을 실행합니다."""
    creds: Credentials | None = None

    # 1) 환경변수에 저장된 토큰 JSON 확인
    token_json_env = os.environ.get("GMAIL_TOKEN_JSON")
    if token_json_env:
        creds = Credentials.from_authorized_user_info(
            json.loads(token_json_env), SCOPES
        )

    # 2) 파일에 저장된 토큰 확인
    if creds is None and os.path.exists(TOKEN_FILE):
        creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)

    if creds and creds.valid:
        return creds

    # 3) 토큰 갱신
    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())
    else:
        # 4) 새 인증 흐름: 환경변수 → 파일 순서로 시도
        client_config = _build_client_config()
        if client_config:
            flow = InstalledAppFlow.from_client_config(client_config, SCOPES)
        elif os.path.exists(CREDENTIALS_FILE):
            flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_FILE, SCOPES)
        else:
            raise FileNotFoundError(
                "Gmail 인증 정보가 없습니다. 아래 중 하나를 설정하세요:\n\n"
                "방법 1 (환경변수 — Codespaces 권장):\n"
                "  GMAIL_CLIENT_ID=xxx\n"
                "  GMAIL_CLIENT_SECRET=xxx\n\n"
                "방법 2 (파일):\n"
                f"  {CREDENTIALS_FILE} 을 프로젝트 루트에 저장"
            )
        creds = flow.run_console()

    # 5) 토큰 저장 (파일 + 콘솔 출력)
    token_data = creds.to_json()
    with open(TOKEN_FILE, "w") as f:
        f.write(token_data)
    print(f"✅ 토큰 파일 저장됨: {TOKEN_FILE}")
    print(
        "\n💡 Codespaces Secret으로도 저장하려면 아래 값을 "
        "GMAIL_TOKEN_JSON 에 등록하세요:"
    )
    print(token_data)
    return creds


if __name__ == "__main__":
    print("Gmail OAuth 인증을 시작합니다...\n")
    try:
        creds = get_gmail_credentials()
        print("\n✅ 인증 완료! 이제 봇에서 /gmail 명령어를 사용할 수 있습니다.")
    except FileNotFoundError as e:
        print(f"❌ {e}")
        sys.exit(1)
    except Exception as e:
        print(f"❌ 인증 실패: {e}")
        sys.exit(1)
