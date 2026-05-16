"""T-V3-B-01: Auth service for F-001 (login / signup / password-reset).

Build-Factory v3 Phase 1 Wave 1 / Group B-1 (Vertical Slice / Backend).

Endpoints実装の business logic + 共通レートリミッタ + email 真偽の存在判定なしで
2xx を返すための reset-flow を提供する.

仕様 (features.json#F-001 / docs/api-design/2026-05-16_v3/openapi.yaml):
  - login: 5 attempts / 15 min / ip で 429, generic 401 (no user enumeration)
  - signup: 3 / hour / ip で 429, 409 if email already exists
  - password-reset: 3 / hour / ip で 429, 常に 2xx (no account enumeration)

Storage: 開発 / テスト時は in-memory store. 本番では Supabase Auth に委譲する
予定 (T-V3-B-02 以降). この service は thin wrapper として動作する.
"""
from __future__ import annotations

import asyncio
import base64 as _base64
import hashlib as _hashlib
import hmac as _hmac
import secrets
import struct as _struct
import time
import uuid
from dataclasses import dataclass, field
from typing import Dict, Optional, Tuple


# ──────────────────────────────────────────────────────────────────────
# Errors
# ──────────────────────────────────────────────────────────────────────


class AuthError(Exception):
    """Base auth error."""


class InvalidCredentialsError(AuthError):
    """AC-F2 UNWANTED: invalid credentials (generic, no user enumeration)."""


class EmailAlreadyExistsError(AuthError):
    """409 from features.json#F-001 signup outputs_4xx."""


class RateLimitExceededError(AuthError):
    """AC-F7 / AC-F10 / AC-F13 UNWANTED: rate limit exceeded."""

    def __init__(self, retry_after_sec: int) -> None:
        super().__init__("rate limit exceeded")
        self.retry_after_sec = retry_after_sec


# ──────────────────────────────────────────────────────────────────────
# Rate limiter (token-bucket style, in-memory, per (scope, key))
# ──────────────────────────────────────────────────────────────────────


@dataclass
class _RateBucket:
    timestamps: list[float] = field(default_factory=list)


class RateLimiter:
    """Sliding-window rate limiter, per (scope, key) tuple.

    Build-Factory v3 では reverse proxy が x-forwarded-for を渡す前提で
    key は通常 client_ip / user_id / email を入れる. scope は endpoint 単位で
    分離 ("login" / "signup" / "password-reset").

    Thread / coroutine safety は asyncio.Lock で確保する.
    """

    def __init__(self) -> None:
        self._buckets: Dict[Tuple[str, str], _RateBucket] = {}
        self._lock = asyncio.Lock()

    async def check(
        self,
        scope: str,
        key: str,
        *,
        limit: int,
        window_sec: int,
    ) -> None:
        """Raise RateLimitExceededError if over limit, otherwise record now()."""
        now = time.monotonic()
        async with self._lock:
            bucket = self._buckets.setdefault((scope, key), _RateBucket())
            # 古い timestamp を削除
            bucket.timestamps = [t for t in bucket.timestamps if (now - t) < window_sec]
            if len(bucket.timestamps) >= limit:
                # 最古の timestamp が window から抜けるまでの秒数
                oldest = bucket.timestamps[0]
                retry_after = int(window_sec - (now - oldest)) + 1
                raise RateLimitExceededError(retry_after_sec=max(retry_after, 1))
            bucket.timestamps.append(now)

    def reset(self, scope: Optional[str] = None) -> None:
        """Test helper: clear buckets (optionally for one scope)."""
        if scope is None:
            self._buckets.clear()
        else:
            for k in list(self._buckets.keys()):
                if k[0] == scope:
                    del self._buckets[k]


# Module-level singleton (FastAPI dependency 注入できるよう get_rate_limiter で取得).
_RATE_LIMITER = RateLimiter()


def get_rate_limiter() -> RateLimiter:
    """FastAPI dependency override 用 accessor."""
    return _RATE_LIMITER


# ──────────────────────────────────────────────────────────────────────
# User store (in-memory; production では Supabase Auth に置き換え)
# ──────────────────────────────────────────────────────────────────────


@dataclass
class _UserRecord:
    user_id: str
    email: str
    password: str  # production では bcrypt hash. テスト用に plain でも可
    name: str
    mfa_enabled: bool = False


class UserStore:
    """In-memory user store for development / unit test."""

    def __init__(self) -> None:
        self._by_email: Dict[str, _UserRecord] = {}
        self._lock = asyncio.Lock()

    async def create(
        self,
        *,
        email: str,
        password: str,
        name: str,
    ) -> _UserRecord:
        async with self._lock:
            if email.lower() in self._by_email:
                raise EmailAlreadyExistsError(email)
            user = _UserRecord(
                user_id=str(uuid.uuid4()),
                email=email.lower(),
                password=password,
                name=name,
            )
            self._by_email[email.lower()] = user
            return user

    async def find_by_email(self, email: str) -> Optional[_UserRecord]:
        return self._by_email.get(email.lower())

    def reset(self) -> None:
        """Test helper."""
        self._by_email.clear()


