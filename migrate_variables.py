"""Copy projects.variables (JSON) into the project_variables table. Idempotent, non-destructive."""

import argparse
import json
import os
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
ROOT = Path(__file__).resolve().parent


def connect():
    url = os.environ.get("DESLAB_DATABASE_URL", "")
    if not url:
        secrets = ROOT / ".streamlit" / "secrets.toml"
        if secrets.exists():
            for line in secrets.read_text(encoding="utf-8").splitlines():
                if line.strip().startswith("url") and "postgres" in line:
                    url = line.split("=", 1)[1].strip().strip('"').strip("'")
                    break
    if not url:
        raise SystemExit("no database URL")
    import psycopg

    return psycopg.connect(url, autocommit=False)


def parse(raw):
    """The stored value may be a bare list or a dict with 'items'."""
    if raw is None:
        return []
    if isinstance(raw, dict):
        return list(raw.get("items") or [])
    try:
        parsed = json.loads(raw)
    except (TypeError, ValueError):
        return []
    if isinstance(parsed, dict):
        return list(parsed.get("items") or [])
    return [{"name": str(value)} for value in parsed or []]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    conn = connect()
    try:
        with conn.cursor() as cur:
            cur.execute("select to_regclass('public.project_variables') is not null")
            if not cur.fetchone()[0]:
                raise SystemExit("run migrate_v2.py --apply first (project_variables is missing)")
            cur.execute("select owner, name, variables from projects order by owner, name")
            projects = cur.fetchall()
            cur.execute("select count(*) from project_variables")
            before = cur.fetchone()[0]

        print("projects:", len(projects), "| project_variables rows before:", before)
        planned = 0
        for owner, name, raw in projects:
            items = parse(raw)
            planned += len([item for item in items if item.get("name")])
        print("variable rows that the JSON would contribute:", planned)

        if not args.apply:
            print("dry run only; add --apply to copy")
            return

        copied = 0
        with conn.cursor() as cur:
            for owner, name, raw in projects:
                for position, item in enumerate(parse(raw)):
                    if not item.get("name"):
                        continue
                    cur.execute(
                        "insert into project_variables (owner, project, name, display_name, unit,"
                        " data_type, role, priority, definition, synonyms, method, formula,"
                        " hidden, position) values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)"
                        " on conflict (owner, project, name) do nothing",
                        (owner, name, str(item["name"]),
                         item.get("display_name") or str(item["name"]),
                         item.get("unit") or "", item.get("dtype") or "",
                         item.get("role") or "", item.get("priority") or "",
                         item.get("definition") or "",
                         json.dumps(item.get("synonyms") or []),
                         item.get("method") or "", item.get("formula") or "",
                         bool(item.get("hidden")), position))
                    copied += cur.rowcount
        conn.commit()
        with conn.cursor() as cur:
            cur.execute("select count(*) from project_variables")
            after = cur.fetchone()[0]
        print("inserted:", copied, "| rows after:", after)
        print("second run inserts nothing (on conflict do nothing)")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
