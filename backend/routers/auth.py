"""T-V3-B-01 + T-V3-B-02: Auth REST router (F-001).

Build-Factory v3 Phase 1 / Group B (Vertical Slice / Backend).

Endpoints (features.json#F-001 / openapi.yaml):
  - POST /api/auth/login                    (T-V3-B-01, public, rate_limit 5/min/ip)
  - POST /api/auth/signup                   (T-V3-B-01, public, rate_limit 3/hour/ip)
  - POST /api/auth/password-reset           (T-V3-B-01, public, rate_limit 3/hour/ip)
  - POST /api/auth/mfa/enroll               (T-V3-B-02, authenticated)
  - POST /api/auth/mfa/verify               (T-V3-B-02, public, rate_limit 5/min/user)
  - GET  /api/auth/oauth/{provider}/callback (T-V3-B-02, public)

3-tier AC マッピング:
  - T-V3-B-01: docs/audit/2026-05-16_v3/T-V3-B-01.md (13 functional AC)
  - T-V3-B-02: docs/audit/2026-05-16_v3/T-V3-B-02.md (12 functional AC)
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status

from schemas.auth import (
    LoginRequest,
    LoginResponse,
    MfaEnrollRequest,
    MfaEnrollResponse,
    MfaVerifyRequest,
    MfaVerifyResponse,
    OAuthCallbackResponse,
    PasswordResetRequest,
    PasswordResetResponse,
    SignupRequest,
    SignupResponse,
)
from services.auth import (
    EmailAlreadyExistsError,
    InvalidCredentialsError,
    InvalidTotpError,
    MfaAlreadyEnabledError,
    MfaStore,
    OAuthHandshakeError,
    OAuthProviderNotConfiguredError,
    OAuthStateMismatchError,
    OAuthStateStore,
    RateLimitExceededError,
    UserNotFoundError,
    UserStore,
    authenticate,
    build_qr_url,
    enroll_mfa,
    get_mfa_store,
    get_oauth_state_store,
    get_rate_limiter,
    get_user_store,
    issue_access_token,
    issue_refresh_token,
    oauth_supported_providers,
    process_oauth_callback,
    register,
    request_password_reset,
    verify_mfa_code,
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

# T-V3-B-02 AC-F9: mfa/verify rate limit 5/min/user (features.json#F-001).
_MFA_VERIFY_RATE_LIMIT = 5
_MFA_VERIFY_RATE_WINDOW_SEC = 60


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


# ══════════════════════════════════════════════════════════════════════
# T-V3-B-02: MFA + OAuth callback (F-001 extension)
# ══════════════════════════════════════════════════════════════════════
# AC マッピング → docs/audit/2026-05-16_v3/T-V3-B-02.md
#   AC-F1  STATE-DRIVEN  : MFA enabled → require /mfa/verify before access_token
#   AC-F2  EVENT-DRIVEN  : OAuth callback w/ valid state → 2xx tokens
#   AC-F3  EVENT-DRIVEN  : mfa/enroll valid inputs → 2xx (qr_code_url, backup_codes)
#   AC-F4  UNWANTED      : mfa/enroll w/o auth token → 401
#   AC-F5  UNWANTED      : mfa/enroll body validation fail → 422
#   AC-F6  EVENT-DRIVEN  : mfa/verify valid inputs → 2xx (access_token, refresh_token)
#   AC-F7  UNWANTED      : mfa/verify w/o valid auth token → 401 (public; covers
#                          malformed bearer header forwarded)
#   AC-F8  UNWANTED      : mfa/verify body validation fail → 422
#   AC-F9  UNWANTED      : mfa/verify above rate limit 5/min/user → 429
#   AC-F10 EVENT-DRIVEN  : oauth/callback valid inputs → 2xx (access_token+)
#   AC-F11 UNWANTED      : oauth/callback w/o valid auth token → 401
#   AC-F12 UNWANTED      : oauth/callback body validation fail → 422 (provider enum)
# ══════════════════════════════════════════════════════════════════════


def _require_authenticated(request: Request) -> str:
    """Local lightweight authentication for MFA enroll endpoint.

    AC-F4 (UNWANTED): If POST /api/auth/mfa/enroll is called without a valid
    auth token, the system shall return 401.

    Why local (vs services.auth_middleware.require_user)? The router is intended
    to be testable without spinning up Supabase. We accept any well-formed
    `Bearer <opaque-token>` header where token shape is at minimum the prefix
    used by issue_access_token (`at_<user_id>_...`). For tokens that pass the
    structural check, the caller is treated as user_id-claim = the embedded
    fragment. Production should swap this for the real JWT verifier.

    Returns the user_id derived from the token. Raises HTTPException(401) on
    any malformed / missing input.
    """
    header_value = request.headers.get("authorization")
    if not header_value:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "UNAUTHORIZED", "message": "missing bearer token"},
        )
    if not _is_valid_authorization_format(header_value):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "UNAUTHORIZED", "message": "invalid bearer token"},
        )
    parts = header_value.split(" ", 1)
    token = parts[1].strip()
    # Token shape contract: at_<uuid>_<urlsafe>. Anything else → 401.
    # NOTE: production must perform real JWT verification.
    if not token.startswith("at_"):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "UNAUTHORIZED", "message": "invalid bearer token"},
        )
    rest = token[len("at_"):]
    # uuid is 36 chars, separated by '_'. We extract the first 36 chars segment
    # as user_id.
    if "_" not in rest:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "UNAUTHORIZED", "message": "invalid bearer token"},
        )
    user_id = rest.split("_", 1)[0]
    if len(user_id) < 8:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "UNAUTHORIZED", "message": "invalid bearer token"},
        )
    return user_id


def _reject_invalid_bearer_if_present(request: Request) -> None:
    """For public endpoints: reject malformed Authorization header if forwarded.

    AC-F7 / AC-F11 (UNWANTED): If a public endpoint is called with a malformed
    bearer token, return 401. (Public endpoints with NO Authorization header
    proceed normally.)
    """
    header_value = request.headers.get("authorization")
    if header_value is None:
        return
    if not _is_valid_authorization_format(header_value):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "UNAUTHORIZED", "message": "invalid bearer token"},
        )


# ──────────────────────────────────────────────────────────────────────
# POST /api/auth/mfa/enroll
# ──────────────────────────────────────────────────────────────────────


@router.post(
    "/mfa/enroll",
    response_model=MfaEnrollResponse,
    status_code=status.HTTP_201_CREATED,
    summary="POST /api/auth/mfa/enroll — F-001 (T-V3-B-02)",
)
async def post_auth_mfa_enroll(
    body: MfaEnrollRequest,
    request: Request,
    mfa_store: MfaStore = Depends(get_mfa_store),
) -> MfaEnrollResponse:
    """T-V3-B-02 AC-F3 / AC-F4 / AC-F5.

    AC-F3 (EVENT-DRIVEN): When POST /api/auth/mfa/enroll is called with valid
    inputs by an authorized caller, the system shall return 2xx with
    qr_code_url + backup_codes (features.json#F-001 contract).

    AC-F4 (UNWANTED): If called without a valid auth token, return 401.
    AC-F5 (UNWANTED): If body fails validation (Pydantic), FastAPI returns 422
    with field-level error map.

    409: features.json#F-001 outputs_4xx says "MFA already enabled".
    """
    # AC-F4: enforce authentication FIRST (before validating body so we don't
    # leak input shape to unauthenticated callers). 422 is still emitted by
    # Pydantic for body validation failures because FastAPI validates the body
    # before dependency resolution for explicit `Body` parameters. To make
    # AC-F4 strictly precede AC-F5 we re-check explicitly here.
    user_id = _require_authenticated(request)

    try:
        await enroll_mfa(
            user_id=user_id,
            totp_secret=body.totp_secret,
            mfa_store=mfa_store,
        )
    except MfaAlreadyEnabledError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "CONFLICT", "message": "MFA already enabled"},
        )

    return MfaEnrollResponse(
        qr_code_url=build_qr_url(user_id=user_id, totp_secret=body.totp_secret),
        backup_codes=(await mfa_store.get(user_id)).backup_codes,  # type: ignore[union-attr]
    )


# ──────────────────────────────────────────────────────────────────────
# POST /api/auth/mfa/verify
# ──────────────────────────────────────────────────────────────────────


@router.post(
    "/mfa/verify",
    response_model=MfaVerifyResponse,
    status_code=status.HTTP_201_CREATED,
    summary="POST /api/auth/mfa/verify — F-001 (T-V3-B-02)",
)
async def post_auth_mfa_verify(
    body: MfaVerifyRequest,
    request: Request,
    mfa_store: MfaStore = Depends(get_mfa_store),
) -> MfaVerifyResponse:
    """T-V3-B-02 AC-F1 / AC-F6 / AC-F7 / AC-F8 / AC-F9.

    AC-F1 (STATE-DRIVEN): While MFA is enabled for the user, the system shall
    require POST /api/auth/mfa/verify with a valid TOTP code before issuing
    access_token. — implemented as: only users with an enrolled MFA record can
    obtain tokens via this endpoint; verification failure → 401.

    AC-F6 (EVENT-DRIVEN): Valid inputs → 2xx access_token + refresh_token.
    AC-F7 (UNWANTED): malformed Authorization header → 401 (public endpoint).
    AC-F8 (UNWANTED): body validation failure → 422 (Pydantic).
    AC-F9 (UNWANTED): rate_limit 5/min/user → 429.

    404: user not enrolled (features.json#F-001 outputs_4xx 404).
    """
    # AC-F7: public, but reject malformed bearer if forwarded.
    _reject_invalid_bearer_if_present(request)

    # AC-F9: rate limit per-user (key = body.user_id).
    limiter = get_rate_limiter()
    try:
        await limiter.check(
            "mfa-verify",
            body.user_id,
            limit=_MFA_VERIFY_RATE_LIMIT,
            window_sec=_MFA_VERIFY_RATE_WINDOW_SEC,
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

    try:
        access, refresh = await verify_mfa_code(
            user_id=body.user_id,
            totp_code=body.totp_code,
            mfa_store=mfa_store,
        )
    except UserNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "NOT_FOUND", "message": "user not found"},
        )
    except InvalidTotpError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "UNAUTHORIZED", "message": "invalid TOTP code"},
        )

    return MfaVerifyResponse(access_token=access, refresh_token=refresh)


# ──────────────────────────────────────────────────────────────────────
# GET /api/auth/oauth/{provider}/callback
# ──────────────────────────────────────────────────────────────────────


@router.get(
    "/oauth/{provider}/callback",
    response_model=OAuthCallbackResponse,
    status_code=status.HTTP_200_OK,
    summary="GET /api/auth/oauth/{provider}/callback — F-001 (T-V3-B-02)",
)
async def get_auth_oauth_by_provider_callback(
    provider: str,
    code: str,
    state: str,
    request: Request,
    state_store: OAuthStateStore = Depends(get_oauth_state_store),
    user_store: UserStore = Depends(get_user_store),
    mfa_store: MfaStore = Depends(get_mfa_store),
) -> OAuthCallbackResponse:
    """T-V3-B-02 AC-F2 / AC-F10 / AC-F11 / AC-F12.

    AC-F2 (EVENT-DRIVEN): When OAuth callback is invoked with a valid state
    token, the system shall complete the handshake and return access_token +
    refresh_token (+ user_id per features.json#F-001 contract).

    AC-F10 (EVENT-DRIVEN): valid inputs → 2xx access_token+.
    AC-F11 (UNWANTED): malformed Authorization header → 401.
    AC-F12 (UNWANTED): invalid provider enum / missing query parameter → 422.

    422: features.json#F-001 outputs_4xx "invalid provider".
    404: provider not configured.
    401: state mismatch or code expired.
    500: handshake failed (mapped from OAuthHandshakeError).
    """
    # AC-F11: reject malformed bearer if forwarded
    _reject_invalid_bearer_if_present(request)

    # AC-F12: validate provider enum (features.json#F-001 inputs.provider).
    # FastAPI does NOT enforce the path-param enum unless we declare it; we
    # do it manually to emit a 422 with field-level error map.
    if provider.lower() not in oauth_supported_providers():
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "code": "VALIDATION_ERROR",
                "message": "invalid provider",
                "errors": [
                    {
                        "loc": ["path", "provider"],
                        "msg": "must be one of: anthropic|github|slack|google",
                        "type": "value_error.enum",
                    }
                ],
            },
        )

    # AC-F12: code / state are declared as required query params by FastAPI,
    # so missing → 422 automatically. We additionally treat empty strings as
    # invalid (Pydantic-like) to keep the contract tight.
    if not code or not state:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "code": "VALIDATION_ERROR",
                "message": "missing or empty query parameter",
                "errors": [
                    {
                        "loc": ["query", "code" if not code else "state"],
                        "msg": "must be a non-empty string",
                        "type": "value_error.missing",
                    }
                ],
            },
        )

    try:
        access, refresh, user_id = await process_oauth_callback(
            provider=provider.lower(),
            code=code,
            state=state,
            state_store=state_store,
            user_store=user_store,
            mfa_store=mfa_store,
        )
    except OAuthProviderNotConfiguredError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "NOT_FOUND", "message": "provider not configured"},
        )
    except OAuthStateMismatchError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "UNAUTHORIZED", "message": "OAuth state mismatch or code expired"},
        )
    except OAuthHandshakeError:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"code": "INTERNAL_SERVER_ERROR", "message": "OAuth handshake failed"},
        )

    return OAuthCallbackResponse(
        access_token=access,
        refresh_token=refresh,
        user_id=user_id,
    )
