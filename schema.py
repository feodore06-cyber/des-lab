# -*- coding: utf-8 -*-
"""Canonical, machine-readable columns for a DES-pretreatment experiment.

The whole point is that a row written by one intern means exactly the same thing as a row written by
another - numbers instead of the free-text "formulation" string, so the dataset is directly usable
for training a model. ``formulation`` is kept only as a human-readable label.
"""
from __future__ import annotations

import re

import pandas as pd

# the AI-relevant schema, in the order the record form shows it
SCHEMA_COLUMNS = [
    "sample_id", "feedstock", "des_hba", "des_hbd", "molar_ratio",
    "purity_wt_pct", "water_wt_pct", "biomass_g", "temperature_C", "time_min",
    "lignin_mg", "lignin_yield_pct", "replicate", "notes", "recorded_at", "recorded_by",
]

CANONICAL = {
    "chcl": "ChCl", "choline chloride": "ChCl", "氯化胆碱": "ChCl", "胆碱": "ChCl",
    "ga": "Glyoxylic acid", "glyoxylic acid": "Glyoxylic acid", "乙醛酸": "Glyoxylic acid",
    "lactic acid": "Lactic acid", "乳酸": "Lactic acid",
    "citric acid": "Citric acid", "柠檬酸": "Citric acid",
    "oxalic acid": "Oxalic acid", "草酸": "Oxalic acid",
    "urea": "Urea", "尿素": "Urea",
    "glycerol": "Glycerol", "甘油": "Glycerol",
    "ethylene glycol": "Ethylene glycol", "乙二醇": "Ethylene glycol",
}

RATIO_RE = re.compile(r"(\d+(?:\.\d+)?)\s*[:：]\s*(\d+(?:\.\d+)?)")


def canonical_name(token: str) -> str:
    cleaned = (token or "").strip()
    return CANONICAL.get(cleaned.lower(), cleaned)


def parse_formulation(text: object) -> dict:
    """Turn "ChCl:GA 1:2" or "ChCl-GA 1:1" into structured fields, if it can."""
    raw = str(text or "").strip()
    if not raw:
        return {}
    match = RATIO_RE.search(raw)
    ratio = None
    if match:
        try:
            ratio = round(float(match.group(2)) / float(match.group(1)), 4)
        except ZeroDivisionError:
            ratio = None
    head = raw[: match.start()] if match else raw
    parts = [part.strip() for part in re.split(r"[-:/_]+", head) if part.strip()]
    result = {}
    if len(parts) >= 1:
        result["des_hba"] = canonical_name(parts[0])
    if len(parts) >= 2:
        result["des_hbd"] = canonical_name(parts[1])
    if ratio is not None:
        result["molar_ratio"] = ratio
    return result


def build_formulation(row) -> str:
    """The human label: "ChCl:Glyoxylic acid 1:2"."""
    hba = str(row.get("des_hba") or "").strip()
    hbd = str(row.get("des_hbd") or "").strip()
    ratio = row.get("molar_ratio")
    parts = [part for part in (hba, hbd) if part]
    text = ":".join(parts)
    if ratio is not None and pd.notna(ratio) and parts:
        value = float(ratio)
        if value >= 1 and abs(value - round(value)) < 1e-6:
            label = f"1:{int(round(value))}"
        elif 0 < value < 1 and abs(1 / value - round(1 / value)) < 1e-6:
            label = f"{int(round(1 / value))}:1"
        else:
            label = f"{value:g}"
        text = f"{text} {label}"
    return text


def backfill(frame: pd.DataFrame) -> pd.DataFrame:
    """Normalise the structured columns and fill them from an old 'formulation' string.

    Existing values always win; a table that has neither a label nor structured columns is left
    untouched, so unrelated tables are not given empty columns.
    """
    if frame is None or frame.empty:
        return frame
    has_structured = any(column in frame.columns for column in ("des_hba", "des_hbd", "molar_ratio"))
    if "formulation" not in frame.columns and not has_structured:
        return frame
    frame = frame.copy()
    for column in ("des_hba", "des_hbd", "molar_ratio"):
        if column not in frame.columns:
            frame[column] = None
    # a sheet may hold "氯化胆碱" in the HBA column: canonicalise before anything else
    for column in ("des_hba", "des_hbd"):
        frame[column] = [canonical_name(value) if isinstance(value, str) and value.strip() else value
                         for value in frame[column]]
    if "formulation" in frame.columns:
        for index, row in frame.iterrows():
            if pd.isna(row.get("formulation")):
                continue
            parsed = parse_formulation(row["formulation"])
            for column in ("des_hba", "des_hbd", "molar_ratio"):
                if column in parsed and pd.isna(row.get(column)):
                    frame.at[index, column] = parsed[column]
    return frame


def row_to_schema(row: dict) -> dict:
    """A new record: structured fields plus a derived formulation label."""
    record = dict(row)
    if not record.get("formulation"):
        record["formulation"] = build_formulation(record)
    return record
