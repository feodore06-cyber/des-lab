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
# Modified 2026-10-14: Chinese DES preparation calculator and experimental results workbench.
"""入口脚本：注册三个页面并运行。计算与绘图逻辑见 lab_core.py / lab_plots.py，页面见 views.py。"""
import streamlit as st

import views

st.set_page_config(page_title="DES Lab · 实验工作台", page_icon="🧪", layout="wide")

with st.sidebar:
    st.title("🧪 DES Lab")
    st.caption("实验工作台 / LOCAL EDITION")

page = st.navigation([
    st.Page(views.calculator, title="DES 配比计算", icon="🧪", default=True),
    st.Page(views.results, title="实验结果与图表", icon="📊", url_path="results"),
    st.Page(views.guide, title="使用说明与模板", icon="📖", url_path="guide"),
])
page.run()

st.sidebar.divider()
st.sidebar.caption("本机运行 · 配方可追溯 · CSV / PNG / SVG")
