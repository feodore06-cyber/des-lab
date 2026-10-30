# -*- coding: utf-8 -*-
"""The public page: what this is, why it can be trusted, and the one thing to do next.

No stored data is shown here. Not even a sample: the numbers on a public page must never come from
anybody's record, so the illustration is a schematic instead of a chart of real runs.
"""
from __future__ import annotations

import streamlit as st

import i18n
from i18n import t


def landing() -> None:
    """Render the signed-out page."""
    top = st.columns([3, 1, 0.6], vertical_alignment="center")
    top[0].markdown('<div class="bm-wordmark">BioMat Lab</div>', unsafe_allow_html=True)
    i18n.language_switch(top[1])
    with top[2]:
        if st.button(t("land.signin"), key="land_signin", use_container_width=True):
            st.session_state["show_signin"] = True
            st.query_params["view"] = "signin"
            st.rerun()

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
            st.button(t("land.example"), key="land_example", disabled=True,
                      help=t("land.example_locked"), use_container_width=True)
    with right:
        _schematic()

    st.divider()
    st.markdown(f'<p class="bm-positioning">{t("land.positioning")}</p>', unsafe_allow_html=True)

    columns = st.columns(3)
    for column, (title_key, body_key) in zip(columns, (("land.p1", "land.p1b"),
                                                      ("land.p2", "land.p2b"),
                                                      ("land.p3", "land.p3b"))):
        column.markdown(f"**{t(title_key)}**")
        column.caption(t(body_key))

    st.caption(t("land.footer"))


def _schematic() -> None:
    """A drawing of what the app does - no record, no number, nothing personal."""
    st.markdown(
        '<div class="bm-flow">'
        '<div class="bm-flow-step"><span class="bm-flow-n">1</span>'
        '<span class="bm-flow-t">' + t("land.flow1") + "</span>"
        '<span class="bm-flow-d">' + t("land.flow1b") + "</span></div>"
        '<div class="bm-flow-arrow">→</div>'
        '<div class="bm-flow-step"><span class="bm-flow-n">2</span>'
        '<span class="bm-flow-t">' + t("land.flow2") + "</span>"
        '<span class="bm-flow-d">' + t("land.flow2b") + "</span></div>"
        '<div class="bm-flow-arrow">→</div>'
        '<div class="bm-flow-step"><span class="bm-flow-n">3</span>'
        '<span class="bm-flow-t">' + t("land.flow3") + "</span>"
        '<span class="bm-flow-d">' + t("land.flow3b") + "</span></div>"
        "</div>",
        unsafe_allow_html=True,
    )
    st.caption(t("land.flow_note"))
