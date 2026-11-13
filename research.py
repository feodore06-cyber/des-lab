"""Project creation and data import as one atomic operation.

Rules enforced here, not in the UI:
  * variable names are normalised once, then de-duplicated
  * a sample-ID conflict is reported before anything is written, never auto-fixed
  * project, variables and runs are written in a single transaction
  * missing values stay missing; nothing is invented
"""

import json
import re
import time

import pandas as pd

import auth
import store

CLEAN = re.compile(r"[^a-z0-9_]+")
SAMPLE = re.compile(r"^[A-Za-z0-9._:\- ]+$")
RESERVED = {"project", "_owner", "recorded_at", "imported_at", "source_file", "source_sheet",
            "source_row", "sample_id"}


def normalise_name(raw) -> str:
    """One canonical form for every variable name: lowercase, underscore-separated."""
    text = str(raw or "").strip().lower()
    text = re.sub(r"[\s\-]+", "_", text)
    text = CLEAN.sub("_", text)
    text = re.sub(r"_+", "_", text).strip("_")
    return text


def normalise_variables(items: list) -> tuple[list, list]:
    """Return (kept, dropped). Duplicate names after normalisation are dropped, not merged."""
    kept, dropped, seen = [], [], set()
    for item in items or []:
        if isinstance(item, str):
            item = {"name": item}
        name = normalise_name(item.get("name"))
        if not name or name in RESERVED:
            dropped.append({**item, "reason": "empty or reserved name"})
            continue
        if name in seen:
            dropped.append({**item, "reason": f"duplicate of {name}"})
            continue
        seen.add(name)
        kept.append({**item, "name": name,
                     "display_name": str(item.get("display_name") or name).strip()})
    return kept, dropped


def sample_rows(frame: pd.DataFrame, mapping: dict | None = None) -> list:
    """Turn an uploaded table into plain rows plus provenance, without touching the file."""
    work = frame.rename(columns=mapping) if mapping else frame.copy()
    rows = []
    for position, record in enumerate(work.to_dict("records")):
        row = {}
        for key, value in record.items():
            name = normalise_name(key)
            if not name or name in {"project", "_owner"}:
                continue
            if value is None or (isinstance(value, float) and pd.isna(value)):
                row[name] = None
                continue
            if isinstance(value, str):
                value = value.strip()
                if value == "":
                    row[name] = None
                    continue
            row[name] = value
        rows.append({"row": position + 1, "values": row})
    return rows


def find_conflicts(rows: list, existing: set) -> dict:
    """Sample IDs that clash inside the file or with the project already on record."""
    inside, outside, missing = {}, {}, []
    seen = {}
    for entry in rows:
        sid = str(entry["values"].get("sample_id") or "").strip()
        if not sid:
            missing.append(entry["row"])
            continue
        if sid in existing:
            outside[str(entry["row"])] = sid
        if sid in seen:
            inside.setdefault(sid, [seen[sid]]).append(str(entry["row"]))
        else:
            seen[sid] = str(entry["row"])
    return {"inside_file": inside, "in_project": outside, "missing": missing}


def plan(rows: list, resolutions: dict) -> tuple[list, list]:
    """Apply the user's decisions: rename, skip or merge. Nothing is guessed."""
    ready, rejected = [], []
    for entry in rows:
        sid = str(entry["values"].get("sample_id") or "").strip()
        decision = resolutions.get(str(entry["row"])) or {}
        action = decision.get("action")
        if not sid:
            if action == "rename" and decision.get("sample_id"):
                entry = {**entry, "values": {**entry["values"],
                                             "sample_id": str(decision["sample_id"]).strip()}}
            else:
                rejected.append({**entry, "reason": "no sample_id"})
                continue
        elif action == "skip":
            rejected.append({**entry, "reason": "skipped by user"})
            continue
        elif action == "rename":
            new_id = str(decision.get("sample_id") or "").strip()
            if not new_id:
                rejected.append({**entry, "reason": "rename without a new id"})
                continue
            entry = {**entry, "values": {**entry["values"], "sample_id": new_id}}
        ready.append(entry)
    return ready, rejected


