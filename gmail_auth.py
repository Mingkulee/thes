"""Gmail OAuth 2.0 인증 헬퍼.

최초 1회 실행:  python gmail_auth.py
이후 봇 실행 시 자동으로 저장된 토큰을 사용합니다.
"""

from __future__ import annotations

import os
import sys

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]

CREDENTIALS_FILE = os.environ.get("GMAIL_CREDENTIALS_FILE", "gmail_credentials.json")
TOKEN_FILE = os.environ.get("GMAIL_TOKEN_FILE", "gmail_token.json")


def get_gmail_credentials() -> Credentials:
    """저장된 토큰을 불러오거나, 없으면 OAuth 인증 흐름을 실행합니다."""
    creds: Credentials | None = None

    if os.path.exists(TOKEN_FILE):
        creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)

    if creds and creds.valid:
        return creds

    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())
    else:
        if not os.path.exists(CREDENTIALS_FILE):
            raise FileNotFoundError(
                f"Gmail 인증 파일({CREDENTIALS_FILE})이 없습니다.\n"
                "Google Cloud Console에서 OAuth 2.0 클라이언트 자격증명을 다운로드한 후\n"
                f"{CREDENTIALS_FILE} 로 저장하고 다시 실행하세요."
            )
        flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_FILE, SCOPES)
        # run_console: URL 표시 후 코드 입력 방식 (Codespaces/헤드리스 환경 호환)
        creds = flow.run_console()

    with open(TOKEN_FILE, "w") as f:
        f.write(creds.to_json())
    print(f"✅ 토큰이 저장되었습니다: {TOKEN_FILE}")
    return creds


if __name__ == "__main__":
    print("Gmail OAuth 인증을 시작합니다...")
    try:
        creds = get_gmail_credentials()
        print("✅ 인증 완료! 이제 봇에서 Gmail을 사용할 수 있습니다.")
    except FileNotFoundError as e:
        print(f"❌ {e}")
        sys.exit(1)
    except Exception as e:
        print(f"❌ 인증 실패: {e}")
        sys.exit(1)
