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

import store

from i18n import language_switch, t

ITERATIONS = 200_000
SESSION_KEY = "auth_user"
MODE_KEY = "login_mode"          # "signin" or "signup"
DATA_DIR_ENV = "DESLAB_DATA_DIR"
INVITE_ENV = "DESLAB_INVITE_CODE"      # when set, sign-up requires this code
HOSTED_ENV = "DESLAB_HOSTED"           # when set, warn that storage is ephemeral
ADMIN_ENV = "DESLAB_ADMINS"             # comma separated list of admin usernames
DEFAULT_ADMINS = ("Chuanyu",)

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


def seeded_accounts() -> dict:
    """Accounts created on the very first launch.

    ``[accounts]`` in Streamlit secrets wins over the built-in defaults, so a hosted deployment can
    start with its own names and passwords instead of the documented local ones. A hosted deployment
    with no ``[accounts]`` seeds *nothing* - so the documented demo password can never be the door to
    a public site.
    """
    try:
        accounts = dict(st.secrets.get("accounts") or {})
    except Exception:  # no secrets file, or secrets unavailable
        accounts = {}
    if accounts:
        return {str(name): str(password) for name, password in accounts.items()}
    if hosted_mode():
        return {}
    return {name: DEFAULT_PASSWORD for name in SEED_USERS}


def ensure_store() -> dict:
    """Create the store with the seeded teammates if it does not exist yet."""
    users = load_users()
    if not users:
        accounts = seeded_accounts()
        if not accounts:
            return {}
        users = {name: _entry(password) for name, password in accounts.items()}
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
    user_dir(username)  # create the empty record folder straight away


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
def admins() -> set:
    """Who may read the feedback inbox: DESLAB_ADMINS or the [admins] secret, else the default."""
    raw = os.environ.get(ADMIN_ENV)
    if not raw:
        try:
            secret = st.secrets.get("admins")
        except Exception:
            secret = None
        if secret:
            raw = ",".join(secret) if isinstance(secret, (list, tuple)) else str(secret)
    if raw:
        return {name.strip() for name in raw.split(",") if name.strip()}
    return set(DEFAULT_ADMINS)


def is_admin(username: str | None) -> bool:
    return bool(username) and username in admins()


def current_user() -> str | None:
    return st.session_state.get(SESSION_KEY)


def logout() -> None:
    st.session_state.pop(SESSION_KEY, None)
    st.session_state.pop(MODE_KEY, None)


def login(username: str, password: str) -> bool:
    if verify(username, password):
        st.session_state[SESSION_KEY] = username.strip()
        return True
    return False


# ---------------------------------------------------------------- record files
def hosted_mode() -> bool:
    """True when running on a host whose filesystem does not persist (Streamlit Cloud, ...)."""
    return bool(os.environ.get(HOSTED_ENV))


def invite_required() -> bool:
    return bool(os.environ.get(INVITE_ENV))


def save_results(username: str, frame: pd.DataFrame, append: bool = True) -> Path | str:
    """Store a results table: in Postgres when configured, otherwise in the user's folder."""
    if store.enabled():
        if append:
            store.append(username, "results", frame)
        else:
            store.replace(username, "results", frame)
        return "database"
    path = results_path(username)
    if append and path.exists():
        try:
            existing = pd.read_csv(path, encoding="utf-8-sig")
            frame = pd.concat([existing, frame], ignore_index=True, sort=False)
        except (OSError, pd.errors.ParserError, UnicodeDecodeError):
            pass
    frame.to_csv(path, index=False, encoding="utf-8-sig")
    return path


def _import_results_csv(username: str) -> None:
    """One-off migration: push a user's existing results.csv into the database."""
    path = results_path(username)
    if not path.exists():
        return
    try:
        frame = pd.read_csv(path, encoding="utf-8-sig")
    except (OSError, pd.errors.ParserError, UnicodeDecodeError):
        return
    if not frame.empty:
        store.append(username, "results", frame)


def load_results(username: str) -> pd.DataFrame | None:
    """The saved rows for this user; local CSVs are imported once when a database is switched on."""
    if store.enabled():
        frame = store.load(username, "results")
        if frame.empty:
            _import_results_csv(username)
            frame = store.load(username, "results")
        return None if frame.empty else frame
    path = results_path(username)
    if not path.exists():
        return None
    try:
        return pd.read_csv(path, encoding="utf-8-sig")
    except (OSError, pd.errors.ParserError, UnicodeDecodeError):
        return None


