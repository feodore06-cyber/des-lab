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
    """Render the signed-out page. One action, no stored data, no decorative image."""
    top = st.columns([3, 1], vertical_alignment="center")
    top[0].markdown(
        '<div class="bm-brand"><img src="app/static/astar_mark.png" alt="">'
        '<span class="bm-wordmark">BioMat Lab</span></div>',
        unsafe_allow_html=True)
    i18n.language_switch(top[1])

    st.markdown('<div class="bm-hero">', unsafe_allow_html=True)
    st.markdown(f'<h1 class="bm-hero-title">{t("land.headline")}</h1>', unsafe_allow_html=True)
    st.markdown(f'<p class="bm-hero-sub">{t("land.sub")}</p>', unsafe_allow_html=True)
    st.markdown("</div>", unsafe_allow_html=True)

    action = st.columns([1, 2.4])
    with action[0]:
        if st.button(t("land.start"), key="land_start", type="primary", use_container_width=True):
            st.session_state["show_signin"] = True
            st.query_params["view"] = "signin"
            st.rerun()

    st.divider()
    st.markdown(f'<p class="bm-positioning">{t("land.positioning")}</p>', unsafe_allow_html=True)

    columns = st.columns(3)
    for column, (title_key, body_key) in zip(columns, (("land.p1", "land.p1b"),
                                                      ("land.p2", "land.p2b"),
                                                      ("land.p3", "land.p3b"))):
        column.markdown(f"**{t(title_key)}**")
        column.caption(t(body_key))

    st.caption(t("land.footer"))
