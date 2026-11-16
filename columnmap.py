"""Column-name understanding for Chinese, English and mixed headers.

The original header is never rewritten: it stays as the display name, and this module only proposes
a standard variable name, a unit and a role. When a header carries no unit, no unit is invented.
"""

import re

import ai
import research

# units are matched inside brackets, or as a trailing token - never as letters inside a word,
# otherwise "HBA" would be read as hours
UNITS = [
    ("°c", "°c"), ("℃", "°c"), ("celsius", "°c"), ("c", "°c"),
    ("pct", "%"), ("percent", "%"), ("vv", "v/v"), ("vol", "v/v"),
    ("wt", "wt%"),
    ("mg", "mg"), ("毫克", "mg"),
    ("g", "g"), ("克", "g"),
    ("min", "min"), ("mins", "min"), ("minute", "min"), ("分钟", "min"),
    ("h", "h"), ("hr", "h"), ("hrs", "h"), ("hour", "h"), ("小时", "h"),
    ("%", "%"), ("wt%", "%"), ("percent", "%"), ("百分", "%"),
    ("ml", "ml"), ("l", "l"), ("mpa", "mpa"), ("bar", "bar"), ("rpm", "rpm"),
    ("mol/mol", "mol/mol"), ("w", "w"),
]

# token -> canonical concept; the unit suffix is added afterwards
CONCEPTS = [
    (("木质素", "lignin"), "lignin"),
    (("温度", "temperature", "temp"), "temperature"),
    (("反应时间", "反应时间", "reaction time", "reaction_time", "time", "时间"), "time"),
    (("生物质", "biomass", "原料质量"), "biomass"),
    (("样品编号", "样品", "sample id", "sample_id", "sample", "编号"), "sample_id"),
    (("得率", "产率", "yield"), "yield"),
    (("纯度", "purity"), "purity"),
    (("纤维素", "cellulose"), "cellulose"),
    (("半纤维素", "hemicellulose", "xylan"), "hemicellulose"),
    (("水分", "含水", "moisture", "water"), "moisture"),
    (("压力", "pressure"), "pressure"),
    (("转速", "搅拌", "rpm", "stir"), "stir"),
    (("ph", "酸碱"), "ph"),
    (("时间", "time"), "time"),
]

ROLE_BY_CONCEPT = {
    "sample_id": "metadata",
    "temperature": "independent",
    "time": "independent",
    "biomass": "independent",
    "pressure": "independent",
    "stir": "independent",
    "ph": "independent",
    "moisture": "independent",
    "lignin": "dependent",
    "yield": "dependent",
    "purity": "dependent",
    "cellulose": "dependent",
    "hemicellulose": "dependent",
}

SUFFIX = {"°c": "c", "mg": "mg", "g": "g", "min": "min", "h": "h", "%": "pct",
          "ml": "ml", "l": "l", "mpa": "mpa", "bar": "bar", "rpm": "rpm"}


def _unit(text: str) -> str:
    low = text.lower().replace("（", "(").replace("）", ")")
    inside = re.findall(r"\(([^)]*)\)", low)
    for chunk in inside:
        chunk = chunk.strip()
        for token, unit in UNITS:
            if chunk == token:
                return unit
    # a trailing unit is accepted ("reaction time min", "lignin mg")
    tail = re.split(r"[\s_]+", low.strip())[-1] if low.strip() else ""
    tail = tail.strip("()")
    for token, unit in UNITS:
        if tail == token:
            return unit
    return ""


def _concept(text: str) -> str:
    low = text.lower().replace("（", "(").replace("）", ")")
    best = ""
    for tokens, concept in CONCEPTS:
        for token in tokens:
            if token in low:
                if len(token) > len(best):
                    best = token
                    found = concept
                break
    if not best:
        return ""
    return found


def suggest(original: str) -> dict:
    """Propose name, unit, type, role and a confidence for one original column header."""
    text = str(original or "")
    unit = _unit(text)
    concept = _concept(text)
    role = ROLE_BY_CONCEPT.get(concept, "covariate")
    if concept == "sample_id":
        name, data_type = "sample_id", "text"
    elif concept:
        suffix = SUFFIX.get(unit, "")
        name = f"{concept}_{suffix}" if suffix else concept
        data_type = "number" if suffix else "text"
    else:
        # an unfamiliar header is proposed exactly as written; a blank one has no name at all
        name = research.normalise_name(text)
        data_type = "number" if unit else "text"
    if concept == "sample_id":
        # an identifier needs no unit, so it is not uncertain
        confidence = "high"
    elif concept and unit:
        confidence = "high"
    elif concept:
        confidence = "medium"
    else:
        confidence = "low"
    reason = []
    if concept:
        reason.append(f"recognised as {concept}")
    else:
        reason.append("no known concept in the header")
    if unit:
        reason.append(f"unit {unit}")
    else:
        reason.append("no unit stated, left blank")
    return {"original": text, "name": name, "unit": unit, "data_type": data_type,
            "role": role, "confidence": confidence, "why": "; ".join(reason)}


def suggest_all(columns: list) -> list:
    return [suggest(column) for column in columns]


def needs_review(suggestion: dict) -> bool:
    """A proposal the researcher must look at: no unit, or no recognised concept."""
    return suggestion["confidence"] != "high"


def ai_suggest(columns: list, samples: list, language: str = "en") -> list:
    """Ask the model when a key is configured; the local rules are the fallback."""
    try:
        pairs = ai.normalise_columns(columns, samples, language) or []
    except Exception:
        return suggest_all(columns)
    by_original = {item.get("original"): item for item in pairs if isinstance(item, dict)}
    out = []
    for column in columns:
        local = suggest(column)
        remote = by_original.get(column) or {}
        key = research.normalise_name(remote.get("key") or local["name"]) or local["name"]
        unit = str(remote.get("unit") or "").strip() or local["unit"]
        out.append({**local, "name": key, "unit": unit,
                    "confidence": "high" if remote else local["confidence"],
                    "why": local["why"] + ("; model agreed" if remote else "")})
    return out


def duplicates(suggestions: list) -> dict:
    """Which proposals collide, so the researcher chooses instead of losing a column silently."""
    seen, clashes = {}, {}
    for item in suggestions:
        name = item.get("name")
        if not name:
            continue
        if name in seen:
            clashes.setdefault(name, [seen[name]]).append(item["original"])
        else:
            seen[name] = item["original"]
    return clashes
