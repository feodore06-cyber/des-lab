# -*- coding: utf-8 -*-
"""Record storage: Postgres when it is configured, local CSV otherwise.

One table holds everything, so the schema never has to change when a new kind of record appears:

    records(id, username, kind, payload jsonb, created_at)

``kind`` is ``results`` (experiment rows), ``recipe`` (a saved weighing list) or ``feedback``.
``payload`` is one JSON object per row, which keeps the uploaded CSV columns exactly as they were.

The connection string comes from ``DESLAB_DATABASE_URL`` or ``[database] url`` in
``.streamlit/secrets.toml``. With neither, every function here stays out of the way and the app keeps
using the CSV files in ``user_data/``.
"""
from __future__ import annotations

import json
import math
import os
from typing import Any, Iterable

import pandas as pd

URL_ENV = "DESLAB_DATABASE_URL"
SCHEMA = """
create table if not exists records (
    id bigserial primary key,
    username text not null,
    kind text not null,
    payload jsonb not null,
    created_at timestamptz not null default now()
);
create index if not exists records_lookup on records (username, kind, id);
create table if not exists accounts (
    username text primary key,
    salt text not null,
    hash text not null,
    iterations integer not null,
    created timestamptz not null default now(),
    last_login timestamptz
);
alter table accounts add column if not exists failed_attempts integer not null default 0;
alter table accounts add column if not exists locked_until timestamptz;
alter table accounts add column if not exists is_admin boolean not null default false;
alter table accounts add column if not exists role text not null default 'intern';
alter table accounts add column if not exists supervisor text;
alter table accounts add column if not exists expires_at timestamptz;
create table if not exists reset_tokens (
    token_hash text primary key,
    username text not null,
    created timestamptz not null default now(),
    expires timestamptz not null,
    used boolean not null default false
);
create index if not exists reset_tokens_user on reset_tokens (username);
"""


def database_url() -> str | None:
    """The Postgres URL, or None when the app should stay on local CSV files."""
    if os.environ.get("DESLAB_STORAGE", "").strip().lower() == "file":
        return None  # explicit override: keep using local CSV files
    url = os.environ.get(URL_ENV)
    if url:
        return url.strip()
    try:
        import streamlit as st

        for section in ("database", "supabase", "postgres"):
            try:
                block = st.secrets[section]
            except Exception:
                continue
            if not block:
                continue
            value = block.get("url") or block.get("DATABASE_URL") or block.get("connection_string")
            if value:
                return str(value).strip()
    except Exception:
        pass
    return None


def enabled() -> bool:
    return bool(database_url())


def _clean(value: Any) -> Any:
    """Make a value JSON-safe: NaN/inf become null, numpy scalars become plain Python."""
    if value is None:
        return None
    if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
        return None
    if hasattr(value, "item") and callable(value.item):  # numpy scalar
        try:
            value = value.item()
        except Exception:
            return str(value)
        if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
            return None
        return value
    if isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, (pd.Timestamp,)):
        return value.isoformat()
    return str(value)


def clean_row(row: dict) -> dict:
    return {str(key): _clean(value) for key, value in row.items()}


def _rows(frame: pd.DataFrame) -> list[dict]:
    # NaN -> None first, otherwise json cannot represent the payload
    return [clean_row(record) for record in frame.astype(object).where(pd.notna(frame), None).to_dict("records")]


_POOL = None
_POOL_URL = None


def close_pool() -> None:
    """Drop the shared pool (used by tests and when the URL changes)."""
    global _POOL, _POOL_URL
    if _POOL is not None:
        try:
            _POOL.close()
        except Exception:
            pass
    _POOL, _POOL_URL = None, None


def _pool(url: str):
    """One process-wide pool: opening a connection costs ~2.5 s, a query ~0.2 s, so reusing wins."""
    global _POOL, _POOL_URL
    if _POOL is not None and _POOL_URL == url:
        return _POOL
    from psycopg_pool import ConnectionPool

    pool = ConnectionPool(conninfo=url, min_size=1, max_size=4, timeout=15,
                          kwargs={"connect_timeout": 15}, open=True)
    with pool.connection() as conn:  # make sure the schema exists, once per process
        conn.execute(SCHEMA)
        conn.commit()
    _POOL, _POOL_URL = pool, url
    return pool


def _connect():
    """A connection borrowed from the pool; the caller's ``with`` returns it."""
    return _pool(database_url()).connection()


