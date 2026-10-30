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
from datetime import datetime, timedelta, timezone
import hmac
import json
import os
import re
import secrets
import time
from pathlib import Path

import pandas as pd
import streamlit as st

import schema
import store

from i18n import language_switch, t

ITERATIONS = 200_000
SESSION_KEY = "auth_user"
ROLE_SUPERVISOR = "supervisor"
ROLE_INTERN = "intern"
EXPIRY_KEY = "expires_at"
MODE_KEY = "login_mode"          # "signin" or "signup"
DATA_DIR_ENV = "DESLAB_DATA_DIR"
INVITE_ENV = "DESLAB_INVITE_CODE"      # when set, sign-up requires this code
HOSTED_ENV = "DESLAB_HOSTED"           # when set, warn that storage is ephemeral
ADMIN_ENV = "DESLAB_ADMINS"             # comma separated list of admin usernames
DEFAULT_ADMINS = ("Chuanyu",)
EMAIL_RE = re.compile(r"^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$")
EMAIL_MAX = 120

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


def folder_name(username: str) -> str:
    """A filesystem-safe folder name for an account.

    Accounts are e-mail addresses now; ``@`` is legal on disk but awkward in paths and shells, so it
    becomes ``_at_``. Separators and ``..`` are refused outright, because a folder name must never be
    able to escape ``records/``.
    """
    if not isinstance(username, str) or not username.strip():
        raise ValueError("invalid user name")
    name = username.strip()
    if USERNAME_RE.fullmatch(name):
        return name
    if "/" in name or "\\" in name or ".." in name or "\x00" in name:
        raise ValueError("invalid user name")
    safe = name.replace("@", "_at_")
    safe = re.sub(r"[^A-Za-z0-9._-]", "_", safe)
    if not safe or safe in {".", ".."}:
        raise ValueError("invalid user name")
    return safe


def user_dir(username: str) -> Path:
    """Record folder for one account; creates it on first use."""
    path = data_root() / "records" / folder_name(username)
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
def _load_users_json() -> dict:
    path = users_path()
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8")).get("users", {})
    except (json.JSONDecodeError, OSError):
        return {}


def load_users() -> dict:
    """Accounts live in the database when one is configured, otherwise in users.json.

    A container filesystem is temporary, so a hosted deployment would lose every account on each
    redeploy while they only lived in the file. The first run with a database imports the file once.
    """
    if store.enabled():
        try:
            accounts = store.accounts_all()
            if accounts:
                return accounts
            local = _load_users_json()
            if local:
                for name, entry in local.items():
                    store.account_upsert(name, entry)
                return local
            return {}
        except Exception:
            pass  # database unreachable: fall back to the file below
    return _load_users_json()


