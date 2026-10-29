# -*- coding: utf-8 -*-
"""Read experiment tables out of Excel files the way a human wrote them.

Lab sheets rarely start at A1: there is a title, a note, sometimes a blank row, merged cells, units
inside the header, and Chinese column names. This module finds the header row, maps the columns it
recognises onto canonical names, and leaves everything else alone.
"""
from __future__ import annotations

import io
import re
from typing import Iterable

import pandas as pd

import schema

# canonical name -> patterns that identify it (lower-case, no spaces/punctuation)
SYNONYMS: dict[str, tuple[str, ...]] = {
    "sample_id": ("sampleid", "sample", "id", "code", "number", "no", "样品编号", "样品", "编号", "试样"),
    "formulation": ("formulation", "des", "solvent", "system", "condition", "配方", "体系", "条件"),
    "feedstock": ("feedstock", "substrate", "rawmaterial", "biomasssource", "原料", "生物质种类"),
    "des_hba": ("hba", "hydrogenbondacceptor", "acceptor", "氢键受体", "组分a"),
    "des_hbd": ("hbd", "hydrogenbonddonor", "donor", "氢键供体", "组分b"),
    "molar_ratio": ("molarratio", "hbdhba", "ratio", "摩尔比", "比例", "配比"),
    "biomass_g": ("biomassg", "biomass", "biomassmass", "feedstock", "substrate", "生物质", "生物质质量",
                  "原料", "木粉"),
    "lignin_mg": ("ligninmg", "ligninmass", "lignin", "recoveredlignin", "木质素", "木质素质量", "回收木质素"),
    "lignin_yield_pct": ("ligninyieldpct", "ligninyield", "yield", "yieldpct", "yieldpercent", "得率",
                         "木质素得率", "产率"),
    "temperature_C": ("temperaturec", "temperature", "temp", "温度"),
    "time_min": ("timemin", "time", "duration", "reactiontime", "时间", "反应时间"),
    "purity_wt_pct": ("purity", "puritywt", "puritypct", "assay", "纯度", "含量"),
    "water_wt_pct": ("water", "waterwt", "waterpct", "moisture", "水分", "含水"),
    "replicate": ("replicate", "rep", "run", "trial", "重复", "重复编号", "平行"),
    "notes": ("notes", "note", "comment", "remark", "备注", "说明"),
}

UNITS = {
    "biomass_g": "g",
    "lignin_mg": "mg",
    "lignin_yield_pct": "%",
    "temperature_C": "°C",
    "time_min": "min",
}

HEADER_SCAN_ROWS = 25


def _clean(text: object) -> str:
    """Lower-case, strip spaces/punctuation/units so 'Lignin (mg)' and '木质素质量(mg)' can match."""
    value = str(text or "")
    value = value.replace("（", "(").replace("）", ")").replace("：", ":").replace("／", "/")
    value = re.sub(r"\(.*?\)", "", value)          # drop the unit bracket
    value = re.sub(r"[^0-9A-Za-z\u4e00-\u9fff]+", "", value)
    return value.lower()


def match_column(name: object) -> str | None:
    """Canonical field for one column header, or None when it is not something we know."""
    cleaned = _clean(name)
    if not cleaned:
        return None
    for canonical, patterns in SYNONYMS.items():
        for pattern in patterns:
            if cleaned == pattern:
                return canonical
    for canonical, patterns in SYNONYMS.items():
        for pattern in patterns:
            if len(pattern) >= 4 and pattern in cleaned:
                return canonical
    return None


def read_workbook(content: bytes) -> list[tuple[str, pd.DataFrame]]:
    """Every sheet as a raw DataFrame with no header assumption."""
    buffer = io.BytesIO(content)
    sheets = pd.read_excel(buffer, sheet_name=None, header=None, dtype=object)
    return list(sheets.items())


