"""
gmail_client.py — Gmail API クライアント

google-api-python-client SDK を使った Gmail 操作。
初回のみブラウザ認証が必要。以降はトークンを自動更新。

セットアップ手順:
1. Google Cloud Console でプロジェクト作成
2. Gmail API を有効化
3. OAuth2 クライアントID（デスクトップアプリ）を作成
4. credentials.json を ~/.config/google/gmail_credentials.json に配置
5. python3 -c "from integrations.gmail_client import authenticate; authenticate()"
   → ブラウザが開き認証後 token.json が保存される
"""

import os
import base64
import time
import email.mime.text
from pathlib import Path
from typing import Optional

CREDENTIALS_PATH = Path(
    os.environ.get(
        "GMAIL_CREDENTIALS_PATH",
        str(Path.home() / ".config" / "google" / "gmail_credentials.json"),
    )
)
TOKEN_PATH = Path(
    os.environ.get(
        "GMAIL_TOKEN_PATH",
        str(Path.home() / ".config" / "google" / "gmail_token.json"),
    )
)
SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.send",
]

# 送信元アドレス設定
# メインアカウント（認証用）
GMAIL_MAIN_ACCOUNT = "masatotakamoto14@gmail.com"
# ビジネス用送信元（Gmailのエイリアスとして設定済み）
GMAIL_BUSINESS_ADDRESS = "info@engine-base.com"
GMAIL_BUSINESS_NAME = "株式会社ENGINE BASE"


def is_configured() -> bool:
    """credentials.json が存在するか確認する（設定済みチェック用）"""
    return CREDENTIALS_PATH.exists()


def authenticate():
    """
    OAuth2 フローを実行してトークンを保存する。
    初回のみブラウザが開く。以降は token.json から自動復元。
    """
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from google.auth.transport.requests import Request

    creds = None
    if TOKEN_PATH.exists():
        creds = Credentials.from_authorized_user_file(str(TOKEN_PATH), SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not CREDENTIALS_PATH.exists():
                raise FileNotFoundError(
                    f"credentials.json が見つかりません: {CREDENTIALS_PATH}\n"
                    "Google Cloud Console からダウンロードして配置してください"
                )
            flow = InstalledAppFlow.from_client_secrets_file(
                str(CREDENTIALS_PATH), SCOPES
            )
            creds = flow.run_local_server(port=0)
        TOKEN_PATH.parent.mkdir(parents=True, exist_ok=True)
        TOKEN_PATH.write_text(creds.to_json())
        print(f"[gmail] トークン保存完了: {TOKEN_PATH}")

    return creds


def _get_service():
    """認証済みの Gmail サービスオブジェクトを返す。"""
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request
    from googleapiclient.discovery import build

    if not TOKEN_PATH.exists():
        raise RuntimeError(
            "Gmail 未認証です。先に authenticate() を実行してください"
        )

    creds = Credentials.from_authorized_user_file(str(TOKEN_PATH), SCOPES)
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
        TOKEN_PATH.write_text(creds.to_json())

    return build("gmail", "v1", credentials=creds, cache_discovery=False)


def get_unread_messages(max_results: int = 20) -> list[dict]:
    """
    未読メールを取得して辞書リストで返す。

    Returns:
        [{"external_id", "subject", "sender_name", "sender_email",
          "received_at", "snippet"}, ...]
    """
    if not is_configured() or not TOKEN_PATH.exists():
        print("[gmail] 未設定のため Gmail 取得をスキップ")
        return []

    try:
        service = _get_service()
        result = service.users().messages().list(
            userId="me",
            labelIds=["UNREAD", "INBOX"],
            maxResults=max_results,
        ).execute()

        messages = []
        for msg_ref in result.get("messages", []):
            try:
                msg = service.users().messages().get(
                    userId="me",
                    id=msg_ref["id"],
                    format="metadata",
                    metadataHeaders=["From", "Subject", "Date"],
                ).execute()

                headers = {
                    h["name"]: h["value"]
                    for h in msg["payload"]["headers"]
                }
                from_raw = headers.get("From", "")
                # "表示名 <email@example.com>" を分解
                sender_name, sender_email = _parse_sender(from_raw)

                messages.append({
                    "external_id": msg_ref["id"],
                    "subject": headers.get("Subject", "(件名なし)"),
                    "sender_name": sender_name,
                    "sender_email": sender_email,
                    "received_at": headers.get("Date", ""),
                    "snippet": msg.get("snippet", ""),
                })
                time.sleep(0.1)  # レート制限対応
            except Exception as e:
                print(f"[gmail] メッセージ取得エラー id={msg_ref['id']}: {e}")
                continue

        return messages

    except Exception as e:
        print(f"[gmail] 未読取得エラー: {e}")
        return []


def send_email(
    to: str,
    subject: str,
    body: str,
    from_address: str = None,
    from_name: str = None,
) -> bool:
    """
    メールを送信する。approval_worker から呼ばれる。
    必ず approval_queue 承認後のみ呼ぶこと。

    Args:
        to: 宛先メールアドレス
        subject: 件名
        body: 本文
        from_address: 送信元アドレス（省略時は GMAIL_BUSINESS_ADDRESS）
        from_name: 送信元表示名（省略時は GMAIL_BUSINESS_NAME）

    Returns:
        True: 送信成功 / False: 失敗
    """
    if not is_configured() or not TOKEN_PATH.exists():
        print(f"[gmail] 未設定のため送信スキップ: {subject}")
        return False

    sender_addr = from_address or GMAIL_BUSINESS_ADDRESS
    sender_name = from_name or GMAIL_BUSINESS_NAME

    try:
        service = _get_service()
        msg = email.mime.text.MIMEText(body, "plain", "utf-8")
        msg["To"] = to
        msg["Subject"] = subject
        msg["From"] = f"{sender_name} <{sender_addr}>"
        raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
        service.users().messages().send(
            userId="me", body={"raw": raw}
        ).execute()
        print(f"[gmail] 送信完了: {subject} → {to} (from: {sender_addr})")
        return True
    except Exception as e:
        print(f"[gmail] 送信失敗: {e}")
        return False


def mark_as_read(message_id: str) -> bool:
    """指定メッセージを既読にする。"""
    if not is_configured() or not TOKEN_PATH.exists():
        return False
    try:
        service = _get_service()
        service.users().messages().modify(
            userId="me",
            id=message_id,
            body={"removeLabelIds": ["UNREAD"]},
        ).execute()
        return True
    except Exception as e:
        print(f"[gmail] 既読化失敗 id={message_id}: {e}")
        return False


def _parse_sender(from_raw: str) -> tuple[str, str]:
    """'表示名 <email>' 形式から (名前, メールアドレス) を抽出する。"""
    import re
    match = re.match(r'"?([^"<]+)"?\s*<([^>]+)>', from_raw)
    if match:
        return match.group(1).strip(), match.group(2).strip()
    # メールアドレスのみの場合
    if "@" in from_raw:
        return from_raw.strip(), from_raw.strip()
    return from_raw.strip(), ""