def _existing_sample_ids(owner: str, project: str) -> set:
    if not store.enabled():
        return set()
    with store._connect() as conn:
        rows = conn.execute("select sample_id from runs where owner = %s and project = %s",
                            (owner, project)).fetchall()
    return {str(row[0]) for row in rows}


def _write(owner: str, name: str, description: str, variables: list, rows: list,
           source: dict | None) -> dict:
    """One transaction: project, its variables, then its runs."""
    source = source or {}
    now = time.strftime("%Y-%m-%d %H:%M:%S")
    with store._connect() as conn:
        with conn.transaction():
            conn.execute(
                "insert into projects (owner, name, status, description) values (%s, %s, %s, %s)",
                (owner, name, "In progress", description or None))
            for position, item in enumerate(variables):
                conn.execute(
                    "insert into project_variables (owner, project, name, display_name, unit,"
                    " data_type, role, priority, definition, synonyms, method, formula, hidden,"
                    " position) values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)"
                    " on conflict (owner, project, name) do nothing",
                    (owner, name, item["name"], item.get("display_name") or item["name"],
                     item.get("unit") or "", item.get("data_type") or "", item.get("role") or "",
                     item.get("priority") or "", item.get("definition") or "",
                     json.dumps(item.get("synonyms") or []), item.get("method") or "",
                     item.get("formula") or "", bool(item.get("hidden")), position))
            written = 0
            for entry in rows:
                payload = {key: value for key, value in entry["values"].items()
                           if key != "sample_id"}
                conn.execute(
                    "insert into runs (owner, project, sample_id, recorded_at, source_file,"
                    " source_sheet, source_row, payload) values (%s,%s,%s,%s,%s,%s,%s,%s::jsonb)",
                    (owner, name, str(entry["values"]["sample_id"]).strip(),
                     entry.get("recorded_at"), source.get("file"), source.get("sheet"),
                     entry.get("row"), json.dumps(payload, ensure_ascii=False)))
                written += 1
    return {"project": name, "variables": len(variables), "imported": written,
            "finished_at": now}


def _write_local(owner: str, name: str, description: str, variables: list, rows: list) -> dict:
    """Same contract without a database, so the flow can be exercised offline."""
    auth.create_project(owner, name)
    auth.set_variable_items(owner, name, variables)
    if rows:
        frame = pd.DataFrame([entry["values"] for entry in rows])
        frame["project"] = name
        if "recorded_at" not in frame.columns:
            frame["recorded_at"] = time.strftime("%Y-%m-%d %H:%M")
        auth.save_results(owner, frame, append=True)
    return {"project": name, "variables": len(variables), "imported": len(rows),
            "finished_at": time.strftime("%Y-%m-%d %H:%M:%S")}


def create_project_with_data(owner: str, name: str, description: str, variables: list,
                             rows: list, source: dict | None = None) -> dict:
    """Create everything, or nothing. Raises ValueError before writing when a rule is broken."""
    clean_name = str(name or "").strip()
    if not clean_name:
        raise ValueError("A project needs a name.")
    if clean_name in auth.list_projects(owner):
        raise ValueError("A project with this name already exists.")

    kept, _dropped = normalise_variables(variables)
    if not kept:
        raise ValueError("A project needs at least one variable.")

    ids = [str(entry["values"].get("sample_id") or "").strip() for entry in rows]
    if any(not value for value in ids):
        raise ValueError("Every imported row needs a sample_id before saving.")
    if len(ids) != len(set(ids)):
        raise ValueError("The file contains duplicate sample IDs; resolve them before saving.")
    clash = set(ids) & _existing_sample_ids(owner, clean_name)
    if clash:
        raise ValueError("These sample IDs already exist in the project: "
                         + ", ".join(sorted(clash)))

    if store.enabled():
        return _write(owner, clean_name, description, kept, rows, source)
    return _write_local(owner, clean_name, description, kept, rows)
