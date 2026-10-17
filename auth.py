# -*- coding: utf-8 -*-
"""Local accounts and per-user record folders for DES Lab.

Passwords are stored as salted PBKDF2-HMAC-SHA256 hashes in
``user_data/users.json``; the file and every record folder live under
``user_data/`` which is git-ignored, so no credentials or lab data reach GitHub.

This guards against team members mixing up each other's records on a shared
machine. It is not internet-grade authentication - do not publish the app with
these accounts and expect it to protect data.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import secrets
import time
from pathlib import Path

import pandas as pd
import streamlit as st

ITERATIONS = 200_000
SESSION_KEY = "auth_user"
DATA_DIR_ENV = "DESLAB_DATA_DIR"

# Teammates seeded on the very first launch. Change the password in the app
# (Guide & Templates -> Account) as soon as the real team is set up.
DEFAULT_PASSWORD = "ChCl/Ga(1:2)"
SEED_USERS = ("Thena", "Chuanyu")
USERNAME_RE = re.compile(r"[A-Za-z0-9._-]{1,32}")


# ---------------------------------------------------------------- storage paths
def data_root() -> Path:
    override = os.environ.get(DATA_DIR_ENV)
    root = Path(override) if override else Path(__file__).parent / "user_data"
    root.mkdir(parents=True, exist_ok=True)
    return root


def users_path() -> Path:
    return data_root() / "users.json"


def user_dir(username: str) -> Path:
    """Record folder for one user; rejects anything that is not a plain handle."""
    if not isinstance(username, str) or not USERNAME_RE.fullmatch(username):
        raise ValueError("invalid user name")
    path = data_root() / "records" / username
    path.mkdir(parents=True, exist_ok=True)
    return path


def results_path(username: str) -> Path:
    return user_dir(username) / "results.csv"


# ------------------------------------------------------------------- hashing
def _hash(password: str, salt_hex: str, iterations: int = ITERATIONS) -> str:
    return hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), bytes.fromhex(salt_hex),
                               iterations).hex()


def _entry(password: str) -> dict:
    salt = secrets.token_hex(16)
    return {"salt": salt, "hash": _hash(password, salt), "iterations": ITERATIONS,
            "created": time.strftime("%Y-%m-%d %H:%M:%S")}


# --------------------------------------------------------------------- store
def load_users() -> dict:
    path = users_path()
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8")).get("users", {})
    except (json.JSONDecodeError, OSError):
        return {}


def save_users(users: dict) -> None:
    path = users_path()
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps({"users": users}, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(path)


def ensure_store() -> dict:
    """Create the store with the seeded teammates if it does not exist yet."""
    users = load_users()
    if not users:
        users = {name: _entry(DEFAULT_PASSWORD) for name in SEED_USERS}
        save_users(users)
    return users


def add_user(username: str, password: str) -> None:
    username = username.strip()
    if not USERNAME_RE.fullmatch(username):
        raise ValueError("Use 1-32 characters: letters, digits, dot, dash or underscore.")
    if len(password) < 6:
        raise ValueError("Use a password with at least 6 characters.")
    users = ensure_store()
    if username in users:
        raise ValueError(f"{username} already exists.")
    users[username] = _entry(password)
    save_users(users)


def change_password(username: str, password: str) -> None:
    users = ensure_store()
    if username not in users:
        raise ValueError("unknown user")
    if len(password) < 6:
        raise ValueError("Use a password with at least 6 characters.")
    users[username] = _entry(password)
    save_users(users)


def verify(username: str, password: str) -> bool:
    users = load_users()
    entry = users.get((username or "").strip())
    if not entry:
        return False
    candidate = _hash(password, entry["salt"], int(entry.get("iterations", ITERATIONS)))
    return hmac.compare_digest(candidate, entry["hash"])


# ------------------------------------------------------------------- session
def current_user() -> str | None:
    return st.session_state.get(SESSION_KEY)


def logout() -> None:
    st.session_state.pop(SESSION_KEY, None)


def login(username: str, password: str) -> bool:
    if verify(username, password):
        st.session_state[SESSION_KEY] = username.strip()
        return True
    return False


# ---------------------------------------------------------------- record files
def save_results(username: str, frame: pd.DataFrame, append: bool = True) -> Path:
    """Store a results table in the user's folder, appending or replacing."""
    path = results_path(username)
    if append and path.exists():
        try:
            existing = pd.read_csv(path, encoding="utf-8-sig")
            frame = pd.concat([existing, frame], ignore_index=True, sort=False)
        except (OSError, pd.errors.ParserError, UnicodeDecodeError):
            pass
    frame.to_csv(path, index=False, encoding="utf-8-sig")
    return path


def load_results(username: str) -> pd.DataFrame | None:
    path = results_path(username)
    if not path.exists():
        return None
    try:
        return pd.read_csv(path, encoding="utf-8-sig")
    except (OSError, pd.errors.ParserError, UnicodeDecodeError):
        return None


def save_recipe(username: str, frame: pd.DataFrame) -> Path:
    """Keep a timestamped copy of a weighing list next to the user's records."""
    folder = user_dir(username) / "recipes"
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"recipe_{(frame.attrs.get('tag') or time.strftime('%Y%m%d-%H%M%S'))}.csv"
    frame.to_csv(path, index=False, encoding="utf-8-sig")
    return path


# ------------------------------------------------------------------ login page
def login_form() -> None:
    """Render the sign-in gate. Caller stops the script when it returns.

    No placeholders and no names are shown here: a grey example like "Thena" both hints at a real
    account and looks pre-filled, so the field is left blank instead.
    """
    left, middle, right = st.columns([1, 1.1, 1])
    with middle:
        st.markdown("### Sign in")
        st.caption("Each teammate signs in to their own record folder. Ask your lab lead for an account.")
        with st.form("login", clear_on_submit=False):
            username = st.text_input("Username")
            password = st.text_input("Password", type="password")
            submitted = st.form_submit_button("Sign in", type="primary", use_container_width=True)
        if submitted:
            if not username.strip() or not password:
                st.warning("Enter both your username and password.")
            elif login(username, password):
                st.rerun()
            else:
                st.error("Unknown username or wrong password.")
