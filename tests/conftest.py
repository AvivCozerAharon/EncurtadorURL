import os
import tempfile

_tmp_dir = tempfile.mkdtemp()
os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{os.path.join(_tmp_dir, 'test.db')}"

import pytest_asyncio  # noqa: E402

from db import Base, engine  # noqa: E402


@pytest_asyncio.fixture(autouse=True)
async def _reset_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield
