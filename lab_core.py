"""Explicit mass balance and auditable CSV summaries."""
from io import BytesIO
import csv
import math
import numpy as np
import pandas as pd


def calculate_recipe(components, target_g, basis="active", added_water_g=0):
    if not math.isfinite(target_g) or target_g <= 0:
        raise ValueError("目标质量必须大于 0。")
    if not math.isfinite(added_water_g) or added_water_g < 0:
        raise ValueError("额外加水量不能为负数。")
    if basis not in ("active", "reagent"):
        raise ValueError("未知的质量基准。")
    data = pd.DataFrame(components).copy()
    if len(data) < 2:
        raise ValueError("至少填写两种组分。")
    for col in ["mw", "ratio", "assay_pct", "water_pct"]:
        data[col] = pd.to_numeric(data[col], errors="coerce")
    if not np.isfinite(data[["mw", "ratio", "assay_pct", "water_pct"]].to_numpy()).all():
        raise ValueError("摩尔质量、比例、含量和水分必须是有限数值。")
    if data["name"].isna().any() or data["name"].astype(str).str.strip().eq("").any():
        raise ValueError("每种组分都需要名称。")
    if (data[["mw", "ratio", "assay_pct"]] <= 0).any().any():
        raise ValueError("摩尔质量、摩尔份数和有效含量必须大于 0。")
    if (data["assay_pct"] > 100).any() or (data["water_pct"] < 0).any():
        raise ValueError("有效含量须 ≤100%，水分须 ≥0%。")
    if (data["assay_pct"] + data["water_pct"] > 100 + 1e-9).any():
        raise ValueError("有效含量 + 独立水分不能超过 100%。")
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
        raise ValueError("CSV 表头不能为空或重复；请使用逗号分隔。")
    frame = pd.read_csv(BytesIO(content), encoding=encoding)
    frame.columns = frame.columns.str.strip()
    if "_source_file" in frame.columns:
        raise ValueError("_source_file 是来源追踪保留列，请先重命名。")
    return frame.dropna(how="all")


def merge_results(files, encoding="utf-8-sig"):
    frames = []
    for name, content in files:
        frame = read_csv_bytes(content, encoding)
        frame["_source_file"] = name
        frames.append(frame)
    if not frames:
        raise ValueError("请先选择 CSV 文件。")
    return pd.concat(frames, ignore_index=True, sort=False)


def summarize(frame, groups, measurement):
    if not groups or measurement in groups:
        raise ValueError("请选择分组列，且不要把测量值本身作为分组列。")
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
