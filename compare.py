# -*- coding: utf-8 -*-
"""Compare one of your runs with a value reported in a paper, and explain the gap.

The explanations are ordered on purpose: **definition first, then chemistry, then technique**. In
practice most "our number does not match the paper" cases turn out to be different definitions or a
different basis, not a mistake by either lab. Every statement here is a hypothesis with a way to test
it, never a verdict - which also keeps the conversation with a supervisor calm.

This module stays language-neutral: it returns codes and numbers, and the interface turns them into
English or Chinese sentences.
"""
from __future__ import annotations


def severity(temperature_c, minutes) -> float:
    """Classic severity factor: log(R0) = log(t) + (T-100)/14.75."""
    try:
        heat = (float(temperature_c) - 100.0) / 14.75
        time = max(float(minutes), 1e-6)
        return round(time * 10 ** heat, 4)
    except (TypeError, ValueError):
        return 0.0


def effective_ratio(ratio, purity_pct) -> float:
    """The ratio you actually mixed: a 90 % reagent carries 10 % that is not the reagent."""
    try:
        return round(float(ratio) * float(purity_pct) / 100.0, 4)
    except (TypeError, ValueError):
        return float(ratio or 0)


def _number(value, default=None):
    try:
        if value in (None, ""):
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _text(value) -> str:
    return " ".join(str(value or "").split())


def _finding(code: str, weight: int, kind: str, **params) -> dict:
    return {"code": code, "weight": weight, "kind": kind, "params": params}


def compare(mine: dict, theirs: dict) -> dict:
    """Return the deltas and the ranked explanations (as codes the interface can translate)."""
    m_yield = _number(mine.get("lignin_yield_pct"))
    t_yield = _number(theirs.get("lignin_yield_pct"))
    delta = None if (m_yield is None or t_yield is None) else round(m_yield - t_yield, 4)
    relative = None
    if delta is not None and t_yield:
        relative = round(delta / t_yield * 100.0, 1)

    findings = []

    mine_basis = _text(mine.get("basis"))
    their_basis = _text(theirs.get("basis"))
    if mine_basis and their_basis and mine_basis != their_basis:
        findings.append(_finding("definition", 100, "definition",
                                 mine=mine_basis, theirs=their_basis))

    if _number(mine.get("moisture_wt_pct")) is None or _number(theirs.get("moisture_wt_pct")) is None:
        findings.append(_finding("moisture", 80, "basis"))

    m_purity, t_purity = _number(mine.get("purity_wt_pct")), _number(theirs.get("purity_wt_pct"))
    if m_purity is not None and t_purity is not None and abs(m_purity - t_purity) >= 2:
        findings.append(_finding("purity", 70, "chemistry",
                                 mine=m_purity, theirs=t_purity,
                                 mine_eff=effective_ratio(mine.get("molar_ratio"), m_purity),
                                 theirs_eff=effective_ratio(theirs.get("molar_ratio"), t_purity)))

    m_water, t_water = _number(mine.get("water_wt_pct")), _number(theirs.get("water_wt_pct"))
    if m_water is not None and t_water is not None and abs(m_water - t_water) >= 2:
        findings.append(_finding("water", 60, "chemistry",
                                 mine=m_water, theirs=t_water, gap=abs(m_water - t_water),
                                 side="mine" if m_water > t_water else "theirs"))

    m_ratio, t_ratio = _number(mine.get("molar_ratio")), _number(theirs.get("molar_ratio"))
    if m_ratio is not None and t_ratio is not None and abs(m_ratio - t_ratio) >= 0.5:
        findings.append(_finding("ratio", 55, "chemistry", mine=m_ratio, theirs=t_ratio))

    m_sev = severity(mine.get("temperature_C"), mine.get("time_min"))
    t_sev = severity(theirs.get("temperature_C"), theirs.get("time_min"))
    if m_sev and t_sev:
        ratio_of = m_sev / t_sev
        if ratio_of > 1.5 or ratio_of < 0.67:
            findings.append(_finding("severity", 50, "technique",
                                     factor=max(ratio_of, 1 / ratio_of),
                                     mine=m_sev, theirs=t_sev,
                                     side="mine" if ratio_of > 1 else "theirs",
                                     mine_temp=mine.get("temperature_C"),
                                     theirs_temp=theirs.get("temperature_C"),
                                     mine_time=mine.get("time_min"),
                                     theirs_time=theirs.get("time_min")))

    m_feed, t_feed = _text(mine.get("feedstock")), _text(theirs.get("feedstock"))
    if m_feed and t_feed and m_feed.lower() not in t_feed.lower() and t_feed.lower() not in m_feed.lower():
        findings.append(_finding("feedstock", 45, "material", mine=m_feed, theirs=t_feed))

    if _number(theirs.get("replicates")) in (None, 0, 1):
        findings.append(_finding("single_value", 30, "noise"))

    findings.sort(key=lambda item: item["weight"], reverse=True)
    return {"delta": delta, "relative": relative,
            "mine_yield": m_yield, "theirs_yield": t_yield, "findings": findings}


def headline(result: dict) -> str:
    """A code for the one-line framing: agree, missing, or different-but-not-wrong."""
    delta = result.get("delta")
    if delta is None:
        return "missing"
    if abs(delta) < 0.05:
        return "agree"
    return "different"
