# -*- coding: utf-8 -*-
"""Outbound email over SMTP.

Delivery is optional: with no ``[smtp]`` settings the app simply keeps working and the reset flow
falls back to "an administrator creates the link". Settings come from the environment or from
Streamlit secrets::

    [smtp]
    host = "smtp.gmail.com"
    port = 587
    user = "biomatlab697@gmail.com"
    password = "the 16 character app password"
    from_name = "BioMat Lab"

Nothing here raises into the UI: ``send`` returns False on any problem, so a broken mail server can
never block a sign-up or a password reset.
"""
from __future__ import annotations

import os
import smtplib
import ssl
import sys
from email.message import EmailMessage

DEFAULTS = {"host": "smtp.gmail.com", "port": "587", "from_name": "BioMat Lab"}
APP_URL_SETTING = "DESLAB_APP_URL"


def _section() -> dict:
    try:
        import streamlit as st

        return dict(st.secrets.get("smtp") or {})
    except Exception:
        return {}


def setting(name: str) -> str | None:
    """Environment first (handy for tests), then Streamlit secrets, then the built-in default."""
    value = os.environ.get(f"DESLAB_SMTP_{name.upper()}")
    if value:
        return value
    value = _section().get(name)
    if value:
        return str(value)
    return DEFAULTS.get(name)


def configured() -> bool:
    return bool(setting("user") and setting("password"))


def app_url() -> str:
    value = os.environ.get(APP_URL_SETTING)
    if value:
        return value.rstrip("/")
    try:
        import streamlit as st

        value = st.secrets.get("app_url")
        if value:
            return str(value).rstrip("/")
    except Exception:
        pass
    return ""


def _text(name: str, lines: list[str]) -> str:
    return "\n".join([f"Hello {name},", ""] + lines + ["", "— BioMat Lab"])


def welcome_message(to: str, name: str, link: str = "") -> EmailMessage:
    msg = EmailMessage()
    msg["To"] = to
    msg["Subject"] = "Welcome to BioMat Lab"
    body = _text(name, [
        "Your account is ready. You can sign in with this address and the password you chose.",
        "",
        "BioMat Lab keeps recipes, experiment records and figures in one place:",
        "  · Recipe calculator - molar ratios, purity, weighing list",
        "  · Results - merge CSVs, group by condition, export figures",
        "  · Chemical lookup - molar mass straight from PubChem",
    ] + (["", f"Open it here: {link}"] if link else []) + [
        "",
        "If you ever forget the password, use 'Forgot password' on the sign-in page.",
    ])
    msg.set_content(body)
    return msg


def reset_message(to: str, name: str, link: str) -> EmailMessage:
    msg = EmailMessage()
    msg["To"] = to
    msg["Subject"] = "Reset your BioMat Lab password"
    msg.set_content(_text(name, [
        "Someone asked to reset the password for this account. If it was you, open the link below:",
        "",
        link,
        "",
        "The link works once and expires in 60 minutes. If you did not ask for it, ignore this mail -",
        "your password stays unchanged.",
    ]))
    return msg


def _deliver(message: EmailMessage) -> bool:
    """Hand the message to the SMTP server. Returns False instead of raising."""
    host = setting("host") or ""
    port = int(setting("port") or 587)
    user = setting("user") or ""
    password = setting("password") or ""
    if not (host and user and password):
        return False
    message["From"] = f"{setting('from_name')} <{user}>"
    try:
        context = ssl.create_default_context()
        if port == 465:  # implicit TLS; some networks only allow this one
            with smtplib.SMTP_SSL(host, port, timeout=20, context=context) as server:
                server.login(user, password)
                server.send_message(message)
        else:
            with smtplib.SMTP(host, port, timeout=20) as server:
                server.ehlo()
                server.starttls(context=context)
                server.ehlo()
                server.login(user, password)
                server.send_message(message)
        return True
    except Exception as exc:  # noqa: BLE001 - mail must never break the app
        print(f"mail delivery failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return False


def send(message: EmailMessage) -> bool:
    if not configured():
        return False
    return _deliver(message)


def send_welcome(to: str, name: str) -> bool:
    return send(welcome_message(to, name, app_url()))


def send_reset(to: str, link: str) -> bool:
    """Called by the sign-in page; a missing account name is not an error."""
    if not to:
        return False
    name = to.split("@", 1)[0] if "@" in to else to
    return send(reset_message(to, name, link))

def check() -> str:
    """A one-line status for the Guide page."""
    if not configured():
        return "not configured"
    return f"{setting('user')} via {setting('host')}:{setting('port')}"
