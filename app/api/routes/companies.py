from __future__ import annotations

from fastapi import APIRouter
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import SessionDep
from app.repositories import companies as companies_repo

router = APIRouter(prefix="/api/companies", tags=["companies"])


@router.get("")
async def list_companies(session: AsyncSession = SessionDep):
    companies = await companies_repo.list_active(session)
    return [
        {
            "id": c.id,
            "slug": c.slug,
            "name": c.name,
            "source": c.source.value,
            "external_id": c.external_id,
            "careers_url": c.careers_url,
            "active": c.active,
        }
        for c in companies
    ]
