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
    "You read a paper's text and copy out the numbers that describe its experiment. You are given a "
    "list of variable names the lab records. For each one, if the paper states a value, return it as "
    "a number in a JSON object; if the paper does not state it, leave that key out entirely. Also "
    "return reported_result with the paper's own headline number for the same measurement, and quote "
    "with the sentence you took it from. Never guess: an omitted key is better than an invented "
    "number."
)


def extract_comparison(variables: list, title: str, paper_text: str,
                       language: str = "en") -> dict:
    """Copy the paper's numbers out of a title plus the text the user pasted.

    Returns {"values": {variable: number}, "reported_result": number or None, "quote": str}, or an
    empty dict when nothing usable came back.
    """
    config = settings()
    if not config["key"] or not (title.strip() or paper_text.strip()):
        return {}
    payload = {
        "model": config["model"],
        "temperature": 0.0,
        "messages": [
            {"role": "system", "content": EXTRACT_SYSTEM},
            {"role": "user", "content": json.dumps(
                {"variables": variables, "title": title, "paper_text": paper_text[:6000]},
                ensure_ascii=False)},
        ],
    }
    request = urllib.request.Request(
        config["base"] + "/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json",
                 "Authorization": "Bearer " + config["key"]},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
            body = json.load(response)
        raw = str(body["choices"][0]["message"]["content"]).strip()
        for fence in ("```json", "```"):
            raw = raw.replace(fence, "")
        parsed = json.loads(raw.strip())
    except (urllib.error.URLError, TimeoutError, OSError, KeyError, ValueError, IndexError,
            json.JSONDecodeError):
        return {}
    if not isinstance(parsed, dict):
        return {}

    # accept both shapes: values nested under a key, or the variable names at the top level
    flat = parsed.get("values")
    if not isinstance(flat, dict) or not flat:
        flat = {key: value for key, value in parsed.items() if key in variables}
    values = {}
    for key, value in flat.items():
        if key in variables:
            try:
                values[key] = float(value)
            except (TypeError, ValueError):
                continue
    result = parsed.get("reported_result")
    try:
        result = float(result) if result is not None else None
    except (TypeError, ValueError):
        result = None
    return {"values": values, "reported_result": result, "quote": str(parsed.get("quote") or "")}

SUGGEST_SYSTEM = (
    "You propose the variables a scientific experiment project should record, given its name. "
    "Return a JSON array of objects with exactly two keys: "
    "key (a snake_case identifier, with the unit in the name, e.g. shear_strength_MPa) and "
    "why (one short sentence saying what it changes). Give the variables that actually drive the "
    "result first, then the ones that describe the result. At most 8, no prose outside the JSON."
)


def suggest_variables(project_name: str, language: str = "en") -> list:
    """Propose the variables worth recording for a project, or [] when unavailable."""
    config = settings()
    name = str(project_name or "").strip()
    if not config["key"] or not name:
        return []
    payload = {
        "model": config["model"],
        "temperature": 0.2,
        "messages": [
            {"role": "system", "content": SUGGEST_SYSTEM},
            {"role": "user", "content": json.dumps({"project": name, "language": language},
                                                   ensure_ascii=False)},
        ],
    }
    request = urllib.request.Request(
        config["base"] + "/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json",
                 "Authorization": "Bearer " + config["key"]},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
            body = json.load(response)
        raw = str(body["choices"][0]["message"]["content"]).strip()
        for fence in ("```json", "```"):
            raw = raw.replace(fence, "")
        parsed = json.loads(raw.strip())
    except (urllib.error.URLError, TimeoutError, OSError, KeyError, ValueError, IndexError,
            json.JSONDecodeError):
        return []
    if not isinstance(parsed, list):
        return []
    seen, out = set(), []
    for item in parsed:
        if isinstance(item, dict) and item.get("key"):
            key = str(item["key"]).strip()
        elif isinstance(item, str):
            key = item.strip()
        else:
            continue
        if not key or key in seen:
            continue
        seen.add(key)
        out.append({"key": key, "why": str(item.get("why", "")).strip()
                    if isinstance(item, dict) else ""})
    return out[:8]

RESULT_STEMS = ("yield", "recovery", "strength", "purity", "efficiency", "conversion",
                "retention", "content", "performance", "activity")
