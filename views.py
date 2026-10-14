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
"""Streamlit 页面视图：配比计算 / 实验结果与图表 / 使用说明。

拆成独立模块是为了让每个页面都能被 streamlit.testing.v1.AppTest 直接运行测试。
"""
from pathlib import Path

import pandas as pd
import streamlit as st

from lab_core import calculate_recipe, csv_bytes, merge_results, summarize
from lab_plots import figure_bytes, make_figure

ROOT = Path(__file__).parent
DEMO_CSV = ROOT / "sample_data/demo_lignin.csv"
MY_CSV = ROOT / "sample_data/my_des_runs.csv"
LABELS = {"name": "组分 / 试剂形式", "mw": "摩尔质量 (g/mol)", "ratio": "摩尔份数",
          "assay_pct": "有效含量 (wt%)", "water_pct": "独立水分 (wt%)"}


def calculator():
    st.caption("01 / PREPARE")
    st.title("DES 配比计算")
    st.write("输入摩尔比与试剂实际含量，得到可追溯的称量清单。")
    st.info("下面是计算示例，不是推荐配方。请按试剂瓶标签修改；计算结果不能证明混合物已形成 DES。")
    components = st.data_editor(pd.DataFrame([
        {"name": "ChCl（按无水计）", "mw": 139.62, "ratio": 1.0, "assay_pct": 100.0, "water_pct": 0.0},
        {"name": "乙醛酸 / 50% 水溶液", "mw": 74.04, "ratio": 2.0, "assay_pct": 50.0, "water_pct": 50.0},
    ]), column_config=LABELS, num_rows="dynamic", hide_index=True, width="stretch", key="components")
    st.caption("可在末行添加第三组分。含量不足 100% 的差额不会自动当作水；水分需单独填写。")
    a, b, c = st.columns([2, 1, 1])
    basis_label = a.selectbox("目标质量基准", ["有效组分合计（不含溶剂水）", "试剂称量合计（含带入水）"], key="basis")
    target = b.number_input("目标质量 (g)", min_value=0.001, value=10.0, step=1.0, format="%.3f", key="target")
    water = c.number_input("额外加水 (g)", min_value=0.0, value=0.0, step=0.1, format="%.3f", key="water")
    st.caption("额外加水始终在目标质量之外另加。水合物：使用该水合物的摩尔质量；勿将结晶水再次填入独立水分。")
    basis = "active" if basis_label.startswith("有效") else "reagent"
    try:
        recipe, totals = calculate_recipe(components, target, basis, water)
    except ValueError as exc:
        st.error(str(exc))
        return
    a, b, c = st.columns(3)
    a.metric("配制总质量", f"{totals['total_g']:.4f} g")
    b.metric("已填报水量 + 额外加水", f"{totals['known_water_g']:.4f} g")
    c.metric("已计入的水质量分数", f"{totals['known_water_pct']:.2f}%")
    st.caption("水分统计仅含所填的独立水分与额外加水；不估算吸湿水、结晶水或加热蒸发。")
    result_labels = {**LABELS, "moles": "物质的量 (mol)", "active_g": "有效组分 (g)",
                     "weigh_g": "应称取试剂 (g)", "water_g": "带入水 (g)"}
    st.subheader("称量清单")
    st.dataframe(recipe.rename(columns=result_labels).round(6), hide_index=True, width="stretch")
    export = recipe.copy()
    export["target_basis"] = basis
    export["target_g"] = target
    export["added_water_g"] = water
    for name, value in totals.items():
        export[name] = value
    st.download_button("下载配方 CSV", csv_bytes(export), "des_recipe.csv", "text/csv")
    with st.expander("计算公式与数据来源"):
        st.markdown("摩尔份数为 r，摩尔质量为 M，有效含量为 p（小数）。有效组分质量 = k × r × M；试剂称量 = 有效组分质量 / p。按选定目标质量求 k。")
        st.markdown("预设摩尔质量：[ChCl 139.62](https://www.sigmaaldrich.com/GI/en/product/sigma/c1879)；[乙醛酸 74.04，50 wt% 水溶液](https://www.sigmaaldrich.com/PM/en/product/aldrich/260150)。ChCl 的 100% 是理想计算示例，不是瓶签纯度。")


