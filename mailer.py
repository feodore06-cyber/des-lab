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


def _disabled() -> bool:
    """DESLAB_MAIL_DISABLE=1 ignores the secrets file (used by the test suite)."""
    return os.environ.get("DESLAB_MAIL_DISABLE", "").strip() not in ("", "0", "false")


def _section() -> dict:
    if _disabled():
        return {}
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


def _brevo_settings() -> dict:
    block = {}
    if not _disabled():
        try:
            import streamlit as st

            block = dict(st.secrets.get("brevo") or {})
        except Exception:
            block = {}
    # environment wins, so a one-off check_mail.py run never needs the secrets file
    api_key = os.environ.get("DESLAB_BREVO_KEY") or block.get("api_key")
    sender = (os.environ.get("DESLAB_BREVO_SENDER") or block.get("sender")
              or setting("user") or "")
    name = os.environ.get("DESLAB_BREVO_SENDER_NAME") or block.get("sender_name") or "BioMat Lab"
    return {"api_key": str(api_key) if api_key else "", "sender": str(sender), "sender_name": str(name)}


def _post_json(url: str, payload: dict, headers: dict) -> tuple[int, str]:
    import json as _json
    import urllib.error
    import urllib.request

    body = _json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(url, data=body, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            return response.status, response.read().decode("utf-8", "ignore")
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode("utf-8", "ignore")


def _deliver_brevo(message: EmailMessage) -> bool:
    """HTTPS delivery through Brevo (no SMTP, no two-factor setup needed)."""
    settings = _brevo_settings()
    if not (settings["api_key"] and settings["sender"]):
        return False
    payload = {
        "sender": {"name": settings["sender_name"], "email": settings["sender"]},
        "to": [{"email": address.strip()} for address in str(message["To"]).split(",") if address.strip()],
        "subject": str(message["Subject"]),
        "textContent": message.get_content(),
    }
    status, text = _post_json("https://api.brevo.com/v3/smtp/email", payload,
                              {"api-key": settings["api_key"], "content-type": "application/json",
                               "accept": "application/json"})
    if status in (200, 201, 202):
        return True
    print(f"brevo delivery failed: HTTP {status} {text[:200]}", file=sys.stderr)
    return False


def provider() -> str:
    if _brevo_settings()["api_key"]:
        return "brevo"
    if configured():
        return "smtp"
    return "none"


def send(message: EmailMessage) -> bool:
    if not message.get("From"):
        message["From"] = f"{setting('from_name')} <{setting('user') or _brevo_settings()['sender']}>"
    kind = provider()
    if kind == "brevo":
        return _deliver_brevo(message)
    if kind == "smtp":
        return _deliver(message)
    return False


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
    kind = provider()
    if kind == "brevo":
        return f"brevo · {_brevo_settings()['sender']}"
    if kind == "smtp":
        return f"smtp · {setting('user')} via {setting('host')}:{setting('port')}"
    return "not configured"
