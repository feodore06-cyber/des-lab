"""Comparison arithmetic: units, relative differences, replicate statistics, condition sections."""

import math

# factors to a common base per dimension
UNITS = {
    "mass": {"g": 1.0, "mg": 0.001, "kg": 1000.0},
    "time": {"min": 1.0, "h": 60.0, "s": 1.0 / 60.0},
    "percent": {"%": 1.0, "fraction": 100.0},
    "temperature": {"°C": 1.0, "C": 1.0},
}


def unit_family(unit: str) -> str:
    text = str(unit or "").strip()
    for family, table in UNITS.items():
        if text in table:
            return family
    return ""


def convert(value, from_unit: str, to_unit: str):
    """Convert between units of the same family; None when the units are not compatible."""
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    source, target = unit_family(from_unit), unit_family(to_unit)
    if not source or source != target:
        return None
    return number * UNITS[source][str(from_unit).strip()] / UNITS[source][str(to_unit).strip()]


def relative_difference(a, b):
    """Difference as a percentage of the first value; None when it is not meaningful."""
    try:
        first, second = float(a), float(b)
    except (TypeError, ValueError):
        return None
    if first == 0:
        return None
    return (second - first) / abs(first) * 100.0


def replicate_stats(values) -> dict:
    """n, mean and sample standard deviation, skipping anything that is not a number."""
    clean = []
    for value in values or []:
        try:
            clean.append(float(value))
        except (TypeError, ValueError):
            continue
    if not clean:
        return {"n": 0, "mean": None, "sd": None}
    mean = sum(clean) / len(clean)
    if len(clean) < 2:
        return {"n": len(clean), "mean": mean, "sd": None}
    variance = sum((value - mean) ** 2 for value in clean) / (len(clean) - 1)
    return {"n": len(clean), "mean": mean, "sd": math.sqrt(variance)}


def condition_sections(a: dict, b: dict, skip=("sample_id", "notes", "recorded_at", "project")):
    """Split the two rows into identical, differing and missing conditions."""
    identical, differing, missing = {}, {}, {}
    keys = [key for key in list(a) + list(b) if key not in skip]
    seen = set()
    for key in keys:
        if key in seen:
            continue
        seen.add(key)
        left, right = a.get(key), b.get(key)
        if _empty(left) and _empty(right):
            continue
        if _empty(left) or _empty(right):
            missing[key] = {"a": left, "b": right}
            continue
        if _same(left, right):
            identical[key] = left
        else:
            differing[key] = {"a": left, "b": right}
    return {"identical": identical, "differing": differing, "missing": missing}


def rank(runs: list, measure: str) -> list:
    """Order runs by one result, highest first, keeping the unmeasurable ones at the end."""
    scored, unknown = [], []
    for run in runs or []:
        value = run.get(measure)
        try:
            scored.append((float(value), run))
        except (TypeError, ValueError):
            unknown.append(run)
    scored.sort(key=lambda pair: pair[0], reverse=True)
    return [{"run": run, "value": value} for value, run in scored] + \
           [{"run": run, "value": None} for run in unknown]


def _empty(value) -> bool:
    if value is None:
        return True
    if isinstance(value, float) and math.isnan(value):
        return True
    return str(value).strip() == ""


def _same(left, right) -> bool:
    try:
        return abs(float(left) - float(right)) < 1e-9
    except (TypeError, ValueError):
        return str(left).strip().lower() == str(right).strip().lower()