def save_users(users: dict) -> None:
    """Write the accounts to users.json and, when configured, to the database."""
    path = users_path()
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps({"users": users}, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(path)
    if store.enabled():
        try:
            for name, entry in users.items():
                store.account_upsert(name, entry)
        except Exception:
            pass  # keep working with the local file if the database is down


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


def _find_user(users: dict, identifier: str) -> str | None:
    """Find an account by name or e-mail, ignoring case."""
    wanted = (identifier or "").strip()
    if wanted in users:
        return wanted
    lowered = wanted.lower()
    for name in users:
        if name.lower() == lowered:
            return name
    return None


def add_user(identifier: str, password: str, role: str = ROLE_INTERN,
             supervisor: str | None = None, expires=None) -> str:
    """Create an account. The identifier is an e-mail address (new style) or a username (legacy)."""
    identifier = (identifier or "").strip()
    if "@" in identifier:
        identifier = identifier.lower()
        if not EMAIL_RE.fullmatch(identifier) or len(identifier) > EMAIL_MAX:
            raise ValueError("Enter a valid email address.")
    elif not USERNAME_RE.fullmatch(identifier):
        raise ValueError("Use 1-32 characters: letters, digits, dot, dash or underscore.")
    if len(password) < 6:
        raise ValueError("Use a password with at least 6 characters.")
    users = ensure_store()
    existing = _find_user(users, identifier)
    if existing:
        raise ValueError(f"{identifier} already exists.")
    entry = _entry(password)
    entry["role"] = role
    entry["supervisor"] = supervisor or ""
    entry[EXPIRY_KEY] = _parse_moment(expires).isoformat() if expires else ""
    users[identifier] = entry
    save_users(users)
    user_dir(identifier)  # create the empty record folder straight away
    if store.enabled():
        try:
            store.account_set_team(identifier, role, supervisor, _parse_moment(expires) if expires else None)
        except Exception:
            pass
    # never leave a fresh deployment without an administrator: the first account gets the role
    if not admins():
        set_admin(identifier, True)
    return identifier


def change_password(username: str, password: str) -> None:
    users = ensure_store()
    name = _find_user(users, username)
    if not name:
        raise ValueError("unknown user")
    username = name
    if len(password) < 6:
        raise ValueError("Use a password with at least 6 characters.")
    users[username] = _entry(password)
    save_users(users)


def verify(identifier: str, password: str) -> bool:
    users = load_users()
    name = _find_user(users, identifier)
    entry = users.get(name) if name else None
    if not entry:
        return False
    candidate = _hash(password, entry["salt"], int(entry.get("iterations", ITERATIONS)))
    return hmac.compare_digest(candidate, entry["hash"])


# ------------------------------------------------------- brute-force protection
MAX_ATTEMPTS = 5          # wrong passwords before the account is locked
LOCK_MINUTES = 15         # how long the lock lasts
SESSION_TIMEOUT_H = 12    # an idle session signs itself out
LOGIN_ERROR = "login_error"
SESSION_SEEN = "auth_seen"


def _lock_state(name: str) -> dict:
    if store.enabled():
        try:
            return store.account_lock_state(name)
        except Exception:
            pass
    entry = load_users().get(name) or {}
    raw = entry.get("locked_until")
    locked = None
    if raw:
        try:
            locked = datetime.fromisoformat(str(raw))
        except ValueError:
            locked = None
    return {"failed": int(entry.get("failed_attempts", 0) or 0), "locked_until": locked}


def _record_attempt(name: str, failed: int, locked_until) -> None:
    if store.enabled():
        try:
            store.account_login_failed(name, failed, locked_until)
            return
        except Exception:
            pass
    users = load_users()
    if name in users:
        users[name]["failed_attempts"] = failed
        users[name]["locked_until"] = locked_until.isoformat() if locked_until else ""
        save_users(users)


def _clear_attempts(name: str) -> None:
    if store.enabled():
        try:
            store.account_touch_login(name)
            return
        except Exception:
            pass
    users = load_users()
    if name in users:
        users[name]["failed_attempts"] = 0
        users[name]["locked_until"] = ""
        users[name]["last_login"] = time.strftime("%Y-%m-%d %H:%M:%S")
        save_users(users)


# ---------------------------------------------------------------- team scope
def _parse_moment(value):
    if not value:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    try:
        parsed = datetime.fromisoformat(str(value))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def profile(username: str | None) -> dict:
    """Role, supervisor and expiry of one account (database first, local file second)."""
    if not username:
        return {"role": ROLE_INTERN, "supervisor": None, "expires_at": None, "is_admin": False}
    if store.enabled():
        try:
            return store.account_profile(username)
        except Exception:
            pass
    entry = load_users().get(username) or {}
    return {"role": entry.get("role", ROLE_INTERN), "supervisor": entry.get("supervisor"),
            "expires_at": _parse_moment(entry.get(EXPIRY_KEY)), "is_admin": bool(entry.get("is_admin"))}


def role_of(username: str | None) -> str:
    return profile(username)["role"]


def is_supervisor(username: str | None) -> bool:
    return bool(username) and (profile(username)["role"] == ROLE_SUPERVISOR or is_admin(username))


def is_expired(username: str | None) -> bool:
    expires = profile(username)["expires_at"]
    return bool(expires and expires < _now())


def team_members(supervisor: str | None) -> list:
    """The accounts that belong to one supervisor - never anyone else's."""
    if not supervisor:
        return []
    if store.enabled():
        try:
            return store.team_of(supervisor)
        except Exception:
            pass
    return [name for name, entry in load_users().items() if entry.get("supervisor") == supervisor]


def data_owners(username: str | None) -> list:
    """Whose rows this account may read: its own, plus its own interns when it is a supervisor.

    An administrator gets no extra rows here on purpose: platform duties must never expose another
    team's experiment data.
    """
    if not username:
        return []
    owners = [username]
    if is_supervisor(username):
        owners += [name for name in team_members(username) if name != username]
    return owners


def set_team(username: str, role: str = ROLE_INTERN, supervisor: str | None = None, expires=None) -> None:
    moment = _parse_moment(expires) if expires else None
    if store.enabled():
        store.account_set_team(username, role, supervisor, moment)
        return
    users = load_users()
    if username in users:
        users[username]["role"] = role
        users[username]["supervisor"] = supervisor
        users[username][EXPIRY_KEY] = moment.isoformat() if moment else ""
        save_users(users)


def expired_accounts() -> list:
    """Accounts past their expiry date, for the team page."""
    return [name for name in load_users() if is_expired(name)]


# ------------------------------------------------------------------- session
def admins() -> set:
    """Administrators: the configured list plus anyone flagged in the database.

    Storing roles in the database means a supervisor can promote a successor from the Team page, and
    a deployment can never end up with nobody who can manage it.
    """
    names: set = set()
    if store.enabled():
        try:
            names |= store.account_admin_names()
        except Exception:
            pass
    else:
        # local file mode keeps the same flag inside users.json
        names |= {name for name, entry in load_users().items() if entry.get("is_admin")}
    raw = _flag(ADMIN_ENV)
    if not raw:
        try:
            secret = st.secrets.get("admins")
        except Exception:
            secret = None
        if secret:
            raw = ",".join(secret) if isinstance(secret, (list, tuple)) else str(secret)
    if raw:
        names |= {name.strip() for name in raw.split(",") if name.strip()}
    elif not names:
        names = set(DEFAULT_ADMINS)
    return names


def set_admin(username: str, flag: bool) -> None:
    """Promote or demote an account; this is what the Team page writes."""
    if store.enabled():
        store.account_set_admin(username, flag)
        return
    users = load_users()
    if username in users:
        users[username]["is_admin"] = bool(flag)
        save_users(users)


def is_admin(username: str | None) -> bool:
    return bool(username) and username in admins()


def display_name(identifier: str | None) -> str:
    """The greeting shows the part before @ for e-mail accounts, otherwise the username."""
    name = (identifier or "").strip()
    if "@" in name:
        return name.split("@", 1)[0]
    return name


# ------------------------------------------------------------ password resets
RESET_PARAM = "reset_token"
RESET_TTL_MIN = 60
RESET_FILE = "reset_tokens.json"


def _now():
    return datetime.now(timezone.utc)


def _reset_path() -> Path:
    return data_root() / RESET_FILE


def _tokens_json() -> dict:
    path = _reset_path()
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8")).get("tokens", {})
    except (json.JSONDecodeError, OSError):
        return {}


def _save_tokens_json(tokens: dict) -> None:
    path = _reset_path()
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps({"tokens": tokens}, indent=2), encoding="utf-8")
    tmp.replace(path)


