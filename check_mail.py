# -*- coding: utf-8 -*-
"""Check the mail configuration from the command line.

Usage (PowerShell):
    $env:DESLAB_BREVO_KEY = "xkeysib-..."
    .\.venv\Scripts\python.exe check_mail.py you@example.com

It answers three questions in order, so a failure points at the exact step to fix:
    1. is the API key accepted?
    2. which account and senders does it see?
    3. does a real message go out?
"""
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request

import mailer


def _get(url: str, api_key: str) -> tuple[int, str]:
    request = urllib.request.Request(url, headers={"api-key": api_key, "accept": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            return response.status, response.read().decode("utf-8", "ignore")
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode("utf-8", "ignore")


def main() -> int:
    destination = sys.argv[1] if len(sys.argv) > 1 else ""
    settings = mailer._brevo_settings()
    if not settings["api_key"]:
        print("No API key found. Set DESLAB_BREVO_KEY or [brevo] api_key in the secrets file.")
        return 2

    print(f"provider   : {mailer.provider()}")
    print(f"sender     : {settings['sender'] or '(not set)'}")
    print(f"key length : {len(settings['api_key'])}")

    print("\n1) account check")
    status, body = _get("https://api.brevo.com/v3/account", settings["api_key"])
    if status != 200:
        print(f"   FAILED HTTP {status}: {body[:300]}")
        print("   -> the key is wrong, revoked, or the account is not activated yet")
        return 1
    account = json.loads(body)
    print(f"   ok: {account.get('email')} · plan {account.get('plan')} · company {account.get('companyName')}")

    print("\n2) senders")
    status, body = _get("https://api.brevo.com/v3/senders", settings["api_key"])
    if status == 200:
        for sender in json.loads(body).get("senders", []):
            print(f"   {sender.get('email')} · active={sender.get('active')}")
    else:
        print(f"   cannot list senders (HTTP {status})")

    if not destination:
        print("\n3) send test: skipped (pass an address as the first argument)")
        return 0

    print(f"\n3) send test to {destination}")
    ok = mailer.send_welcome(destination, destination.split("@")[0])
    print("   sent" if ok else "   FAILED - see the message above (sender unverified? phone not verified?)")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