def ping() -> str:
    """Round-trip check used by the setup screen."""
    with _connect() as conn:
        row = conn.execute("select count(*), now() from records").fetchone()
    return f"connected · {row[0]} rows · server time {row[1]:%Y-%m-%d %H:%M}"


def append(username: str, kind: str, frame: pd.DataFrame) -> int:
    rows = _rows(frame)
    if not rows:
        return 0
    with _connect() as conn:
        with conn.cursor() as cur:
            cur.executemany(
                "insert into records (username, kind, payload) values (%s, %s, %s::jsonb)",
                [(username, kind, json.dumps(row, ensure_ascii=False)) for row in rows],
            )
        conn.commit()
    return len(rows)


def append_row(username: str, kind: str, row: dict) -> None:
    with _connect() as conn:
        conn.execute(
            "insert into records (username, kind, payload) values (%s, %s, %s::jsonb)",
            (username, kind, json.dumps(clean_row(row), ensure_ascii=False)),
        )
        conn.commit()


def replace(username: str, kind: str, frame: pd.DataFrame) -> int:
    with _connect() as conn:
        conn.execute("delete from records where username = %s and kind = %s", (username, kind))
        conn.commit()
        return append(username, kind, frame)


def load(username: str, kind: str) -> pd.DataFrame:
    with _connect() as conn:
        rows = conn.execute(
            "select payload from records where username = %s and kind = %s order by id",
            (username, kind),
        ).fetchall()
    if not rows:
        return pd.DataFrame()
    return pd.DataFrame([row[0] for row in rows])


def load_all(kind: str, limit: int = 5000) -> pd.DataFrame:
    with _connect() as conn:
        rows = conn.execute(
            "select payload from records where kind = %s order by id desc limit %s", (kind, limit)
        ).fetchall()
    if not rows:
        return pd.DataFrame()
    frame = pd.DataFrame([row[0] for row in rows])
    return frame.iloc[::-1].reset_index(drop=True)


def count(username: str | None = None, kind: str | None = None) -> int:
    query = "select count(*) from records where true"
    params: list[Any] = []
    if username:
        query += " and username = %s"
        params.append(username)
    if kind:
        query += " and kind = %s"
        params.append(kind)
    with _connect() as conn:
        return int(conn.execute(query, params).fetchone()[0])


def add_columns(username: str, kind: str, columns: Iterable[str]) -> None:
    """Postgres needs no schema change for new columns: they live inside the jsonb payload."""
    return None


# ------------------------------------------------------------------ accounts
def accounts_all() -> dict:
    """Every account as ``{username: entry}``; ``entry`` keeps the same shape the JSON store uses."""
    with _connect() as conn:
        rows = conn.execute(
            "select username, salt, hash, iterations, created, last_login from accounts order by created"
        ).fetchall()
    accounts = {}
    for username, salt, digest, iterations, created, last_login in rows:
        accounts[username] = {
            "salt": salt,
            "hash": digest,
            "iterations": iterations,
            "created": created.strftime("%Y-%m-%d %H:%M:%S") if created else "",
            "last_login": last_login.strftime("%Y-%m-%d %H:%M:%S") if last_login else "",
        }
    return accounts


def account_upsert(username: str, entry: dict) -> None:
    with _connect() as conn:
        conn.execute(
            """
            insert into accounts (username, salt, hash, iterations)
            values (%s, %s, %s, %s)
            on conflict (username) do update
              set salt = excluded.salt, hash = excluded.hash, iterations = excluded.iterations
            """,
            (username, entry["salt"], entry["hash"], int(entry.get("iterations", 200_000))),
        )
        conn.commit()


def account_delete(username: str) -> None:
    with _connect() as conn:
        conn.execute("delete from accounts where username = %s", (username,))
        conn.commit()


def account_touch_login(username: str) -> None:
    with _connect() as conn:
        conn.execute(
            "update accounts set last_login = now(), failed_attempts = 0, locked_until = null"
            " where username = %s",
            (username,),
        )
        conn.commit()


def account_lock_state(username: str) -> dict:
    """How many failures so far and until when the account is locked."""
    with _connect() as conn:
        row = conn.execute(
            "select failed_attempts, locked_until from accounts where username = %s", (username,)
        ).fetchone()
    if not row:
        return {"failed": 0, "locked_until": None}
    locked = row[1]
    if locked is not None and locked.tzinfo is None:
        from datetime import timezone

        locked = locked.replace(tzinfo=timezone.utc)
    return {"failed": int(row[0] or 0), "locked_until": locked}


