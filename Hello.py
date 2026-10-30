# Copyright 2018-2022 Streamlit Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#
# Modified 2026-10-14: DES preparation calculator and experimental results workbench.
"""Entry script: look and feel, the A*STAR intro, sign-in, page registration.

Logic lives in lab_core.py / lab_plots.py, accounts and record folders in auth.py, page content in views.py.
"""
from pathlib import Path

import pandas as pd
import streamlit as st

import auth
import i18n
import landing
import store
import views
from i18n import t

ROOT = Path(__file__).parent
# ---- product identity: change these two lines to rename the whole app ----
APP_NAME = "BioMat Lab"
APP_TAGLINE = "Experiment Workbench"
APP_TITLE = f"{APP_NAME} {chr(183)} {APP_TAGLINE}"
# Institutional branding is opt-in: the A*STAR assets are only shown when the deployment says it is
# allowed to use them (DESLAB_ASTAR_BRAND=1 or [brand] astar = true). The default is our own mark, so
# nothing pretends to be an official institutional site.
# On by default at the lab's request (2026-10-30); DESLAB_ASTAR_BRAND=0 hides the institutional
# lockup and falls back to the plain wordmark if the permission ever lapses.
_brand_flag = str(auth._flag("DESLAB_ASTAR_BRAND")).strip().lower()
BRAND_IS_ASTAR = _brand_flag not in ("0", "false", "no", "off")

LOGO_PATH = ROOT / ("static/astar_logo.png" if BRAND_IS_ASTAR else "static/biomat_mark.png")
LOGO_MARK_PATH = ROOT / ("static/astar_mark.png" if BRAND_IS_ASTAR else "static/biomat_mark.png")
LOGO_URL = "app/static/astar_logo.png" if BRAND_IS_ASTAR else "app/static/biomat_mark.png"

