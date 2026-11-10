"""An append-only record of what changed, so a number can never change without a trace."""

import json
import time

SKIP = {"recorded_at"}


def diff(before: dict, after: dict) -> dict:
    """Which fields changed between two versions of the same thing."""
    changes = {}
    keys = set(before or {}) | set(after or {})
    for key in sorted(keys):
        if key in SKIP:
            continue
        old, new = (before or {}).get(key), (after or {}).get(key)
        if _same(old, new):
            continue
        changes[key] = {"before": old, "after": new}
    return changes


def entry(user: str, kind: str, target: str, changes: dict, note: str = "") -> dict:
    """One log line. ``kind`` is what was touched: record, variable, paper."""
    return {"at": time.strftime("%Y-%m-%d %H:%M:%S"), "user": str(user or ""),
            "kind": str(kind), "target": str(target), "changes": changes,
            "note": str(note or "")}


def describe(item: dict) -> str:
    """A single line a person can read without opening the JSON."""
    changes = item.get("changes") or {}
    if not changes:
        return f"{item.get('at')} · {item.get('user')} · {item.get('kind')} {item.get('target')}"
    parts = []
    for key, change in list(changes.items())[:3]:
        parts.append(f"{key}: {_show(change['before'])} -> {_show(change['after'])}")
    more = "" if len(changes) <= 3 else f" (+{len(changes) - 3} more)"
    return (f"{item.get('at')} · {item.get('user')} · {item.get('kind')} {item.get('target')} · "
            + "; ".join(parts) + more)


def load(raw) -> list:
    if isinstance(raw, list):
        return raw
    try:
        parsed = json.loads(raw or "[]")
    except (TypeError, ValueError):
        return []
    return parsed if isinstance(parsed, list) else []


def _show(value) -> str:
    if value is None or value == "":
        return "—"
    return str(value)


def _same(left, right) -> bool:
    if left is None and right is None:
        return True
    try:
        return abs(float(left) - float(right)) < 1e-12
    except (TypeError, ValueError):
        return str(left) == str(right)
