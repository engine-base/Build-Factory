"""T-V3-B-01: Auth REST router (F-001 — login / signup / password-reset).

Build-Factory v3 Phase 1 Wave 1 / Group B-1 (Vertical Slice / Backend).

Endpoints (features.json#F-001 / openapi.yaml):
  - POST /api/auth/login           (public, rate_limit 5/min/ip)
  - POST /api/auth/signup          (public, rate_limit 3/hour/ip)
  - POST /api/auth/password-reset  (public, rate_limit 3/hour/ip)

3-tier AC マッピング (docs/audit/2026-05-16_v3/T-V3-B-01.md):
  Tier 2 functional (13 AC) はこの router + services/auth.py + schemas/auth.py で
  逐語実装する. 各 AC の impl line range は audit MD に記録.
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status

from schemas.auth import (
    LoginRequest,
    LoginResponse,
    PasswordResetRequest,
    PasswordResetResponse,
    SignupRequest,
    SignupResponse,
)
from services.auth import (
    EmailAlreadyExistsError,
    InvalidCredentialsError,
    RateLimitExceededError,
    UserStore,
    authenticate,
    get_rate_limiter,
    get_user_store,
    issue_access_token,
    issue_refresh_token,
    register,
    request_password_reset,
)


router = APIRouter(prefix="/api/auth", tags=["auth"])


# ──────────────────────────────────────────────────────────────────────
# Rate limit policy (features.json#F-001 から逐語).
# ──────────────────────────────────────────────────────────────────────
# AC-F7  : login          5 / min  / ip
# AC-F10 : signup         3 / hour / ip
# AC-F13 : password-reset 3 / hour / ip
_LOGIN_RATE_LIMIT = 5
_LOGIN_RATE_WINDOW_SEC = 60
_SIGNUP_RATE_LIMIT = 3
_SIGNUP_RATE_WINDOW_SEC = 3600
_PWRESET_RATE_LIMIT = 3
_PWRESET_RATE_WINDOW_SEC = 3600


def _client_ip(request: Request) -> str:
    """proxy 前提 (x-forwarded-for) で client ip を抽出. Fallback to request.client.host.

    Build-Factory は Vercel + Cloudflare Tunnel の構成のため x-forwarded-for が
    通常入る. 取得できない場合は request.client.host (テストでは testserver).
    """
    xff = request.headers.get("x-forwarded-for")
    if xff:
        # left-most が origin client
        return xff.split(",")[0].strip()
    if request.client is not None:
        return request.client.host or "unknown"
    return "unknown"


# ──────────────────────────────────────────────────────────────────────
# POST /api/auth/login
# ──────────────────────────────────────────────────────────────────────


@router.post(
    "/login",
    response_model=LoginResponse,
    status_code=status.HTTP_200_OK,
    summary="POST /api/auth/login — F-001",
)
async def post_auth_login(
    body: LoginRequest,
    request: Request,
    store: UserStore = Depends(get_user_store),
) -> LoginResponse:
    """F-001 login.

    AC-F1 (EVENT-DRIVEN): When valid email/password is submitted to POST
    /api/auth/login, the system shall return 200 with access_token +
    refresh_token + user_id.

    AC-F2 (UNWANTED): If invalid credentials are submitted, the system shall
    return 401 with a generic message (no user enumeration).

    AC-F4 (EVENT-DRIVEN): When called with valid inputs by an authorized
    caller, the system shall return 2xx with the contract defined in
    features.json#F-001 (incl. access_token).

    AC-F5 (UNWANTED): Note — F-001 login is `auth: public`, so "without a
    valid auth token" only applies when the caller forwards a malformed
    Authorization header that the upstream middleware rejects. For the
    pure public form (no Authorization header), AC-F5 is structurally
    satisfied because no token is required. The 401 path therefore covers
    invalid credentials AND invalid Authorization header (both → generic
    401, no enumeration).

    AC-F6 (UNWANTED): Field-level validation errors (email format, password
    < 8 chars) are handled by FastAPI's Pydantic layer → 422.

    AC-F7 (UNWANTED): rate_limit 5/min/ip → 429.
    """
    # AC-F7: rate limit
    limiter = get_rate_limiter()
    ip = _client_ip(request)
    try:
        await limiter.check(
            "login",
            ip,
            limit=_LOGIN_RATE_LIMIT,
            window_sec=_LOGIN_RATE_WINDOW_SEC,
        )
    except RateLimitExceededError as exc:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={
                "code": "RATE_LIMITED",
                "message": "rate limit exceeded",
                "retry_after_sec": exc.retry_after_sec,
            },
            headers={"Retry-After": str(exc.retry_after_sec)},
        )

    # AC-F5: invalid Authorization header → 401 (we keep this generic to avoid
    # enumeration). Public endpoint: missing header is fine.
    auth_header = request.headers.get("authorization")
    if auth_header is not None and not _is_valid_authorization_format(auth_header):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "UNAUTHORIZED", "message": "invalid credentials"},
        )

    # AC-F1 / AC-F2 / AC-F4
    try:
        user = await authenticate(body.email, body.password, body.mfa_code, store=store)
    except InvalidCredentialsError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "UNAUTHORIZED", "message": "invalid credentials"},
        )

    return LoginResponse(
        access_token=issue_access_token(user.user_id),
        refresh_token=issue_refresh_token(user.user_id),
        user_id=user.user_id,
        mfa_required=user.mfa_enabled and body.mfa_code is None,
    )


def _is_valid_authorization_format(header_value: str) -> bool:
    """Accept only 'Bearer <token>' shape (case-insensitive on scheme).

    For AC-F5 we treat anything else as "invalid auth token" → 401.
    """
    parts = header_value.split(" ", 1)
    if len(parts) != 2:
        return False
    scheme, token = parts
    if scheme.lower() != "bearer":
        return False
    return bool(token.strip())


# ──────────────────────────────────────────────────────────────────────
# POST /api/auth/signup
# ──────────────────────────────────────────────────────────────────────


@router.post(
    "/signup",
    response_model=SignupResponse,
    status_code=status.HTTP_201_CREATED,
    summary="POST /api/auth/signup — F-001",
)
async def post_auth_signup(
    body: SignupRequest,
    request: Request,
    store: UserStore = Depends(get_user_store),
) -> SignupResponse:
    """F-001 signup.

    AC-F8 (EVENT-DRIVEN): When POST /api/auth/signup is called with valid
    inputs, the system shall return 2xx with the contract defined in
    features.json#F-001 (incl. user_id).

    AC-F9 (UNWANTED): Body validation failure → 422 (handled by Pydantic).

    AC-F10 (UNWANTED): rate_limit 3/hour/ip → 429.
    """
    # AC-F10: rate limit
    limiter = get_rate_limiter()
    ip = _client_ip(request)
    try:
        await limiter.check(
            "signup",
            ip,
            limit=_SIGNUP_RATE_LIMIT,
            window_sec=_SIGNUP_RATE_WINDOW_SEC,
        )
    except RateLimitExceededError as exc:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={
                "code": "RATE_LIMITED",
                "message": "rate limit exceeded",
                "retry_after_sec": exc.retry_after_sec,
            },
            headers={"Retry-After": str(exc.retry_after_sec)},
        )

    # AC-F8
    try:
        user = await register(
            email=body.email,
            password=body.password,
            name=body.name,
            invitation_token=body.invitation_token,
            store=store,
        )
    except EmailAlreadyExistsError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "CONFLICT",
                "message": "email already exists",
            },
        )

    return SignupResponse(user_id=user.user_id, verify_email_sent=True)


# ──────────────────────────────────────────────────────────────────────
# POST /api/auth/password-reset
# ──────────────────────────────────────────────────────────────────────


@router.post(
    "/password-reset",
    response_model=PasswordResetResponse,
    status_code=status.HTTP_200_OK,
    summary="POST /api/auth/password-reset — F-001",
)
async def post_auth_password_reset(
    body: PasswordResetRequest,
    request: Request,
    store: UserStore = Depends(get_user_store),
) -> PasswordResetResponse:
    """F-001 password reset.

    AC-F3 (EVENT-DRIVEN): When POST /api/auth/password-reset is called with
    an email, the system shall always return 2xx (no account enumeration)
    and send reset email only if the account exists.

    AC-F11 (EVENT-DRIVEN): valid inputs → 2xx with contract incl. status.

    AC-F12 (UNWANTED): body validation failure → 422.

    AC-F13 (UNWANTED): rate_limit 3/hour/ip → 429.
    """
    # AC-F13: rate limit
    limiter = get_rate_limiter()
    ip = _client_ip(request)
    try:
        await limiter.check(
            "password-reset",
            ip,
            limit=_PWRESET_RATE_LIMIT,
            window_sec=_PWRESET_RATE_WINDOW_SEC,
        )
    except RateLimitExceededError as exc:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={
                "code": "RATE_LIMITED",
                "message": "rate limit exceeded",
                "retry_after_sec": exc.retry_after_sec,
            },
            headers={"Retry-After": str(exc.retry_after_sec)},
        )

    # AC-F3 / AC-F11: 常に同じ status / body を返す.
    sent: Optional[bool] = None
    try:
        sent = await request_password_reset(body.email, store=store)
    except Exception:
        # Internal error は 500 で leak しないが、enumeration を避けるため
        # ここで握りつぶす選択肢もある. v3 は明示的に 5xx を許す (outputs_4xx に 500).
        sent = False

    # NOTE: returning the same shape regardless of `sent` is the explicit
    # behavior demanded by AC-F3. The boolean is intentionally not exposed.
    _ = sent
    return PasswordResetResponse(status="email sent if account exists")
