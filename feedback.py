# -*- coding: utf-8 -*-
"""Feedback capture and the admin inbox.

Feedback is appended to ``user_data/feedback/feedback.csv``: one row per report, with the time, the
signed-in user, a category, the message and the page it came from. Because it lives under
``user_data/`` it is git-ignored and never reaches GitHub.

On a hosted deployment the container filesystem is temporary, so feedback collected there disappears
on a restart - see DEPLOY.md for the database-backed upgrade path.
"""
from __future__ import annotations

import time
from pathlib import Path

import pandas as pd

import auth
import store

CATEGORIES = ("bug", "idea", "data", "other")
COLUMNS = ["timestamp", "user", "category", "message", "page", "contact", "app_version"]
APP_VERSION = "2026.10"


def feedback_dir() -> Path:
    path = auth.data_root() / "feedback"
    path.mkdir(parents=True, exist_ok=True)
    return path


def feedback_path() -> Path:
    return feedback_dir() / "feedback.csv"


def add(user: str, category: str, message: str, page: str = "", contact: str = "") -> Path:
    """Append one report and return the file it went into."""
    row = pd.DataFrame([{
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "user": user or "anonymous",
        "category": category if category in CATEGORIES else "other",
        "message": (message or "").strip(),
        "page": page or "",
        "contact": (contact or "").strip(),
        "app_version": APP_VERSION,
    }], columns=COLUMNS)
    if store.enabled():
        try:
            store.append_row(user or "anonymous", "feedback", row.iloc[0].to_dict())
            return "database"
        except Exception:
            pass  # database unreachable: keep the report in a local CSV
    path = feedback_path()
    if path.exists():
        row.to_csv(path, mode="a", header=False, index=False, encoding="utf-8-sig")
    else:
        row.to_csv(path, index=False, encoding="utf-8-sig")
    return path


def load_all() -> pd.DataFrame | None:
    if store.enabled():
        frame = store.load_all("feedback")
        if frame.empty:
            return None
        if "timestamp" in frame.columns:
            frame = frame.sort_values("timestamp", ascending=False).reset_index(drop=True)
        return frame
    path = feedback_path()
    if not path.exists():
        return None
    try:
        frame = pd.read_csv(path, encoding="utf-8-sig")
    except (OSError, pd.errors.ParserError, UnicodeDecodeError):
        return None
    return frame.sort_values("timestamp", ascending=False).reset_index(drop=True)


def stats(frame: pd.DataFrame) -> dict:
    counts = frame["category"].value_counts().to_dict() if not frame.empty else {}
    recent = 0
    if not frame.empty:
        cutoff = pd.Timestamp.now() - pd.Timedelta(days=7)
        recent = int((pd.to_datetime(frame["timestamp"], errors="coerce") >= cutoff).sum())
    return {"total": len(frame), "recent": recent, "by_category": counts}
