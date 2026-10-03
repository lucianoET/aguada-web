# backend/auth.py
"""Usuários, papéis e sessões (Normas_Tecnicas.md §12.4).

Senha com scrypt (stdlib), sessão = token aleatório em cookie HttpOnly; no banco só o
sha256 do token, então vazar o banco não entrega sessões. Logout apaga a sessão.
"""
from __future__ import annotations

import hashlib
import hmac
import os
import secrets
import time

import aiosqlite

ROLES = ("operador", "supervisor", "admin")
COOKIE = "aguada_sess"
SESSION_S = 12 * 3600       # um turno
MAX_FAILS = 5               # tentativas erradas por usuário ...
FAIL_WINDOW_S = 600         # ... em 10 min antes de bloquear

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    username   TEXT    NOT NULL UNIQUE COLLATE NOCASE,
    name       TEXT    NOT NULL,
    role       TEXT    NOT NULL CHECK (role IN ('operador', 'supervisor', 'admin')),
    pw_hash    TEXT    NOT NULL,
    active     INTEGER NOT NULL DEFAULT 1,
    created_ts INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS sessions (
    token_hash TEXT    PRIMARY KEY,
    user_id    INTEGER NOT NULL REFERENCES users(id),
    created_ts INTEGER NOT NULL,
    expires_ts INTEGER NOT NULL
);
"""

_fails: dict[str, list[float]] = {}


def hash_password(password: str) -> str:
    salt = os.urandom(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, n=2 ** 14, r=8, p=1)
    return f"scrypt${salt.hex()}${digest.hex()}"


def check_password(password: str, stored: str) -> bool:
    try:
        _, salt, digest = stored.split("$")
    except ValueError:
        return False
    test = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), n=2 ** 14, r=8, p=1)
    return hmac.compare_digest(test.hex(), digest)


def validate_password(password: str) -> str | None:
    if len(password) < 8:
        return "A senha precisa de pelo menos 8 caracteres"
    return None


def locked(username: str, now: float | None = None) -> bool:
    now = now or time.time()
    recent = [t for t in _fails.get(username.lower(), []) if now - t < FAIL_WINDOW_S]
    _fails[username.lower()] = recent
    return len(recent) >= MAX_FAILS


def register_fail(username: str) -> None:
    _fails.setdefault(username.lower(), []).append(time.time())


def clear_fails(username: str) -> None:
    _fails.pop(username.lower(), None)


def role_at_least(role: str, minimum: str) -> bool:
    return ROLES.index(role) >= ROLES.index(minimum)


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


async def count_users(conn: aiosqlite.Connection) -> int:
    async with conn.execute("SELECT COUNT(*) FROM users") as cur:
        return (await cur.fetchone())[0]


async def create_user(conn: aiosqlite.Connection, username: str, name: str, role: str, password: str) -> dict:
    cur = await conn.execute(
        "INSERT INTO users (username, name, role, pw_hash, created_ts) VALUES (?, ?, ?, ?, ?)",
        (username.strip(), name.strip(), role, hash_password(password), int(time.time())),
    )
    await conn.commit()
    return {"id": cur.lastrowid, "username": username.strip(), "name": name.strip(), "role": role, "active": 1}


async def get_user_by_username(conn: aiosqlite.Connection, username: str) -> dict | None:
    conn.row_factory = aiosqlite.Row
    async with conn.execute("SELECT * FROM users WHERE username = ?", (username.strip(),)) as cur:
        row = await cur.fetchone()
    return dict(row) if row else None


async def list_users(conn: aiosqlite.Connection) -> list[dict]:
    conn.row_factory = aiosqlite.Row
    async with conn.execute("SELECT id, username, name, role, active, created_ts FROM users ORDER BY name") as cur:
        return [dict(r) for r in await cur.fetchall()]


async def update_user(conn: aiosqlite.Connection, user_id: int, fields: dict) -> bool:
    sets, args = [], []
    for k in ("name", "role", "active"):
        if k in fields and fields[k] is not None:
            sets.append(f"{k} = ?")
            args.append(fields[k])
    if fields.get("password"):
        sets.append("pw_hash = ?")
        args.append(hash_password(fields["password"]))
    if not sets:
        return False
    cur = await conn.execute(f"UPDATE users SET {', '.join(sets)} WHERE id = ?", (*args, user_id))
    if fields.get("password") or fields.get("active") == 0:
        await conn.execute("DELETE FROM sessions WHERE user_id = ?", (user_id,))  # derruba sessões abertas
    await conn.commit()
    return cur.rowcount > 0


async def create_session(conn: aiosqlite.Connection, user_id: int) -> str:
    token = secrets.token_urlsafe(32)
    now = int(time.time())
    await conn.execute("DELETE FROM sessions WHERE expires_ts < ?", (now,))
    await conn.execute("INSERT INTO sessions (token_hash, user_id, created_ts, expires_ts) VALUES (?, ?, ?, ?)",
                       (_token_hash(token), user_id, now, now + SESSION_S))
    await conn.commit()
    return token


async def session_user(conn: aiosqlite.Connection, token: str | None) -> dict | None:
    if not token:
        return None
    conn.row_factory = aiosqlite.Row
    async with conn.execute(
        """SELECT u.id, u.username, u.name, u.role FROM sessions s JOIN users u ON u.id = s.user_id
           WHERE s.token_hash = ? AND s.expires_ts > ? AND u.active = 1""",
        (_token_hash(token), int(time.time())),
    ) as cur:
        row = await cur.fetchone()
    return dict(row) if row else None


async def delete_session(conn: aiosqlite.Connection, token: str | None) -> None:
    if token:
        await conn.execute("DELETE FROM sessions WHERE token_hash = ?", (_token_hash(token),))
        await conn.commit()
