from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from aventi_backend.db.repository import AventiRepository, build_repository
from aventi_backend.db.session import get_optional_db_session


async def get_repository(
    session: AsyncSession | None = Depends(get_optional_db_session),
) -> AventiRepository:
    return build_repository(session)