def account_login_failed(username: str, failed: int, locked_until) -> None:
    with _connect() as conn:
        conn.execute(
            "update accounts set failed_attempts = %s, locked_until = %s where username = %s",
            (int(failed), locked_until, username),
        )
        conn.commit()


def team_of(supervisor: str) -> list[str]:
    """Accounts that belong to one supervisor (never anyone else's)."""
    with _connect() as conn:
        rows = conn.execute("select username from accounts where supervisor = %s", (supervisor,)).fetchall()
    return [row[0] for row in rows]


def account_profile(username: str) -> dict:
    with _connect() as conn:
        row = conn.execute(
            "select role, supervisor, expires_at, is_admin from accounts where username = %s", (username,)
        ).fetchone()
    if not row:
        return {"role": "intern", "supervisor": None, "expires_at": None, "is_admin": False}
    expires = row[2]
    if expires is not None and expires.tzinfo is None:
        from datetime import timezone

        expires = expires.replace(tzinfo=timezone.utc)
    return {"role": row[0] or "intern", "supervisor": row[1], "expires_at": expires,
            "is_admin": bool(row[3])}


def account_set_team(username: str, role: str, supervisor: str | None, expires_at) -> None:
    with _connect() as conn:
        conn.execute(
            "update accounts set role = %s, supervisor = %s, expires_at = %s where username = %s",
            (role, supervisor, expires_at, username),
        )
        conn.commit()


def load_many(usernames: list[str], kind: str) -> pd.DataFrame:
    """Rows for several accounts at once, newest last, with the owner recorded per row."""
    if not usernames:
        return pd.DataFrame()
    with _connect() as conn:
        rows = conn.execute(
            "select username, payload from records where kind = %s and username = any(%s) order by id",
            (kind, list(usernames)),
        ).fetchall()
    if not rows:
        return pd.DataFrame()
    frame = pd.DataFrame([{**payload, "_owner": owner} for owner, payload in rows])
    return frame


def accounts_rows() -> list[dict]:
    """Rows for the team table, newest first."""
    with _connect() as conn:
        rows = conn.execute(
            "select username, created, last_login, is_admin, role, supervisor, expires_at"
            " from accounts order by created desc"
        ).fetchall()
    return [
        {
            "username": name,
            "created": created.strftime("%Y-%m-%d") if created else "",
            "last_login": last_login.strftime("%Y-%m-%d %H:%M") if last_login else "never",
            "is_admin": bool(is_admin),
            "role": role or "intern",
            "supervisor": supervisor or "",
            "expires": expires.strftime("%Y-%m-%d") if expires else "",
        }
        for name, created, last_login, is_admin, role, supervisor, expires in rows
    ]


def account_admin_names() -> set:
    with _connect() as conn:
        rows = conn.execute("select username from accounts where is_admin").fetchall()
    return {row[0] for row in rows}


def account_set_admin(username: str, flag: bool) -> None:
    with _connect() as conn:
        conn.execute("update accounts set is_admin = %s where username = %s", (bool(flag), username))
        conn.commit()


# ------------------------------------------------------------- password resets
def token_create(username: str, token_hash: str, expires) -> None:
    """Store one pending link; older unused links for the same account are dropped."""
    with _connect() as conn:
        conn.execute("delete from reset_tokens where username = %s and used = false", (username,))
        conn.execute(
            "insert into reset_tokens (token_hash, username, expires) values (%s, %s, %s)",
            (token_hash, username, expires),
        )
        conn.commit()


def token_lookup(token_hash: str) -> dict | None:
    with _connect() as conn:
        row = conn.execute(
            "select username, expires, used from reset_tokens where token_hash = %s", (token_hash,)
        ).fetchone()
    if not row:
        return None
    return {"username": row[0], "expires": row[1], "used": row[2]}


def token_use(token_hash: str) -> None:
    with _connect() as conn:
        conn.execute("update reset_tokens set used = true where token_hash = %s", (token_hash,))
        conn.commit()


def tokens_pending() -> list[dict]:
    with _connect() as conn:
        rows = conn.execute(
            "select username, created, expires from reset_tokens where used = false order by created desc"
        ).fetchall()
    return [
        {
            "username": name,
            "created": created.strftime("%Y-%m-%d %H:%M") if created else "",
            "expires": expires.strftime("%Y-%m-%d %H:%M") if expires else "",
        }
        for name, created, expires in rows
    ]

