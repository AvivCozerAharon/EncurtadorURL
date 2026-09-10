import pytest
from sqlalchemy.exc import IntegrityError

from db import Link, SessionLocal


async def test_short_code_unique_constraint():
    async with SessionLocal() as session:
        session.add(Link(original_url="https://a.com", short_code="abc123"))
        await session.commit()

        session.add(Link(original_url="https://b.com", short_code="abc123"))
        with pytest.raises(IntegrityError):
            await session.commit()


async def test_hits_defaults_to_zero():
    async with SessionLocal() as session:
        link = Link(original_url="https://a.com", short_code="zzz999")
        session.add(link)
        await session.commit()
        await session.refresh(link)
        assert link.hits == 0
