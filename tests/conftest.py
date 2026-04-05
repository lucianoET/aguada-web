# tests/conftest.py
import pytest_asyncio
import aiosqlite
from backend.db import init_db

@pytest_asyncio.fixture
async def db(tmp_path):
    db_path = str(tmp_path / "test.db")
    async with aiosqlite.connect(db_path) as conn:
        await init_db(conn)
        yield conn