def _token_store(username: str, digest: str, expires) -> None:
    if store.enabled():
        try:
            store.token_create(username, digest, expires)
            return
        except Exception:
            pass
    tokens = {k: v for k, v in _tokens_json().items() if v.get("username") != username or v.get("used")}
    tokens[digest] = {"username": username, "expires": expires.isoformat(), "used": False}
    _save_tokens_json(tokens)


def _token_read(digest: str) -> dict | None:
    if store.enabled():
        try:
            record = store.token_lookup(digest)
        except Exception:
            record = None
        if record:
            expires = record["expires"]
            return {"username": record["username"], "used": record["used"],
                    "expires": expires if expires.tzinfo else expires.replace(tzinfo=timezone.utc)}
    record = _tokens_json().get(digest)
    if not record:
        return None
    try:
        expires = datetime.fromisoformat(record["expires"])
    except (KeyError, ValueError):
        return None
    return {"username": record.get("username"), "used": bool(record.get("used")), "expires": expires}


def _token_mark_used(digest: str) -> None:
    if store.enabled():
        try:
            store.token_use(digest)
        except Exception:
            pass
    tokens = _tokens_json()
    if digest in tokens:
        tokens[digest]["used"] = True
        _save_tokens_json(tokens)


def create_reset_token(identifier: str) -> str | None:
    """Issue a one-time password-reset token. Unknown accounts get None (no account enumeration)."""
    name = _find_user(load_users(), identifier)
    if not name:
        return None
    token = secrets.token_urlsafe(32)
    digest = hashlib.sha256(token.encode("utf-8")).hexdigest()
    _token_store(name, digest, _now() + timedelta(minutes=RESET_TTL_MIN))
    return token


def reset_password(token: str, new_password: str) -> str | None:
    """Redeem a token and set a new password. Returns the account name, or None."""
    if not token or len(new_password) < 6:
        return None
    digest = hashlib.sha256(token.encode("utf-8")).hexdigest()
    record = _token_read(digest)
    if not record or record.get("used") or record["expires"] < _now():
        return None
    change_password(record["username"], new_password)
    _token_mark_used(digest)
    return record["username"]


