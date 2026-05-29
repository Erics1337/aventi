from unittest import IsolatedAsyncioTestCase

from fastapi import HTTPException
from starlette.requests import Request

from aventi_backend.core.auth import require_user
from aventi_backend.core.settings import Settings


def _request() -> Request:
    return Request({"type": "http", "headers": []})


class RequireUserTests(IsolatedAsyncioTestCase):
    async def test_missing_token_rejected_when_dev_bypass_disabled(self) -> None:
        settings = Settings(AVENTI_ENV="production", AVENTI_AUTH_DEV_BYPASS=False)

        with self.assertRaises(HTTPException) as raised:
            await require_user(_request(), credentials=None, settings=settings)

        self.assertEqual(raised.exception.status_code, 401)
        self.assertEqual(raised.exception.detail, "Missing bearer token")

    async def test_missing_token_uses_dev_bypass_only_in_nonprod(self) -> None:
        settings = Settings(AVENTI_ENV="development", AVENTI_AUTH_DEV_BYPASS=True)

        user = await require_user(_request(), credentials=None, settings=settings)

        self.assertEqual(user.id, "dev-user")
        self.assertEqual(user.email, "dev@aventi.local")
