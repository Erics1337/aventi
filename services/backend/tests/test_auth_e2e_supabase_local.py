from __future__ import annotations

import json
import os
import subprocess
from uuid import uuid4

import httpx
import pytest
from fastapi.testclient import TestClient


def _parse_status_json(stdout: str) -> dict[str, str]:
    start = stdout.find('{')
    end = stdout.rfind('}')
    if start == -1 or end == -1 or end <= start:
        raise ValueError('Could not parse JSON payload from `supabase status -o json` output')
    payload = json.loads(stdout[start : end + 1])
    if not isinstance(payload, dict):
        raise ValueError('Unexpected Supabase status payload')
    return {str(k): str(v) for k, v in payload.items()}


def _get_local_supabase_status() -> dict[str, str]:
    proc = subprocess.run(
        ['supabase', 'status', '-o', 'json'],
        capture_output=True,
        text=True,
        check=False,
        cwd=os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')),
    )
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip() or proc.stdout.strip() or 'supabase status failed')
    return _parse_status_json(proc.stdout)


def _signup_for_real_session(api_url: str, publishable_key: str) -> tuple[str, str]:
    email = f'jwks-e2e-{uuid4()}@example.com'
    password = 'Passw0rd!Passw0rd!'
    headers = {
        'apikey': publishable_key,
        'Authorization': f'Bearer {publishable_key}',
        'Content-Type': 'application/json',
    }
    with httpx.Client(timeout=10.0) as client:
        signup = client.post(
            f'{api_url.rstrip("/")}/auth/v1/signup',
            headers=headers,
            json={'email': email, 'password': password},
        )
        signup.raise_for_status()
        payload = signup.json()
        access_token = payload.get('access_token')
        user_id = (payload.get('user') or {}).get('id')
        if isinstance(access_token, str) and isinstance(user_id, str):
            return access_token, user_id

        login = client.post(
            f'{api_url.rstrip("/")}/auth/v1/token?grant_type=password',
            headers=headers,
            json={'email': email, 'password': password},
        )
        login.raise_for_status()
        login_payload = login.json()
        login_access_token = login_payload.get('access_token')
        login_user_id = (login_payload.get('user') or {}).get('id')
        if not isinstance(login_access_token, str) or not isinstance(login_user_id, str):
            raise RuntimeError('Could not obtain local Supabase session token from signup or password grant')
        return login_access_token, login_user_id


@pytest.mark.integration
def test_local_supabase_session_token_auth_smoke(monkeypatch: pytest.MonkeyPatch) -> None:
    try:
        status = _get_local_supabase_status()
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f'Local Supabase status unavailable: {exc}')

    required_keys = ['API_URL', 'PUBLISHABLE_KEY', 'JWT_SECRET']
    missing = [key for key in required_keys if not status.get(key)]
    if missing:
        pytest.skip(f'Local Supabase status missing keys: {missing}')

    try:
        access_token, user_id = _signup_for_real_session(status['API_URL'], status['PUBLISHABLE_KEY'])
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f'Unable to create local Supabase session token: {exc}')

    monkeypatch.setenv('AVENTI_ENV', 'test')
    monkeypatch.setenv('AVENTI_AUTH_DEV_BYPASS', 'false')
    monkeypatch.setenv('AVENTI_SUPABASE_URL', status['API_URL'])
    monkeypatch.setenv('AVENTI_SUPABASE_JWKS_URL', f"{status['API_URL'].rstrip('/')}/auth/v1/.well-known/jwks.json")
    monkeypatch.setenv('AVENTI_SUPABASE_JWT_AUDIENCE', 'authenticated')
    # Local Supabase emits HS256 access tokens and returns an empty JWKS set; use explicit local fallback secret.
    monkeypatch.setenv('AVENTI_SUPABASE_JWT_SECRET', status['JWT_SECRET'])
    monkeypatch.delenv('AVENTI_DATABASE_URL', raising=False)

    from aventi_backend.core.settings import get_settings
    import aventi_backend.core.auth as auth_module
    import aventi_backend.db.session as db_session
    from aventi_backend.app import create_app

    get_settings.cache_clear()
    auth_module._JWKS_CACHE.clear()
    db_session._engine = None
    db_session._session_factory = None

    try:
        client = TestClient(create_app())

        unauthorized = client.post('/v1/me/bootstrap')
        assert unauthorized.status_code == 401

        authorized = client.post('/v1/me/bootstrap', headers={'Authorization': f'Bearer {access_token}'})
        assert authorized.status_code == 200, authorized.text
        body = authorized.json()
        assert body['id'] == user_id
        assert body['id'] != 'dev-user'

        # Verify JWKS fetch/cache path was exercised (local Supabase returns an empty key set today).
        assert auth_module._JWKS_CACHE, 'Expected JWKS cache to be populated during auth verification'
    finally:
        get_settings.cache_clear()
        auth_module._JWKS_CACHE.clear()
