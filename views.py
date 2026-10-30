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
streamlit.testing.v1.AppTest. All user-facing text goes through i18n.t().
"""
import io
import re
import time
from pathlib import Path

import pandas as pd
import streamlit as st

import auth
import chem
import compare
import excel_export
import excel_io
import schema
import feedback as feedback_mod
import store
import i18n
import mailer
from i18n import t
from lab_core import calculate_recipe, csv_bytes, merge_results, summarize
import lab_plots
import papers

ROOT = Path(__file__).parent
DEMO_CSV = ROOT / "sample_data/demo_lignin.csv"
MY_CSV = ROOT / "sample_data/my_des_runs.csv"


def _column_labels() -> dict:
    return {"name": t("calc.col_name"), "mw": t("calc.col_mw"), "ratio": t("calc.col_ratio"),
            "assay_pct": t("calc.col_assay"), "water_pct": t("calc.col_water")}


def _y_label(measurement: str) -> str:
    known = {"lignin_yield_pct": ("Lignin yield (%)", "木质素得率 (%)"),
             "lignin_mg": ("Recovered lignin (mg)", "回收木质素 (mg)"),
             "biomass_g": ("Biomass (g)", "生物质 (g)"),
             "dry_strength_MPa": ("Dry strength (MPa)", "干强度 (MPa)"),
             "wet_strength_MPa": ("Wet strength (MPa)", "湿强度 (MPa)")}
    pair = known.get(measurement)
    if not pair:
        return measurement
    return pair[1] if i18n.lang() == "zh" else pair[0]


def _recipe_rows() -> list:
    """The component table lives in session state so the look-up page can append to it."""
    rows = st.session_state.get("recipe_rows")
    if rows is None:
        rows = [
            {"name": t("calc.preset_chcl"), "mw": 139.62, "ratio": 1.0, "assay_pct": 98.0, "water_pct": 0.0},
            {"name": t("calc.preset_ga"), "mw": 74.04, "ratio": 2.0, "assay_pct": 98.0, "water_pct": 0.0},
        ]
        st.session_state["recipe_rows"] = rows
    return rows


def _add_reagent(term: str) -> None:
    """Look a reagent up on PubChem and append it to the component table."""
    try:
        cids = chem.find_cids(term)
        if not cids:
            st.warning(t("lookup.notfound", term=term))
            return
        record = chem.compound(cids[0])
    except chem.ChemError as exc:
        st.error(t("lookup.offline") if str(exc) == "offline" else str(exc))
        return
    rows = _recipe_rows()
    rows.append({"name": record["name"], "mw": float(record["mw"] or 0.0), "ratio": 1.0,
                 "assay_pct": 98.0, "water_pct": 0.0})
    st.session_state["recipe_rows"] = rows
    st.success(t("calc.reagent_added", name=record["name"],
                 mw=f"{record['mw']:.3f}" if record["mw"] else "-"))
    st.session_state["last_reagent"] = record


def calculator():
    labels = _column_labels()
    st.title(t("calc.title"))
    st.write(t("calc.intro"))
    st.info(t("calc.info"))

    st.markdown(t("calc.s1"))
    ideal = st.toggle(t("calc.ideal"), value=False, key="ideal", help=t("calc.ideal_help"))
    find_left, find_right = st.columns([3, 1])
    query = find_left.text_input(t("calc.find_label"), placeholder=t("calc.find_ph"), key="calc_find")
    if find_right.button(t("calc.find_add"), key="calc_find_add", use_container_width=True) and query.strip():
        _add_reagent(query.strip())
    st.caption(t("calc.find_hint"))

    rows = _recipe_rows()
    components = st.data_editor(pd.DataFrame(rows), column_config=labels, num_rows="dynamic",
                                hide_index=True, width="stretch",
                                disabled=["assay_pct"] if ideal else [],
                                key=f"components_{len(rows)}")
    if ideal:
        components = components.copy()
        components["assay_pct"] = 100.0
    st.session_state["recipe_rows"] = components.to_dict("records")
    st.caption(t("calc.table_caption"))

    record = st.session_state.get("last_reagent")
    if record:
        unknown = t("lookup.unknown_value")
        with st.expander(t("calc.reagent_details", name=record["name"]), expanded=True):
            a, b, c, d = st.columns(4)
            a.metric(t("lookup.mw"), f"{record['mw']:.3f} g/mol" if record["mw"] else unknown)
            b.metric(t("lookup.formula"), record["formula"] or unknown)
            c.metric(t("lookup.cas"), record["cas"] or unknown)
            d.metric(t("lookup.cid"), str(record["cid"]))
            a, b, c, d = st.columns(4)
            a.metric(t("lookup.hbd"), f"{record['hbd']:.0f}" if record["hbd"] is not None else unknown)
            b.metric(t("lookup.hba"), f"{record['hba']:.0f}" if record["hba"] is not None else unknown)
            c.metric(t("lookup.xlogp"), f"{record['xlogp']:g}" if record["xlogp"] is not None else unknown)
            d.metric(t("lookup.tpsa"), f"{record['tpsa']:g}" if record["tpsa"] is not None else unknown)
            if record["iupac"]:
                st.caption(record["iupac"])
            st.code(record["smiles"] or unknown, language="text")
            st.link_button(t("lookup.open"), record["url"], use_container_width=False)
            st.caption(t("lookup.source"))

    st.markdown(t("calc.s2"))
    bases = [("active", t("calc.basis_active")), ("reagent", t("calc.basis_reagent"))]
    a, b, c = st.columns([2, 1, 1])
    basis_label = a.selectbox(t("calc.basis"), [label for _, label in bases], key="basis")
    target = b.number_input(t("calc.target"), min_value=0.001, value=10.0, step=1.0, format="%.3f", key="target")
    water = c.number_input(t("calc.water"), min_value=0.0, value=0.0, step=0.1, format="%.3f", key="water")
    st.caption(t("calc.water_caption"))
    basis = dict((label, key) for key, label in bases)[basis_label]
    try:
        recipe, totals = calculate_recipe(components, target, basis, water)
    except ValueError as exc:
        st.error(t(str(exc)))
        return
    active_sum = float(recipe["active_g"].sum())
    weighed_sum = float(recipe["weigh_g"].sum())
    over_pct = 100 * (weighed_sum / active_sum - 1) if active_sum else 0.0

    st.markdown(t("calc.s3"))
    a, b, c, d = st.columns(4)
    a.metric(t("calc.m_total"), f"{totals['total_g']:.4f} g")
    b.metric(t("calc.m_water"), f"{totals['known_water_g']:.4f} g")
    c.metric(t("calc.m_water_pct"), f"{totals['known_water_pct']:.2f}%")
    d.metric(t("calc.m_over"), f"{over_pct:.2f}%", help=t("calc.over_help"))
    if over_pct < 1e-9 and not water:
        st.success(t("calc.success_ideal"))
    else:
        st.caption(t("calc.caption_assay", over=over_pct, weighed=weighed_sum, active=active_sum))
    st.caption(t("calc.caption_water"))

    result_labels = {**labels, "moles": t("calc.moles"), "active_g": t("calc.active_g"),
                     "weigh_g": t("calc.weigh_g"), "water_g": t("calc.water_g")}
    st.subheader(t("calc.weighing"))
    st.dataframe(recipe.rename(columns=result_labels).round(6), hide_index=True, width="stretch")
    export = recipe.copy()
    export["target_basis"] = basis
    export["target_g"] = target
    export["added_water_g"] = water
    for name, value in totals.items():
        export[name] = value
    st.download_button(t("calc.download"), csv_bytes(export), "des_recipe.csv", "text/csv")
    user = auth.current_user()
    if user:
        if st.button(t("calc.save"), key="save_recipe"):
            saved = auth.save_recipe(user, export)
            st.success(t("calc.saved", path=saved))
    with st.expander(t("calc.formulas")):
        st.markdown(t("calc.formula_1"))
        st.markdown(t("calc.formula_2"))
        st.markdown(t("calc.formula_3"))


RECORD_COLUMNS = ["sample_id", "formulation", "feedstock", "des_hba", "des_hbd", "molar_ratio",
                  "purity_wt_pct", "water_wt_pct", "biomass_g", "temperature_C", "time_min",
                  "lignin_mg", "lignin_yield_pct", "replicate", "notes", "recorded_at"]
ORDER_KEYS = ("given", "label", "mean_desc", "mean_asc")


def _yield_pct(biomass_g, lignin_mg):
    """Lignin yield in percent, or None when the numbers cannot support it."""
    try:
        biomass = float(biomass_g)
        lignin = float(lignin_mg)
    except (TypeError, ValueError):
        return None
    if biomass <= 0 or lignin < 0:
        return None
    return round(lignin / (biomass * 1000.0) * 100.0, 4)


def _next_sample_id(frame: pd.DataFrame) -> str:
    if frame is None or frame.empty or "sample_id" not in frame:
        return "EXP-01"
    numbers = []
    for value in frame["sample_id"].dropna().astype(str):
        match = re.search(r"(\d+)\s*$", value)
        if match:
            numbers.append(int(match.group(1)))
    if numbers:
        return f"EXP-{max(numbers) + 1:02d}"
    return f"EXP-{len(frame) + 1:02d}"


@st.cache_data(show_spinner=False, ttl=600)
def _cached_merge(files: tuple, encoding: str) -> pd.DataFrame:
    """Merging the same files again is pure work: keep the result for a while."""
    return merge_results([(name, content) for name, content in files], encoding)


@st.cache_data(show_spinner=False, ttl=600)
def _cached_summary(frame: pd.DataFrame, groups: tuple, measurement: str):
    return summarize(frame, list(groups), measurement)


@st.cache_data(show_spinner=False, ttl=600)
def _cached_figure(clean: pd.DataFrame, summary: pd.DataFrame, groups: tuple, measurement: str,
                   title: str, ylabel: str, bar_colour: str, point_colour: str,
                   show_errors: bool, show_values: bool, show_points: bool,
                   y_from, y_to, order: str):
    """Drawing costs a few hundred milliseconds; cache it per input."""
    ordered = lab_plots.order_summary(summary, order)
    return lab_plots.make_figure(clean, ordered, list(groups), measurement, title, ylabel,
                                 bar_colour=bar_colour, point_colour=point_colour,
                                 show_errors=show_errors, show_values=show_values,
                                 show_points=show_points, y_from=y_from, y_to=y_to)


@st.cache_data(show_spinner=False, ttl=600)
def _cached_figure_bytes(clean: pd.DataFrame, summary: pd.DataFrame, groups: tuple, measurement: str,
                         title: str, ylabel: str, bar_colour: str, point_colour: str,
                         show_errors: bool, show_values: bool, show_points: bool,
                         y_from, y_to, order: str, fmt: str, dpi: int) -> bytes:
    fig = _cached_figure(clean, summary, groups, measurement, title, ylabel, bar_colour, point_colour,
                         show_errors, show_values, show_points, y_from, y_to, order)
    return lab_plots.figure_bytes(fig, fmt, dpi=int(dpi))


@st.cache_data(show_spinner=False, ttl=15)
def _cached_saved(user: str, where: str, project: str | None = None):
    """Reading the records costs a database round trip; cache it briefly.

    ``where`` (the store location) is part of the key so two stores never share an entry, and
    ``project`` keeps one project's rows out of another's view.
    """
    frame = auth.load_results(user)
    if frame is None or not project or "project" not in frame.columns:
        return frame
    return frame[frame["project"].fillna(auth.DEFAULT_PROJECT) == project].reset_index(drop=True)


@st.cache_data(show_spinner=False, ttl=60)
def _cached_db_status() -> tuple:
    return True, store.ping()


def _store_where() -> str:
    try:
        return str(auth.data_root())
    except Exception:
        return "unknown"


def _dataset_zip(frame: pd.DataFrame) -> bytes:
    """One row per experiment in three forms: JSONL (for training), CSV (for spreadsheets),
    and a data dictionary (what every column means and looks like)."""
    import json
    import zipfile

    export = frame.copy()
    if "_owner" in export.columns:
        export = export.rename(columns={"_owner": "recorded_by"})
    lines = []
    for record in export.to_dict("records"):
        clean = {str(key): (None if (isinstance(value, float) and pd.isna(value)) else value)
                 for key, value in record.items()}
        lines.append(json.dumps(clean, ensure_ascii=False, default=str))
    jsonl = "\n".join(lines).encode("utf-8")

    dictionary = ["# Dataset dictionary", "",
                  f"- rows: {len(export)}", f"- columns: {len(export.columns)}", "",
                  "## Columns", ""]
    for column in export.columns:
        values = export[column].dropna()
        kind = "text" if values.map(lambda v: isinstance(v, str)).all() else "number"
        sample = "no values"
        if len(values):
            sample = str(values.iloc[0])[:40]
        dictionary.append(f"- **{column}** ({kind}): e.g. {sample}")
    dictionary_text = "\n".join(dictionary).encode("utf-8")

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("experiments.jsonl", jsonl)
        archive.writestr("experiments.csv", export.to_csv(index=False).encode("utf-8-sig"))
        archive.writestr("data_dictionary.md", dictionary_text)
        # the pictures travel with the data, filed under the run they belong to
        try:
            user = auth.current_user()
            for row in auth.images_of(user) if user else []:
                stored = auth.image_content(user, int(row["id"]))
                if not stored:
                    continue
                folder = str(row.get("sample_id") or "unassigned")
                name = str(row.get("filename") or f"image_{row['id']}.png")
                archive.writestr(f"images/{folder}/{row['id']}_{name}", stored[0])
                if row.get("note") or row.get("category"):
                    archive.writestr(f"images/{folder}/{row['id']}_note.txt",
                                     f"{row.get('category') or ''}\n{row.get('note') or ''}\n"
                                     .encode("utf-8"))
        except Exception:
            pass  # a missing picture must never stop the data export
    return buffer.getvalue()


def _read_any(name: str, content: bytes) -> tuple[pd.DataFrame, dict | None]:
    """Read a CSV or an Excel sheet; Excel also returns what had to be guessed."""
    if excel_io.is_excel(name):
        result = excel_io.read_table(content)
        return result["frame"], result
    return pd.read_csv(io.BytesIO(content), encoding="utf-8-sig"), None


def _project_picker(user: str | None) -> str:
    """The project every write goes into and every read is filtered by."""
    if not user:
        return auth.DEFAULT_PROJECT
    projects = auth.list_projects(user)
    # a freshly created project becomes the default on the next run; assigning the widget's own key
    # after it exists raises StreamlitWidgetAlreadyInstantiatedError
    wanted = st.session_state.pop("project_wanted", None)
    if wanted and wanted in projects:
        st.session_state["project_pick"] = wanted
    if st.session_state.get("project_pick") not in projects:
        st.session_state["project_pick"] = projects[0]
    choice = st.selectbox(t("res.project"), projects, key="project_pick",
                          help=t("res.project_help"))
    states = auth.project_statuses(user)
    current = states.get(choice, "In progress")
    labels = [_status_label(item) for item in auth.PROJECT_STATUSES]
    picked = st.selectbox(t("exp.status"), labels,
                          index=max(0, labels.index(_status_label(current)))
                          if _status_label(current) in labels else 1,
                          key=f"status_{choice}")
    wanted = dict(zip(labels, auth.PROJECT_STATUSES))[picked]
    if wanted != current:
        auth.set_project_status(user, choice, wanted)
    with st.expander(t("res.project_new"), expanded=False):
        with st.form("new_project", clear_on_submit=True):
            name = st.text_input(t("res.project_name"), placeholder=t("res.project_ph"))
            if st.form_submit_button(t("res.project_create")):
                try:
                    created = auth.create_project(user, name)
                except ValueError as exc:
                    st.error(t(str(exc)))
                else:
                    st.success(t("res.project_created", name=created))
                    st.session_state["project_wanted"] = created
                    st.rerun()
    return choice


def _search_section(frame: pd.DataFrame) -> None:
    """Find a past run by any word in it: id, formulation, feedstock, note, project."""
    if frame is None or frame.empty:
        return
    with st.expander(t("res.search"), expanded=False):
        term = st.text_input(t("res.search_ph"), key="records_search",
                             placeholder=t("res.search_example"))
        if not term.strip():
            st.caption(t("res.search_hint"))
            return
        needle = term.strip().lower()
        haystack = frame.astype(str).apply(lambda column: column.str.lower(), axis=0)
        mask = haystack.apply(lambda row: needle in " ".join(row.values), axis=1)
        found = frame[mask]
        if found.empty:
            st.warning(t("res.search_none", term=term.strip()))
            return
        st.success(t("res.search_found", n=len(found)))
        columns = [column for column in ("sample_id", "formulation", "feedstock", "molar_ratio",
                                         "biomass_g", "lignin_mg", "lignin_yield_pct",
                                         "recorded_at", "notes") if column in found.columns]
        st.dataframe(found[columns], width="stretch", hide_index=True)
        st.download_button(t("res.search_download"), csv_bytes(found[columns]),
                           "search_results.csv", "text/csv", key="search_download")


def _library_results(query: str, since, citations: int, sort: str, limit: int) -> list:
    @st.cache_data(show_spinner=False, ttl=3600)
    def run(text: str, since_year, min_cites: int, order: str, count: int):
        return papers.search(text, limit=count, since=since_year,
                             min_citations=min_cites, sort=order)

    return run(query, since, citations, sort, limit)


def library() -> None:
    st.markdown(t("lib.title"))
    st.caption(t("lib.sub"))
    with st.form("paper_search"):
        query = st.text_input(t("lib.query"), placeholder=t("lib.query_ph"))
        a, b, c, d = st.columns(4)
        since = a.number_input(t("lib.since"), min_value=1900, max_value=2100, value=2015, step=1)
        citations = b.number_input(t("lib.min_cites"), min_value=0, value=0, step=5)
        order = c.selectbox(t("lib.order"), [t("lib.by_relevance"), t("lib.by_citations"),
                                             t("lib.by_newest")])
        limit = d.number_input(t("lib.limit"), min_value=5, max_value=30, value=10, step=5)
        submitted = st.form_submit_button(t("lib.search"), type="primary")
    if not submitted or not query.strip():
        st.info(t("lib.how"))
        return

    mapping = {t("lib.by_relevance"): "relevant", t("lib.by_citations"): "cited",
               t("lib.by_newest"): "newest"}
    try:
        with st.spinner(t("lib.searching")):
            found = _library_results(query.strip(), int(since), int(citations),
                                     mapping.get(order, "relevant"), int(limit))
    except papers.PaperError as exc:
        st.error(t("lib.failed", error=str(exc)))
        return

    if not found:
        st.warning(t("lib.none", query=query.strip()))
        return
    st.caption(papers.summarise(query.strip(), found))
    for index, paper in enumerate(found, start=1):
        title = paper["title"]
        link = f"[{title}]({paper['url']})" if paper["url"] else title
        st.markdown(f"**{index}. {link}**")
        bits = [str(paper["year"]) or "n.d.", paper["venue"] or t("lib.no_venue"),
                t("lib.citations", n=paper["citations"])]
        if paper["authors"]:
            bits.insert(1, paper["authors"])
        st.caption(" · ".join(bits))
        if paper["abstract"]:
            with st.expander(t("lib.abstract"), expanded=False):
                st.write(paper["abstract"])
        if paper["doi"]:
            st.caption(f"DOI: `{paper['doi']}`")
        if st.button(t("lib.use_in_compare"), key=f"compare_{index}",
                     help=t("lib.use_in_compare_help")):
            st.session_state["compare_ref"] = {"title": paper["doi"] or paper["title"],
                                               "title_text": paper["title"]}
            st.session_state.pop("compare_outcome", None)
            _goto("compare")
        st.divider()


BASIS_KEYS = ("cmp.basis_yield", "cmp.basis_delign", "cmp.basis_purity", "cmp.basis_other")


def compare_page() -> None:
    st.markdown(t("cmp.title"))
    st.caption(t("cmp.sub"))
    user = auth.current_user()
    if not user:
        st.info(t("guide.signin_hint"))
        return

    saved = _cached_saved(user, _store_where())
    if saved is None or saved.empty or "sample_id" not in saved.columns:
        st.info(t("res.empty_records"))
        return
    ids = [str(value) for value in saved["sample_id"].dropna().unique()]

    mode = st.radio(t("cmp.mode"), [t("cmp.mode_paper"), t("cmp.mode_runs")],
                    horizontal=True, key="compare_mode")

    def _row_of(sample: str) -> dict:
        return saved[saved["sample_id"].astype(str) == str(sample)].iloc[0].to_dict()

    if mode == t("cmp.mode_runs"):
        st.subheader(t("cmp.mine"))
        a_col, b_col = st.columns(2)
        first = a_col.selectbox(t("cmp.run_a"), ids, key="compare_a")
        second = b_col.selectbox(t("cmp.run_b"), ids,
                                 index=min(1, len(ids) - 1), key="compare_b")
        if st.button(t("cmp.run_btn"), type="primary", key="compare_runs_btn"):
            if str(first) == str(second):
                st.warning(t("cmp.same_run"))
            else:
                left_row, right_row = _row_of(first), _row_of(second)
                mine = {**left_row, "basis": t("cmp.basis_yield"), "replicates": 3}
                theirs = {**right_row, "basis": t("cmp.basis_yield"), "replicates": 3}
                st.session_state["compare_outcome"] = compare.compare(mine, theirs)
                st.session_state["compare_result"] = {
                    "mine": mine, "theirs": theirs, "label": f"{first} vs {second}",
                    "sides": {"mine": str(first), "theirs": str(second)}}
        _render_outcome()
        return

    st.subheader(t("cmp.mine"))
    pick = st.selectbox(t("cmp.pick_run"), ids, key="compare_run")
    mine_row = saved[saved["sample_id"].astype(str) == str(pick)].iloc[0].to_dict()

    st.subheader(t("cmp.ref"))
    st.caption(t("cmp.ref_hint"))
    with st.form("compare_paper"):
        label = st.text_input(t("cmp.title_field"),
                              value=str(st.session_state.get("compare_ref", {}).get("title", "")),
                              placeholder="10.1016/j.indcrop.2022.115040")
        basis_labels = [t(key) for key in BASIS_KEYS]
        basis = st.selectbox(t("cmp.basis"), basis_labels, index=0, key="compare_basis")
        a, b, c = st.columns(3)
        feedstock = a.text_input(t("cmp.feedstock"), placeholder=str(mine_row.get("feedstock") or ""))
        ratio = b.text_input(t("cmp.ratio"), placeholder=str(mine_row.get("molar_ratio") or ""))
        purity = c.text_input(t("cmp.purity"), placeholder=str(mine_row.get("purity_wt_pct") or ""))
        a, b, c = st.columns(3)
        water = a.text_input(t("cmp.water"), placeholder=str(mine_row.get("water_wt_pct") or ""))
        temp = b.text_input(t("cmp.temp"), placeholder=str(mine_row.get("temperature_C") or ""))
        minutes = c.text_input(t("cmp.time"), placeholder=str(mine_row.get("time_min") or ""))
        a, b, c = st.columns(3)
        reported = a.text_input(t("cmp.yield"), placeholder="")
        replicates = b.text_input(t("cmp.replicates"), placeholder="")
        moisture = c.text_input(t("cmp.moisture"), placeholder="")
        if st.form_submit_button(t("cmp.run_btn"), type="primary"):
            if not str(reported).strip():
                st.error(t("cmp.need_numbers"))
            else:
                theirs = {
                    "lignin_yield_pct": reported, "basis": basis, "feedstock": feedstock,
                    "molar_ratio": ratio, "purity_wt_pct": purity, "water_wt_pct": water,
                    "temperature_C": temp, "time_min": minutes, "replicates": replicates,
                    "moisture_wt_pct": moisture,
                }
                mine = {
                    "lignin_yield_pct": mine_row.get("lignin_yield_pct"),
                    "basis": t("cmp.basis_yield"), "feedstock": mine_row.get("feedstock"),
                    "molar_ratio": mine_row.get("molar_ratio"),
                    "purity_wt_pct": mine_row.get("purity_wt_pct"),
                    "water_wt_pct": mine_row.get("water_wt_pct"),
                    "temperature_C": mine_row.get("temperature_C"),
                    "time_min": mine_row.get("time_min"),
                    "replicates": 3, "moisture_wt_pct": mine_row.get("moisture_wt_pct"),
                }
                st.session_state["compare_result"] = {
                    "mine": mine, "theirs": theirs, "label": label or pick,
                    "sides": {"mine": t("cmp.mine"), "theirs": t("cmp.ref")}}
                st.session_state["compare_outcome"] = compare.compare(mine, theirs)

    _render_outcome()


def _render_outcome() -> None:
    """The shared result block: two numbers, the difference, then the ranked explanations."""
    outcome = st.session_state.get("compare_outcome")
    if not outcome:
        st.caption(t("cmp.nothing_saved"))
        return

    st.divider()
    st.subheader(t("cmp.side_by_side"))
    details = st.session_state.get("compare_result", {})
    sides = details.get("sides") or {"mine": t("cmp.mine"), "theirs": t("cmp.ref")}
    cols = st.columns(3)
    for column, name, value in zip(
            cols,
            (sides["mine"], sides["theirs"], t("cmp.delta")),
            (details.get("mine", {}).get("lignin_yield_pct"),
             details.get("theirs", {}).get("lignin_yield_pct"),
             outcome["delta"])):
        if isinstance(value, (int, float)):
            column.metric(str(name), f"{value:.2f} %" if name != t("cmp.delta") else f"{value:+.2f}")
        else:
            column.metric(str(name), "—")
    st.caption(t("cmp.nothing_saved"))
    st.info(t(f"cmp.headline_{compare.headline(outcome)}"))

    st.subheader(t("cmp.explanations"))
    for item in outcome["findings"]:
        params = dict(item["params"])
        if "side" in params:
            sides = details.get("sides") or {}
            params["side"] = sides.get(params["side"]) or (
                t("cmp.mine") if params["side"] == "mine" else t("cmp.ref"))
        with st.container(border=True):
            st.markdown(f"**{t('cmp.tag_' + item['kind'])}** · "
                        f"{t('cmp.' + item['code'] + '.claim', **params)}")
            st.caption(t("cmp." + item["code"] + ".why", **params))
            st.markdown(f"*{t('cmp.' + item['code'] + '.check', **params)}*")
            st.markdown(t("cmp." + item["code"] + ".step", **params))


PAGE_OBJECTS: dict = {}


def _goto(key: str) -> None:
    """Switch to a registered page by key (file paths do not work for function-defined pages)."""
    page = PAGE_OBJECTS.get(key)
    if page is None:
        st.error(f"navigation target {key!r} is not registered")
        return
    st.switch_page(page)


CHIP_CLASS = {"Draft": "draft", "In progress": "running", "Pending test": "pending",
              "Completed": "done", "Needs review": "review"}


def _status_label(status: str) -> str:
    mapping = {"Draft": "exp.draft", "In progress": "exp.running", "Pending test": "exp.pending",
               "Completed": "exp.done", "Needs review": "exp.review"}
    return t(mapping.get(status, "exp.running"))


def workspace() -> None:
    """The signed-in home. New work happens here, so no button ever has to leave the page."""
    user = auth.current_user()
    if not user:
        st.info(t("guide.signin_hint"))
        return
    mode = st.session_state.get("ws_mode", "home")

    if mode == "new":
        if st.button("← " + t("ws.back"), key="ws_back"):
            st.session_state["ws_mode"] = "home"
            st.rerun()
        project = _project_picker(user)
        _record_tab(user, project)
        return

    if mode == "open":
        name = st.session_state.get("ws_open", auth.DEFAULT_PROJECT)
        if st.button("← " + t("ws.back"), key="ws_back_open"):
            st.session_state["ws_mode"] = "home"
            st.rerun()
        _experiment_panel(user, name)
        return

    st.markdown(f"### {t('ws.greeting', user=auth.display_name(user))}")
    st.caption(t("ws.question"))

    left, right = st.columns(2)
    if left.button(t("ws.new"), type="primary", use_container_width=True, key="ws_new"):
        st.session_state["ws_mode"] = "new"
        st.rerun()
    if right.button(t("ws.continue"), use_container_width=True, key="ws_continue"):
        latest = _latest_experiment(user)
        if latest:
            st.session_state["ws_open"] = latest
            st.session_state["ws_mode"] = "open"
            st.rerun()
        else:
            st.session_state["ws_mode"] = "new"
            st.rerun()

    st.divider()
    st.markdown(f"#### {t('ws.recent')}")
    projects = auth.list_projects(user)
    states = auth.project_statuses(user)
    frame = auth.load_results(user)
    if frame is None or frame.empty:
        st.caption(t("ws.none"))
        return

    rows = frame.copy()
    if "project" not in rows.columns:
        rows["project"] = auth.DEFAULT_PROJECT
    rows["project"] = rows["project"].fillna(auth.DEFAULT_PROJECT)
    grouped = []
    for name in projects:
        part = rows[rows["project"] == name]
        if part.empty:
            continue
        last = ""
        if "recorded_at" in part.columns:
            stamps = pd.to_datetime(part["recorded_at"], errors="coerce").dropna()
            last = stamps.max().strftime("%Y-%m-%d") if len(stamps) else ""
        grouped.append({"name": name, "runs": len(part), "last": last,
                        "status": states.get(name, "In progress")})
    grouped.sort(key=lambda item: item["last"], reverse=True)

    for item in grouped[:5]:
        with st.container(border=True):
            head, tail = st.columns([3, 1])
            key = CHIP_CLASS.get(item["status"], "running")
            head.markdown(f'<div class="bm-status bm-status-{key}">'
                          f'{_status_label(item["status"])}</div>', unsafe_allow_html=True)
            head.markdown(f"**{item['name']}**")
            head.caption(f"{t('ws.runs', n=item['runs'])} · "
                         f"{t('ws.last', date=item['last'] or '—')}")
            if tail.button(t("ws.open"), key=f"open_{item['name']}", use_container_width=True):
                st.session_state["ws_open"] = item["name"]
                st.session_state["ws_mode"] = "open"
                st.rerun()


def _latest_experiment(user: str | None) -> str | None:
    frame = auth.load_results(user)
    if frame is None or frame.empty:
        return None
    column = "project" if "project" in frame.columns else None
    if column is None:
        return auth.DEFAULT_PROJECT
    values = [str(value) for value in frame[column].dropna().unique()]
    return values[-1] if values else None


def _experiment_panel(user: str | None, name: str) -> None:
    """One experiment, read like a report: overview, formulation, process, results, records."""
    frame = auth.load_results(user)
    if frame is None or frame.empty:
        st.info(t("res.empty_records"))
        return
    frame = frame.copy()
    if "project" not in frame.columns:
        frame = frame.assign(project=auth.DEFAULT_PROJECT)
    frame["project"] = frame["project"].fillna(auth.DEFAULT_PROJECT)
    part = frame[frame["project"] == name].reset_index(drop=True)
    state = auth.project_statuses(user).get(name, "In progress")

    head, badge = st.columns([4, 1], vertical_alignment="center")
    head.markdown(f"### {name}")
    labels = [_status_label(item) for item in auth.PROJECT_STATUSES]
    current = _status_label(state)
    with badge:
        picked = st.selectbox(t("exp.status"), labels,
                              index=labels.index(current) if current in labels else 1,
                              key=f"panel_status_{name}", label_visibility="collapsed")
    wanted = dict(zip(labels, auth.PROJECT_STATUSES))[picked]
    if wanted != state:
        auth.set_project_status(user, name, wanted)
        st.rerun()

    if part.empty:
        st.info(t("ws.none"))
        return

    tab_overview, tab_formulation, tab_process, tab_results, tab_records = st.tabs(
        [t("exp.tab_overview"), t("exp.tab_formulation"), t("exp.tab_process"),
         t("exp.tab_results"), t("exp.tab_records")])

    latest = part.iloc[-1]
    with tab_overview:
        columns = st.columns(3)
        columns[0].metric(t("res.lignin_yield"),
                          f"{float(latest.get('lignin_yield_pct') or 0):.2f} %")
        columns[1].metric(t("res.lignin_mg"), f"{float(latest.get('lignin_mg') or 0):.1f} mg")
        columns[2].metric(t("ws.runs_label"), len(part))
        heading = auth.project_formulation(user, name)
        st.caption(t("exp.header_line", hba=heading["des_hba"], hbd=heading["des_hbd"],
                     ratio=heading["molar_ratio"], runs=len(part)))
        keep = [column for column in ("sample_id", "formulation", "lignin_yield_pct", "recorded_at")
                if column in part.columns]
        st.dataframe(part[keep], width="stretch", hide_index=True)

    with tab_formulation:
        current = auth.project_formulation(user, name)
        st.caption(t("exp.formulation_setting"))
        with st.form(f"formulation_{name}"):
            a, b, c = st.columns(3)
            hba = a.text_input(t("res.hba"), value=str(current["des_hba"]))
            hbd = b.text_input(t("res.hbd"), value=str(current["des_hbd"]))
            ratio = c.number_input(t("res.ratio"), min_value=0.0, value=float(current["molar_ratio"]),
                                   step=0.5, format="%.2f", help=t("res.ratio_help"))
            a, b, c = st.columns(3)
            purity = a.number_input(t("res.purity"), min_value=0.0, max_value=100.0,
                                    value=float(current["purity_wt_pct"]), step=1.0,
                                    format="%.1f")
            water = b.number_input(t("res.water"), min_value=0.0, max_value=100.0,
                                   value=float(current["water_wt_pct"]), step=0.5, format="%.2f")
            if st.form_submit_button(t("exp.formulation_save")):
                auth.set_project_formulation(user, name, {
                    "des_hba": hba.strip(), "des_hbd": hbd.strip(), "molar_ratio": float(ratio),
                    "purity_wt_pct": float(purity), "water_wt_pct": float(water)})
                st.success(t("exp.formulation_saved"))
        columns = [column for column in ("sample_id", "des_hba", "des_hbd", "molar_ratio",
                                         "purity_wt_pct", "water_wt_pct", "feedstock")
                   if column in part.columns]
        st.dataframe(part[columns], width="stretch", hide_index=True)
        st.caption(t("exp.formulation_note"))

    with tab_process:
        columns = [column for column in ("sample_id", "biomass_g", "temperature_C", "time_min",
                                         "replicate", "recorded_at") if column in part.columns]
        st.dataframe(part[columns], width="stretch", hide_index=True)
        st.caption(t("exp.process_note"))

    with tab_results:
        measurement = "lignin_yield_pct" if "lignin_yield_pct" in part.columns else part.columns[-1]
        groups = ["formulation"] if "formulation" in part.columns else []
        if groups and len(part) > 1:
            try:
                clean, summary, _audit = _cached_summary(part, tuple(groups), measurement)
                figure = _cached_figure(clean, summary, tuple(groups), measurement, name,
                                        _y_label(measurement), "#002F86", "#0B1F4B",
                                        True, False, True, None, None, "none")
                st.pyplot(figure, width="stretch")
                st.dataframe(summary, width="stretch", hide_index=True)
                st.caption(t("exp.results_note", n=len(clean)))
            except Exception as exc:  # a bad row must not take the page down
                st.warning(t("res.read_error", error=str(exc)[:160]))
        else:
            st.info(t("exp.results_single"))

    with tab_records:
        keep = [column for column in RECORD_COLUMNS if column in part.columns]
        st.dataframe(part[keep], width="stretch", hide_index=True)
        _photos_section(user, part)

    st.divider()
    st.caption(t("exp.traceability", date=str(latest.get("recorded_at") or "—"),
                 who=user or "—", rows=len(part)))
    row = st.columns(3)
    payload = excel_export.records_workbook(part, meta={"user": user or "", "scope": name})
    row[0].download_button(t("res.download_excel"), payload,
                           f"{auth.folder_name(user)}_{name}.xlsx",
                           "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                           key=f"exp_xlsx_{name}")
    row[1].download_button(t("res.download_table"), csv_bytes(part), f"{name}.csv", "text/csv",
                           key=f"exp_csv_{name}")
    if row[2].button(t("exp.add_run"), key=f"exp_add_{name}"):
        st.session_state["ws_mode"] = "new"
        st.rerun()

def _photos_section(user: str | None, frame: pd.DataFrame) -> None:
    """Attach pictures to a run: unlimited count, a category from the list, plus a note."""
    if not user:
        return
    with st.expander(t("res.photos"), expanded=False):
        st.caption(t("res.photos_hint"))
        if not store.enabled():
            st.info(t("res.photos_db_only"))
            return
        ids = []
        if frame is not None and not frame.empty and "sample_id" in frame.columns:
            ids = [str(value) for value in frame["sample_id"].dropna().unique()]
        if not ids:
            st.info(t("res.photos_no_runs"))
            return
        target = st.selectbox(t("res.photos_for"), ids, key="photo_sample")
        counts = auth.image_counts(user)
        st.caption(t("res.photos_count", n=counts.get(str(target), 0)))

        with st.form("add_photos", clear_on_submit=True):
            uploads = st.file_uploader(t("res.photos_upload"),
                                       type=["png", "jpg", "jpeg", "gif", "webp", "tif", "tiff", "bmp"],
                                       accept_multiple_files=True)
            category = st.selectbox(t("res.photos_category"), auth.IMAGE_CATEGORIES)
            note = st.text_input(t("res.photos_note"), placeholder=t("res.photos_note_ph"))
            if st.form_submit_button(t("res.photos_add")):
                if not uploads:
                    st.warning(t("res.photos_pick"))
                else:
                    saved_count, failed = 0, []
                    for upload in uploads:
                        try:
                            auth.add_image(user, str(target), category, note, upload.name,
                                           upload.type or "image/png", upload.getvalue())
                            saved_count += 1
                        except ValueError as exc:
                            failed.append(f"{upload.name}: {t(str(exc))}")
                    if saved_count:
                        st.success(t("res.photos_saved", n=saved_count, sample=target))
                    for message in failed:
                        st.error(message)

        existing = auth.images_of(user, str(target))
        if existing:
            st.markdown(t("res.photos_existing", n=len(existing)))
            for row in existing:
                left, right = st.columns([1, 3])
                stored = auth.image_content(user, int(row["id"]))
                if stored:
                    left.image(stored[0], width=140)
                right.markdown(f"**{row.get('category') or t('res.photos_no_category')}**")
                if row.get("note"):
                    right.caption(row["note"])
                right.caption(f"{row.get('filename')} · {int(row.get('size') or 0) // 1024} KB")
                if right.button(t("res.photos_delete"), key=f"del_image_{row['id']}"):
                    auth.remove_image(user, int(row["id"]))
                    st.rerun()


def _looks_duplicate(frame: pd.DataFrame, sample_id: str, lignin_mg: float,
                     biomass_g: float) -> bool:
    """True when the same run is already stored, so a double click cannot add it twice."""
    wanted = (str(sample_id or "").strip().lower(), round(float(lignin_mg), 4),
              round(float(biomass_g), 4))
    if not wanted[0] or "sample_id" not in frame.columns:
        return False
    for _, row in frame.iterrows():
        try:
            other = (str(row.get("sample_id", "")).strip().lower(),
                     round(float(row.get("lignin_mg")), 4),
                     round(float(row.get("biomass_g")), 4))
        except (TypeError, ValueError):
            continue
        if other == wanted:
            return True
    return False


def _record_tab(user: str | None, project: str = auth.DEFAULT_PROJECT) -> None:
    """Type one run in by hand: the yield is computed, the row goes into the records."""
    if not user:
        st.info(t("guide.signin_hint"))
        return
    saved = auth.load_results(user)
    saved = pd.DataFrame() if saved is None else saved
    st.caption(t("res.new_hint"))
    with st.form("record_run", clear_on_submit=True):
        left, right = st.columns(2)
        sample_id = left.text_input(t("res.sample_id"), value=_next_sample_id(saved), key="run_sample")
        feedstock = right.text_input(t("res.feedstock"), placeholder=t("res.feedstock_ph"),
                                     key="run_feedstock")
        formulation = auth.project_formulation(user, project)
        st.caption(t("res.project_formulation", hba=formulation["des_hba"],
                     hbd=formulation["des_hbd"], ratio=formulation["molar_ratio"],
                     purity=formulation["purity_wt_pct"]))
        hba, hbd = formulation["des_hba"], formulation["des_hbd"]
        ratio, purity = formulation["molar_ratio"], formulation["purity_wt_pct"]
        water = formulation["water_wt_pct"]
        replicate = st.number_input(t("res.replicate"), min_value=1, value=1, step=1,
                                    key="run_replicate")
        a, b, c, d = st.columns(4)
        biomass = a.number_input(t("res.biomass"), min_value=0.0, value=0.0, step=0.1,
                                 format="%.4f", key="run_biomass")
        lignin = b.number_input(t("res.lignin_mg"), min_value=0.0, value=0.0, step=0.1,
                                format="%.3f", key="run_lignin")
        temperature = c.number_input(t("res.temperature"), min_value=0.0, value=80.0, step=5.0,
                                     format="%.1f", key="run_temp")
        minutes = d.number_input(t("res.time"), min_value=0.0, value=60.0, step=5.0,
                                 format="%.0f", key="run_time")
        notes = st.text_input(t("res.notes"), key="run_notes")
        submitted = st.form_submit_button(t("res.save_run"), type="primary", use_container_width=True)
    preview = _yield_pct(biomass, lignin)
    label = schema.build_formulation({"des_hba": hba, "des_hbd": hbd, "molar_ratio": ratio})
    if label:
        st.caption(t("res.formulation_preview", label=label))
    if preview is not None:
        st.caption(t("res.yield_preview", pct=f"{preview:.2f}"))
    if submitted:
        if biomass <= 0 or lignin <= 0:
            st.warning(t("res.need_numbers"))
        elif ratio <= 0 or not hba.strip() or not hbd.strip():
            st.warning(t("res.need_composition"))
        else:
            already = _cached_saved(user, _store_where(), project)
            if already is not None and not already.empty and _looks_duplicate(already, sample_id,
                                                                             lignin, biomass):
                st.warning(t("res.duplicate_submit"))
                return
            row = {
                "sample_id": sample_id.strip() or _next_sample_id(saved),
                "formulation": label,
                "feedstock": feedstock.strip(),
                "des_hba": hba.strip(),
                "des_hbd": hbd.strip(),
                "molar_ratio": float(ratio),
                "purity_wt_pct": float(purity),
                "water_wt_pct": float(water),
                "biomass_g": biomass,
                "temperature_C": temperature,
                "time_min": minutes,
                "lignin_mg": lignin,
                "lignin_yield_pct": preview,
                "replicate": int(replicate),
                "notes": notes.strip(),
                "recorded_at": time.strftime("%Y-%m-%d %H:%M"),
                "project": project,
            }
            auth.save_results(user, pd.DataFrame([row]), append=True)
            total = auth.load_results(user)
            st.success(t("res.saved_run", sid=row["sample_id"], pct=f"{preview:.2f}",
                         rows=0 if total is None else len(total)))


def _records_tab(user: str | None, project: str = auth.DEFAULT_PROJECT) -> None:
    """Edit, add and delete rows in place, then save the whole table."""
    if not user:
        st.info(t("guide.signin_hint"))
        return
    saved = _cached_saved(user, _store_where(), project)
    empty = saved is None or saved.empty
    if not empty and store.enabled():
        try:
            photo_counts = auth.image_counts(user)
            saved = saved.copy()
            saved["photos"] = [photo_counts.get(str(value), 0)
                               for value in saved.get("sample_id", [])]
        except Exception:
            pass
    if empty:
        st.info(t("res.empty_records"))
    frame = pd.DataFrame(columns=RECORD_COLUMNS) if empty else saved
    ordered = [c for c in RECORD_COLUMNS if c in frame.columns]
    frame = frame.reindex(columns=ordered + [c for c in frame.columns if c not in ordered])
    with st.expander(t("res.import_excel"), expanded=False):
        upload = st.file_uploader(t("res.import_pick"), type=["csv", "xlsx", "xlsm", "xls"],
                                  key="records_upload")
        mode_label = st.radio(t("res.save_mode"), [t("res.save_append"), t("res.save_replace")],
                              horizontal=True, key="import_mode")
        if upload is None:
            st.caption(t("res.import_none"))
        else:
            try:
                incoming, info = _read_any(upload.name, upload.getvalue())
            except (ValueError, UnicodeError, pd.errors.ParserError) as exc:
                st.error(t("res.read_error", error=t(str(exc))))
                incoming, info = None, None
            if incoming is not None:
                if info:
                    st.caption(t("res.import_found", sheet=info["sheet"], row=info["header_row"],
                                 rows=info["rows"]))
                    if info["mapping"]:
                        st.caption(" · ".join(f"{k} → {v}" for k, v in info["mapping"].items()))
                    if info["unknown"]:
                        st.caption(t("res.import_unknown") + ": " + ", ".join(map(str, info["unknown"])))
                st.dataframe(incoming.head(20), hide_index=True, width="stretch")
                if st.button(t("res.import_confirm"), type="primary", key="import_confirm"):
                    append = mode_label == t("res.save_append")
                    auth.save_results(user, incoming, append=append)
                    st.success(t("res.import_done", rows=len(incoming)))

    st.caption(t("res.editor_hint"))
    locked = ["_owner"] if "_owner" in frame.columns else []
    edited = st.data_editor(frame, num_rows="dynamic", hide_index=True, width="stretch",
                            disabled=locked, key="records_editor")
    a, b, c = st.columns([1, 1, 1])
    if a.button(t("res.save_table"), type="primary", key="save_table"):
        cleaned = edited.dropna(how="all")
        if {"biomass_g", "lignin_mg"} <= set(cleaned.columns):
            cleaned = cleaned.copy()
            cleaned["lignin_yield_pct"] = [_yield_pct(g, m)
                                           for g, m in zip(cleaned["biomass_g"], cleaned["lignin_mg"])]
        auth.save_results(user, cleaned, append=False)
        st.success(t("res.save_table_done", rows=len(cleaned)))
    b.download_button(t("res.download_table"), csv_bytes(frame), "my_records.csv", "text/csv")
    with st.expander(t("res.email_data"), expanded=False):
        st.caption(t("res.email_data_hint"))
        with st.form("email_data"):
            dest = st.text_input(t("res.email_to"), value=user if "@" in str(user) else "")
            if st.form_submit_button(t("res.email_send")):
                if not dest.strip():
                    st.error(t("res.email_need_address"))
                elif frame.empty:
                    st.error(t("res.email_no_rows"))
                elif mailer.provider() == "none":
                    st.error(t("res.email_not_configured"))
                elif mailer.send_data(dest.strip(), len(frame), clean_excel,
                                      f"{auth.folder_name(user)}_records.xlsx"):
                    st.success(t("res.email_sent", to=dest))
                else:
                    st.error(t("res.email_failed"))

    clean_excel = excel_export.records_workbook(
        frame if not frame.empty else pd.DataFrame(columns=RECORD_COLUMNS),
        meta={"user": user or "", "scope": "my records"})
    b.download_button(t("res.download_excel"), clean_excel,
                      f"{auth.folder_name(user)}_records.xlsx",
                      "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                      key="download_excel")

    dataset = _dataset_zip(frame) if not frame.empty else _dataset_zip(pd.DataFrame(columns=RECORD_COLUMNS))
    b.download_button(t("res.download_dataset"), dataset, "dataset_for_ai.zip",
                      "application/zip", key="download_dataset")
    with st.expander(t("res.danger"), expanded=False):
        confirm = st.checkbox(t("res.clear_confirm"), key="clear_confirm")
        if st.button(t("res.clear_all"), disabled=not confirm, key="clear_all"):
            auth.save_results(user, frame.iloc[:0], append=False)
            st.warning(t("res.cleared"))


    _search_section(frame)
    _photos_section(user, frame)


def _quality_report(frame: pd.DataFrame, groups: list, measurement: str, summary: pd.DataFrame) -> None:
    """Say plainly what is wrong or thin in the data before anyone plots it."""
    problems = []
    columns = [c for c in frame.columns if c not in ("_source_file", "_owner")]
    duplicates = int(frame.duplicated(subset=columns).sum())
    if duplicates:
        problems.append(t("res.q_dupes", n=duplicates))
    if not summary.empty:
        singles = [str(", ".join(str(row[g]) for g in groups)) for _, row in summary.iterrows()
                   if int(row["n"]) <= 1]
        if singles:
            problems.append(t("res.q_single", groups=", ".join(singles)))
    if {"des_hba", "des_hbd", "molar_ratio"} & set(frame.columns):
        missing = int(frame[[c for c in ("des_hba", "des_hbd", "molar_ratio") if c in frame.columns]]
                      .isna().any(axis=1).sum()) if not frame.empty else 0
        if missing:
            problems.append(t("res.q_no_composition", n=missing))
    if "molar_ratio" in frame.columns:
        bad = int((pd.to_numeric(frame["molar_ratio"], errors="coerce") <= 0).sum())
        if bad:
            problems.append(t("res.q_bad_ratio", n=bad))
    for column, low, high in (("purity_wt_pct", 0, 100), ("water_wt_pct", 0, 100)):
        if column in frame.columns:
            values = pd.to_numeric(frame[column], errors="coerce")
            bad = int(((values <= low) | (values > high)).sum()) if column == "purity_wt_pct" else int((values > high).sum())
            if bad:
                problems.append(t("res.q_out_of_range", n=bad, column=column))
    if "lignin_yield_pct" in frame.columns and {"biomass_g", "lignin_mg"} <= set(frame.columns):
        mismatch = 0
        for _, row in frame.iterrows():
            expected = _yield_pct(row.get("biomass_g"), row.get("lignin_mg"))
            stored = pd.to_numeric(row.get("lignin_yield_pct"), errors="coerce")
            if expected is not None and pd.notna(stored) and abs(float(stored) - expected) > 0.05:
                mismatch += 1
        if mismatch:
            problems.append(t("res.q_yield_mismatch", n=mismatch))
    if problems:
        for message in problems:
            st.warning(message)
    else:
        st.success(t("res.q_ok"))


def _chart_tab(user: str | None, project: str = auth.DEFAULT_PROJECT) -> None:
    """Merge a source, check the data, summarise it and draw the figure."""
    sources = []
    if user:
        sources.append(("saved", t("res.src_saved")))
    sources += [("sample", t("res.src_sample")), ("demo", t("res.src_demo")), ("upload", t("res.src_upload"))]
    label = st.radio(t("res.source"), [text for _, text in sources], horizontal=True, key="source")
    kind = dict((text, key) for key, text in sources)[label]

    if kind == "saved":
        saved = _cached_saved(user, _store_where(), project)
        if saved is None or saved.empty:
            st.info(t("res.empty"))
            if st.button(t("res.load_example"), key="import_runs"):
                auth.save_results(user, pd.read_csv(MY_CSV), append=False)
                st.rerun()
            return
        location = "database" if store.enabled() else str(auth.results_path(user))
        st.caption(t("res.loaded", rows=len(saved), path=location))
        files = [(f"{auth.folder_name(user)}_results.csv", csv_bytes(saved))]
        encoding, data_kind = "utf-8-sig", "user_saved"
    elif kind == "sample":
        st.info(t("res.sample_info"))
        files = [("my_des_runs.csv", MY_CSV.read_bytes())]
        encoding, data_kind = "utf-8-sig", "my_experiments"
    elif kind == "demo":
        st.warning(t("res.demo_warning"))
        files = [("demo_lignin.csv", DEMO_CSV.read_bytes())]
        encoding, data_kind = "utf-8-sig", "synthetic_demo"
    else:
        uploads = st.file_uploader(t("res.uploader"), type=["csv", "xlsx", "xlsm", "xls"],
                                   accept_multiple_files=True)
        encoding = st.selectbox(t("res.encoding"), ["utf-8-sig", "gb18030"], help=t("res.encoding_help"))
        if not uploads:
            st.info(t("res.upload_hint"))
            return
        files = []
        for upload in uploads:
            frame_in, info = _read_any(upload.name, upload.getvalue())
            if info:
                st.caption(t("res.import_found", sheet=info["sheet"], row=info["header_row"],
                             rows=info["rows"]) + "  ·  " + t("res.import_mapping") + ": " +
                           ", ".join(f"{k} → {v}" for k, v in info["mapping"].items()))
            files.append((upload.name, excel_io.to_csv_bytes(frame_in) if info else upload.getvalue()))
        data_kind = "user_uploaded"

    try:
        frame = _cached_merge(tuple(files), encoding)
    except (ValueError, UnicodeError, pd.errors.ParserError) as exc:
        st.error(t("res.read_error", error=t(str(exc))))
        return
    if frame.empty:
        st.info(t("res.no_rows"))
        return

    columns = [c for c in frame.columns if c != "_source_file"]
    a, b, c = st.columns(3)
    a.metric(t("res.m_rows"), len(frame))
    b.metric(t("res.m_files"), len(files))
    duplicate_count = int(frame.duplicated(subset=columns).sum())
    c.metric(t("res.m_dupes"), duplicate_count)

    with st.expander(t("res.raw"), expanded=False):
        st.dataframe(frame, hide_index=True, width="stretch")
        st.download_button(t("res.download_merged"), csv_bytes(frame), "merged_results.csv", "text/csv")

    default_groups = [c for c in ["formulation", "temperature_C", "time_min"] if c in columns]
    groups = st.multiselect(t("res.groups"), columns, default=default_groups, key="groups")
    candidates = [c for c in columns if c not in groups and pd.to_numeric(frame[c], errors="coerce").notna().any()]
    if not groups or not candidates:
        st.info(t("res.need_group"))
        return
    for first_choice in ("lignin_yield_pct", "lignin_mg", "dry_strength_MPa"):
        if first_choice in candidates:
            preferred = candidates.index(first_choice)
            break
    else:
        preferred = 0
    measurement = st.selectbox(t("res.measure"), candidates, index=preferred, key="measurement")
    st.caption(t("res.yield_caption"))
    try:
        clean, summary, audit = _cached_summary(frame, tuple(groups), measurement)
    except (ValueError, TypeError) as exc:
        st.error(t(str(exc)))
        return
    if audit["excluded"]:
        st.warning(t("res.excluded", rows=audit["excluded"], bad=audit["invalid_measurement"],
                     missing=audit["missing_groups"]))
        with st.expander(t("res.excluded_expander")):
            st.dataframe(frame.loc[~audit["valid_mask"]], hide_index=True)
    if summary.empty:
        st.error(t("res.no_valid"))
        return

    st.subheader(t("res.quality"))
    _quality_report(frame, groups, measurement, summary)

    st.subheader(t("res.summary"))
    st.dataframe(summary, hide_index=True, width="stretch")
    st.caption(t("res.summary_caption"))
    summary_export = summary.assign(measurement=measurement, data_kind=data_kind)
    st.download_button(t("res.download_summary"), csv_bytes(summary_export), "summary.csv", "text/csv")

    with st.expander(t("res.fig_options"), expanded=True):
        a, b, c = st.columns(3)
        order_label = a.selectbox(t("res.fig_order"), [t("res.order_given"), t("res.order_label"),
                                                       t("res.order_desc"), t("res.order_asc")], key="fig_order")
        order = ("given", "label", "mean_desc", "mean_asc")[[t("res.order_given"), t("res.order_label"),
                                                             t("res.order_desc"), t("res.order_asc")].index(order_label)]
        palette = {"#0B1F4B": t("res.col_ink"), "#002F86": t("res.col_navy"),
                   "#4A5A7A": t("res.col_slate"), "#0F7A5A": t("res.col_teal")}
        names = list(palette.values())
        bar_pick = b.selectbox(t("res.fig_bar_colour"), names, index=1, key="fig_bar_name")
        point_pick = c.selectbox(t("res.fig_point_colour"), names, index=0, key="fig_point_name")
        bar_colour = [code for code, label in palette.items() if label == bar_pick][0]
        point_colour = [code for code, label in palette.items() if label == point_pick][0]
        a, b, c = st.columns(3)
        show_errors = a.toggle(t("res.fig_errors"), value=True, key="fig_errors")
        show_points = b.toggle(t("res.fig_points"), value=True, key="fig_points")
        show_values = c.toggle(t("res.fig_values"), value=False, key="fig_values")
        a, b, c = st.columns(3)
        y_min_text = a.text_input(t("res.fig_ymin"), key="fig_ymin")
        y_max_text = b.text_input(t("res.fig_ymax"), key="fig_ymax")
        dpi = c.selectbox(t("res.fig_dpi"), [150, 300, 600], index=1, key="fig_dpi")
        a, b = st.columns(2)
        title = a.text_input(t("res.fig_title"),
                             value=t("res.fig_title_demo") if data_kind == "synthetic_demo" else t("res.fig_title_real"),
                             key="fig_title")
        ylabel = b.text_input(t("res.yaxis"), value=_y_label(measurement), key=f"ylabel_{measurement}")

    def _number(text):
        try:
            return float(str(text).strip()) if str(text).strip() else None
        except ValueError:
            return None

    fig = _cached_figure(clean, summary, tuple(groups), measurement, title, ylabel,
                         bar_colour, point_colour, bool(show_errors), bool(show_values),
                         bool(show_points), _number(y_min_text), _number(y_max_text), order)
    st.pyplot(fig, width="stretch")
    st.caption(t("res.fig_caption"))
    a, b = st.columns(2)
    common = (clean, summary, tuple(groups), measurement, title, ylabel, bar_colour, point_colour,
              bool(show_errors), bool(show_values), bool(show_points),
              _number(y_min_text), _number(y_max_text), order)
    a.download_button(t("res.download_png"), _cached_figure_bytes(*common, "png", int(dpi)),
                      "experiment.png", "image/png")
    b.download_button(t("res.download_svg"), _cached_figure_bytes(*common, "svg", int(dpi)),
                      "experiment.svg", "image/svg+xml")


def results():
    st.title(t("res.title"))
    st.write(t("res.intro"))
    user = auth.current_user()
    if user:
        # Results is an analysis page: it selects a project, it does not create one
        projects = auth.list_projects(user)
        wanted = st.session_state.pop("project_wanted", None)
        if wanted and wanted in projects:
            st.session_state["project_pick"] = wanted
        if st.session_state.get("project_pick") not in projects:
            st.session_state["project_pick"] = projects[0]
        project = st.selectbox(t("res.project"), projects, key="project_pick",
                               help=t("res.project_help"))
    else:
        project = auth.DEFAULT_PROJECT
    tab_new, tab_records, tab_chart = st.tabs([t("res.tab_new"), t("res.tab_saved"), t("res.tab_chart")])
    with tab_new:
        _record_tab(user, project)
    with tab_records:
        _records_tab(user, project)
    with tab_chart:
        _chart_tab(user, project)


def guide():
    st.caption(t("guide.step"))
    st.title(t("guide.title"))
    st.markdown(t("guide.body"))
    st.download_button(t("guide.dl_demo"), DEMO_CSV.read_bytes(), "demo_lignin.csv", "text/csv")
    st.download_button(t("guide.dl_mine"), MY_CSV.read_bytes(), "my_des_runs.csv", "text/csv")
    st.download_button(t("guide.dl_template"), csv_bytes(pd.read_csv(DEMO_CSV).iloc[:0]),
                       "results_template.csv", "text/csv")
    st.link_button(t("guide.link_source"), "https://github.com/streamlit/hello")

    st.divider()
    st.subheader(t("store.title"))
    if store.enabled():
        try:
            _, detail = _cached_db_status()
        except Exception as exc:
            st.error(t("store.error", error=str(exc).splitlines()[0][:200]))
        else:
            st.success(t("store.database") + " · " + detail)
    else:
        st.info(t("store.local"))

    st.divider()
    st.subheader(t("guide.my_account"))
    user = auth.current_user()
    if not user:
        st.info(t("guide.signin_hint"))
        return
    st.markdown(t("guide.signed_in", user=user, path=auth.user_dir(user)))
    with st.form("change_password", clear_on_submit=True):
        first = st.text_input(t("guide.new_pw"), type="password")
        second = st.text_input(t("guide.repeat_pw"), type="password")
        if st.form_submit_button(t("guide.change_btn")):
            if first != second:
                st.error(t("guide.pw_mismatch"))
            elif len(first) < 6:
                st.error(t("guide.pw_short"))
            else:
                auth.change_password(user, first)
                st.success(t("guide.pw_done"))
    st.caption(t("guide.forgot_hint"))

    st.divider()
    st.subheader(t("guide.team"))
    if not (auth.is_admin(user) or auth.is_supervisor(user)):
        st.caption(t("guide.team_intern_note"))
        return

    # a supervisor sees only their own interns; an administrator sees the whole roster
    try:
        all_rows = store.accounts_rows() if store.enabled() else [
            {"username": name, "created": entry.get("created", ""),
             "last_login": entry.get("last_login", ""), "is_admin": bool(entry.get("is_admin")),
             "role": entry.get("role", "intern"), "supervisor": entry.get("supervisor", ""),
             "expires": entry.get("expires_at", "")}
            for name, entry in auth.load_users().items()
        ]
    except Exception as exc:
        st.error(t("guide.accounts_error", error=str(exc).splitlines()[0][:160]))
        all_rows = []
    mine = [row for row in all_rows
            if auth.is_admin(user) or row.get("supervisor") == user or row["username"] == user]

    if mine:
        week_ago = pd.Timestamp.now() - pd.Timedelta(days=7)
        recent = sum(1 for row in mine
                     if row["created"] and pd.to_datetime(row["created"], errors="coerce") >= week_ago)
        active = sum(1 for row in mine if row["last_login"] and row["last_login"] != "never")
        a, b, c = st.columns(3)
        a.metric(t("guide.accounts_total"), len(mine))
        b.metric(t("guide.accounts_recent"), recent)
        c.metric(t("guide.accounts_active"), active)
        table = pd.DataFrame(mine).reindex(
            columns=["username", "role", "supervisor", "expires", "created", "last_login", "is_admin"])
        table["expires"] = [value if value else t("guide.no_expiry") for value in table["expires"]]
        edited = st.data_editor(table, hide_index=True, width="stretch",
                                disabled=[c for c in table.columns if c != "is_admin"],
                                key="team_editor")
        if auth.is_admin(user) and st.button(t("guide.save_roles"), key="save_roles"):
            for _, row in edited.iterrows():
                auth.set_admin(str(row["username"]), bool(row["is_admin"]))
            st.success(t("guide.roles_saved"))
        st.caption(t("guide.accounts_hint") + "  " + t("guide.records_note"))
    else:
        st.info(t("guide.accounts_none"))

    with st.expander(t("guide.add_intern"), expanded=True):
        st.caption(t("guide.intern_hint"))
        supervisors = sorted({row.get("supervisor") or row["username"] for row in all_rows
                              if row.get("role") == "supervisor"})
        with st.form("add_intern", clear_on_submit=True):
            who = st.text_input(t("guide.intern_id"), placeholder="name@lab.org")
            initial = st.text_input(t("guide.intern_pw"), type="password",
                                    help=t("guide.intern_pw_help"))
            a, b = st.columns(2)
            if auth.is_admin(user) and supervisors:
                owner = a.selectbox(t("guide.col_supervisor"), supervisors, key="intern_owner")
            else:
                owner = user
                a.text_input(t("guide.col_supervisor"), value=user, disabled=True)
            until = b.date_input(t("guide.intern_expiry"),
                                 value=(pd.Timestamp.now() + pd.Timedelta(days=180)).date())
            if st.form_submit_button(t("guide.intern_create"), type="primary"):
                # the supervisor types the password: nothing is generated, and an empty field never
                # creates an account
                password = initial.strip()
                if not password:
                    st.error(t("guide.intern_pw_required"))
                elif len(password) < 6:
                    st.error(t("guide.pw_short"))
                else:
                    try:
                        created = auth.add_user(who, password, role="intern", supervisor=owner,
                                                expires=pd.Timestamp(until).to_pydatetime())
                    except ValueError as exc:
                        st.error(t(str(exc)))
                    else:
                        mailed = False
                        if "@" in created and mailer.provider() != "none":
                            mailed = mailer.send_welcome(created, auth.display_name(created))
                        st.success(t("guide.intern_created", user=created))
                        st.caption(t("guide.intern_expiry_note", date=until.strftime("%Y-%m-%d")))
                        st.caption(t("guide.intern_mailed", user=created) if mailed
                                   else t("guide.intern_nomail"))

    with st.expander(t("guide.mail"), expanded=False):
        state = mailer.check()
        if mailer.provider() == "none":
            st.info(t("guide.mail_off"))
        else:
            st.success(t("guide.mail_on", state=state))
            with st.form("mail_test"):
                dest = st.text_input(t("guide.mail_to"), value=user if "@" in user else "")
                if st.form_submit_button(t("guide.mail_send")):
                    if mailer.send_welcome(dest.strip(), auth.display_name(user) or user):
                        st.success(t("guide.mail_sent", to=dest))
                    else:
                        st.error(t("guide.mail_failed"))

    with st.expander(t("guide.reset_fallback"), expanded=False):
        st.caption(t("guide.reset_fallback_hint"))
        names = sorted(row["username"] for row in mine)
        if names:
            with st.form("admin_reset"):
                who_reset = st.selectbox(t("guide.resets_pick"), names, key="reset_who")
                if st.form_submit_button(t("guide.resets_create")):
                    token = auth.create_reset_token(who_reset)
                    st.session_state["last_reset_link"] = auth.reset_link(token) if token else ""
            link = st.session_state.get("last_reset_link")
            if link:
                st.code(link, language="text")
                st.caption(t("guide.resets_link"))


def _feedback_form(suffix: str = "page") -> None:
    """The report form, shared by the Feedback page and the floating dialog."""
    user = auth.current_user()
    kinds = [("bug", t("fb.cat_bug")), ("idea", t("fb.cat_idea")),
             ("data", t("fb.cat_data")), ("other", t("fb.cat_other"))]
    with st.form(f"feedback_form_{suffix}", clear_on_submit=True):
        kind_label = st.selectbox(t("fb.category"), [label for _, label in kinds], key=f"fb_kind_{suffix}")
        message = st.text_area(t("fb.message"), height=140, placeholder=t("fb.message_hint"),
                               key=f"fb_message_{suffix}")
        a, b = st.columns(2)
        page_ref = a.text_input(t("fb.page"), placeholder="e.g. Results & Figures", key=f"fb_page_{suffix}")
        contact = b.text_input(t("fb.contact"), placeholder="email / chat handle", key=f"fb_contact_{suffix}")
        submitted = st.form_submit_button(t("fb.submit"), type="primary", use_container_width=True)
    if not submitted:
        return
    if not message.strip():
        st.warning(t("fb.need_text"))
        return
    kind = dict((label, key) for key, label in kinds)[kind_label]
    try:
        path = feedback_mod.add(user or "anonymous", kind, message, page_ref, contact)
    except OSError:
        st.error(t("fb.write_failed"))
        st.code(f"{kind}: {message}", language="text")
    else:
        st.success(t("fb.saved"))
        st.caption(t("fb.saved_path", path=path))


@st.dialog("💬 " + t("fb.title"))
def feedback_dialog() -> None:
    """Opened by the floating button, so a report never costs you your session."""
    st.caption(t("fb.intro"))
    _feedback_form("dialog")


def feedback():
    """Send a report and - for admins - read the inbox."""
    st.caption(t("fb.step"))
    st.title(t("fb.title"))
    st.write(t("fb.intro"))
    user = auth.current_user()
    _feedback_form("page")

    st.divider()
    if not auth.is_admin(user):
        st.caption(t("fb.inbox_hint"))
        return

    st.subheader(t("fb.inbox"))
    if auth.hosted_mode() and not store.enabled():
        st.warning(t("fb.hosted_note"), icon="⚠️")
    frame = feedback_mod.load_all()
    if frame is None or frame.empty:
        st.info(t("fb.inbox_empty"))
        st.caption(t("fb.inbox_hint"))
        return

    kinds = [("bug", t("fb.cat_bug")), ("idea", t("fb.cat_idea")),
             ("data", t("fb.cat_data")), ("other", t("fb.cat_other"))]
    counts = feedback_mod.stats(frame)
    a, b, c = st.columns(3)
    a.metric(t("fb.inbox_total"), counts["total"])
    b.metric(t("fb.inbox_recent"), counts["recent"])
    c.metric(t("fb.inbox_kinds"),
             ", ".join(f"{k}: {v}" for k, v in sorted(counts["by_category"].items())) or "-")

    options = [t("fb.inbox_all")] + [label for _, label in kinds]
    choice = st.selectbox(t("fb.inbox_filter"), options, key="fb_filter")
    view = frame
    if choice != t("fb.inbox_all"):
        wanted = dict((label, key) for key, label in kinds)[choice]
        view = frame[frame["category"] == wanted]

    st.dataframe(view, hide_index=True, width="stretch")
    st.download_button(t("fb.download"), csv_bytes(frame), "feedback.csv", "text/csv")
    st.caption(t("fb.inbox_hint"))

