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
"""Streamlit page views: recipe calculator, results & figures, guide.

Kept in a separate module so every page can be run and tested headlessly with
streamlit.testing.v1.AppTest.
"""
from pathlib import Path

import pandas as pd
import streamlit as st

import auth
from lab_core import calculate_recipe, csv_bytes, merge_results, summarize
from lab_plots import figure_bytes, make_figure

ROOT = Path(__file__).parent
DEMO_CSV = ROOT / "sample_data/demo_lignin.csv"
MY_CSV = ROOT / "sample_data/my_des_runs.csv"
LABELS = {"name": "Component / reagent form", "mw": "Molar mass (g/mol)", "ratio": "Molar ratio",
          "assay_pct": "Active content (wt%)", "water_pct": "Separate water (wt%)"}
Y_LABELS = {"lignin_yield_pct": "Lignin yield (%)", "lignin_mg": "Recovered lignin (mg)",
            "biomass_g": "Biomass (g)", "dry_strength_MPa": "Dry strength (MPa)",
            "wet_strength_MPa": "Wet strength (MPa)"}


def calculator():
    st.caption("01 / PREPARE")
    st.title("DES Recipe Calculator")
    st.write("Enter molar ratios and the real reagent assays to get a traceable weighing list.")
    st.info("The numbers below are a calculation example, not a recommended formulation. Update them from your "
            "reagent labels; a mass balance cannot prove that a mixture has formed a DES.")

    st.markdown("**1 · Purity of each reagent**")
    ideal = st.toggle("Assume 100 wt% purity (ideal)", value=False, key="ideal",
                      help="On: every reagent is treated as 100% active, so the reagent to weigh equals the "
                           "active mass. With no extra water the total prepared mass then equals the target "
                           "mass. Off: type the real assay from each bottle into the table below.")
    default_assay = 100.0 if ideal else 98.0
    components = st.data_editor(pd.DataFrame([
        {"name": "ChCl", "mw": 139.62, "ratio": 1.0, "assay_pct": default_assay, "water_pct": 0.0},
        {"name": "Glyoxylic acid (solid)", "mw": 74.04, "ratio": 2.0, "assay_pct": default_assay, "water_pct": 0.0},
    ]), column_config=LABELS, num_rows="dynamic", hide_index=True, width="stretch",
        disabled=["assay_pct"] if ideal else [], key="components")
    if ideal:
        components = components.copy()
        components["assay_pct"] = 100.0
    st.caption("Edit **Active content (wt%)** per row for the real bottle label (98, 99, 100 …). Below 100 %, the "
               "missing part is impurity — never solvent water. Add a third component on the last row; enter any "
               "real water separately in **Separate water (wt%)**.")

    st.markdown("**2 · How much to prepare**")
    a, b, c = st.columns([2, 1, 1])
    basis_label = a.selectbox("Target mass basis",
                             ["Total active components (excluding solvent water)",
                              "Total reagent weighed (including carried water)"], key="basis")
    target = b.number_input("Target mass (g)", min_value=0.001, value=10.0, step=1.0, format="%.3f", key="target")
    water = c.number_input("Extra water added (g)", min_value=0.0, value=0.0, step=0.1, format="%.3f", key="water")
    st.caption("Extra water is always added on top of the target mass. Hydrates: use the molar mass of the hydrate "
               "and do not enter its crystal water again as separate water.")
    basis = "active" if basis_label.startswith("Total active") else "reagent"
    try:
        recipe, totals = calculate_recipe(components, target, basis, water)
    except ValueError as exc:
        st.error(str(exc))
        return
    active_sum = float(recipe["active_g"].sum())
    weighed_sum = float(recipe["weigh_g"].sum())
    over_pct = 100 * (weighed_sum / active_sum - 1) if active_sum else 0.0
    st.markdown("**3 · Result**")
    a, b, c, d = st.columns(4)
    a.metric("Total prepared mass", f"{totals['total_g']:.4f} g")
    b.metric("Entered water + extra water", f"{totals['known_water_g']:.4f} g")
    c.metric("Water mass fraction counted", f"{totals['known_water_pct']:.2f}%")
    d.metric("Weighed above active mass", f"{over_pct:.2f}%",
             help="How much extra reagent you weigh to deliver the same active amount because of the assay. "
                  "0.00% means the reagents are being treated as 100 wt% pure.")
    if over_pct < 1e-9 and not water:
        st.success("Every reagent is 100 wt% and no extra water is added, so **total prepared mass = target mass** "
                   "exactly. That is expected, not a bug: you are weighing only active component.")
    else:
        st.caption(f"Because of the assay you weigh **{over_pct:.2f}%** more reagent than the active mass it "
                   f"delivers ({weighed_sum:.4f} g weighed for {active_sum:.4f} g active). "
                   f"Set the assay to 100 % to see the ideal case where both are equal.")
    st.caption("Water accounting covers only the separate water you entered plus extra water; absorbed water, "
               "crystal water and evaporation are not estimated.")
    result_labels = {**LABELS, "moles": "Amount (mol)", "active_g": "Active component (g)",
                     "weigh_g": "Reagent to weigh (g)", "water_g": "Carried water (g)"}
    st.subheader("Weighing list")
    st.dataframe(recipe.rename(columns=result_labels).round(6), hide_index=True, width="stretch")
    export = recipe.copy()
    export["target_basis"] = basis
    export["target_g"] = target
    export["added_water_g"] = water
    for name, value in totals.items():
        export[name] = value
    st.download_button("Download recipe CSV", csv_bytes(export), "des_recipe.csv", "text/csv")
    user = auth.current_user()
    if user:
        if st.button("Save this weighing list to my records", key="save_recipe"):
            saved = auth.save_recipe(user, export)
            st.success(f"Saved to {saved}")
    with st.expander("Formulas and data sources"):
        st.markdown("With molar ratio r, molar mass M and active content p (as a fraction): "
                    "active mass = k × r × M, and reagent to weigh = active mass / p. "
                    "The scale factor k follows from the selected target mass.")
        st.markdown("**Purity**: at 98 wt% you weigh 1 / 0.98 = 2.04 % more reagent than the active mass it "
                    "delivers. At 100 wt% the two are equal, so with no extra water the total prepared mass "
                    "equals the target mass exactly. The missing percent at 98 wt% is impurity, and it is never "
                    "counted as water or solvent.")
        st.markdown("Preset molar masses: [ChCl 139.62](https://www.sigmaaldrich.com/GI/en/product/sigma/c1879); "
                    "[glyoxylic acid 74.04](https://www.sigmaaldrich.com/PM/en/product/aldrich/260150). "
                    "Both presets are 98 wt% solids with no separate water; the remaining 2% is impurity, not water.")


