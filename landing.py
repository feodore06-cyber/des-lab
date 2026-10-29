# -*- coding: utf-8 -*-
"""The public page: what this is, why it can be trusted, and the one thing to do next.

Deliberately quiet: one headline, one sentence, two actions, and a real chart drawn from the bundled
example data - no stock imagery and no marketing adjectives.
"""
from __future__ import annotations

import pandas as pd
import streamlit as st

import i18n
from i18n import t


def _example_frame(load_example) -> pd.DataFrame | None:
    try:
        frame = load_example()
    except Exception:
        return None
    return None if frame is None or frame.empty else frame


def _hero_figure(frame: pd.DataFrame):
    """A small, honest chart of the example data: white ground, thin grid, one colour."""
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except Exception:
        return None
    if not {"formulation", "lignin_yield_pct"} <= set(frame.columns):
        return None
    data = frame.copy()
    data["lignin_yield_pct"] = pd.to_numeric(data["lignin_yield_pct"], errors="coerce")
    data = data.dropna(subset=["lignin_yield_pct"])
    if data.empty:
        return None
    grouped = (data.groupby("formulation")["lignin_yield_pct"]
               .agg(["mean", "std"]).reset_index().sort_values("mean"))
    fig, ax = plt.subplots(figsize=(5.2, 3.0), dpi=150)
    fig.patch.set_facecolor("white")
    ax.set_facecolor("white")
    ax.bar(range(len(grouped)), grouped["mean"], color="#0B1F4B", width=0.55)
    if grouped["std"].notna().any():
        ax.errorbar(range(len(grouped)), grouped["mean"], yerr=grouped["std"].fillna(0),
                    fmt="none", ecolor="#55637D", elinewidth=1, capsize=3)
    ax.set_xticks(range(len(grouped)))
    ax.set_xticklabels([str(label)[:18] for label in grouped["formulation"]], fontsize=7,
                       color="#33415C")
    ax.set_ylabel("Lignin yield (%)", fontsize=8, color="#33415C")
    ax.tick_params(axis="y", labelsize=7, colors="#33415C")
    ax.grid(axis="y", color="#E4EAF6", linewidth=0.6)
    ax.set_axisbelow(True)
    for side in ("top", "right", "left"):
        ax.spines[side].set_visible(False)
    ax.spines["bottom"].set_color("#C9D5EC")
    fig.tight_layout()
    return fig


def landing(load_example) -> None:
    """Render the signed-out page."""
    top = st.columns([3, 1, 0.6], vertical_alignment="center")
    top[0].markdown('<div class="bm-wordmark">BioMat Lab</div>', unsafe_allow_html=True)
    i18n.language_switch(top[1])
    with top[2]:
        if st.button(t("land.signin"), key="land_signin", use_container_width=True):
            st.session_state["show_signin"] = True
            st.query_params["view"] = "signin"
            st.rerun()

    frame = _example_frame(load_example)
    left, right = st.columns([1.05, 1], gap="large", vertical_alignment="center")
    with left:
        st.markdown('<div class="bm-hero">', unsafe_allow_html=True)
        st.markdown(f'<h1 class="bm-hero-title">{t("land.headline")}</h1>', unsafe_allow_html=True)
        st.markdown(f'<p class="bm-hero-sub">{t("land.sub")}</p>', unsafe_allow_html=True)
        st.markdown("</div>", unsafe_allow_html=True)
        actions = st.columns([1, 1], gap="small")
        with actions[0]:
            if st.button(t("land.start"), key="land_start", type="primary", use_container_width=True):
                st.session_state["show_signin"] = True
                st.query_params["view"] = "signin"
                st.rerun()
        with actions[1]:
            if st.button(t("land.example"), key="land_example", use_container_width=True):
                st.session_state["landing_example"] = not st.session_state.get("landing_example", False)
                st.rerun()
    with right:
        figure = _hero_figure(frame) if frame is not None else None
        if figure is not None:
            st.pyplot(figure, width="stretch")
            st.caption(t("land.figure_note"))

    if st.session_state.get("landing_example"):
        _example_report(frame)

    st.divider()
    st.markdown(f'<p class="bm-positioning">{t("land.positioning")}</p>', unsafe_allow_html=True)

    columns = st.columns(3)
    for column, (title_key, body_key) in zip(columns, (("land.p1", "land.p1b"),
                                                      ("land.p2", "land.p2b"),
                                                      ("land.p3", "land.p3b"))):
        column.markdown(f"**{t(title_key)}**")
        column.caption(t(body_key))

    st.caption(t("land.footer"))


def _example_report(frame: pd.DataFrame | None) -> None:
    """A small, real table - no invented numbers."""
    st.markdown(f"#### {t('land.example_title')}")
    if frame is None:
        st.caption(t("land.example_missing"))
        return
    keep = [column for column in ("sample_id", "formulation", "temperature_C", "time_min",
                                  "lignin_yield_pct") if column in frame.columns]
    if not keep:
        st.caption(t("land.example_missing"))
        return
    labels = {"sample_id": t("res.sample_id"), "formulation": t("res.formulation"),
              "temperature_C": t("res.temperature"), "time_min": t("res.time"),
              "lignin_yield_pct": t("res.lignin_yield")}
    st.dataframe(frame[keep].head(6).rename(columns=labels), width="stretch", hide_index=True)
    st.caption(t("land.example_note"))