def results():
    st.caption("02 / ANALYZE")
    st.title("实验结果与图表")
    st.write("合并数据 → 选择实验条件 → 查看重复数与误差 → 导出图表。")
    source = st.radio("数据来源", ["虚构示例（9 条 · 演示操作）", "我的 DES 实验数据（3 组 · n=1）", "上传我的 CSV"],
                      horizontal=True, key="source")
    if source.startswith("虚构"):
        st.warning("DEMO · 以下 9 条记录完全虚构，只用于演示操作，不代表你的实验或文献结果。")
        files = [("demo_lignin.csv", DEMO_CSV.read_bytes())]
        encoding, data_kind = "utf-8-sig", "synthetic_demo"
    elif source.startswith("我的 DES"):
        st.info("已录入的 3 组实验：ChCl:GA = 1:1 / 1:2 / 2:1，每组只有 1 次测量，因此不会画误差棒。")
        files = [("my_des_runs.csv", MY_CSV.read_bytes())]
        encoding, data_kind = "utf-8-sig", "my_experiments"
    else:
        uploads = st.file_uploader("选择一个或多个 CSV（每行一次测量；同名列须使用相同单位）", type="csv", accept_multiple_files=True)
        encoding = st.selectbox("文件编码", ["utf-8-sig", "gb18030"], help="Excel 中文 CSV 若读取失败，可选择 gb18030。")
        if not uploads:
            st.info("请上传 CSV，或打开示例数据。Excel 文件请先另存为 CSV UTF-8。")
            return
        files = [(f.name, f.getvalue()) for f in uploads]
        data_kind = "user_uploaded"
    try:
        frame = merge_results(files, encoding)
    except (ValueError, UnicodeError, pd.errors.ParserError) as exc:
        st.error(f"无法读取 CSV：{exc}")
        return
    if frame.empty:
        st.info("文件没有数据行。")
        return
    columns = [c for c in frame.columns if c != "_source_file"]
    a, b, c = st.columns(3)
    a.metric("合并记录", len(frame))
    b.metric("来源文件", len(files))
    duplicate_count = int(frame.duplicated(subset=columns).sum())
    c.metric("完全相同的重复行", duplicate_count)
    if duplicate_count:
        st.warning("发现重复行，尚未删除。请核对是否重复导入；相同数值也可能是真实重复实验。")
    with st.expander("原始合并数据（保留来源文件）", expanded=False):
        st.dataframe(frame, hide_index=True, width="stretch")
        st.download_button("下载合并 CSV", csv_bytes(frame), "merged_results.csv", "text/csv")
    default_groups = [c for c in ["formulation", "temperature_C", "time_min"] if c in columns]
    groups = st.multiselect("按哪些实验条件分组？", columns, default=default_groups, key="groups")
    candidates = [c for c in columns if c not in groups and pd.to_numeric(frame[c], errors="coerce").notna().any()]
    if not groups or not candidates:
        st.info("至少选择一个分组列，并保留一个数值测量列。")
        return
    for first_choice in ("lignin_yield_pct", "lignin_mg", "dry_strength_MPa"):
        if first_choice in candidates:
            preferred = candidates.index(first_choice)
            break
    else:
        preferred = 0
    measurement = st.selectbox("测量值列（列名应包含单位）", candidates, index=preferred, key="measurement")
    st.caption("木质素得率 (%) = 木质素质量(mg) ÷ [生物质质量(g) × 1000] × 100%；请把配方、含水量、原料、温度、时间等不同条件纳入分组。每行按一个观测值统计；程序不能判断它们是否为独立重复。")
    try:
        clean, summary, audit = summarize(frame, groups, measurement)
    except (ValueError, TypeError) as exc:
        st.error(str(exc))
        return
    if audit["excluded"]:
        st.warning(f"有 {audit['excluded']} 行未参加统计：非数值/缺失/无穷测量 {audit['invalid_measurement']} 行，分组信息缺失 {audit['missing_groups']} 行（原因可能重叠）。原始数据保留。")
        with st.expander("查看未参加统计的记录"):
            st.dataframe(frame.loc[~audit["valid_mask"]], hide_index=True)
    if summary.empty:
        st.error("所选列没有完整的有效记录可用于统计。")
        return
    st.subheader("分组汇总")
    st.dataframe(summary, hide_index=True, width="stretch")
    st.caption("n = 有效测量次数；mean = 均值；sd = 样本标准差（ddof=1）。n=1 时 sd 留空，不画误差棒。")
    summary_export = summary.assign(measurement=measurement, data_kind=data_kind)
    st.download_button("下载统计 CSV", csv_bytes(summary_export), "summary.csv", "text/csv")
    if len(summary) > 30:
        st.info("当前分组超过 30 个，请减少数据范围后绘图；汇总仍可下载。")
        return
    a, b = st.columns(2)
    title = a.text_input("图标题", value="DEMO · 虚构示例数据" if data_kind == "synthetic_demo" else "DES 预处理 · 木质素得率")
    ylabel = b.text_input("纵轴标题 / 单位", value=measurement, key=f"ylabel_{measurement}")
    fig = make_figure(clean, summary, groups, measurement, title, ylabel)
    st.pyplot(fig, width="stretch")
    st.caption("柱 = 均值 · 误差棒 = ±1 样本标准差 · 点 = 原始观测。误差棒不代表显著性检验。")
    a, b = st.columns(2)
    a.download_button("下载 PNG · 300 dpi", figure_bytes(fig, "png"), "experiment.png", "image/png")
    b.download_button("下载 SVG · 矢量图", figure_bytes(fig, "svg"), "experiment.svg", "image/svg+xml")


def guide():
    st.caption("03 / GUIDE")
    st.title("使用说明")
    st.markdown("""
1. **配比计算**：确认试剂形式、摩尔质量、有效含量和独立水分，填写摩尔份数与目标质量，再下载称量清单。
2. **整理结果**：将 Excel 另存为 CSV UTF-8；每行代表一次测量，列名写清单位。数据来源可选“我的 DES 实验数据”或上传文件。
3. **分组与绘图**：选择定义同一实验条件的列（如 formulation），选择测量指标（如 lignin_yield_pct），下载汇总 CSV 或图片。

木质素得率 (%) = 木质素质量 (mg) ÷ [生物质质量 (g) × 1000] × 100%。

数据只在本机进程中处理。上传的结果不会自动保存；关闭或刷新页面前请下载需要的结果。
不同文件按列名对齐，未匹配的列保留为空；不换算单位，不填补缺失测量，不自动删除重复。

这是基于 Streamlit 官方 `hello` 仓库改造的本地程序，保留 Apache-2.0 许可证。
""")
    st.download_button("下载虚构示例 CSV", DEMO_CSV.read_bytes(), "demo_lignin.csv", "text/csv")
    st.download_button("下载我的实验数据 CSV", MY_CSV.read_bytes(), "my_des_runs.csv", "text/csv")
    st.download_button("下载空白记录模板", csv_bytes(pd.read_csv(DEMO_CSV).iloc[:0]), "results_template.csv", "text/csv")
    st.link_button("查看改造来源 · streamlit/hello (Apache-2.0)", "https://github.com/streamlit/hello")