def reset_link(token: str) -> str:
    """A full URL when the host can be detected, otherwise the bare query string."""
    base = _flag("DESLAB_BASE_URL")
    if not base:
        try:
            headers = st.context.headers
            host = headers.get("Host")
            proto = headers.get("X-Forwarded-Proto", "https")
            if host:
                base = f"{proto}://{host}"
        except Exception:
            base = None
    suffix = f"?{RESET_PARAM}={token}"
    return base.rstrip("/") + "/" + suffix if base else suffix


def current_user() -> str | None:
    """The signed-in account; an idle session signs itself out after SESSION_TIMEOUT_H hours."""
    name = st.session_state.get(SESSION_KEY)
    if not name:
        return None
    if is_expired(name):
        st.session_state.pop(SESSION_KEY, None)
        st.session_state.pop(SESSION_SEEN, None)
        st.session_state[LOGIN_ERROR] = "expired_account"
        st.session_state["login_expired_user"] = name
        return None
    seen = st.session_state.get(SESSION_SEEN)
    if seen and time.time() - float(seen) > SESSION_TIMEOUT_H * 3600:
        st.session_state.pop(SESSION_KEY, None)
        st.session_state.pop(SESSION_SEEN, None)
        st.session_state[LOGIN_ERROR] = "expired"
        return None
    st.session_state[SESSION_SEEN] = time.time()
    return name


def logout() -> None:
    st.session_state.pop(SESSION_KEY, None)
    st.session_state.pop(MODE_KEY, None)
    st.session_state.pop(SESSION_SEEN, None)


def login(username: str, password: str) -> bool:
    """Sign in, with a temporary lock after MAX_ATTEMPTS wrong passwords."""
    name = _find_user(load_users(), username)
    state = _lock_state(name) if name else {"failed": 0, "locked_until": None}
    until = state.get("locked_until")
    if until and until > _now():
        st.session_state[LOGIN_ERROR] = "locked"
        st.session_state["login_locked_until"] = until.strftime("%H:%M")
        return False

    if name and is_expired(name):
        st.session_state[LOGIN_ERROR] = "expired_account"
        st.session_state["login_expired_user"] = name
        return False

    if verify(username, password):
        st.session_state.pop(LOGIN_ERROR, None)
        st.session_state.pop("login_locked_until", None)
        st.session_state[SESSION_KEY] = name or username.strip()
        st.session_state[SESSION_SEEN] = time.time()
        _clear_attempts(name or username.strip())
        return True

    if name:
        failed = int(state.get("failed", 0)) + 1
        lock_at = _now() + timedelta(minutes=LOCK_MINUTES) if failed >= MAX_ATTEMPTS else None
        _record_attempt(name, failed, lock_at)
        if lock_at:
            st.session_state[LOGIN_ERROR] = "locked"
            st.session_state["login_locked_until"] = lock_at.strftime("%H:%M")
    return False


# ---------------------------------------------------------------- record files
def _flag(name: str) -> str | None:
    """Read a deployment setting from the environment or from Streamlit secrets.

    Streamlit Community Cloud does NOT export secrets as environment variables, so reading
    os.environ alone silently ignored DESLAB_HOSTED / DESLAB_INVITE_CODE / DESLAB_ADMINS there.
    """
    value = os.environ.get(name)
    if value:
        return str(value)
    try:
        value = st.secrets.get(name)
    except Exception:
        return None
    return str(value) if value else None


def hosted_mode() -> bool:
    """True when running on a host whose filesystem does not persist (Streamlit Cloud, ...)."""
    return bool(_flag(HOSTED_ENV))


def invite_required() -> bool:
    return bool(_flag(INVITE_ENV))


# the categories a photo can belong to; kept as data so the picker can offer them all
IMAGE_CATEGORIES = [
    "Optical microscope", "SEM", "TEM", "AFM", "Confocal",
    "XRD pattern", "FTIR spectrum", "NMR spectrum", "TGA curve", "DSC curve",
    "UV-Vis spectrum", "HPLC chromatogram", "GC chromatogram", "Mass spectrum",
    "Sample photo (macro)", "Reaction setup", "Apparatus / weighing", "Gel / membrane",
    "Chart or screenshot", "Raw data", "Other",
]

IMAGE_LIMIT_BYTES = 8 * 1024 * 1024  # one picture; the number of pictures is unlimited


