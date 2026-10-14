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
"""Entry script: look and feel, the A*STAR intro, page registration.

Logic lives in lab_core.py / lab_plots.py, page content in views.py.
"""
from pathlib import Path

import streamlit as st

import views

ROOT = Path(__file__).parent
LOGO_PATH = ROOT / "static/astar_logo.png"
LOGO_URL = "app/static/astar_logo.png"

# A*STAR brand colours sampled from the supplied logo: blue #002F86, red #D8291B.
STYLE = """
<style>
  /* ---------- layout ---------- */
  .stMainBlockContainer { max-width: 1180px; padding-top: 2.0rem; padding-bottom: 3rem; }
  /* NOTE: never animate the app container's opacity from 0. If such an animation fails to
     run (background tab, animations disabled, a re-render resetting it) the whole app would
     stay invisible behind a white shell. The intro overlay below is the only moving part. */
  h1 { font-weight: 800; letter-spacing: -0.02em; color: #0B1F4B; }
  h2, h3 { font-weight: 700; letter-spacing: -0.01em; color: #0B1F4B; }
  h1 + div p, h1 ~ p { color: #33415C; }

  /* ---------- sidebar ---------- */
  [data-testid="stSidebar"] {
    background: linear-gradient(180deg, #F8FAFE 0%, #EEF2FA 100%);
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

  /* ---------- cards ---------- */
  div[data-testid="stMetric"] {
    background: #FFFFFF;
    border: 1px solid #E4EAF6;
    border-radius: 14px;
    padding: 14px 16px 12px 16px;
    box-shadow: 0 1px 3px rgba(0, 47, 134, .06);
  }
  div[data-testid="stMetricLabel"] p { color: #55637D; font-weight: 600; }
  div[data-testid="stMetricValue"] { color: #002F86; font-weight: 700; }
  [data-testid="stExpander"] {
    border: 1px solid #E4EAF6;
    border-radius: 12px;
    background: #FCFDFF;
  }
  [data-testid="stDataFrame"], [data-testid="stDataEditor"] {
    border: 1px solid #E4EAF6;
    border-radius: 12px;
    overflow: hidden;
  }
  [data-testid="stAlert"] { border-radius: 12px; }

  /* ---------- buttons ---------- */
  .stButton > button, .stDownloadButton > button, .stLinkButton > a {
    border-radius: 10px;
    border: 1px solid #C9D5EC;
    font-weight: 600;
    transition: all .18s ease;
  }
  .stDownloadButton > button:hover, .stButton > button:hover, .stLinkButton > a:hover {
    border-color: #002F86;
    color: #002F86;
    box-shadow: 0 2px 10px rgba(0, 47, 134, .12);
    transform: translateY(-1px);
  }
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
  #dsh-splash img {
    width: min(440px, 64vw);
    height: auto;
    animation: dshLogoIn 1.1s cubic-bezier(.2, .75, .25, 1) both;
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
  /* 0–80 % opaque hold, last 20 % fade out and stop intercepting clicks */
  @keyframes dshIntro {
    0%   { opacity: 1; visibility: visible; }
    80%  { opacity: 1; visibility: visible; }
    100% { opacity: 0; visibility: hidden; }
  }

  @media (prefers-reduced-motion: reduce) {
    #dsh-splash { animation: dshIntro 1.4s ease forwards; }
    #dsh-splash img, #dsh-splash .dsh-bar span, #dsh-splash .dsh-tag {
      animation-duration: .2s; animation-delay: 0s;
    }
  }
</style>
"""

SPLASH = """
<div id="dsh-splash">
  <img src="app/static/astar_logo.png" alt="A*STAR — Agency for Science, Technology and Research, Singapore">
  <div class="dsh-bar"><span></span></div>
  <div class="dsh-tag">DES Lab · Experiment Workbench</div>
</div>
"""

st.set_page_config(page_title="DES Lab · Experiment Workbench", page_icon=str(LOGO_PATH), layout="wide")
st.markdown(STYLE, unsafe_allow_html=True)

# st.logo pins the brand to the very top of the sidebar, above the page navigation.
st.logo(str(LOGO_PATH), size="large", link="https://www.a-star.edu.sg/")

# Show the A*STAR intro once per browser session (about 3 seconds, then it fades away).
if not st.session_state.get("_intro_shown"):
    st.session_state["_intro_shown"] = True
    st.markdown(SPLASH, unsafe_allow_html=True)

page = st.navigation([
    st.Page(views.calculator, title="DES Recipe Calculator", icon="🧪", default=True),
    st.Page(views.results, title="Results & Figures", icon="📊", url_path="results"),
    st.Page(views.guide, title="Guide & Templates", icon="📖", url_path="guide"),
])
page.run()

st.sidebar.divider()
st.sidebar.caption("Experiment workbench / LOCAL EDITION")
st.sidebar.caption("Runs locally · traceable recipes · CSV / PNG / SVG")