CONDITION_STEMS = ("temperature", "time", "ratio", "pressure", "speed", "rpm", "ph", "volume",
                   "mass", "purity", "purity_pct")


def guess_result(variables: list) -> str:
    """Pick the variable that reads like the measured outcome rather than a condition.

    This is a guess from the names alone; the project can always set it explicitly.
    """
    names = [str(value) for value in variables or []]
    if not names:
        return ""
    scored = []
    for name in names:
        low = name.lower()
        score = 0
        if any(stem in low for stem in RESULT_STEMS):
            score += 3
        if low.endswith(("_pct", "_percent", "_MPa", "_mg", "_g_per_g")):
            score += 2
        if any(stem in low for stem in CONDITION_STEMS):
            score -= 2
        scored.append((score, name))
    scored.sort(key=lambda pair: pair[0], reverse=True)
    return scored[0][1] if scored and scored[0][0] > 0 else ""

ROLE_WORDS = {
    "result": ("yield", "recovery", "strength", "purity", "efficiency", "conversion",
               "retention", "performance", "activity", "selectivity", "content", "rate",
               "degree", "improvement", "increase", "output", "recovered", "obtained",
               "measured", "mass_balance"),
    "parameter": ("temperature", "time", "ratio", "pressure", "speed", "rpm", "ph",
                  "volume", "mass", "concentration", "loading", "dosage", "flow",
                  "power", "frequency", "mesh", "size", "humidity", "method", "catalyst",
                  "solvent", "atmosphere", "mode", "type"),
    "identifier": ("sample", "batch", "lot", "operator", "date", "id"),
}


def role_of(name: str, unit: str = "", description: str = "") -> str:
    """Guess a variable's scientific role from its name and unit.

    parameter = something you set, result = something you measure and optimise,
    identifier = a label, covariate = anything else worth recording.
    """
    low = str(name or "").lower()
    if any(word in low for word in ROLE_WORDS["identifier"]) and not unit:
        return "identifier"
    if any(word in low for word in ROLE_WORDS["result"]):
        return "result"
    if any(word in low for word in ROLE_WORDS["parameter"]):
        return "parameter"
    # a percentage with no other clue is usually an outcome
    if str(unit or "").strip() == "%" and not any(word in low for word in ROLE_WORDS["parameter"]):
        return "result"
    return "covariate"


def classify_variables(project_name: str, description: str, variables: list) -> list:
    """Ask the model what each variable is for; fall back to the words in its name."""
    config = settings()
    names = [str(value) for value in variables or []]
    if not names:
        return []
    guessed = [{"name": name, "role": role_of(name), "unit": "",
                "why": "read from the variable name"} for name in names]
    if not config["key"]:
        return guessed
    system = (
        "You classify the variables of a scientific experiment. For each variable decide one role: "
        "parameter (a condition the experimenter sets), result (a measured outcome that is optimised), "
        "identifier (a label), covariate (recorded but neither). Also give the unit if the name implies "
        "one. Answer with a JSON array of objects {name, role, unit, why}; keep the names exactly."
    )
    payload = {"model": config["model"], "temperature": 0.0, "messages": [
        {"role": "system", "content": system},
        {"role": "user", "content": json.dumps(
            {"project": project_name, "description": description, "variables": names},
            ensure_ascii=False)}]}
    request = urllib.request.Request(
        config["base"] + "/chat/completions", data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json",
                 "Authorization": "Bearer " + config["key"]}, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
            body = json.load(response)
        raw = str(body["choices"][0]["message"]["content"]).strip()
        for fence in ("```json", "```"):
            raw = raw.replace(fence, "")
        parsed = json.loads(raw.strip())
    except (urllib.error.URLError, TimeoutError, OSError, KeyError, ValueError, IndexError,
            json.JSONDecodeError):
        return guessed
    if not isinstance(parsed, list):
        return guessed
    by_name = {str(item.get("name")): item for item in parsed if isinstance(item, dict)}
    out = []
    for name in names:
        item = by_name.get(name) or {}
        role = str(item.get("role") or "").strip().lower()
        out.append({"name": name, "role": role if role in
                    ("parameter", "result", "identifier", "covariate") else role_of(name),
                    "unit": str(item.get("unit") or "").strip(),
                    "why": str(item.get("why") or "").strip()})
    return out