# A*STAR brand colours sampled from the supplied logo: blue #002F86, red #D8291B.
STYLE = """
<style>
  /* ---------- layout ---------- */
  /* keep the first line clear of Streamlit's sticky header (about 3.75rem tall) */
  .stMainBlockContainer { max-width: 1180px; padding-top: 4rem; padding-bottom: 3rem; }
  /* NOTE: never animate the app container's opacity from 0. If such an animation fails to
     run (background tab, animations disabled, a re-render resetting it) the whole app would
     stay invisible behind a white shell. The intro overlay below is the only moving part. */
  /* serif display type: the single strongest signal that this is a research tool, not a template */
  h1, h2, h3, [data-testid="stMarkdownContainer"] h1, [data-testid="stMarkdownContainer"] h2,
  [data-testid="stMarkdownContainer"] h3 {
    font-family: Georgia, "Times New Roman", "Songti SC", serif !important;
    font-weight: 600 !important;
    letter-spacing: -0.015em;
    color: #0B1F4B;
  }
  h1 + div p, h1 ~ p { color: #33415C; }

  /* ---------- sidebar ---------- */
  [data-testid="stSidebar"] {
    background: #FAFBFE;
    border-right: 1px solid #E3E9F4;
  }
  /* st.logo defaults to a tiny mark; scale the brand up so the wordmark reads */
  [data-testid="stSidebarHeader"] { height: auto; padding: .9rem 1rem .3rem 1rem; }
  [data-testid="stSidebarHeader"] img,
  [data-testid="stLogo"] img,
  img[data-testid="stLogo"] { height: 50px !important; width: auto !important; border-radius: 0 !important; }
  [data-testid="stSidebar"] [data-testid="stSidebarNav"] a { border-radius: 10px; }
  [data-testid="stSidebar"] [data-testid="stSidebarNav"] a:hover { background: #E4EBF8; }
  [data-testid="stSidebar"] hr { border-color: #DCE4F2; }
  [data-testid="stSidebar"] img { display: block; }

  /* ---------- sign-in page ---------- */
  /* the logo is served from static/ and centred in the column, so it sits on the page centre line;
     it is drawn at 340 px because the source is 697 px wide (crisp at 2x scaling too) */
  .dsh-login-brand { display: flex; justify-content: center; margin: 2.2vh 0 1.5rem; }
  .dsh-login-brand img { width: min(370px, 100%); height: auto; display: block; }

  /* ---------- greeting after sign-in ---------- */
  .dsh-welcome {
    display: flex;
    flex-direction: column;
    gap: .15rem;
    margin: 0 0 1.4rem;
    padding: 0 0 0 1rem;
    border-left: 3px solid #002F86;
  }
  .dsh-welcome-hi { font: 650 1.05rem/1.35 Georgia, "Times New Roman", serif; color: #0B1F4B; }
  .dsh-welcome-sub { font: 400 .8rem/1.45 system-ui, "Segoe UI", sans-serif; color: #5A6478; }

  /* ---------- floating feedback button ---------- */
  .dsh-fab {
    position: fixed;
    right: 22px;
    bottom: 22px;
    z-index: 1000;
    display: flex;
    align-items: center;
    gap: .5rem;
    padding: .7rem 1.05rem;
    border-radius: 999px;
    background: #002F86;
    color: #FFFFFF !important;
    font: 600 .95rem/1 "Segoe UI", system-ui, sans-serif;
    text-decoration: none !important;
    box-shadow: 0 6px 20px rgba(0, 47, 134, .35);
    transition: transform .15s ease, box-shadow .15s ease, background .15s ease;
  }
  .dsh-fab:hover { background: #0B1F4B; transform: translateY(-2px); box-shadow: 0 10px 26px rgba(0, 47, 134, .45); }
  .dsh-fab-icon { font-size: 1.05rem; }
  @media (max-width: 640px) { .dsh-fab-label { display: none; } .dsh-fab { padding: .85rem; } }

  /* the real button behind the floating chip (Streamlit tags keyed widgets with st-key-<key>) */
  div.st-key-open_feedback {
    position: fixed;
    right: 22px;
    bottom: 22px;
    z-index: 1000;
    width: auto;
  }
  div.st-key-open_feedback button {
    border-radius: 999px !important;
    border: none !important;
    background: #002F86 !important;
    color: #FFFFFF !important;
    font-weight: 600 !important;
    padding: .7rem 1.1rem !important;
    box-shadow: 0 6px 20px rgba(0, 47, 134, .35);
    transition: transform .15s ease, box-shadow .15s ease, background .15s ease;
  }
  div.st-key-open_feedback button:hover {
    background: #0B1F4B !important;
    transform: translateY(-2px);
    box-shadow: 0 10px 26px rgba(0, 47, 134, .45);
  }

  /* ---------- the public schematic ---------- */
  .bm-flow { display: flex; align-items: stretch; gap: .4rem; }
  .bm-flow-step { flex: 1; display: flex; flex-direction: column; gap: .25rem;
                  padding: .9rem .95rem; border: 1px solid #DCE4F2; border-radius: 8px;
                  background: #FFFFFF; }
  .bm-flow-n { font: 600 .7rem/1 ui-monospace, Consolas, monospace; color: #8C99B0;
               letter-spacing: .08em; }
  .bm-flow-t { font: 600 .98rem/1.3 Georgia, "Times New Roman", serif; color: #0B1F4B; }
  .bm-flow-d { font: 400 .78rem/1.45 system-ui, "Segoe UI", sans-serif; color: #5A6478; }
  .bm-flow-arrow { align-self: center; color: #B7C2D6; font-size: 1rem; }

  /* ---------- cards ---------- */
  div[data-testid="stMetric"] {
    background: #FFFFFF;
    border: 1px solid #DCE4F2;
    border-radius: 8px;
    padding: 12px 14px 10px 14px;
  }
  div[data-testid="stMetricLabel"] p {
    color: #55637D; font-weight: 600; font-size: .76rem;
    text-transform: uppercase; letter-spacing: .07em;
  }
  div[data-testid="stMetricValue"] {
    color: #0B1F4B; font-weight: 700; font-variant-numeric: tabular-nums;
  }
  [data-testid="stExpander"] {
    border: 1px solid #E4EAF6;
    border-radius: 8px;
    background: #FCFDFF;
  }
  [data-testid="stDataFrame"], [data-testid="stDataEditor"] {
    border: 1px solid #E4EAF6;
    border-radius: 8px;
    overflow: hidden;
  }
  [data-testid="stAlert"] { border-radius: 8px; }

  /* ---------- buttons ---------- */
  .stButton > button, .stDownloadButton > button, .stLinkButton > a {
    border-radius: 6px;
    border: 1px solid #C9D5EC;
    font-weight: 600;
  }
  .stDownloadButton > button:hover, .stButton > button:hover, .stLinkButton > a:hover {
    border-color: #002F86;
    color: #002F86;
  }
  .stTextInput input, .stNumberInput input, .stDateInput input, .stTextArea textarea,
  [data-baseweb="select"] > div { border-radius: 6px; }
  /* keep the app chrome clean, but leave the ⋮ menu usable */
  [data-testid="stAppDeployButton"] { display: none; }
  [data-testid="stDecoration"] { display: none; }

  /* ---------- A*STAR intro (~3 s, once per session) ----------
     Fail-safe design: the overlay is hidden by default and the animation is what shows it.
     If the animation never runs (animations disabled, background tab, reduced motion),
     the overlay simply stays hidden and the app is fully visible. */
  #dsh-splash {
    position: fixed;
    inset: 0;
    z-index: 2147483647;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    gap: 30px;
    background: #FFFFFF;
    opacity: 0;
    visibility: hidden;
    pointer-events: none;
    animation: dshIntro 3s ease forwards;
  }
  #dsh-splash .dsh-shine-wrap {
    position: relative;
    display: inline-block;
    overflow: hidden;
    animation: dshLogoIn 1.1s cubic-bezier(.2, .75, .25, 1) both;
  }
  #dsh-splash img {
    display: block;
    width: min(440px, 64vw);
    height: auto;
  }
  /* Universal-style light sweep: a soft beam travels left to right across the wordmark.
     mix-blend-mode: screen keeps the white paper white and only brightens the navy/red ink. */
  #dsh-splash .dsh-beam {
    position: absolute;
    top: -30%;
    bottom: -30%;
    left: 0;
    width: 30%;
    background: linear-gradient(100deg,
      rgba(255, 255, 255, 0) 0%,
      rgba(255, 255, 255, .18) 24%,
      rgba(255, 255, 255, .85) 42%,
      rgba(255, 255, 255, 1) 52%,
      rgba(255, 255, 255, .18) 78%,
      rgba(255, 255, 255, 0) 100%);
    mix-blend-mode: screen;
    transform: translateX(-170%) skewX(-16deg);
    animation: dshBeam 2.0s cubic-bezier(.42, 0, .58, 1) .65s forwards;
    pointer-events: none;
  }
  #dsh-splash .dsh-bar {
    width: min(230px, 42vw);
    height: 4px;
    border-radius: 999px;
    background: #E7ECF6;
    overflow: hidden;
  }
  #dsh-splash .dsh-bar span {
    display: block;
    height: 100%;
    width: 0;
    border-radius: 999px;
    background: linear-gradient(90deg, #002F86 0%, #D8291B 100%);
    animation: dshBar 2.2s cubic-bezier(.4, .1, .2, 1) .2s forwards;
  }
  #dsh-splash .dsh-tag {
    font: 600 13px/1 "Segoe UI", system-ui, sans-serif;
    letter-spacing: .16em;
    text-transform: uppercase;
    color: #6B7A99;
    animation: dshLogoIn 1.1s ease .25s both;
  }
  @keyframes dshLogoIn {
    from { opacity: 0; transform: scale(.9) translateY(12px); }
    to   { opacity: 1; transform: none; }
  }
  @keyframes dshBar { to { width: 100%; } }
  @keyframes dshBeam {
    from { transform: translateX(-170%) skewX(-16deg); }
    to   { transform: translateX(400%) skewX(-16deg); }
  }
  /* 0–80 % opaque hold, last 20 % fade out and stop intercepting clicks */
  @keyframes dshIntro {
    0%   { opacity: 1; visibility: visible; }
    80%  { opacity: 1; visibility: visible; }
    100% { opacity: 0; visibility: hidden; }
  }

  @media (prefers-reduced-motion: reduce) {
    #dsh-splash { animation: dshIntro 1.4s ease forwards; }
    #dsh-splash img, #dsh-splash .dsh-bar span, #dsh-splash .dsh-tag,
    #dsh-splash .dsh-shine-wrap {
      animation-duration: .2s; animation-delay: 0s;
    }
    #dsh-splash .dsh-beam { display: none; }
  }
</style>
"""