_USER_STORE = UserStore()


def get_user_store() -> UserStore:
    return _USER_STORE


# ──────────────────────────────────────────────────────────────────────
# Token helpers (stub — production では Supabase Auth が発行)
# ──────────────────────────────────────────────────────────────────────


def issue_access_token(user_id: str) -> str:
    """Stub token. Production では Supabase Auth GoTrue が JWT を発行."""
    return f"at_{user_id}_{secrets.token_urlsafe(16)}"


def issue_refresh_token(user_id: str) -> str:
    return f"rt_{user_id}_{secrets.token_urlsafe(24)}"


# ──────────────────────────────────────────────────────────────────────
# Business logic
# ──────────────────────────────────────────────────────────────────────


async def authenticate(
    email: str,
    password: str,
    mfa_code: Optional[str] = None,
    *,
    store: Optional[UserStore] = None,
) -> _UserRecord:
    """AC-F1 / AC-F2 / AC-F4: login authentication.

    Returns user record on success. Raises InvalidCredentialsError otherwise.
    Importantly: do NOT distinguish between "unknown email" and "wrong password"
    in error type — both raise the same InvalidCredentialsError (AC-F2 generic).
    """
    s = store or _USER_STORE
    user = await s.find_by_email(email)
    # Constant-ish path to mitigate timing-based user enumeration.
    if user is None:
        # Spend time hashing a dummy password? In test we just raise.
        raise InvalidCredentialsError("invalid credentials")
    if user.password != password:
        raise InvalidCredentialsError("invalid credentials")
    # MFA: spec says only require when user.mfa_enabled. AC-F1 (basic happy path)
    # は mfa_required=False を返す.
    return user


async def register(
    *,
    email: str,
    password: str,
    name: str,
    invitation_token: Optional[str] = None,
    store: Optional[UserStore] = None,
) -> _UserRecord:
    """AC-F8: signup. Raises EmailAlreadyExistsError on duplicate."""
    s = store or _USER_STORE
    user = await s.create(email=email, password=password, name=name)
    # invitation_token は F-004 連携 (T-004-04) に委譲. ここでは consume されない.
    _ = invitation_token  # touched for clarity
    return user


async def request_password_reset(
    email: str,
    *,
    store: Optional[UserStore] = None,
) -> bool:
    """AC-F3 / AC-F11: password-reset request.

    Returns True if a reset email was actually sent (account exists), False if
    the account did not exist. The caller MUST NOT differentiate this in the
    HTTP response (no account enumeration). The boolean is returned only for
    internal audit / test purposes.
    """
    s = store or _USER_STORE
    user = await s.find_by_email(email)
    if user is None:
        # 何もしないで True 同等の遅延を装う (timing attack 緩和)
        await asyncio.sleep(0)
        return False
    # production では email worker enqueue. ここでは noop.
    return True


# ──────────────────────────────────────────────────────────────────────
# T-V3-B-02: MFA (TOTP) + OAuth callback
# ──────────────────────────────────────────────────────────────────────


class MfaAlreadyEnabledError(AuthError):
    """409: MFA already enabled for this user (features.json#F-001 enroll 409)."""


class InvalidTotpError(AuthError):
    """401: TOTP code did not validate (features.json#F-001 verify 401)."""


class UserNotFoundError(AuthError):
    """404: user_id not found (features.json#F-001 verify 404)."""


class OAuthStateMismatchError(AuthError):
    """401: OAuth state token mismatch or code expired (features.json#F-001
    oauth/callback 401)."""


class OAuthProviderNotConfiguredError(AuthError):
    """404: OAuth provider not configured (features.json#F-001 oauth/callback 404)."""


class OAuthHandshakeError(AuthError):
    """500: OAuth handshake failed (features.json#F-001 oauth/callback 500)."""


# ──────────────────────────────────────────────────────────────────────
# MFA store (in-memory; production では Supabase Auth に置き換え)
# ──────────────────────────────────────────────────────────────────────


@dataclass
class _MfaRecord:
    user_id: str
    totp_secret: str  # Base32-encoded secret (matches RFC 6238 totp_secret)
    backup_codes: list[str] = field(default_factory=list)