def results():
    st.caption("02 / ANALYZE")
    st.title("Results and Figures")
    st.write("Merge data → choose conditions → check replicates and spread → export figures.")
    user = auth.current_user()
    sources = (["My saved data"] if user else []) + [
        "Sample: my DES runs (3 conditions, n=1)", "Fictitious demo (9 rows)", "Upload my CSV"]
    source = st.radio("Data source", sources, horizontal=True, key="source")
    if source.startswith("My saved"):
        saved = auth.load_results(user)
        if saved is None or saved.empty:
            st.info("No rows in your record folder yet. Upload a CSV below and press **Save to my records**, or "
                    "import the three recorded runs to start from.")
            if st.button("Import the 3 recorded runs into my records", key="import_runs"):
                auth.save_results(user, pd.read_csv(MY_CSV), append=False)
                st.rerun()
            return
        st.caption(f"Loaded **{len(saved)} rows** from `{auth.results_path(user)}`.")
        files = [(f"{user}_results.csv", auth.results_path(user).read_bytes())]
        encoding, data_kind = "utf-8-sig", "user_saved"
    elif source.startswith("Sample"):
        st.info("Three recorded runs: ChCl:GA = 1:1 / 1:2 / 2:1. Each condition was measured once, so no error "
                "bar is drawn.")
        files = [("my_des_runs.csv", MY_CSV.read_bytes())]
        encoding, data_kind = "utf-8-sig", "my_experiments"
    elif source.startswith("Fictitious"):
        st.warning("DEMO · The 9 rows below are entirely fictitious. They only demonstrate the workflow and are "
                   "not your results or any literature value.")
        files = [("demo_lignin.csv", DEMO_CSV.read_bytes())]
        encoding, data_kind = "utf-8-sig", "synthetic_demo"
    else:
        uploads = st.file_uploader("Choose one or more CSV files (one measurement per row; identical column "
                                   "names must use identical units)", type="csv", accept_multiple_files=True)
        encoding = st.selectbox("File encoding", ["utf-8-sig", "gb18030"],
                                help="If a Chinese CSV fails to load, choose gb18030.")
        if not uploads:
            st.info("Upload a CSV, or open one of the samples. Save Excel files as CSV UTF-8 first.")
            return
        files = [(f.name, f.getvalue()) for f in uploads]
        data_kind = "user_uploaded"
    try:
        frame = merge_results(files, encoding)
    except (ValueError, UnicodeError, pd.errors.ParserError) as exc:
        st.error(f"Cannot read the CSV: {exc}")
        return
    if frame.empty:
        st.info("The file has no data rows.")
        return
    columns = [c for c in frame.columns if c != "_source_file"]
    a, b, c = st.columns(3)
    a.metric("Merged rows", len(frame))
    b.metric("Source files", len(files))
    duplicate_count = int(frame.duplicated(subset=columns).sum())
    c.metric("Exact duplicate rows", duplicate_count)
    if duplicate_count:
        st.warning("Duplicate rows found and kept. Check whether the same file was imported twice; identical "
                   "values can also be genuine replicates.")
    with st.expander("Merged raw data (source file preserved)", expanded=False):
        st.dataframe(frame, hide_index=True, width="stretch")
        st.download_button("Download merged CSV", csv_bytes(frame), "merged_results.csv", "text/csv")
        if user and data_kind == "user_uploaded":
            st.divider()
            st.caption(f"Saving writes to `{auth.results_path(user)}`, which only exists on this machine.")
            mode = st.radio("Save mode", ["Append to my saved data", "Replace my saved data"],
                            horizontal=True, key="save_mode")
            if st.button("Save these rows to my records", key="save_results"):
                path = auth.save_results(user, frame, append=mode.startswith("Append"))
                st.success(f"Saved {len(frame)} rows to {path}")
    default_groups = [c for c in ["formulation", "temperature_C", "time_min"] if c in columns]
    groups = st.multiselect("Group by which experimental conditions?", columns, default=default_groups, key="groups")
    candidates = [c for c in columns if c not in groups and pd.to_numeric(frame[c], errors="coerce").notna().any()]
    if not groups or not candidates:
        st.info("Select at least one grouping column and keep one numeric measurement column.")
        return
    for first_choice in ("lignin_yield_pct", "lignin_mg", "dry_strength_MPa"):
        if first_choice in candidates:
            preferred = candidates.index(first_choice)
            break
    else:
        preferred = 0
    measurement = st.selectbox("Measurement column (units in the name)", candidates, index=preferred, key="measurement")
    st.caption("Lignin yield (%) = lignin mass (mg) ÷ [biomass mass (g) × 1000] × 100%. Group by every condition that "
               "defines a run (formulation, moisture, feedstock, temperature, time). Each row counts as one "
               "observation; the program cannot tell whether rows are independent replicates.")
    try:
        clean, summary, audit = summarize(frame, groups, measurement)
    except (ValueError, TypeError) as exc:
        st.error(str(exc))
        return
    if audit["excluded"]:
        st.warning(f"{audit['excluded']} row(s) excluded from the summary: non-numeric / missing / infinite "
                   f"measurements {audit['invalid_measurement']}, missing group values {audit['missing_groups']} "
                   f"(causes can overlap). The raw data is preserved.")
        with st.expander("Rows excluded from the summary"):
            st.dataframe(frame.loc[~audit["valid_mask"]], hide_index=True)
    if summary.empty:
        st.error("No complete valid rows for the selected columns.")
        return
    st.subheader("Grouped summary")
    st.dataframe(summary, hide_index=True, width="stretch")
    st.caption("n = valid measurements; mean = average; sd = sample standard deviation (ddof=1). With n=1 the sd is "
               "left blank and no error bar is drawn.")
    summary_export = summary.assign(measurement=measurement, data_kind=data_kind)
    st.download_button("Download summary CSV", csv_bytes(summary_export), "summary.csv", "text/csv")
    if len(summary) > 30:
        st.info("More than 30 groups. Narrow the data range before plotting; the summary can still be downloaded.")
        return
    a, b = st.columns(2)
    title = a.text_input("Figure title",
                         value="DEMO · fictitious example" if data_kind == "synthetic_demo"
                         else "DES pretreatment · lignin yield")
    ylabel = b.text_input("Y-axis title / unit", value=Y_LABELS.get(measurement, measurement),
                          key=f"ylabel_{measurement}")
    fig = make_figure(clean, summary, groups, measurement, title, ylabel)
    st.pyplot(fig, width="stretch")
    st.caption("Bar = mean · error bar = ±1 sample SD · dots = raw observations. Error bars are not a significance "
               "test.")
    a, b = st.columns(2)
    a.download_button("Download PNG · 300 dpi", figure_bytes(fig, "png"), "experiment.png", "image/png")
    b.download_button("Download SVG · vector", figure_bytes(fig, "svg"), "experiment.svg", "image/svg+xml")