SPLASH_MARK = ("app/static/astar_logo.png", "A*STAR - Agency for Science, Technology and Research, Singapore") \
    if BRAND_IS_ASTAR else ("app/static/biomat_mark.png", APP_NAME)

SPLASH = f"""
<div id="dsh-splash">
  <div class="dsh-shine-wrap">
    <img src="{SPLASH_MARK[0]}" alt="{SPLASH_MARK[1]}">
    <span class="dsh-beam" aria-hidden="true"></span>
  </div>
  <div class="dsh-bar"><span></span></div>
  <div class="dsh-tag">{APP_NAME} · {APP_TAGLINE}</div>
</div>
"""

st.set_page_config(page_title=APP_TITLE, page_icon=str(LOGO_MARK_PATH), layout="wide")
st.markdown(STYLE, unsafe_allow_html=True)

# Show the A*STAR intro once per browser session (about 3 seconds, then it fades away).
if not st.session_state.get("_intro_shown"):
    st.session_state["_intro_shown"] = True
    st.markdown(SPLASH, unsafe_allow_html=True)

# ---------------------------------------------------------------- sign in ----
# Every teammate signs in, then only sees their own record folder. Nothing is put in the sidebar
# before this point, so the sign-in page has no sidebar at all - just the form in the middle.
auth.ensure_store()
user = auth.current_user()