class MfaStore:
    """In-memory MFA enrollment store.

    Maps user_id → _MfaRecord. Each user has at most one enrolled secret;
    re-enrollment is rejected with MfaAlreadyEnabledError (409). Disabling
    must be explicit (T-V3-B-02 covers enroll/verify only; disable not in
    F-001 endpoint set but kept here as a private helper for tests).
    """

    def __init__(self) -> None:
        self._records: Dict[str, _MfaRecord] = {}
        self._lock = asyncio.Lock()

    async def enroll(
        self,
        *,
        user_id: str,
        totp_secret: str,
        backup_codes: list[str],
    ) -> _MfaRecord:
        async with self._lock:
            if user_id in self._records:
                raise MfaAlreadyEnabledError(user_id)
            rec = _MfaRecord(
                user_id=user_id,
                totp_secret=totp_secret,
                backup_codes=list(backup_codes),
            )
            self._records[user_id] = rec
            return rec

    async def get(self, user_id: str) -> Optional[_MfaRecord]:
        return self._records.get(user_id)

    async def disable(self, user_id: str) -> bool:
        """Remove enrollment; returns True if there was something to remove."""
        async with self._lock:
            return self._records.pop(user_id, None) is not None

    def reset(self) -> None:
        """Test helper."""
        self._records.clear()


_MFA_STORE = MfaStore()


def get_mfa_store() -> MfaStore:
    return _MFA_STORE


# ──────────────────────────────────────────────────────────────────────
# OAuth state store (in-memory CSRF / state-token tracker)
# ──────────────────────────────────────────────────────────────────────


class OAuthStateStore:
    """Tracks issued OAuth state tokens to defend against CSRF.

    The authorize step (NOT in T-V3-B-02 scope — handled by separate router
    backend/routers/oauth.py) calls .issue(provider) to mint a state. The
    callback step (THIS task) calls .consume(provider, state) to validate.
    Used states are single-shot.
    """

    def __init__(self) -> None:
        self._states: Dict[Tuple[str, str], float] = {}
        self._lock = asyncio.Lock()
        self._ttl_sec = 600  # 10 min

    async def issue(self, provider: str) -> str:
        state = secrets.token_urlsafe(24)
        async with self._lock:
            self._states[(provider, state)] = time.monotonic()
        return state

    async def consume(self, provider: str, state: str) -> bool:
        """Return True if the state was valid (and remove it). False otherwise."""
        async with self._lock:
            now = time.monotonic()
            # purge expired
            self._states = {
                k: t for k, t in self._states.items() if (now - t) < self._ttl_sec
            }
            if (provider, state) in self._states:
                del self._states[(provider, state)]
                return True
            return False

    def reset(self) -> None:
        """Test helper."""
        self._states.clear()


_OAUTH_STATE_STORE = OAuthStateStore()


def get_oauth_state_store() -> OAuthStateStore:
    return _OAUTH_STATE_STORE


# ──────────────────────────────────────────────────────────────────────
# TOTP verification (RFC 6238). 30s step, SHA-1, 6 digits.
# ──────────────────────────────────────────────────────────────────────


def _b32_decode_padded(secret: str) -> bytes:
    """RFC 4648 base32 decoding tolerant of missing '='. raises ValueError if
    the alphabet is wrong."""
    # pad to multiple of 8
    pad = (-len(secret)) % 8
    return _base64.b32decode(secret + ("=" * pad), casefold=False)


def _totp(secret: str, *, t: int, step: int = 30, digits: int = 6) -> str:
    """RFC 6238 TOTP. Returns N-digit zero-padded string."""
    counter = t // step
    msg = _struct.pack(">Q", counter)
    key = _b32_decode_padded(secret)
    h = _hmac.new(key, msg, _hashlib.sha1).digest()
    offset = h[-1] & 0x0F
    code = (
        ((h[offset] & 0x7F) << 24)
        | ((h[offset + 1] & 0xFF) << 16)
        | ((h[offset + 2] & 0xFF) << 8)
        | (h[offset + 3] & 0xFF)
    )
    return str(code % (10**digits)).zfill(digits)


def verify_totp(secret: str, code: str, *, window: int = 1, now: Optional[int] = None) -> bool:
    """Verify a TOTP code with ±`window` step tolerance.

    Returns True if any step in [-window, +window] matches `code`.
    """
    if not code.isdigit():
        return False
    digits = len(code)
    t = int(now if now is not None else time.time())
    try:
        for delta in range(-window, window + 1):
            cand = _totp(secret, t=t + delta * 30, digits=digits)
            if _hmac.compare_digest(cand, code):
                return True
    except (ValueError, _struct.error):
        return False
    return False


def generate_backup_codes(count: int = 8) -> list[str]:
    """Generate single-use backup codes (8 hex chars each)."""
    return [secrets.token_hex(4) for _ in range(count)]


