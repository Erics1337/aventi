import pytest
from fastapi import HTTPException

from aventi_backend.core.auth import (
    _claims_include_admin,
    _decode_and_verify_supabase_token,
    _resolve_claim_role,
)
from aventi_backend.core.settings import Settings


@pytest.mark.parametrize("metadata", [{"role": "admin"}, {"roles": ["owner"]}, {"is_admin": True}])
def test_user_metadata_cannot_grant_admin(metadata):
    claims = {"role": "admin", "user_metadata": metadata}
    assert not _claims_include_admin(claims)
    assert _resolve_claim_role(claims) == "authenticated"


@pytest.mark.parametrize("metadata", [{"role": "admin"}, {"roles": ["owner"]}, {"is_admin": True}])
def test_server_metadata_can_grant_admin(metadata):
    assert _claims_include_admin({"app_metadata": metadata})


def test_production_rejects_insecure_configuration():
    with pytest.raises(ValueError):
        Settings(_env_file=None, AVENTI_ENV="prod", AVENTI_AUTH_DEV_BYPASS=True)


def test_environment_aliases():
    assert Settings(_env_file=None, AVENTI_ENV="dev").env == "development"


async def test_expired_signed_token_rejected(monkeypatch):
    from jose import jwt

    import aventi_backend.core.auth as auth

    async def keys(*args, **kwargs):
        return {}

    monkeypatch.setattr(auth, "_get_jwks_keys", keys)
    settings = Settings(
        _env_file=None,
        AVENTI_SUPABASE_JWT_SECRET="unit-test-only",
        AVENTI_SUPABASE_URL="https://example.supabase.co",
    )
    token = jwt.encode(
        {
            "sub": "user",
            "exp": 1,
            "aud": "authenticated",
            "iss": "https://example.supabase.co/auth/v1",
        },
        "unit-test-only",
        algorithm="HS256",
    )
    with pytest.raises(HTTPException) as result:
        await _decode_and_verify_supabase_token(token, settings)
    assert result.value.status_code == 401


@pytest.mark.parametrize("metadata", [{"role": True}, {"roles": True}, {"roles": "admin"}])
def test_admin_metadata_types_match_web_rules(metadata):
    assert not _claims_include_admin({"app_metadata": metadata})