def _gate(view):
    """Every page keeps its URL in every state; signed out it shows the sign-in form instead."""

    def run():
        if auth.current_user():
            view()
        else:
            auth.login_form(LOGO_URL)

    return run


def _front():
    """Signed out: the public page, or the form itself once somebody clicks "Start an experiment"."""
    if auth.current_user():
        views.workspace()
        return
    params = st.query_params
    direct = (params.get("view") == "signin" or st.session_state.get("show_signin")
              or "reset" in params or "invite" in params)
    if direct:
        if st.button(t("land.back"), key="back_to_landing"):
            st.session_state["show_signin"] = False
            st.query_params.clear()
            st.rerun()
        auth.login_form(LOGO_URL)
        return
    landing.landing()


NAV = [
    ("experiments", st.Page(_front, title=t("nav.experiments"), default=True), t("nav.experiments")),
    ("results", st.Page(_gate(views.results), title=t("nav.results"), url_path="results"),
     t("nav.results")),
    ("calculator", st.Page(_gate(views.calculator), title=t("app.page_calc"), url_path="calculator"),
     t("app.page_calc")),
    ("papers", st.Page(_gate(views.library), title=t("nav.papers"), url_path="papers"),
     t("nav.papers")),
    ("compare", st.Page(_gate(views.compare_page), title=t("nav.compare"), url_path="compare"),
     t("nav.compare")),
    ("profile", st.Page(_gate(views.guide), title=t("nav.profile"), url_path="guide"),
     t("nav.profile")),
    ("feedback", st.Page(_gate(views.feedback), title=t("app.page_feedback"), url_path="feedback"),
     t("app.page_feedback")),
]

page = st.navigation([entry[1] for entry in NAV], position="hidden")
# views needs the page objects to move between pages; a file path does not resolve for these pages
views.PAGE_OBJECTS = {key: page_object for key, page_object, _label in NAV}

if user:
    bar = st.columns([2.0, 1, 1, 1, 1, 1, 1, 1.2, 1], vertical_alignment="center", gap="small")
    bar[0].markdown('<div class="bm-wordmark">BioMat Lab</div>', unsafe_allow_html=True)
    for column, entry in zip(bar[1:7], NAV[:6]):
        with column:
            st.page_link(entry[1], label=entry[2])
    i18n.language_switch(bar[7])
    with bar[8]:
        if st.button(t("app.logout"), key="logout", use_container_width=True):
            auth.logout()
            st.query_params.clear()
            st.rerun()

    if auth.hosted_mode() and not store.enabled():
        st.warning(t("app.hosted_warning"))

page.run()

if user:
    st.caption(t("app.sidebar_signed_in", user=user) + " · "
               + (t("app.sidebar_db") if store.enabled() else t("app.sidebar_records", user=user)))