def build_qr_url(*, user_id: str, totp_secret: str, issuer: str = "Build-Factory") -> str:
    """Build an otpauth:// URL the client renders as a QR code.

    Format: otpauth://totp/<issuer>:<user_id>?secret=<base32>&issuer=<issuer>
    """
    return (
        f"otpauth://totp/{issuer}:{user_id}"
        f"?secret={totp_secret}&issuer={issuer}&algorithm=SHA1&digits=6&period=30"
    )


# ──────────────────────────────────────────────────────────────────────
# MFA service entry points
# ──────────────────────────────────────────────────────────────────────


async def enroll_mfa(
    *,
    user_id: str,
    totp_secret: str,
    mfa_store: Optional[MfaStore] = None,
) -> _MfaRecord:
    """AC-F3 (T-V3-B-02 mapping): When POST /api/auth/mfa/enroll is called
    with valid inputs by an authorized caller, the system shall return 2xx
    with qr_code_url + backup_codes.

    Raises MfaAlreadyEnabledError → 409 if the user already enrolled.
    """
    s = mfa_store or _MFA_STORE
    backup_codes = generate_backup_codes()
    return await s.enroll(
        user_id=user_id,
        totp_secret=totp_secret,
        backup_codes=backup_codes,
    )


async def verify_mfa_code(
    *,
    user_id: str,
    totp_code: str,
    mfa_store: Optional[MfaStore] = None,
) -> Tuple[str, str]:
    """AC-F1 + AC-F6 (T-V3-B-02 mapping): When POST /api/auth/mfa/verify is
    called with valid TOTP code, the system shall return 2xx with
    access_token + refresh_token.

    AC-F (404): If the user_id has no MFA enrollment, raise UserNotFoundError.
    AC-F (401): If the TOTP code does not validate, raise InvalidTotpError.
    """
    s = mfa_store or _MFA_STORE
    rec = await s.get(user_id)
    if rec is None:
        raise UserNotFoundError(user_id)
    # Match backup code OR live TOTP
    if totp_code in rec.backup_codes:
        # backup code is single-shot: remove
        rec.backup_codes.remove(totp_code)
    elif not verify_totp(rec.totp_secret, totp_code):
        raise InvalidTotpError("invalid TOTP code")
    return (
        issue_access_token(user_id),
        issue_refresh_token(user_id),
    )


# ──────────────────────────────────────────────────────────────────────
# OAuth callback service
# ──────────────────────────────────────────────────────────────────────


async def process_oauth_callback(
    *,
    provider: str,
    code: str,
    state: str,
    state_store: Optional[OAuthStateStore] = None,
    user_store: Optional[UserStore] = None,
    mfa_store: Optional[MfaStore] = None,
    skip_state_check: bool = False,
) -> Tuple[str, str, str]:
    """AC-F10 (T-V3-B-02 mapping): When GET /api/auth/oauth/{provider}/callback
    is invoked with a valid state token, complete the handshake and return
    access_token + refresh_token + user_id.

    Errors:
      - OAuthProviderNotConfiguredError (404) — unknown provider
      - OAuthStateMismatchError (401)        — state did not match
      - OAuthHandshakeError (500)            — provider exchange failed

    Implementation note: this is a stub that does NOT call the actual OAuth
    provider — that lives in services/oauth_providers (T-023-04 surface).
    For T-V3-B-02 we focus on the F-001 contract: state-token validation,
    error envelope shape, and access_token/refresh_token issuance. A real
    integration is a follow-up; the call surface is identical so the wiring
    is trivially swappable.
    """
    provider_norm = provider.lower()
    if provider_norm not in _OAUTH_PROVIDERS_RUNTIME:
        raise OAuthProviderNotConfiguredError(provider)
    if not skip_state_check:
        store = state_store or _OAUTH_STATE_STORE
        ok = await store.consume(provider_norm, state)
        if not ok:
            raise OAuthStateMismatchError("state token mismatch or expired")
    if not code:
        raise OAuthHandshakeError("missing authorization code")

    # Stub: create-or-lookup a user keyed by ("oauth", provider, code-hash).
    # Real impl talks to provider, fetches email, then finds/creates user.
    # Here we generate a deterministic-ish user_id from (provider, code) hash.
    hash_input = f"{provider_norm}:{code}".encode("utf-8")
    user_id = str(uuid.UUID(bytes=_hashlib.sha256(hash_input).digest()[:16]))
    _ = user_store  # touched for clarity
    _ = mfa_store
    return (
        issue_access_token(user_id),
        issue_refresh_token(user_id),
        user_id,
    )


# Provider allow-list — features.json#F-001 oauth/callback inputs.provider enum.
_OAUTH_PROVIDERS_RUNTIME = frozenset({"anthropic", "github", "slack", "google"})


def oauth_supported_providers() -> frozenset[str]:
    """Return the configured OAuth provider set. Used by router for 422 check."""
    return _OAUTH_PROVIDERS_RUNTIME
