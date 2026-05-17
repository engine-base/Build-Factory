"""Pytest test-environment bootstrap.

`services/supabase_client.py` validates SUPABASE_URL / SUPABASE_ANON_KEY /
SUPABASE_SERVICE_KEY / SUPABASE_JWT_SECRET at import time and raises
RuntimeError when unset. That fail-fast guard is correct for production but
breaks any test that triggers the import chain (routers/accounts.py →
services/auth_middleware.py → services/supabase_client.py).

We set inert dummy values via `os.environ.setdefault` so they never override
real values when a developer exports them locally or CI provides secrets.
"""
from __future__ import annotations

import os

_TEST_DEFAULTS = {
    "SUPABASE_URL": "http://127.0.0.1:54321",
    "SUPABASE_ANON_KEY": "test-anon-key",
    "SUPABASE_SERVICE_KEY": "test-service-key",
    "SUPABASE_JWT_SECRET": "test-jwt-secret-32chars-minimum-padding",
    "DISABLE_BACKGROUND_WORKERS": "1",
}

for _k, _v in _TEST_DEFAULTS.items():
    os.environ.setdefault(_k, _v)