def add_image(username: str, sample_id: str, category: str, note: str,
              filename: str, mime: str, payload: bytes) -> int:
    """Store one picture against a run. Refuses oversized or non-image files."""
    if not payload:
        raise ValueError("The file is empty.")
    if len(payload) > IMAGE_LIMIT_BYTES:
        raise ValueError("That picture is larger than 8 MB; export it smaller first.")
    if not str(mime or "").startswith("image/"):
        raise ValueError("Only images can be attached here.")
    if not store.enabled():
        raise ValueError("Attaching pictures needs the database; this copy is running on files.")
    image_id = store.image_add(username, None, sample_id, category,
                               " ".join(str(note or "").split())[:200], filename, mime, payload)
    _forget_cached_reads()
    return image_id


def images_of(username: str, sample_id: str | None = None) -> list:
    if not store.enabled():
        return []
    try:
        rows = store.image_rows(data_owners(username))
    except Exception:
        return []
    if sample_id:
        return [row for row in rows if str(row.get("sample_id")) == str(sample_id)]
    return rows


def image_counts(username: str) -> dict:
    counts = {}
    for row in images_of(username):
        key = str(row.get("sample_id") or "")
        counts[key] = counts.get(key, 0) + 1
    return counts


def image_content(username: str, image_id: int):
    if not store.enabled():
        return None
    return store.image_bytes(image_id, data_owners(username))


def remove_image(username: str, image_id: int) -> None:
    if not store.enabled():
        return
    store.image_delete(image_id, data_owners(username))
    _forget_cached_reads()


DEFAULT_PROJECT = "General"


def list_projects(username: str | None) -> list:
    """Projects visible to this account: its own plus its interns', always with General first."""
    owners = data_owners(username)
    names = []
    if store.enabled():
        try:
            names = store.projects_of(owners)
        except Exception:
            names = []
    local = _local_projects()
    for owner in owners:
        names = list(names) + [value for value in (local.get(owner) or []) if value]
    if not names:
        names = sorted({str(value) for value in (_project_values(username) or []) if value})
    if DEFAULT_PROJECT not in names:
        names = [DEFAULT_PROJECT] + names
    return names


def _project_values(username: str | None) -> list:
    frame = load_results(username)
    if frame is None or "project" not in frame.columns:
        return []
    return [value for value in frame["project"].dropna().unique()]


PROJECT_STATUSES = ("Draft", "In progress", "Pending test", "Completed", "Needs review")


def project_statuses(username: str | None) -> dict:
    """name -> status; a project that was never given one counts as in progress."""
    if not username or not store.enabled():
        return {}
    try:
        return store.project_states(data_owners(username))
    except Exception:
        return {}


def set_project_status(username: str, name: str, status: str) -> None:
    if not store.enabled():
        return
    store.project_set_status(username, name, status)
    _forget_cached_reads()


DEFAULT_FORMULATION = {"des_hba": "ChCl", "des_hbd": "Glyoxylic acid", "molar_ratio": 2.0,
                       "purity_wt_pct": 98.0, "water_wt_pct": 0.0}


def project_formulation(username: str | None, name: str) -> dict:
    """The formulation a project was started with; every experiment inherits it."""
    if not username:
        return dict(DEFAULT_FORMULATION)
    stored = None
    if store.enabled():
        try:
            raw = store.project_formulation_get(username, name)
            if raw:
                stored = json.loads(raw)
        except Exception:
            stored = None
    if stored is None:
        mapping = _local_projects().get("_formulation") or {}
        stored = mapping.get(f"{username}::{name}") or {}
    merged = dict(DEFAULT_FORMULATION)
    merged.update({key: value for key, value in stored.items() if value not in (None, "")})
    return merged


def set_project_formulation(username: str, name: str, formulation: dict) -> None:
    payload = json.dumps(dict(formulation), ensure_ascii=False)
    if store.enabled():
        store.project_formulation_set(username, name, payload)
    raw = _local_projects()
    mapping = raw.get("_formulation") or {}
    mapping[f"{username}::{name}"] = dict(formulation)
    raw["_formulation"] = mapping
    _save_local_projects(raw)
    _forget_cached_reads()


def _projects_file() -> Path:
    return data_root() / "projects.json"


def _local_projects() -> dict:
    path = _projects_file()
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8")) or {}
    except (ValueError, OSError):
        return {}


def _save_local_projects(mapping: dict) -> None:
    path = _projects_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(mapping, ensure_ascii=False, indent=2), encoding="utf-8")


