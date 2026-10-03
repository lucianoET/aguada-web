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


TEST_USER = {"id": 1, "username": "teste", "name": "Teste", "role": "admin"}


@pytest_asyncio.fixture(autouse=True)
async def logged_in(request):
    """Rotas de escrita exigem sessão; os testes entram como admin. Marque `no_login` para testar o login de verdade."""
    import backend.main as m
    if request.node.get_closest_marker("no_login"):
        yield
        return
    for dep in (m.require_operador, m.require_supervisor, m.require_admin):
        m.app.dependency_overrides[dep] = lambda: TEST_USER
    yield
    m.app.dependency_overrides.clear()