def save_recipe(username: str, frame: pd.DataFrame) -> Path | str:
    """Keep a copy of a weighing list, in the database when configured."""
    tag = frame.attrs.get("tag") or time.strftime("%Y%m%d-%H%M%S")
    if store.enabled():
        tagged = frame.copy()
        tagged["saved_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
        tagged["tag"] = tag
        tagged["saved_by"] = username
        store.append(username, "recipe", tagged)
        return "database"
    folder = user_dir(username) / "recipes"
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"recipe_{tag}.csv"
    frame.to_csv(path, index=False, encoding="utf-8-sig")
    return path


# ------------------------------------------------------------------ login page
SIGNIN, SIGNUP = "signin", "signup"


def _signup_form() -> None:
    st.markdown("### " + t("signup.title"))
    st.caption(t("signup.sub"))
    with st.form("signup", clear_on_submit=False):
        username = st.text_input(t("login.username"), help=t("signup.username_help"))
        password = st.text_input(t("login.password"), type="password", help=t("signup.password_help"))
        confirm = st.text_input(t("signup.repeat"), type="password")
        invite_needed = os.environ.get(INVITE_ENV)
        invite = st.text_input(t("signup.invite"), type="password") if invite_needed else ""
        submitted = st.form_submit_button(t("signup.submit"), type="primary", use_container_width=True)
    if submitted:
        name = username.strip()
        if not name:
            st.warning(t("signup.choose_name"))
        elif invite_needed and invite.strip() != invite_needed:
            st.error(t("signup.invite_bad"))
        elif password != confirm:
            st.error(t("signup.pw_mismatch"))
        else:
            try:
                add_user(name, password)
            except ValueError as exc:
                st.error(t(str(exc)))
            else:
                if login(name, password):
                    st.session_state.pop(MODE_KEY, None)
                    st.rerun()
    if st.button(t("signup.back"), use_container_width=True, key="go_signin"):
        st.session_state[MODE_KEY] = SIGNIN
        st.rerun()


def login_form(logo_url: str | None = None) -> None:
    """Render the sign-in gate. Caller stops the script when it returns.

    No placeholders and no names are shown here: a grey example like "Thena" both hints at a real
    account and looks pre-filled, so the field is left blank instead. The caller keeps the sidebar
    out of this page by not adding any sidebar elements before signing in.
    """
    if logo_url:
        # its own wider slot so the wordmark is drawn at full size (the form column is narrower)
        logo_left, logo_mid, logo_right = st.columns([1, 1.9, 1])
        with logo_mid:
            st.markdown(
                '<div class="dsh-login-brand">'
                f'<img src="{logo_url}" alt="A*STAR - Agency for Science, Technology and Research, Singapore">'
                "</div>",
                unsafe_allow_html=True,
            )
    switcher_left, switcher_mid, switcher_right = st.columns([1, 1.9, 1])
    language_switch(switcher_mid)

    if st.session_state.get(MODE_KEY) == SIGNUP:
        left, middle, right = st.columns([1, 1.15, 1])
        with middle:
            _signup_form()
        return

    if not load_users():
        st.error(t("login.no_accounts"))
        return

    left, middle, right = st.columns([1, 1.15, 1])
    with middle:
        st.markdown("### " + t("login.title"))
        st.caption(t("login.sub"))
        with st.form("login", clear_on_submit=False):
            username = st.text_input(t("login.username"))
            password = st.text_input(t("login.password"), type="password")
            submitted = st.form_submit_button(t("login.submit"), type="primary", use_container_width=True)
        if submitted:
            if not username.strip() or not password:
                st.warning(t("login.need_both"))
            elif login(username, password):
                st.session_state.pop(MODE_KEY, None)
                st.rerun()
            else:
                st.error(t("login.bad"))
        st.divider()
        st.caption(t("login.new_teammate"))
        if st.button(t("login.create"), use_container_width=True, key="go_signup"):
            st.session_state[MODE_KEY] = SIGNUP
            st.rerun()