def find_header_row(raw: pd.DataFrame) -> int | None:
    """The row that looks most like a header: several distinct short texts, mostly non-empty."""
    best_row, best_score = None, 0
    limit = min(len(raw), HEADER_SCAN_ROWS)
    for index in range(limit):
        row = raw.iloc[index]
        cells = [cell for cell in row.tolist() if isinstance(cell, str) and cell.strip()]
        if len(cells) < 2:
            continue
        recognised = sum(1 for cell in row.tolist() if match_column(cell))
        score = recognised * 3 + len(cells)
        if score > best_score:
            best_row, best_score = index, score
    return best_row


def read_table(content: bytes, sheet: str | None = None) -> dict:
    """Turn workbook bytes into a tidy frame plus what had to be guessed.

    Returns ``{"frame": DataFrame, "sheet": name, "header_row": int, "mapping": {original: canonical},
    "unknown": [original names], "rows": int}``.
    """
    sheets = read_workbook(content)
    if not sheets:
        raise ValueError("The workbook has no sheets.")

    candidates = [(name, raw) for name, raw in sheets]
    if sheet is not None:
        candidates = [(name, raw) for name, raw in candidates if name == sheet] or candidates

    best = None
    for name, raw in candidates:
        header_row = find_header_row(raw)
        if header_row is None:
            continue
        header = [str(cell).strip() if cell is not None else "" for cell in raw.iloc[header_row].tolist()]
        recognised = sum(1 for cell in header if match_column(cell))
        if best is None or recognised > best[3]:
            best = (name, raw, header_row, recognised)
    if best is None:
        raise ValueError("Could not find a header row in any sheet.")

    sheet_name, raw, header_row, _ = best
    header = [str(cell).strip() if cell is not None else "" for cell in raw.iloc[header_row].tolist()]
    body = raw.iloc[header_row + 1:].reset_index(drop=True)
    body.columns = [name or f"column_{i + 1}" for i, name in enumerate(header)]
    body = body.dropna(how="all").dropna(axis=1, how="all")

    mapping, unknown = {}, []
    renamed = {}
    for name in body.columns:
        canonical = match_column(name)
        if canonical and canonical not in renamed.values():
            renamed[name] = canonical
            mapping[name] = canonical
        elif canonical:
            unknown.append(name)          # a second column with the same meaning: keep the name
        else:
            unknown.append(name)
    frame = body.rename(columns=renamed)

    # merged cells only carry a value in the first row: fill the identifying columns downwards
    for column in ("sample_id", "formulation", "feedstock", "des_hba", "des_hbd",
                   "temperature_C", "time_min"):
        if column in frame.columns:
            frame[column] = frame[column].ffill()

    frame = add_missing_yield(frame)
    # a sheet that only carries the old free-text label still yields the structured fields, and a
    # sheet that only carries structured columns gets a human-readable label
    frame = schema.backfill(frame)
    if "formulation" not in frame.columns and {"des_hba", "des_hbd"} <= set(frame.columns):
        frame["formulation"] = [schema.build_formulation(row) for _, row in frame.iterrows()]
    frame = frame.dropna(how="all").reset_index(drop=True)
    return {
        "frame": frame,
        "sheet": sheet_name,
        "header_row": header_row + 1,
        "mapping": mapping,
        "unknown": unknown,
        "rows": len(frame),
    }


def add_missing_yield(frame: pd.DataFrame) -> pd.DataFrame:
    """Compute lignin yield where it is missing but biomass and lignin mass are present."""
    if not {"biomass_g", "lignin_mg"} <= set(frame.columns):
        return frame
    frame = frame.copy()
    biomass = pd.to_numeric(frame["biomass_g"], errors="coerce")
    lignin = pd.to_numeric(frame["lignin_mg"], errors="coerce")
    computed = (lignin / (biomass * 1000.0) * 100.0).round(4)
    if "lignin_yield_pct" in frame.columns:
        stored = pd.to_numeric(frame["lignin_yield_pct"], errors="coerce")
        frame["lignin_yield_pct"] = stored.where(stored.notna(), computed)
    else:
        frame["lignin_yield_pct"] = computed
    return frame


def to_csv_bytes(frame: pd.DataFrame) -> bytes:
    return frame.to_csv(index=False).encode("utf-8-sig")


def is_excel(filename: str) -> bool:
    return str(filename).lower().endswith((".xlsx", ".xlsm", ".xls"))
