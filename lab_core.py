"""Explicit mass balance and auditable CSV summaries."""
from io import BytesIO
import csv
import math
import numpy as np
import pandas as pd


def calculate_recipe(components, target_g, basis="active", added_water_g=0):
    if not math.isfinite(target_g) or target_g <= 0:
        raise ValueError("Target mass must be greater than 0.")
    if not math.isfinite(added_water_g) or added_water_g < 0:
        raise ValueError("Extra water cannot be negative.")
    if basis not in ("active", "reagent"):
        raise ValueError("Unknown target-mass basis.")
    data = pd.DataFrame(components).copy()
    if len(data) < 2:
        raise ValueError("Enter at least two components.")
    for col in ["mw", "ratio", "assay_pct", "water_pct"]:
        data[col] = pd.to_numeric(data[col], errors="coerce")
    if not np.isfinite(data[["mw", "ratio", "assay_pct", "water_pct"]].to_numpy()).all():
        raise ValueError("Molar mass, ratio, active content and water must all be finite numbers.")
    if data["name"].isna().any() or data["name"].astype(str).str.strip().eq("").any():
        raise ValueError("Every component needs a name.")
    if (data[["mw", "ratio", "assay_pct"]] <= 0).any().any():
        raise ValueError("Molar mass, molar ratio and active content must be greater than 0.")
    if (data["assay_pct"] > 100).any() or (data["water_pct"] < 0).any():
        raise ValueError("Active content must be ≤100% and water must be ≥0%.")
    if (data["assay_pct"] + data["water_pct"] > 100 + 1e-9).any():
        raise ValueError("Active content plus separate water cannot exceed 100%.")
    fraction = data["assay_pct"] / 100
    weights = data["mw"] * data["ratio"]
    scale = target_g / (weights.sum() if basis == "active" else (weights / fraction).sum())
    data["moles"] = scale * data["ratio"]
    data["active_g"] = scale * weights
    data["weigh_g"] = data["active_g"] / fraction
    data["water_g"] = data["weigh_g"] * data["water_pct"] / 100
    total = float(data["weigh_g"].sum() + added_water_g)
    water = float(data["water_g"].sum() + added_water_g)
    return data, {"total_g": total, "known_water_g": water, "known_water_pct": 100 * water / total}


def read_csv_bytes(content, encoding="utf-8-sig"):
    header = next(csv.reader(content.decode(encoding).splitlines()), [])
    names = [name.strip() for name in header]
    if not names or any(not name for name in names) or len(names) != len(set(names)):
        raise ValueError("CSV headers cannot be empty or duplicated; use comma-separated values.")
    frame = pd.read_csv(BytesIO(content), encoding=encoding)
    frame.columns = frame.columns.str.strip()
    if "_source_file" in frame.columns:
        raise ValueError("_source_file is a reserved column used for source tracking; rename it first.")
    return frame.dropna(how="all")


def merge_results(files, encoding="utf-8-sig"):
    frames = []
    for name, content in files:
        frame = read_csv_bytes(content, encoding)
        frame["_source_file"] = name
        frames.append(frame)
    if not frames:
        raise ValueError("Choose at least one CSV file.")
    return pd.concat(frames, ignore_index=True, sort=False)


def summarize(frame, groups, measurement):
    if not groups or measurement in groups:
        raise ValueError("Choose grouping columns, and do not use the measurement column itself for grouping.")
    numeric = pd.to_numeric(frame[measurement], errors="coerce")
    finite = np.isfinite(numeric)
    missing_groups = frame[groups].isna().any(axis=1)
    for col in groups:
        missing_groups |= frame[col].astype(str).str.strip().eq("")
    valid = finite & ~missing_groups
    clean = frame.loc[valid].copy()
    clean[measurement] = numeric.loc[valid]
    summary = clean.groupby(groups, dropna=False, sort=True)[measurement].agg(
        n="count", mean="mean", sd="std", minimum="min", maximum="max"
    ).reset_index()
    return clean, summary, {"excluded": int((~valid).sum()),
        "invalid_measurement": int((~finite).sum()), "missing_groups": int(missing_groups.sum()),
        "valid_mask": valid}


def csv_bytes(frame):
    safe = frame.copy()
    for col in safe.columns:
        safe[col] = safe[col].map(lambda v: "'" + v if isinstance(v, str) and v.lstrip().startswith(("=", "+", "-", "@")) else v)
    safe.columns = ["'" + str(c) if str(c).lstrip().startswith(("=", "+", "-", "@")) else c for c in safe.columns]
    return safe.to_csv(index=False).encode("utf-8-sig")
