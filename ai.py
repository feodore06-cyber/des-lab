# -*- coding: utf-8 -*-
"""Optional language-model layer for the comparison screen.

The rule engine in compare.py stays the source of truth for every number: the model only rewrites the
reasoning in prose, and it is told to never invent a value. Without a key the app simply keeps the
deterministic explanations, so nothing breaks on a deployment that has no AI configured.

Configuration (Streamlit secrets or environment):

    [ai]
    key = "sk-..."
    base_url = "https://api.deepseek.com/v1"     # any OpenAI-compatible endpoint
    model = "deepseek-chat"

    or DESLAB_AI_KEY / DESLAB_AI_BASE / DESLAB_AI_MODEL
"""
from __future__ import annotations

import json
import urllib.error
import urllib.request

TIMEOUT = 45
SYSTEM = (
    "You are a careful materials-science mentor. You are given two experiments (yields and conditions) "
    "and a machine-checked list of differences. Write a short, calm analysis in the requested language: "
    "what most likely explains the gap, in order, and one concrete next measurement. Rules: never invent "
    "numbers that are not in the input; never say somebody made a mistake; if the two experiments differ "
    "in material or formulation, say plainly that the comparison is descriptive rather than causal. "
    "Maximum 150 words, no headings, no bullet lists."
)


def _secret(section: str, field: str, env: str, default: str = "") -> str:
    """Read an AI setting from the environment, then from a [section] block of the secrets."""
    import os

    value = os.environ.get(env)
    if not value:
        try:
            import streamlit as st

            block = st.secrets.get(section) or {}
            value = block.get(field)
        except Exception:
            value = None
    return str(value).strip() if value else default


def settings() -> dict:
    return {
        "key": _secret("ai", "key", "DESLAB_AI_KEY"),
        "base": _secret("ai", "base_url", "DESLAB_AI_BASE",
                        "https://api.openai.com/v1").rstrip("/"),
        "model": _secret("ai", "model", "DESLAB_AI_MODEL", "gpt-4o-mini"),
    }


def available() -> bool:
    return bool(settings()["key"])


def _payload(mine: dict, theirs: dict, diff: list, language: str) -> dict:
    keep = ("sample_id", "formulation", "feedstock", "des_hba", "des_hbd", "molar_ratio",
            "purity_wt_pct", "water_wt_pct", "biomass_g", "temperature_C", "time_min",
            "lignin_mg", "lignin_yield_pct", "basis", "replicates")
    clean = lambda row: {key: row.get(key) for key in keep if row.get(key) is not None}  # noqa: E731
    user = {
        "first_experiment": clean(mine),
        "second_experiment": clean(theirs),
        "machine_checked_differences": diff,
        "answer_in": "Chinese" if language == "zh" else "English",
    }
    return {
        "model": settings()["model"],
        "temperature": 0.2,
        "messages": [
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": json.dumps(user, ensure_ascii=False, default=str)},
        ],
    }


def analyse(mine: dict, theirs: dict, differences: list, language: str = "en") -> str | None:
    """Return a written analysis, or None when no model is configured or the call fails."""
    config = settings()
    if not config["key"]:
        return None
    request = urllib.request.Request(
        f"{config['base']}/chat/completions",
        data=json.dumps(_payload(mine, theirs, differences, language)).encode("utf-8"),
        headers={"Content-Type": "application/json",
                 "Authorization": f"Bearer {config['key']}"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
            body = json.load(response)
        return str(body["choices"][0]["message"]["content"]).strip() or None
    except (urllib.error.URLError, TimeoutError, OSError, KeyError, ValueError, IndexError):
        return None

ASK_SYSTEM = (
    "You are a materials-science mentor answering a follow-up question about two experiments the "
    "user can see. Use only the numbers given. If the data cannot answer the question, say what "
    "measurement would. Be concise (120 words), plain, and never blame the user."
)


def ask(question: str, context: dict, language: str = "en") -> str | None:
    """Answer a free-form question about the comparison on screen."""
    text = " ".join(str(question or "").split())
    if not text:
        return None
    config = settings()
    if not config["key"]:
        return None
    payload = {
        "model": config["model"],
        "temperature": 0.3,
        "messages": [
            {"role": "system", "content": ASK_SYSTEM},
            {"role": "user", "content": json.dumps(
                {"question": text, "context": context,
                 "answer_in": "Chinese" if language == "zh" else "English"},
                ensure_ascii=False, default=str)},
        ],
    }
    request = urllib.request.Request(
        f"{config['base']}/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json",
                 "Authorization": f"Bearer {config['key']}"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
            body = json.load(response)
        return str(body["choices"][0]["message"]["content"]).strip() or None
    except (urllib.error.URLError, TimeoutError, OSError, KeyError, ValueError, IndexError):
        return None

SUMMARY_SYSTEM = (
    "You summarise research papers for a lab that works on deep eutectic solvents and lignin. "
    "For each item you receive a title and an abstract. Return a JSON array of strings, one per "
    "item, in the same order. Each string is at most 25 words, in the requested language, saying "
    "what the paper did and what it found. No preamble, no markdown, no numbering. If the abstract "
    "is missing, write a single sentence saying what the title implies and add (title only)."
)


def summarise_papers(items: list, language: str = "en") -> dict:
    """Map index -> one-sentence summary. Returns {} when no model is configured or on failure."""
    config = settings()
    if not config["key"] or not items:
        return {}
    payload = {
        "model": config["model"],
        "temperature": 0.2,
        "messages": [
            {"role": "system", "content": SUMMARY_SYSTEM},
            {"role": "user", "content": json.dumps(
                {"papers": items, "answer_in": "Chinese" if language == "zh" else "English"},
                ensure_ascii=False, default=str)},
        ],
    }
    request = urllib.request.Request(
        f"{config['base']}/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json",
                 "Authorization": f"Bearer {config['key']}"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
            body = json.load(response)
        raw = str(body["choices"][0]["message"]["content"]).strip()
        raw = raw.removeprefix("```json").removeprefix("```").removesuffix("```").strip()
        parsed = json.loads(raw)
    except (urllib.error.URLError, TimeoutError, OSError, KeyError, ValueError, IndexError,
            json.JSONDecodeError):
        return {}
    if not isinstance(parsed, list):
        return {}
    return {index: str(value).strip() for index, value in enumerate(parsed) if str(value).strip()}
