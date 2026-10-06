from unittest.mock import AsyncMock, MagicMock

from aventi_backend.services.verification import VerificationService


async def test_inconclusive_verification_does_not_refresh_event_evidence():
    session = AsyncMock()
    result = MagicMock()
    result.mappings.return_value.first.return_value = {
        "id": "event",
        "booking_url": "https://example.com/event",
        "hidden": False,
        "verification_status": "verified",
        "verification_fail_count": 0,
        "last_verified_at": None,
        "last_verified_active": True,
    }
    session.execute.return_value = result
    verifier = AsyncMock()
    verifier.verify_booking_url.return_value = None
    response = await VerificationService(session, verifier=verifier).verify_event("event")
    assert response["skipped"] is True
    statements = [str(call.args[0]).lower() for call in session.execute.call_args_list]
    assert any("insert into public.verification_runs" in statement for statement in statements)
    assert not any("update public.events" in statement for statement in statements)