def create_project(username: str, name: str) -> str:
    """Make a project; names are trimmed and capped so they stay usable as a filter."""
    clean = " ".join(str(name or "").split())[:40]
    if not clean:
        raise ValueError("Give the project a name.")
    if clean in list_projects(username):
        raise ValueError("A project with that name already exists.")
    if store.enabled():
        store.project_create(username, clean)
    # kept locally as well, so a laptop without a database still has projects
    mapping = _local_projects()
    names = mapping.get(username) or []
    if clean not in names:
        names.append(clean)
    mapping[username] = names
    _save_local_projects(mapping)
    _forget_cached_reads()
    return clean


def _forget_cached_reads() -> None:
    """A write makes every cached view stale."""
    try:
        st.cache_data.clear()
    except Exception:
        pass


def save_results(username: str, frame: pd.DataFrame, append: bool = True) -> Path | str:
    """Store a results table: in Postgres when configured, otherwise in the user's folder."""
    if store.enabled():
        try:
            if append:
                store.append(username, "results", frame)
            else:
                store.replace(username, "results", frame)
            return "database"
        except Exception:
            pass  # database unreachable: fall through to the local CSV so nothing is lost
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
    """Rows this account may read: its own, plus its own interns' when it is a supervisor.

    Every row carries ``_owner`` so a later save can put edits back where they belong.
    """
    owners = data_owners(username)
    if not owners:
        return None
    if store.enabled():
        try:
            frame = store.load_many(owners, "results")
            if frame.empty and len(owners) == 1:
                _import_results_csv(owners[0])
                frame = store.load_many(owners, "results")
            return None if frame.empty else frame
        except Exception:
            pass  # database unreachable: fall back to the local folders
    parts = []
    for owner in owners:
        path = results_path(owner)
        if not path.exists():
            continue
        try:
            part = pd.read_csv(path, encoding="utf-8-sig")
        except (OSError, pd.errors.ParserError, UnicodeDecodeError):
            continue
        part["_owner"] = owner
        parts.append(part)
    if not parts:
        return None
    return pd.concat(parts, ignore_index=True, sort=False)


def save_results(username: str, frame: pd.DataFrame, append: bool = True) -> Path | str:
    """Write rows back to their owners; never into another team's space."""
    allowed = set(data_owners(username))
    work = schema.backfill(frame)  # fills des_hba / des_hbd / molar_ratio from an old label
    if "_owner" not in work.columns:
        work["_owner"] = username
    work["_owner"] = work["_owner"].fillna(username).astype(str)
    work.loc[~work["_owner"].isin(allowed), "_owner"] = username

    if store.enabled():
        try:
            _forget_cached_reads()
            for owner, part in work.groupby("_owner", sort=False):
                payload = part.drop(columns=["_owner"], errors="ignore")
                if append:
                    store.append(owner, "results", payload)
                else:
                    store.replace(owner, "results", payload)
            return "database"
        except Exception:
            pass  # database unreachable: keep the rows in the local files

    _forget_cached_reads()
    for owner, part in work.groupby("_owner", sort=False):
        payload = part.drop(columns=["_owner"], errors="ignore")
        path = results_path(owner)
        if append and path.exists():
            try:
                existing = pd.read_csv(path, encoding="utf-8-sig")
                payload = pd.concat([existing, payload], ignore_index=True, sort=False)
            except (OSError, pd.errors.ParserError, UnicodeDecodeError):
                pass
        payload.to_csv(path, index=False, encoding="utf-8-sig")
    return results_path(username)


