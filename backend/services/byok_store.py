"""T-020-04: BYOK (Bring-Your-Own-Key) per-user/provider API key store.

ユーザが自分の API key を持ち込み、それを Build-Factory が provider 呼び出し時に
代理使用する仕組み. T-023-03 (pgsodium 暗号化保管) のアプリ層側ストアとして、
in-memory & encrypted-at-rest で保管する.

設計:
  - per (user_id, provider) で 1 つの key を保管
  - Fernet で暗号化して in-memory dict に持つ (鍵が漏れても in-memory dump で安全)
  - 鍵 (Fernet key) は環境変数 BF_BYOK_FERNET_KEY、未設定なら ephemeral key を自動生成
  - key version を持ち、rotate() で旧鍵 → 新鍵を再暗号化
  - 取り出し (get_decrypted_key) は plaintext を返すが、ログには絶対出さない
  - list_keys は plain text を返さず、masked preview のみ
"""
from __future__ import annotations

import logging
import os
import threading
import time
from dataclasses import dataclass, field
from typing import Optional

from cryptography.fernet import Fernet, InvalidToken

from services.provider_adapter import SUPPORTED_PROVIDERS

logger = logging.getLogger(__name__)


class BYOKError(RuntimeError):
    pass


MAX_KEY_LEN = 500
MAX_KEYS_PER_USER = 10
MAX_KEYS_TOTAL = 100_000

# プロバイダ別の許容 key prefix (sanity check; 完全な validation ではない)
# 例: anthropic の API key は sk-ant-xxx, openai は sk-xxx, gemini は AIza...
PROVIDER_KEY_PREFIXES: dict[str, tuple[str, ...]] = {
    "anthropic": ("sk-ant-",),
    "openai": ("sk-",),
    "gemini": ("AIza",),
}


@dataclass
class BYOKRecord:
    user_id: str
    provider: str
    ciphertext: bytes
    key_version: int
    created_at: float
    updated_at: float
    masked_preview: str  # 例: "sk-ant-...abcd"
    detail: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        # 平文は絶対に含めない
        return {
            "user_id": self.user_id,
            "provider": self.provider,
            "key_version": self.key_version,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "masked_preview": self.masked_preview,
            "detail": dict(self.detail),
        }


def _generate_ephemeral_key() -> bytes:
    return Fernet.generate_key()


def _mask(plaintext: str) -> str:
    """key を 'prefix...last4' 形式に. <= 8 chars なら '****last4'."""
    if len(plaintext) <= 4:
        return "*" * len(plaintext)
    if len(plaintext) <= 12:
        return f"****{plaintext[-4:]}"
    # 7 chars prefix + ... + last 4 chars
    return f"{plaintext[:7]}...{plaintext[-4:]}"


class BYOKStore:
    def __init__(self, fernet_key: Optional[bytes] = None):
        self._lock = threading.Lock()
        self._records: dict[tuple[str, str], BYOKRecord] = {}
        self._keys: dict[int, Fernet] = {}
        self._current_version = 1
        if fernet_key is None:
            fernet_key = os.environ.get("BF_BYOK_FERNET_KEY", "").encode()
            if not fernet_key:
                fernet_key = _generate_ephemeral_key()
        try:
            self._keys[1] = Fernet(fernet_key)
        except (ValueError, TypeError) as e:
            raise BYOKError(f"invalid fernet_key: {e}")
        self._total = 0

    # ── helpers ─────────────────────────────────────────────────────────

    def _validate_user(self, user_id: str) -> str:
        if not isinstance(user_id, str) or not user_id.strip():
            raise BYOKError("user_id must not be empty")
        if len(user_id) > 200:
            raise BYOKError("user_id must be <= 200 chars")
        return user_id.strip()

    def _validate_provider(self, provider: str) -> str:
        if not isinstance(provider, str) or provider not in SUPPORTED_PROVIDERS:
            raise BYOKError(
                f"provider must be one of {SUPPORTED_PROVIDERS}"
            )
        return provider

    def _validate_api_key(self, provider: str, api_key: str) -> str:
        if not isinstance(api_key, str) or not api_key.strip():
            raise BYOKError("api_key must not be empty")
        api_key = api_key.strip()
        if len(api_key) > MAX_KEY_LEN:
            raise BYOKError(f"api_key must be <= {MAX_KEY_LEN} chars")
        prefixes = PROVIDER_KEY_PREFIXES.get(provider, ())
        if prefixes and not any(api_key.startswith(p) for p in prefixes):
            raise BYOKError(
                f"api_key for {provider} must start with one of {prefixes}"
            )
        return api_key

    def _count_for_user(self, user_id: str) -> int:
        return sum(1 for k in self._records if k[0] == user_id)

    # ── public API ──────────────────────────────────────────────────────

    def set_key(
        self,
        user_id: str,
        provider: str,
        api_key: str,
        *,
        detail: Optional[dict] = None,
    ) -> BYOKRecord:
        user_id = self._validate_user(user_id)
        provider = self._validate_provider(provider)
        api_key = self._validate_api_key(provider, api_key)
        with self._lock:
            key = (user_id, provider)
            existed = key in self._records
            if not existed:
                if self._count_for_user(user_id) >= MAX_KEYS_PER_USER:
                    raise BYOKError(
                        f"max keys per user reached: {MAX_KEYS_PER_USER}"
                    )
                if self._total >= MAX_KEYS_TOTAL:
                    raise BYOKError(
                        f"max keys total reached: {MAX_KEYS_TOTAL}"
                    )
            fernet = self._keys[self._current_version]
            now = time.time()
            ct = fernet.encrypt(api_key.encode("utf-8"))
            rec = BYOKRecord(
                user_id=user_id,
                provider=provider,
                ciphertext=ct,
                key_version=self._current_version,
                created_at=self._records[key].created_at if existed else now,
                updated_at=now,
                masked_preview=_mask(api_key),
                detail=dict(detail or {}),
            )
            self._records[key] = rec
            if not existed:
                self._total += 1
            return rec

    def get_decrypted_key(self, user_id: str, provider: str) -> Optional[str]:
        user_id = self._validate_user(user_id)
        provider = self._validate_provider(provider)
        with self._lock:
            rec = self._records.get((user_id, provider))
        if rec is None:
            return None
        fernet = self._keys.get(rec.key_version)
        if fernet is None:
            raise BYOKError(
                f"no decryption key for version {rec.key_version}"
            )
        try:
            pt = fernet.decrypt(rec.ciphertext)
        except InvalidToken as e:
            raise BYOKError(f"decryption failed: {e}")
        return pt.decode("utf-8")

    def get_record(self, user_id: str, provider: str) -> Optional[BYOKRecord]:
        user_id = self._validate_user(user_id)
        provider = self._validate_provider(provider)
        with self._lock:
            return self._records.get((user_id, provider))

    def list_for_user(self, user_id: str) -> list[BYOKRecord]:
        user_id = self._validate_user(user_id)
        with self._lock:
            return [v for (u, _p), v in self._records.items() if u == user_id]

    def delete_key(self, user_id: str, provider: str) -> bool:
        user_id = self._validate_user(user_id)
        provider = self._validate_provider(provider)
        with self._lock:
            key = (user_id, provider)
            if key not in self._records:
                return False
            del self._records[key]
            self._total -= 1
            return True

    def rotate(self, new_fernet_key: bytes) -> int:
        """新しい Fernet key を登録し、全レコードを再暗号化. 返り値は更新件数."""
        try:
            new_fernet = Fernet(new_fernet_key)
        except (ValueError, TypeError) as e:
            raise BYOKError(f"invalid fernet_key: {e}")
        with self._lock:
            new_version = max(self._keys) + 1
            self._keys[new_version] = new_fernet
            updated = 0
            for key, rec in list(self._records.items()):
                old_fernet = self._keys[rec.key_version]
                pt = old_fernet.decrypt(rec.ciphertext)
                rec.ciphertext = new_fernet.encrypt(pt)
                rec.key_version = new_version
                rec.updated_at = time.time()
                updated += 1
            self._current_version = new_version
            return updated


