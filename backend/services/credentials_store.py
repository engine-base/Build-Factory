"""
credentials_store.py — SaaS認証情報の暗号化保管庫

各サービス（Notion / Slack / Google / X / etc）の ID/PW を AES暗号化して保管。
- 鍵ファイル: ~/.engine-base/master.key（初回自動生成）
- 認証情報: ~/.engine-base/credentials.enc（暗号化された JSON）
- 鍵ファイルは 600 で保存・自動バックアップ非推奨
"""

import json
import os
from pathlib import Path
from typing import Optional

from cryptography.fernet import Fernet

import os
# プロジェクト個別の credentials store。company-dashboard と分離。
_default_dir = Path.home() / ".build-factory"
CONFIG_DIR  = Path(os.environ.get("BF_CREDENTIALS_DIR") or _default_dir)
KEY_FILE    = CONFIG_DIR / "master.key"
CREDS_FILE  = CONFIG_DIR / "credentials.enc"


def _ensure_dir() -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(CONFIG_DIR, 0o700)
    except Exception:
        pass


def _load_or_create_key() -> bytes:
    _ensure_dir()
    if KEY_FILE.exists():
        return KEY_FILE.read_bytes().strip()
    key = Fernet.generate_key()
    KEY_FILE.write_bytes(key)
    try:
        os.chmod(KEY_FILE, 0o600)
    except Exception:
        pass
    print(f"[credentials_store] 新規鍵を生成: {KEY_FILE}（権限600）")
    return key


def _cipher() -> Fernet:
    return Fernet(_load_or_create_key())


def _load_all() -> dict:
    if not CREDS_FILE.exists():
        return {}
    try:
        encrypted = CREDS_FILE.read_bytes()
        decrypted = _cipher().decrypt(encrypted)
        return json.loads(decrypted.decode("utf-8"))
    except Exception as e:
        print(f"[credentials_store] 復号失敗: {e}")
        return {}


def _save_all(data: dict) -> None:
    _ensure_dir()
    encrypted = _cipher().encrypt(json.dumps(data, ensure_ascii=False).encode("utf-8"))
    CREDS_FILE.write_bytes(encrypted)
    try:
        os.chmod(CREDS_FILE, 0o600)
    except Exception:
        pass


# ── 公開API ──────────────────────────────────────────────────────────

def set_credential(service: str, username: str, password: str, **extra) -> None:
    """サービスの認証情報を暗号化保存する。
    extra で OTP secret / login URL / メモ等も保管可能。"""
    data = _load_all()
    data[service.lower()] = {
        "username": username,
        "password": password,
        **extra,
    }
    _save_all(data)


def get_credential(service: str) -> Optional[dict]:
    """サービスの認証情報を取得する。なければ None。"""
    data = _load_all()
    return data.get(service.lower())


def list_services() -> list[str]:
    """登録済みサービス名一覧を返す（パスワードは含まない）。"""
    return sorted(_load_all().keys())


def delete_credential(service: str) -> bool:
    """登録を削除する。"""
    data = _load_all()
    if service.lower() in data:
        del data[service.lower()]
        _save_all(data)
        return True
    return False
