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
"""Entry script: register the three pages and run. Logic lives in lab_core.py / lab_plots.py, pages in views.py."""
import streamlit as st

import views

st.set_page_config(page_title="DES Lab · Experiment Workbench", page_icon="🧪", layout="wide")

with st.sidebar:
    st.title("🧪 DES Lab")
    st.caption("Experiment workbench / LOCAL EDITION")

page = st.navigation([
    st.Page(views.calculator, title="DES Recipe Calculator", icon="🧪", default=True),
    st.Page(views.results, title="Results & Figures", icon="📊", url_path="results"),
    st.Page(views.guide, title="Guide & Templates", icon="📖", url_path="guide"),
])
page.run()

st.sidebar.divider()
st.sidebar.caption("Runs locally · traceable recipes · CSV / PNG / SVG")