# ──────────────────────────────────────────────────────────────────────
# Anthropic prompt cache helper (cache_control: ephemeral)
# ──────────────────────────────────────────────────────────────────────


# Anthropic は messages.create() の system / messages 配列の各ブロックに
# cache_control = {"type": "ephemeral"} を付けると 5 分間 TTL の prompt cache.
# 最大 4 つの cache breakpoint (system + 各 user message に付与可能).
MAX_CACHE_BREAKPOINTS = 4


def build_anthropic_cached_payload(
    model: str,
    messages: list[dict],
    *,
    max_tokens: int = 4096,
    temperature: float = 0.7,
    system_cache: bool = True,
    message_cache_indices: Optional[list[int]] = None,
) -> dict:
    """Anthropic prompt cache 用 payload を作る.

    - system_cache=True なら system プロンプトを 1 ブロックでキャッシュ
    - message_cache_indices で個別の user message にも cache_control を付与
    - 合計 cache_control 数は MAX_CACHE_BREAKPOINTS 以下
    """
    if not isinstance(model, str) or not model.strip():
        raise BYOKError("model must not be empty")
    if not isinstance(messages, list) or not messages:
        raise BYOKError("messages must be a non-empty list")
    if not isinstance(max_tokens, int) or max_tokens <= 0:
        raise BYOKError("max_tokens must be > 0")
    if not isinstance(temperature, (int, float)) or not (0.0 <= temperature <= 2.0):
        raise BYOKError("temperature must be 0.0..2.0")

    sys_msgs = [m for m in messages if m.get("role") == "system"]
    user_msgs = [m for m in messages if m.get("role") != "system"]

    payload: dict = {
        "model": model,
        "max_tokens": max_tokens,
        "temperature": temperature,
    }

    breakpoints = 0
    if sys_msgs:
        system_text = "\n\n".join(m["content"] for m in sys_msgs)
        if system_cache:
            payload["system"] = [
                {
                    "type": "text", "text": system_text,
                    "cache_control": {"type": "ephemeral"},
                }
            ]
            breakpoints += 1
        else:
            payload["system"] = system_text

    indices = set(message_cache_indices or [])
    if indices and not all(isinstance(i, int) and 0 <= i < len(user_msgs) for i in indices):
        raise BYOKError(
            f"message_cache_indices must be int and 0..{len(user_msgs)-1}"
        )
    if breakpoints + len(indices) > MAX_CACHE_BREAKPOINTS:
        raise BYOKError(
            f"total cache breakpoints must be <= {MAX_CACHE_BREAKPOINTS}"
        )

    out_messages: list[dict] = []
    for i, m in enumerate(user_msgs):
        if i in indices:
            out_messages.append({
                "role": m["role"],
                "content": [
                    {
                        "type": "text", "text": m["content"],
                        "cache_control": {"type": "ephemeral"},
                    }
                ],
            })
        else:
            out_messages.append({"role": m["role"], "content": m["content"]})
    payload["messages"] = out_messages
    return payload


# ──────────────────────────────────────────────────────────────────────
# Singleton
# ──────────────────────────────────────────────────────────────────────


_store: Optional[BYOKStore] = None
_lock = threading.Lock()


def get_store() -> BYOKStore:
    global _store
    with _lock:
        if _store is None:
            _store = BYOKStore()
        return _store


def reset_store() -> None:
    global _store
    with _lock:
        _store = BYOKStore()