def save_recipe(username: str, frame: pd.DataFrame) -> Path | str:
    """Keep a copy of a weighing list, in the database when configured."""
    tag = frame.attrs.get("tag") or time.strftime("%Y%m%d-%H%M%S")
    if store.enabled():
        try:
            tagged = frame.copy()
            tagged["saved_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
            tagged["tag"] = tag
            tagged["saved_by"] = username
            store.append(username, "recipe", tagged)
            return "database"
        except Exception:
            pass  # database unreachable: fall back to a local CSV
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
        username = st.text_input(t("signup.email"), help=t("signup.email_help"))
        password = st.text_input(t("login.password"), type="password", help=t("signup.password_help"))
        confirm = st.text_input(t("signup.repeat"), type="password")
        invite_needed = _flag(INVITE_ENV)
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
                # welcome mail is best effort: a broken mail server must never block a sign-up
                try:
                    from mailer import send_welcome
                except Exception:
                    send_welcome = None
                if send_welcome is not None and "@" in name:  # e-mail accounts only; usernames have no inbox
                    send_welcome(name, display_name(name))
                if login(name, password):
                    st.session_state.pop(MODE_KEY, None)
                    st.rerun()
    if st.button(t("signup.back"), use_container_width=True, key="go_signin"):
        st.session_state[MODE_KEY] = SIGNIN
        st.rerun()


def _reset_request_form() -> None:
    """Ask for an address and issue a one-time link. The answer never reveals whether it exists."""
    with st.form("reset_request"):
        ident = st.text_input(t("reset.identifier"), help=t("reset.request_hint"))
        submitted = st.form_submit_button(t("reset.request_submit"), use_container_width=True)
    if submitted:
        token = create_reset_token(ident)
        st.info(t("reset.sent"))
        if token is None:
            return
        try:
            from mailer import send_reset
        except Exception:
            send_reset = None
        if send_reset is not None and send_reset(ident, reset_link(token)):
            st.caption(t("reset.mail_sent"))
        else:
            st.caption(t("reset.no_mail"))
    if st.button(t("reset.back"), use_container_width=True, key="go_signin_from_reset"):
        st.session_state[MODE_KEY] = SIGNIN
        st.rerun()


def _reset_form(token: str) -> None:
    """Set a new password from a one-time link."""
    st.markdown("### " + t("reset.title"))
    st.caption(t("reset.sub"))
    with st.form("reset_commit"):
        first = st.text_input(t("reset.new_pw"), type="password")
        second = st.text_input(t("reset.repeat"), type="password")
        submitted = st.form_submit_button(t("reset.submit"), type="primary", use_container_width=True)
    if submitted:
        if first != second:
            st.error(t("signup.pw_mismatch"))
        elif len(first) < 6:
            st.error(t("guide.pw_short"))
        else:
            who = reset_password(token, first)
            if who:
                st.success(t("reset.done"))
                if st.button(t("reset.back"), use_container_width=True, key="go_signin_after_reset"):
                    st.query_params.clear()
                    st.session_state.pop(MODE_KEY, None)
                    st.rerun()
            else:
                st.error(t("reset.bad"))


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
                f'<img src="{logo_url}" alt="BioMat Lab">'
                "</div>",
                unsafe_allow_html=True,
            )
    switcher_left, switcher_mid, switcher_right = st.columns([1, 1.9, 1])
    language_switch(switcher_mid)

    token = st.query_params.get(RESET_PARAM, "")
    if isinstance(token, list):
        token = token[0] if token else ""
    if token:
        left, middle, right = st.columns([1, 1.15, 1])
        with middle:
            _reset_form(token)
        return

    if st.session_state.get(MODE_KEY) == "reset_request":
        left, middle, right = st.columns([1, 1.15, 1])
        with middle:
            _reset_request_form()
        return

    if st.session_state.get(MODE_KEY) == SIGNUP:
        left, middle, right = st.columns([1, 1.15, 1])
        with middle:
            _signup_form()
        return

    if not load_users():
        # A fresh hosted deployment starts with no accounts. Without this block the sign-up button
        # would be unreachable and nobody could ever create the first account.
        st.error(t("login.no_accounts"))
        left, middle, right = st.columns([1, 1.15, 1])
        with middle:
            st.caption(t("login.new_teammate"))
            if st.button(t("login.create"), use_container_width=True, key="go_signup"):
                st.session_state[MODE_KEY] = SIGNUP
                st.rerun()
        return

    left, middle, right = st.columns([1, 1.15, 1])
    with middle:
        st.markdown("### " + t("login.title"))
        st.caption(t("login.sub"))
        with st.form("login", clear_on_submit=False):
            username = st.text_input(t("login.identifier"))
            password = st.text_input(t("login.password"), type="password")
            submitted = st.form_submit_button(t("login.submit"), type="primary", use_container_width=True)
        if submitted:
            if not username.strip() or not password:
                st.warning(t("login.need_both"))
            elif login(username, password):
                st.session_state.pop(MODE_KEY, None)
                st.rerun()
            else:
                kind = st.session_state.get(LOGIN_ERROR)
                if kind == "locked":
                    st.error(t("login.locked", until=st.session_state.get("login_locked_until", "")))
                elif kind == "expired":
                    st.info(t("login.expired"))
                else:
                    st.error(t("login.bad"))
        st.divider()
        if st.button(t("login.forgot"), use_container_width=True, key="go_forgot"):
            st.session_state[MODE_KEY] = "reset_request"
            st.rerun()
        st.caption(t("login.new_teammate"))
        if st.button(t("login.create"), use_container_width=True, key="go_signup"):
            st.session_state[MODE_KEY] = SIGNUP
            st.rerun()

