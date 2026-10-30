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

EXTRACT_SYSTEM = (
    "Read a paper's title and abstract and extract ONLY values that are explicitly stated. "
    "Return a JSON object with these keys and nothing else: feedstock, molar_ratio (number, HBD:HBA), "
    "purity_wt_pct, water_wt_pct, temperature_C, time_min, lignin_yield_pct, basis, quote, found. "
    "Use null for a key that is not stated. 'quote' is the short sentence from the abstract that "
    "contains the numbers you used (empty if none). 'found' is the number of keys that are not null. "
    "Never guess and never convert units you are unsure about."
)


def extract_from_paper(title: str, abstract: str) -> dict:
    """Return the values explicitly stated in a paper; {} when unavailable."""
    config = settings()
    if not config["key"] or not abstract:
        return {}
    payload = {
        "model": config["model"],
        "temperature": 0.0,
        "messages": [
            {"role": "system", "content": EXTRACT_SYSTEM},
            {"role": "user", "content": json.dumps({"title": title, "abstract": abstract[:4000]},
                                                   ensure_ascii=False)},
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
    return parsed if isinstance(parsed, dict) else {}

SUGGEST_SYSTEM = (
    "You design the data table for a new experiment in a biomaterials lab. Given a short project "
    "name, list the variables worth recording for every run. Return a JSON array of objects, each "
    "with 'key' (snake_case, unit in the name when it applies, e.g. temperature_C, time_min, "
    "stirring_rpm) and 'why' (at most 8 words, in the requested language). Between 4 and 9 entries. "
    "Prefer measurable numbers over free text. Always include the result the lab would report. "
    "No duplicates, no prose outside the JSON."
)


def suggest_variables(project_name: str, language: str = "en") -> list:
    """Ask for variable keys that fit a project name. Returns [] when no model is configured."""
    name = " ".join(str(project_name or "").split())
    if not name:
        return []
    config = settings()
    if not config["key"]:
        return []
    payload = {
        "model": config["model"],
        "temperature": 0.4,
        "messages": [
            {"role": "system", "content": SUGGEST_SYSTEM},
            {"role": "user", "content": json.dumps(
                {"project": name, "answer_in": "Chinese" if language == "zh" else "English"},
                ensure_ascii=False)},
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
        return []
    if not isinstance(parsed, list):
        return []
    clean = []
    for item in parsed:
        if isinstance(item, dict) and item.get("key"):
            key = " ".join(str(item["key"]).split()).replace(" ", "_")[:32]
            clean.append({"key": key, "why": str(item.get("why") or "")[:60]})
        elif isinstance(item, str):
            clean.append({"key": " ".join(item.split()).replace(" ", "_")[:32], "why": ""})
    return [item for item in clean if item["key"]]

COLUMNS_SYSTEM = (
    "You receive the header row of a spreadsheet from a biomaterials lab, plus a few example rows. "
    "Map every column to a clean snake_case key with its unit in the name when the unit is evident "
    "(temperature_C, time_min, lignin_yield_pct). Keep the original order. If two columns mean the "
    "same thing, give them the same key. Return a JSON array of objects with 'original' and 'key'. "
    "No prose, one entry per input column."
)


def normalise_columns(columns: list, sample: list, language: str = "en") -> list:
    """Return [{original, key}] for a spreadsheets headers, or [] when no model is configured."""
    config = settings()
    if not config["key"] or not columns:
        return []
    payload = {
        "model": config["model"],
        "temperature": 0.0,
        "messages": [
            {"role": "system", "content": COLUMNS_SYSTEM},
            {"role": "user", "content": json.dumps(
                {"columns": [str(value) for value in columns], "sample_rows": sample[:3],
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
        raw = str(body["choices"][0]["message"]["content"]).strip()
        raw = raw.removeprefix("```json").removeprefix("```").removesuffix("```").strip()
        parsed = json.loads(raw)
    except (urllib.error.URLError, TimeoutError, OSError, KeyError, ValueError, IndexError,
            json.JSONDecodeError):
        return []
    if not isinstance(parsed, list):
        return []
    pairs = []
    for item in parsed:
        if isinstance(item, dict) and item.get("original") and item.get("key"):
            pairs.append({"original": str(item["original"]),
                          "key": " ".join(str(item["key"]).split()).replace(" ", "_")[:32]})
    return pairs
