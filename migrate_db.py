# -*- coding: utf-8 -*-
"""Copy the whole DES Lab database from one Postgres to another.

Why: Supabase creates a project in one region. Moving the project to a region next to the lab cuts
every query from ~200 ms to ~20 ms, but Supabase cannot move a project - you create a new one and copy
the data across. This script does the copy.

Usage (PowerShell):

    $env:DESLAB_SOURCE = "postgresql://...old..."
    $env:DESLAB_TARGET = "postgresql://...new..."
    .\\.venv\\Scripts\\python.exe migrate_db.py --dry-run
    .\\.venv\\Scripts\\python.exe migrate_db.py            # real copy
    .\\.venv\\Scripts\\python.exe migrate_db.py --verify   # compare row counts afterwards

It copies ``accounts``, ``records`` and ``reset_tokens``, keeps every column as it is, and refuses to
write into a target that already holds accounts unless ``--force`` is given.
"""
from __future__ import annotations

import argparse
import os
import sys

import psycopg
from psycopg.rows import dict_row

import store

SOURCE_ENV = "DESLAB_SOURCE"
TARGET_ENV = "DESLAB_TARGET"

ACCOUNT_COLUMNS = ("username", "salt", "hash", "iterations", "created", "last_login",
                   "failed_attempts", "locked_until", "is_admin", "role", "supervisor", "expires_at")
RECORD_COLUMNS = ("username", "kind", "payload", "created_at")
TOKEN_COLUMNS = ("token_hash", "username", "created", "expires", "used")


def connect(url: str):
    return psycopg.connect(url, connect_timeout=20, autocommit=True, row_factory=dict_row)


def prepare(url: str) -> None:
    with psycopg.connect(url, connect_timeout=20) as conn:
        conn.execute(store.SCHEMA)
        conn.commit()


def counts(url: str) -> dict:
    with connect(url) as conn:
        return {
            "accounts": conn.execute("select count(*) from accounts").fetchone()["count"],
            "records": conn.execute("select count(*) from records").fetchone()["count"],
            "tokens": conn.execute("select count(*) from reset_tokens").fetchone()["count"],
        }


def fetch(url: str, table: str, columns: tuple) -> list[dict]:
    names = ", ".join(columns)
    with connect(url) as conn:
        return conn.execute(f"select {names} from {table} order by 1").fetchall()


def insert(url: str, table: str, columns: tuple, rows: list[dict]) -> int:
    if not rows:
        return 0
    from psycopg.types.json import Jsonb

    names = ", ".join(columns)
    placeholders = ", ".join(f"%({column})s" for column in columns)
    statement = f"insert into {table} ({names}) values ({placeholders}) on conflict do nothing"
    with connect(url) as conn:
        for row in rows:
            # jsonb columns need an explicit wrapper, else psycopg refuses a plain dict
            adapted = {key: (Jsonb(value) if isinstance(value, dict) else value)
                       for key, value in row.items()}
            conn.execute(statement, adapted)
    return len(rows)


def main() -> int:
    parser = argparse.ArgumentParser(description="Copy the DES Lab database to another Postgres.")
    parser.add_argument("--dry-run", action="store_true", help="only report what would be copied")
    parser.add_argument("--force", action="store_true", help="write even if the target has accounts")
    parser.add_argument("--verify", action="store_true", help="only compare row counts")
    args = parser.parse_args()

    source, target = os.environ.get(SOURCE_ENV), os.environ.get(TARGET_ENV)
    if not source or not target:
        print(f"Set {SOURCE_ENV} and {TARGET_ENV} first.")
        return 2
    if source.strip() == target.strip():
        print("Source and target are the same database - nothing to do.")
        return 2

    if args.verify:
        left, right = counts(source), counts(target)
        print(f"source: {left}")
        print(f"target: {right}")
        ok = left == right
        print("counts match" if ok else "MISMATCH - the copy is incomplete")
        return 0 if ok else 1

    left = counts(source)
    print(f"source: {left}")

    if not args.dry_run:
        prepare(target)
        existing = counts(target)
        if existing["accounts"] and not args.force:
            print(f"target already has {existing['accounts']} accounts; pass --force to overwrite anyway")
            return 1

    plan = [("accounts", ACCOUNT_COLUMNS), ("records", RECORD_COLUMNS), ("reset_tokens", TOKEN_COLUMNS)]
    for table, columns in plan:
        rows = fetch(source, table, columns)
        if args.dry_run:
            print(f"would copy {len(rows):4d} rows of {table}")
            continue
        written = insert(target, table, columns, rows)
        print(f"copied {written:4d} rows of {table}")

    if args.dry_run:
        print("\ndry run only - nothing was written")
        return 0

    right = counts(target)
    print(f"target: {right}")
    if right != left:
        print("MISMATCH after copy - check the tables above")
        return 1
    print("\nCopy complete. Update DESLAB_DATABASE_URL (or the [database] secret) to the new URL.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
