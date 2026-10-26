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
"""


def database_url() -> str | None:
    """The Postgres URL, or None when the app should stay on local CSV files."""
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


def _connect():
    import psycopg

    conn = psycopg.connect(database_url(), connect_timeout=15)
    conn.execute(SCHEMA)
    conn.commit()
    return conn


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