def rename_project(username: str, old: str, new: str) -> str:
    """Rename a project: its record, every experiment row, and its formulation entry."""
    clean = " ".join(str(new or "").split())[:40]
    if not clean:
        raise ValueError("Give the project a name.")
    if clean == old:
        return clean
    if clean in list_projects(username):
        raise ValueError("A project with that name already exists.")

    frame = load_results(username)
    if frame is not None and not frame.empty and "project" in frame.columns:
        work = frame.copy()
        mask = work["project"].fillna(DEFAULT_PROJECT) == old
        if mask.any():
            work.loc[mask, "project"] = clean
            save_results(username, work, append=False)

    if store.enabled():
        try:
            store.project_rename(username, old, clean)
        except Exception:
            pass

    raw = _local_projects()
    names = [clean if value == old else value for value in (raw.get(username) or [])]
    if clean not in names:
        names.append(clean)
    raw[username] = [value for value in names if value != old]
    formulation = raw.get("_formulation") or {}
    if f"{username}::{old}" in formulation:
        formulation[f"{username}::{clean}"] = formulation.pop(f"{username}::{old}")
        raw["_formulation"] = formulation
    _save_local_projects(raw)
    _forget_cached_reads()
    return clean

def delete_project(username: str, name: str, force: bool = False) -> int:
    """Delete a project and, when confirmed, every experiment inside it.

    Returns the number of experiments removed. Without ``force`` a project that still holds rows is
    left untouched and the error names how many would be lost.
    """
    frame = load_results(username)
    removed = 0
    if frame is not None and not frame.empty and "project" in frame.columns:
        mask = frame["project"].fillna(DEFAULT_PROJECT) == name
        removed = int(mask.sum())
        if removed and not force:
            raise ValueError(f"This project still holds {removed} experiment(s); "
                             "confirm to delete them as well.")
        if removed:
            save_results(username, frame.loc[~mask], append=False)

    if store.enabled():
        try:
            store.image_delete_by_project(username, name)
        except Exception:
            pass
        try:
            store.project_delete(username, name)
        except Exception:
            pass

    raw = _local_projects()
    raw[username] = [value for value in (raw.get(username) or []) if value != name]
    formulation = raw.get("_formulation") or {}
    formulation.pop(f"{username}::{name}", None)
    raw["_formulation"] = formulation
    variables = raw.get("_variables") or {}
    variables.pop(f"{username}::{name}", None)
    raw["_variables"] = variables
    _save_local_projects(raw)
    _forget_cached_reads()
    return removed

DEFAULT_VARIABLES = ["temperature_C", "time_min", "biomass_g", "lignin_mg",
                     "lignin_yield_pct", "replicate", "notes"]

# what a project may measure, on top of the ones every project starts with
EXTRA_VARIABLES = ["stirring_rpm", "stirring_time_min", "solid_liquid_ratio", "ph",
                   "catalyst_wt_pct", "particle_size_mm", "moisture_before_wt_pct",
                   "ash_wt_pct", "recovery_wt_pct", "purity_of_lignin_pct"]


def project_variables(username: str | None, name: str) -> list:
    """The measured columns this project records; defaults to the standard set."""
    if not username:
        return list(DEFAULT_VARIABLES)
    stored = None
    if store.enabled():
        try:
            raw = store.project_variables_get(username, name)
            if raw:
                stored = json.loads(raw)
        except Exception:
            stored = None
    if stored is None:
        mapping = _local_projects().get("_variables") or {}
        stored = mapping.get(f"{username}::{name}")
    if not stored:
        return list(DEFAULT_VARIABLES)
    return [str(value) for value in stored]


def set_project_variables(username: str, name: str, values: list) -> None:
    clean = []
    for value in values:
        text_value = " ".join(str(value or "").split())[:32]
        if text_value and text_value not in clean:
            clean.append(text_value)
    if not clean:
        raise ValueError("Keep at least one variable.")
    payload = json.dumps(clean, ensure_ascii=False)
    if store.enabled():
        store.project_variables_set(username, name, payload)
    raw = _local_projects()
    mapping = raw.get("_variables") or {}
    mapping[f"{username}::{name}"] = clean
    raw["_variables"] = mapping
    _save_local_projects(raw)
    _forget_cached_reads()
