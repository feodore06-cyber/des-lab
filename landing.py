# -*- coding: utf-8 -*-
"""The public page.

Composition rules: one centred column of measure ~46rem, one brand bar above it, one action below
the headline, and a three-column band aligned to the same width. No data of any kind is shown.
"""
from __future__ import annotations

import streamlit as st

import i18n
from i18n import t


def landing() -> None:
    bar = st.columns([5, 1.15], vertical_alignment="center")
    bar[0].markdown('<div class="bm-brand"><img src="app/static/astar_mark.png" alt="">'
                    '<span class="bm-wordmark">BioMat Lab</span></div>', unsafe_allow_html=True)
    i18n.language_switch(bar[1])
    st.markdown('<div class="bm-rule"></div>', unsafe_allow_html=True)

    st.markdown(f'''
      <div class="bm-hero">
        <h1 class="bm-hero-title">{t("land.headline")}</h1>
        <p class="bm-hero-sub">{t("land.sub")}</p>
      </div>
    ''', unsafe_allow_html=True)

    st.markdown('<div style="height:.6rem"></div>', unsafe_allow_html=True)
    middle = st.columns([1, 0.5, 1])[1]
    with middle:
        if st.button(t("land.start"), key="land_start", type="primary", use_container_width=True):
            st.session_state["show_signin"] = True
            st.query_params["view"] = "signin"
            st.rerun()

    st.markdown(f'''
      <div class="bm-cols">
        <div>
          <div class="bm-col-n">01</div>
          <div class="bm-col-t">{t("land.p1")}</div>
          <div class="bm-col-d">{t("land.p1b")}</div>
        </div>
        <div>
          <div class="bm-col-n">02</div>
          <div class="bm-col-t">{t("land.p2")}</div>
          <div class="bm-col-d">{t("land.p2b")}</div>
        </div>
        <div>
          <div class="bm-col-n">03</div>
          <div class="bm-col-t">{t("land.p3")}</div>
          <div class="bm-col-d">{t("land.p3b")}</div>
        </div>
      </div>
      <p class="bm-positioning">{t("land.positioning")}</p>
      <p class="bm-foot">{t("land.footer")}</p>
    ''', unsafe_allow_html=True)
