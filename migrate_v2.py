"""Phase 3 migration: project_variables + runs, copied from records without touching records.

Safe by construction:
  * dry-run by default; nothing is written without --apply
  * the original `records` table is only ever SELECTed
  * the copy is idempotent: runs.legacy_record_id is unique, so re-running inserts nothing new
  * --rollback deletes only the rows this script created (legacy_record_id is not null)
  * a JSON backup of the source rows is written before anything is applied
"""

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parent
SCHEMA = """
alter table projects add column if not exists description text;

create table if not exists project_variables (
    owner text not null,
    project text not null,
    name text not null,
    display_name text,
    unit text,
    data_type text,
    role text,
    priority text,
    definition text,
    synonyms jsonb default '[]'::jsonb,
    method text,
    formula text,
    hidden boolean default false,
    position int default 0,
    removed_at timestamptz,
    created timestamptz default now(),
    primary key (owner, project, name)
);

create table if not exists runs (
    id bigserial primary key,
    owner text not null,
    project text not null,
    sample_id text not null,
    recorded_at timestamptz,
    imported_at timestamptz default now(),
    source_file text,
    source_sheet text,
    source_row int,
    legacy_record_id bigint,
    payload jsonb not null default '{}'::jsonb,
    created timestamptz default now()
);

create unique index if not exists runs_legacy_idx on runs (legacy_record_id);
create index if not exists runs_project_idx on runs (owner, project);
"""

DUPLICATE_CHECK = """
select owner, project, sample_id, count(*) as n
from (
  select username as owner,
         coalesce(payload->>'project', 'General') as project,
         coalesce(nullif(payload->>'sample_id', ''), '') as sample_id
  from records where kind = 'results'
) t
group by owner, project, sample_id having count(*) > 1
"""

COPY = """
insert into runs (owner, project, sample_id, recorded_at, payload, legacy_record_id)
select username,
       coalesce(payload->>'project', 'General'),
       coalesce(nullif(payload->>'sample_id', ''), 'EXP-UNKNOWN-' || id::text),
       nullif(payload->>'recorded_at', '')::timestamptz,
       payload - 'project' - 'sample_id' - '_owner' - 'recorded_at',
       id
from records
where kind = 'results'
on conflict (legacy_record_id) do nothing
"""


def connect():
    url = os.environ.get("DESLAB_DATABASE_URL", "")
    if not url:
        secrets = ROOT / ".streamlit" / "secrets.toml"
        if secrets.exists():
            text = secrets.read_text(encoding="utf-8")
            for line in text.splitlines():
                if line.strip().startswith("url") and "postgres" in line:
                    url = line.split("=", 1)[1].strip().strip('"').strip("'")
                    break
    if not url:
        raise SystemExit("no database URL (set DESLAB_DATABASE_URL)")
    import psycopg

    return psycopg.connect(url, autocommit=False)


def counts(conn):
    with conn.cursor() as cur:
        cur.execute("select count(*) from records where kind = 'results'")
        source = cur.fetchone()[0]
        cur.execute("select to_regclass('public.runs') is not null")
        exists = cur.fetchone()[0]
        migrated = total = None
        if exists:
            cur.execute("select count(*) from runs where legacy_record_id is not null")
            migrated = cur.fetchone()[0]
            cur.execute("select count(*) from runs")
            total = cur.fetchone()[0]
    return {"records": source, "migrated": migrated, "runs_total": total}


def backup(conn) -> Path:
    with conn.cursor() as cur:
        cur.execute("select id, username, payload from records where kind = 'results' order by id")
        rows = [{"id": row[0], "owner": row[1], "payload": row[2]} for row in cur.fetchall()]
    folder = ROOT / "backups"
    folder.mkdir(exist_ok=True)
    path = folder / f"records-{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}.json"
    path.write_text(json.dumps(rows, ensure_ascii=False, default=str), encoding="utf-8")
    return path


def duplicates(conn):
    with conn.cursor() as cur:
        cur.execute("select to_regclass('public.records') is not null")
        if not cur.fetchone()[0]:
            return []
        cur.execute(DUPLICATE_CHECK)
        return cur.fetchall()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true", help="actually write")
    parser.add_argument("--rollback", action="store_true", help="delete only migrated rows")
    args = parser.parse_args()

    conn = connect()
    try:
        before = counts(conn)
        print("before:", before)

        if args.rollback:
            if not args.apply:
                print("rollback is a write; add --apply to do it")
                return
            with conn.cursor() as cur:
                cur.execute("delete from runs where legacy_record_id is not null")
                deleted = cur.rowcount
            conn.commit()
            print("rolled back:", deleted, "migrated rows; records untouched")
            return

        found = duplicates(conn)
        if found:
            print("duplicate (owner, project, sample_id) in the source, migrate after resolving:")
            for row in found[:10]:
                print("  ", row)
        else:
            print("no duplicate sample IDs in the source")

        if not args.apply:
            print("dry run only: schema, backup and copy were not executed")
            print("plan: create project_variables + runs, write a backup, copy records -> runs,")
            print("      then create the unique (owner, project, sample_id) index once clean")
            return

        path = backup(conn)
        print("backup written:", path)

        with conn.cursor() as cur:
            cur.execute(SCHEMA)
        conn.commit()
        print("schema applied")

        with conn.cursor() as cur:
            cur.execute(COPY)
            copied = cur.rowcount
        conn.commit()
        print("copied rows:", copied)

        if not duplicates(conn):
            with conn.cursor() as cur:
                cur.execute("create unique index if not exists runs_sample_idx "
                            "on runs (owner, project, sample_id)")
            conn.commit()
            print("unique (owner, project, sample_id) enforced")
        else:
            print("sample-id uniqueness NOT enforced yet: duplicates remain")

        after = counts(conn)
        print("after:", after)
        print("verify:", "OK" if after["records"] == before["records"] else "records changed!")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