def guide():
    st.caption("03 / GUIDE")
    st.title("How to use")
    st.markdown("""
1. **Recipe calculator**: confirm the reagent form, molar mass, active content and separate water, enter the molar
   ratios and target mass, then download the weighing list.
2. **Results**: save Excel as CSV UTF-8; one row per measurement, with units in the column names. Pick "My DES runs"
   or upload your own files.
3. **Group and plot**: choose the columns that define one experimental condition (for example `formulation`), pick
   the measurement (for example `lignin_yield_pct`), then download the summary CSV or the figure.

Lignin yield (%) = lignin mass (mg) ÷ [biomass mass (g) × 1000] × 100%.

Data is processed in this local process only. Uploaded results are only kept if you press **Save to my records**;
download anything else you need before closing or refreshing the page. Files are aligned by column name, unmatched
columns stay empty, units are never converted, missing measurements are never filled in and duplicates are never
deleted automatically.

This is a local workbench built on Streamlit's official `hello` repository, keeping the Apache-2.0 licence.
""")
    st.download_button("Download fictitious demo CSV", DEMO_CSV.read_bytes(), "demo_lignin.csv", "text/csv")
    st.download_button("Download my experiment data CSV", MY_CSV.read_bytes(), "my_des_runs.csv", "text/csv")
    st.download_button("Download blank record template", csv_bytes(pd.read_csv(DEMO_CSV).iloc[:0]),
                       "results_template.csv", "text/csv")
    st.link_button("Source project · streamlit/hello (Apache-2.0)", "https://github.com/streamlit/hello")

    st.divider()
    st.subheader("Account & team")
    user = auth.current_user()
    if not user:
        st.info("Sign in to see your record folder here.")
        return
    st.markdown(f"Signed in as **{user}** · your records: `{auth.user_dir(user)}`")
    st.caption("Everything you save stays in that folder on this machine. It is git-ignored, so it never reaches "
               "GitHub.")

    left, right = st.columns(2)
    with left:
        st.markdown("**Change my password**")
        with st.form("change_password", clear_on_submit=True):
            first = st.text_input("New password", type="password")
            second = st.text_input("Repeat new password", type="password")
            if st.form_submit_button("Change password"):
                if first != second:
                    st.error("The two passwords do not match.")
                elif len(first) < 6:
                    st.error("Use at least 6 characters.")
                else:
                    auth.change_password(user, first)
                    st.success("Password updated for this local account.")
    with right:
        st.markdown("**Add a teammate**")
        with st.form("add_teammate", clear_on_submit=True):
            name = st.text_input("Username", placeholder="teammate's username")
            initial = st.text_input("Initial password", type="password")
            if st.form_submit_button("Add teammate"):
                try:
                    auth.add_user(name, initial)
                    st.success(f"Account created for {name.strip()}. Their records get their own folder.")
                except ValueError as exc:
                    st.error(str(exc))
