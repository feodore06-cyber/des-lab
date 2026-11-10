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

import ai
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
import audit
import comparability
import comparison
import dataset
import derive
import lab_core
import literature
from lab_core import calculate_recipe, csv_bytes, merge_results, summarize
import lab_plots
import papers

ROOT = Path(__file__).parent
DEMO_CSV = ROOT / "sample_data/demo_lignin.csv"
MY_CSV = ROOT / "sample_data/my_des_runs.csv"


COLUMNS_SHOWN = {"name": "Component", "moles": "Mol", "weigh_g": "Weigh (g)",
                 "water_g": "Water (g)"}


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


def recipe_for_basis(components: pd.DataFrame, ratio_basis: str, ideal: bool) -> pd.DataFrame:
    """Turn a mass or volume ratio into the molar ratio the calculator works with."""
    work = components.copy()
    work["ratio"] = pd.to_numeric(work["ratio"], errors="coerce")
    work["mw"] = pd.to_numeric(work["mw"], errors="coerce")
    if ratio_basis == "mass":
        work["ratio"] = work["ratio"] / work["mw"]
    elif ratio_basis == "volume":
        work["density"] = pd.to_numeric(work.get("density", 0.0), errors="coerce")
        if (work["density"] <= 0).any():
            raise ValueError(t("calc.need_density"))
        work["ratio"] = work["ratio"] * work["density"] / work["mw"]
    if work["ratio"].isna().any():
        raise ValueError(t("calc.need_ratio"))
    return work


def ratio_summary(components: pd.DataFrame, ideal: bool) -> str:
    """One compact line: molar, mass and volume ratio against the first component."""
    work = components.copy()
    if "density" not in work.columns:
        work["density"] = 0.0
    for column in ("ratio", "mw", "density", "assay_pct"):
        work[column] = pd.to_numeric(work.get(column, 0.0), errors="coerce")
    assay = 1.0 if ideal else work["assay_pct"].fillna(0) / 100.0
    molar = work["ratio"] * assay
    if not len(molar) or not float(molar.iloc[0]):
        return ""
    molar = molar / float(molar.iloc[0])
    mass = molar * work["mw"]
    mass = mass / float(mass.iloc[0])
    parts = [t("calc.ratio_line_molar", values=" : ".join(f"{value:.3g}" for value in molar))]
    parts.append(t("calc.ratio_line_mass", values=" : ".join(f"{value:.3g}" for value in mass)))
    if (work["density"] > 0).all():
        volume = mass / work["density"]
        volume = volume / float(volume.iloc[0])
        parts.append(t("calc.ratio_line_volume",
                       values=" : ".join(f"{value:.3g}" for value in volume)))
    return " · ".join(parts)


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

    bases = {"calc.by_molar": "molar", "calc.by_mass": "mass", "calc.by_volume": "volume"}
    basis_label = st.radio(t("calc.ratio_basis"), [t(key) for key in bases], horizontal=True,
                           key="ratio_basis", help=t("calc.ratio_basis_help"))
    ratio_basis = bases[[key for key in bases if t(key) == basis_label][0]]

    rows = _recipe_rows()
    frame = pd.DataFrame(rows)
    if "density" not in frame.columns:
        frame["density"] = 0.0
    table_labels = dict(labels)
    if ratio_basis == "volume":
        table_labels["density"] = t("calc.col_density")
    components = st.data_editor(frame, column_config=table_labels, num_rows="dynamic",
                                hide_index=True, width="stretch",
                                disabled=["assay_pct"] if ideal else [],
                                key=f"components_{len(rows)}_{ratio_basis}")
    if "density" not in components.columns:
        components["density"] = 0.0
    if ratio_basis != "volume":
        components = components.drop(columns=["density"])
    # an empty row at the bottom of the editor is not a component: drop it before anything uses it
    components = components[
        components["name"].astype(str).str.strip().ne("")
        & components["name"].notna()
    ].reset_index(drop=True)
    if ideal:
        components = components.copy()
        components["assay_pct"] = 100.0
    st.session_state["recipe_rows"] = components.to_dict("records")

    # one button per chemical: press it and that row is gone, no selection needed
    if len(components):
        st.caption(t("calc.remove_hint"))
        slots = st.columns(min(len(components), 4))
        for position, (_, row) in enumerate(components.iterrows()):
            label = str(row.get("name") or t("calc.unnamed"))
            if slots[position % len(slots)].button(
                    t("calc.remove_one", name=label), key=f"del_component_{position}",
                    use_container_width=True):
                remaining = components.drop(index=components.index[position])
                st.session_state["recipe_rows"] = remaining.to_dict("records")
                st.session_state.pop("last_reagent", None)
                st.rerun()

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
    modes = {t("calc.mode_batch"): "batch", t("calc.mode_reverse"): "reverse"}
    mode = modes[st.radio(t("calc.mode"), list(modes), horizontal=True, key="calc_mode")]

    if mode == "reverse":
        st.caption(t("calc.reverse_hint"))
        names = [str(value) for value in components.get("name", [])]
        if not names:
            st.info(t("calc.reverse_no_components"))
            return
        # the form only collects the input: a download button is not allowed inside it
        with st.form("reverse_recipe"):
            a, b = st.columns([2, 1])
            which = a.selectbox(t("calc.reverse_pick"), names, key="reverse_which")
            weighed = b.number_input(t("calc.reverse_mass"), min_value=0.0, value=8.0,
                                     step=0.1, format="%.3f", key="reverse_mass")
            submitted = st.form_submit_button(t("calc.reverse_btn"), type="primary")
        if submitted:
            try:
                frame, info, scale = lab_core.recipe_for_component(
                    components, names.index(which), weighed,
                    basis="active" if ideal else "reagent")
            except ValueError as exc:
                st.error(t(str(exc)))
            else:
                st.session_state["reverse_result"] = {
                    "name": which, "mass": weighed, "scale": scale,
                    "rows": frame.to_dict("records"), "info": info}

        stored = st.session_state.get("reverse_result")
        if stored:
            frame = pd.DataFrame(stored["rows"])
            info = stored["info"]
            active_sum = float(frame["active_g"].sum())
            weighed_sum = float(frame["weigh_g"].sum())
            over_pct = 100 * (weighed_sum / active_sum - 1) if active_sum else 0.0
            st.markdown(t("calc.s3"))
            cols = st.columns(4)
            cols[0].metric(t("calc.m_total"), f"{info.get('total_g', 0):.4f} g")
            cols[1].metric(t("calc.reverse_others"),
                           ", ".join(f"{row['name']} {row['weigh_g']:.3f} g"
                                     for _, row in frame.iterrows()
                                     if row["name"] != stored["name"]))
            cols[2].metric(t("calc.m_water"), f"{info.get('known_water_g', 0):.4f} g")
            cols[3].metric(t("calc.m_over"), f"{over_pct:.2f}%", help=t("calc.over_help"))
            st.caption(t("calc.reverse_done", name=stored["name"], mass=stored["mass"]))
            result_labels = {**labels, "moles": t("calc.moles"), "active_g": t("calc.active_g"),
                             "weigh_g": t("calc.weigh_g"), "water_g": t("calc.water_g")}
            st.subheader(t("calc.weighing"))
            st.dataframe(frame.rename(columns=result_labels).round(6), hide_index=True,
                         width="stretch")
            export = frame.copy()
            export["target_basis"] = "active" if ideal else "reagent"
            export["fixed_component"] = stored["name"]
            export["fixed_g"] = stored["mass"]
            st.download_button(t("calc.download"), csv_bytes(export), "des_recipe.csv",
                               "text/csv", key="reverse_download")
        return

    bases = [("active", t("calc.basis_active")), ("reagent", t("calc.basis_reagent"))]
    a, b, c = st.columns([2, 1, 1])
    basis_label = a.selectbox(t("calc.basis"), [label for _, label in bases], key="basis")
    target = b.number_input(t("calc.target"), min_value=0.001, value=10.0, step=1.0, format="%.3f", key="target")
    water = c.number_input(t("calc.water"), min_value=0.0, value=0.0, step=0.1, format="%.3f", key="water")
    st.caption(t("calc.water_caption"))
    basis = dict((label, key) for key, label in bases)[basis_label]
    try:
        solve_rows = recipe_for_basis(components, ratio_basis, ideal)
        recipe, totals = calculate_recipe(solve_rows, target, basis, water)
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
    summary = ratio_summary(components, ideal)
    if summary:
        st.caption(summary)
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
    """Choose the project a new experiment goes into. Creating one happens on the workspace."""
    if not user:
        return auth.DEFAULT_PROJECT
    projects = auth.list_projects(user)
    wanted = st.session_state.pop("project_wanted", None)
    if wanted and wanted in projects:
        st.session_state["project_pick"] = wanted
    if st.session_state.get("project_pick") not in projects:
        st.session_state["project_pick"] = projects[0]
    return st.selectbox(t("res.project"), projects, key="project_pick",
                        help=t("res.project_help"))


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


def _saved_papers(user: str) -> None:
    """The literature the researcher kept, with the review state of every extracted value."""
    papers = auth.papers_of(user)
    st.subheader(t("lib.saved_title"))
    if not papers:
        st.caption(t("lib.saved_none"))
        return
    for paper in papers:
        counts = literature.review(paper.get("values") or [])
        title = paper.get("title") or paper.get("doi") or f"#{paper['id']}"
        with st.expander(f"{title} \u00b7 {counts['total']} value(s) \u00b7 "
                         f"{counts['extracted_awaiting_review']} to check"):
            if paper.get("doi"):
                st.caption(f"DOI: `{paper['doi']}`")
            values = paper.get("values") or []
            if not values:
                st.caption(t("lib.saved_empty"))
                continue
            for value in values:
                columns = st.columns([2, 3, 1, 2])
                columns[0].markdown(f"**{value.get('variable')}**")
                normalised = value.get("normalized")
                columns[1].caption(f"{value.get('original') or '-'} -> "
                                   f"{normalised if normalised is not None else '-'}")
                columns[2].caption(f"p.{value['page']}" if value.get("page") else "-")
                columns[3].caption(str(value.get("status", "")).replace("_", " "))
            counts = literature.review(values)
            st.caption(t("lib.saved_counts", total=counts["total"],
                         pending=counts["extracted_awaiting_review"],
                         verified=counts["verified"] + counts["corrected_by_user"],
                         missing=counts["without_source"]))
            with st.form(f"review_{paper['id']}"):
                name = st.text_input(t("lib.review_variable"), key=f"rv_{paper['id']}")
                corrected = st.text_input(t("lib.review_value"), key=f"rc_{paper['id']}")
                accept = st.form_submit_button(t("lib.review_accept"))
            if accept and name.strip():
                updated = literature.verify(values, name.strip(),
                                            corrected if corrected.strip() else None)
                auth.review_paper(user, paper["id"], updated)
                st.rerun()


def library() -> None:
    if st.session_state.get("compare_inline"):
        if st.button("← " + t("lib.back_to_papers"), key="leave_compare"):
            st.session_state["compare_inline"] = False
            st.rerun()
        compare_page()
        return

    st.markdown(t("lib.title"))
    st.caption(t("lib.sub"))
    user = auth.current_user()
    if user:
        _saved_papers(user)
        st.divider()
    with st.form("paper_search"):
        query = st.text_input(t("lib.query"), placeholder=t("lib.query_ph"))
        a, b, c, d = st.columns(4)
        windows = {t("lib.any_year"): None, t("lib.since_2020"): 2020,
                   t("lib.since_2015"): 2015, t("lib.since_2010"): 2010}
        since = windows[a.selectbox(t("lib.since"), list(windows), index=0)]
        citations = b.number_input(t("lib.min_cites"), min_value=0, value=0, step=5)
        order = c.selectbox(t("lib.order"), [t("lib.by_relevance"), t("lib.by_citations"),
                                             t("lib.by_newest")])
        limit = d.number_input(t("lib.limit"), min_value=5, max_value=30, value=10, step=5)
        st.caption(t("lib.since_help"))
        submitted = st.form_submit_button(t("lib.search"), type="primary")
    mapping = {t("lib.by_relevance"): "relevant", t("lib.by_citations"): "cited",
               t("lib.by_newest"): "newest"}
    if submitted and query.strip():
        st.session_state["lib_last"] = {"query": query.strip(), "since": since,
                                        "citations": int(citations),
                                        "order": mapping.get(order, "relevant"),
                                        "limit": int(limit)}
    last = st.session_state.get("lib_last")
    if not last:
        st.info(t("lib.how"))
        return
    query = last["query"]
    since = last["since"]
    citations = last["citations"]

    try:
        with st.spinner(t("lib.searching")):
            found = _library_results(query, since, citations,
                                     last["order"], last["limit"])
    except papers.PaperError as exc:
        # the catalogue being busy must not lose the page: show what was found last time, say what
        # happened, and offer a retry
        st.warning(t("lib.failed", error=str(exc)))
        stale = st.session_state.get("lib_stale") or []
        if stale:
            st.caption(t("lib.stale", n=len(stale)))
            found = stale
        else:
            if st.button(t("lib.retry"), key="lib_retry"):
                st.rerun()
            return
    else:
        if not found:
            st.warning(t("lib.none", query=query.strip()))
            return
        st.session_state["lib_stale"] = found
    st.caption(papers.summarise(query.strip(), found))
    summaries = {}
    if ai.available():
        if st.button(t("lib.summarise"), key="lib_summarise"):
            items = [{"title": paper["title"], "year": paper["year"],
                      "abstract": paper["abstract"][:1400]} for paper in found]
            with st.spinner(t("lib.summarising")):
                summaries = ai.summarise_papers(items, st.session_state.get(i18n.LANG_KEY, "en"))
            st.session_state["paper_summaries"] = summaries
        else:
            summaries = st.session_state.get("paper_summaries") or {}
    for index, paper in enumerate(found, start=1):
        title = paper["title"]
        link = f"[{title}]({paper['url']})" if paper["url"] else title
        st.markdown(f"**{index}. {link}**")
        bits = [str(paper["year"]) or "n.d.", paper["venue"] or t("lib.no_venue"),
                t("lib.citations", n=paper["citations"])]
        if paper["authors"]:
            bits.insert(1, paper["authors"])
        st.caption(" · ".join(bits))
        if summaries.get(index - 1):
            st.markdown(f"> {summaries[index - 1]}")
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
            st.session_state["compare_inline"] = True
            st.rerun()
        st.divider()


BASIS_KEYS = ("cmp.basis_yield", "cmp.basis_delign", "cmp.basis_purity", "cmp.basis_other")


def _pick_run(saved, user, prefix: str, label_key: str, run_index: int = 0) -> dict | None:
    """Choose a project first, then a run inside it - sample IDs repeat across projects."""
    if saved is None or saved.empty or "sample_id" not in saved.columns:
        return None
    frame = saved.copy()
    if "project" not in frame.columns:
        frame["project"] = auth.DEFAULT_PROJECT
    frame["project"] = frame["project"].fillna(auth.DEFAULT_PROJECT)
    projects = auth.list_projects(user)
    if not projects:
        return None
    with_data = [name for name in projects if name in set(frame["project"])]
    start = projects.index(with_data[0]) if with_data else 0
    project = st.selectbox(t("cmp.project"), projects, index=start, key=f"{prefix}_project")
    part = frame[frame["project"] == project]
    if part.empty:
        st.caption(t("cmp.project_empty"))
        return None
    options = {}
    for _, row in part.iterrows():
        stamp = pd.to_datetime(row.get("recorded_at"), errors="coerce")
        when = stamp.strftime("%Y-%m-%d") if pd.notna(stamp) else t("cmp.no_date")
        bits = [str(row["sample_id"])]
        if row.get("formulation") and str(row.get("formulation")) != "nan":
            bits.append(str(row["formulation"]))
        bits.append(when)
        options[" · ".join(bits)] = row.to_dict()
    keys = list(options)
    choice = st.selectbox(t(label_key), keys, index=min(run_index, len(keys) - 1),
                          key=f"{prefix}_run")
    return options[choice]


def _project_ranking(user: str, project: str) -> None:
    """Every run of the project, ordered by a chosen result variable."""
    frame = _cached_saved(user, _store_where(), project)
    if frame is None or frame.empty:
        return
    results = auth.project_result_variables(user, project)
    if not results:
        return
    with st.expander(t("cmp.rank_title"), expanded=False):
        measure = st.selectbox(t("cmp.rank_measure"), results, key=f"rank_{project}")
        unit = auth.unit_of(measure)
        ranked = comparison.rank(frame.to_dict("records"), measure)
        rows = []
        for position, entry in enumerate(ranked, start=1):
            value = entry["value"]
            rows.append({"#": position, "sample_id": entry["run"].get("sample_id"),
                         measure: "—" if value is None else f"{value:g}",
                         **{key: entry["run"].get(key)
                            for key in ("temperature_C", "time_min", "mixing_method")
                            if entry["run"].get(key) is not None}})
        st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")
        if unit:
            st.caption(t("cmp.rank_unit", unit=unit))
        st.caption(t("cmp.rank_note"))


def compare_page() -> None:
    st.markdown(t("cmp.title"))
    st.warning(t("cmp.disclaimer"))
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

    if mode == t("cmp.mode_runs"):
        st.subheader(t("cmp.mine"))
        a_col, b_col = st.columns(2)
        with a_col:
            left_row = _pick_run(saved, user, "cmp_a", "cmp.run_a")
        with b_col:
            right_row = _pick_run(saved, user, "cmp_b", "cmp.run_b", run_index=1)
        if left_row:
            _project_ranking(user, left_row.get("project") or auth.DEFAULT_PROJECT)
        if left_row is None or right_row is None:
            st.info(t("res.empty_records"))
            return
        if st.button(t("cmp.run_btn"), type="primary", key="compare_runs_btn"):
            if (str(left_row.get("sample_id")), str(left_row.get("project"))) == (
                    str(right_row.get("sample_id")), str(right_row.get("project"))):
                st.warning(t("cmp.same_run"))
            else:
                mine = {**left_row, "basis": t("cmp.basis_yield"), "replicates": 3}
                theirs = {**right_row, "basis": t("cmp.basis_yield"), "replicates": 3}
                st.session_state["compare_outcome"] = compare.compare(mine, theirs)
                st.session_state["compare_result"] = {
                    "mine": mine, "theirs": theirs,
                    "label": f"{left_row.get('sample_id')} vs {right_row.get('sample_id')}",
                    "sides": {"mine": str(left_row.get("sample_id")),
                              "theirs": str(right_row.get("sample_id"))}}
        _render_outcome()
        return

    st.subheader(t("cmp.mine"))
    mine_row = _pick_run(saved, user, "cmp_mine", "cmp.pick_run")
    if mine_row:
        _project_ranking(user, mine_row.get("project") or auth.DEFAULT_PROJECT)
    if mine_row is None:
        st.info(t("res.empty_records"))
        return

    st.subheader(t("cmp.ref"))
    reference = st.session_state.get("compare_ref") or {}
    doi = str(reference.get("title") or "")
    extracted = st.session_state.get("compare_extracted") or {}
    if doi and not extracted and ai.available():
        with st.spinner(t("cmp.reading_paper")):
            work = papers.by_doi(doi)
            if work and work.get("abstract"):
                extracted = ai.extract_from_paper(work["title"], work["abstract"])
                extracted["_title"] = work["title"]
                extracted["_doi"] = work["doi"]
            elif work:
                extracted = {"_title": work["title"], "_doi": work.get("doi", doi),
                             "_no_abstract": True}
            if extracted:
                st.session_state["compare_extracted"] = extracted
    if extracted:
        found_count = int(extracted.get("found") or 0)
        if found_count:
            st.info(t("cmp.read_found", n=found_count, title=extracted.get("_title", doi)))
            st.caption(t("cmp.read_check"))
            if extracted.get("quote"):
                st.caption("“" + str(extracted["quote"]) + "”")
        elif extracted.get("_no_abstract"):
            st.warning(t("cmp.read_no_abstract", title=extracted.get("_title", doi)))
        else:
            st.info(t("cmp.read_empty"))
    elif doi and ai.available():
        st.warning(t("cmp.read_not_found", doi=doi))
    if doi:
        st.caption(t("cmp.placeholder_note"))
    st.caption(t("cmp.ref_hint"))
    own = [value for value in auth.project_variables(
        user, mine_row.get("project") or auth.DEFAULT_PROJECT)
        if value not in ("sample_id", "notes", "recorded_at", "replicate")]

    st.markdown(t("cmp.paper_title"))
    st.caption(t("cmp.paper_help"))
    reference = st.session_state.get("compare_ref") or {}
    paper_title = st.text_input(t("cmp.title_field"), value=str(reference.get("title") or ""),
                                placeholder="10.1016/j.indcrop.2022.115040 or the title")
    paper_text = st.text_area(t("cmp.paste"), height=120,
                              placeholder=t("cmp.paste_ph"))

    if ai.available():
        if st.button(t("cmp.read_with_ai"), key="cmp_read"):
            with st.spinner(t("cmp.ai_thinking")):
                found = ai.extract_comparison(
                    own, paper_title, paper_text,
                    st.session_state.get(i18n.LANG_KEY, "en"))
            if found and (found.get("values") or found.get("reported_result")):
                st.session_state["cmp_filled"] = found
                for key, value in (found.get("values") or {}).items():
                    st.session_state[f"cmp_field_{key}"] = f"{value:g}"
                if found.get("reported_result") is not None:
                    st.session_state["cmp_reported"] = f"{found['reported_result']:g}"
            else:
                st.session_state["cmp_filled"] = {"empty": True}
            st.rerun()
        filled = st.session_state.get("cmp_filled")
        if filled and filled.get("empty"):
            st.warning(t("cmp.nothing_read"))
        elif filled:
            st.success(t("cmp.read_ok", n=len(filled.get("values") or {})))
            if filled.get("quote"):
                st.caption("“" + str(filled["quote"]) + "”")
            st.caption(t("cmp.read_check_hint"))
    else:
        st.caption(t("cmp.ai_offline"))

    with st.form("compare_paper"):
        basis_labels = [t(key) for key in BASIS_KEYS]
        basis = st.selectbox(t("cmp.basis"), basis_labels, index=0, key="compare_basis")
        for chunk in range(0, len(own), 3):
            columns = st.columns(3)
            for column, variable in zip(columns, own[chunk:chunk + 3]):
                column.text_input(variable.replace("_", " "),
                                  key=f"cmp_field_{variable}",
                                  placeholder=t("cmp.blank_if_absent"))
        reported = st.text_input(t("cmp.yield"), key="cmp_reported",
                                 placeholder=t("cmp.blank_if_absent"))
        if st.form_submit_button(t("cmp.run_btn"), type="primary"):
            if not str(reported).strip():
                st.error(t("cmp.need_numbers"))
            else:
                theirs = {variable: st.session_state.get(f"cmp_field_{variable}", "")
                          for variable in own}
                theirs["basis"] = basis
                theirs["lignin_yield_pct"] = reported
                mine = {"lignin_yield_pct": mine_row.get("lignin_yield_pct"),
                        "basis": t("cmp.basis_yield")}
                for variable in own:
                    mine[variable] = mine_row.get(variable)
                mine["replicates"] = 3
                st.session_state["compare_result"] = {
                    "mine": mine, "theirs": theirs, "label": paper_title or pick,
                    "sides": {"mine": t("cmp.mine"), "theirs": t("cmp.ref")}}
                st.session_state["compare_outcome"] = compare.compare(mine, theirs)

    _render_outcome()


def _comparability(mine: dict, theirs: dict) -> list:
    """Name the differences that make two runs not really comparable, before any explanation."""
    notes = []

    def text_of(row, key):
        value = row.get(key)
        return "" if value is None or (isinstance(value, float) and pd.isna(value)) else str(value).strip().lower()

    if text_of(mine, "feedstock") and text_of(theirs, "feedstock") \
            and text_of(mine, "feedstock") != text_of(theirs, "feedstock"):
        notes.append(t("cmp.guard_feedstock", mine=mine.get("feedstock"), theirs=theirs.get("feedstock")))
    if text_of(mine, "formulation") and text_of(theirs, "formulation") \
            and text_of(mine, "formulation") != text_of(theirs, "formulation"):
        notes.append(t("cmp.guard_formulation", mine=mine.get("formulation"),
                       theirs=theirs.get("formulation")))
    for key, label in (("des_hbd", "cmp.guard_donor"), ("des_hba", "cmp.guard_acceptor")):
        if text_of(mine, key) and text_of(theirs, key) and text_of(mine, key) != text_of(theirs, key):
            notes.append(t(label, mine=mine.get(key), theirs=theirs.get(key)))
    return notes


SKIP_FROM_CONDITIONS = {"sample_id", "project", "notes", "recorded_at", "replicate",
                        "basis", "feedstock", "lignin_yield_pct"}


def _condition_rows(mine: dict, theirs: dict):
    """Every condition of both runs next to each other, with the ones that differ marked."""
    if not mine or not theirs:
        return None
    keys = [key for key in list(mine) + list(theirs)
            if key not in SKIP_FROM_CONDITIONS and str(key) not in SKIP_FROM_CONDITIONS]
    seen, ordered = set(), []
    for key in keys:
        if key not in seen:
            seen.add(key)
            ordered.append(key)
    differing = 0
    rows = []
    for key in ordered:
        left, right = mine.get(key), theirs.get(key)
        if left is None and right is None:
            continue
        same = _same_value(left, right)
        differing += 0 if same else 1
        rows.append({"variable": str(key).replace("_", " "),
                     t("cmp.run_a"): _show(left, key), t("cmp.run_b"): _show(right, key),
                     t("cmp.differs"): "" if same else "•"})
    return pd.DataFrame(rows) if rows else None


def _same_value(left, right) -> bool:
    if left is None or right is None:
        return left is None and right is None
    try:
        return abs(float(left) - float(right)) < 1e-9
    except (TypeError, ValueError):
        return str(left).strip().lower() == str(right).strip().lower()


def _show(value, key: str = "") -> str:
    if value is None or (isinstance(value, float) and value != value):
        return "room temp" if key == "temperature_C" else "—"
    if key == "temperature_C":
        try:
            if float(value) <= 30:
                return f"{float(value):g} (room temp)"
        except (TypeError, ValueError):
            pass
    if isinstance(value, float):
        return f"{value:g}"
    return str(value)


def _render_outcome() -> None:
    """The shared result block: two numbers, the difference, then the ranked explanations."""
    outcome = st.session_state.get("compare_outcome")
    if not outcome:
        st.caption(t("cmp.nothing_saved"))
        return

    st.divider()
    details = st.session_state.get("compare_result", {})
    guard = _comparability(details.get("mine", {}), details.get("theirs", {}))
    if guard:
        st.warning(t("cmp.guard_title") + "\n\n- " + "\n- ".join(guard))
        st.caption(t("cmp.guard_note"))
    # the comparability verdict comes before any number: two values that mean different things
    # must not be printed side by side as if a difference between them were meaningful
    verdict = details.get("comparability") or {}
    if not verdict:
        project = (details.get("mine") or {}).get("project") or auth.DEFAULT_PROJECT
        items = {item["name"]: item
                 for item in auth.project_variable_items(auth.current_user(), project)}
        wanted = (details.get("measures") or [details.get("measure")])[0]
        mine_item = items.get(wanted, {})
        theirs_item = details.get("theirs_item") or mine_item
        verdict = comparability.check(details.get("mine") or {}, details.get("theirs") or {},
                                      mine_item, theirs_item,
                                      replicates=int(details.get("replicates") or 1))
    if verdict:
        status = verdict.get("status")
        label = t(f"cmp.status_{status}")
        text_lines = "\n\n- ".join(verdict.get("reasons") or [])
        if status == "not_comparable":
            st.error(t("cmp.not_comparable_title", status=label) + "\n\n- " + text_lines)
            if verdict.get("conversion"):
                st.info(verdict["conversion"])
            return
        if status == "insufficient_information":
            st.warning(t("cmp.insufficient_title", status=label) + "\n\n- " + text_lines)
        elif status == "comparable_with_caveats":
            st.info(t("cmp.caveats_title", status=label) + "\n\n- " + text_lines)
        else:
            st.success(t("cmp.direct_title", status=label))

    st.subheader(t("cmp.side_by_side"))
    sides = details.get("sides") or {"mine": t("cmp.mine"), "theirs": t("cmp.ref")}
    # every result variable of the project gets a row of numbers, not just the first
    measures = details.get("measures") or ([details["measure"]] if details.get("measure") else [])
    if not measures:
        measures = auth.project_result_variables(
            auth.current_user(), (details.get("mine") or {}).get("project")
            or auth.DEFAULT_PROJECT) or ["lignin_yield_pct"]
    for position, measure in enumerate(measures):
        unit = auth.unit_of(measure) or ("%" if "pct" in str(measure) else "")
        st.markdown(f"**{measure.replace('_', ' ')}{f' ({unit})' if unit else ''}**")
        columns = st.columns(3)
        values = (details.get("mine", {}).get(measure),
                  details.get("theirs", {}).get(measure),
                  outcome["delta"] if position == 0 else None)
        for column, name, value in zip(columns,
                                       (sides["mine"], sides["theirs"], t("cmp.delta")), values):
            title = name
            if isinstance(value, (int, float)) and value == value:
                shown = f"{value:+.2f}" if name == t("cmp.delta") else f"{value:.2f}"
                column.metric(title, f"{shown} {unit}".strip())
            else:
                column.metric(title, "—")
    st.caption(t("cmp.measure_note", what=", ".join(m.replace("_", " ") for m in measures)))
    first = measures[0]
    left_value = (details.get("mine") or {}).get(first)
    right_value = (details.get("theirs") or {}).get(first)
    relative = comparison.relative_difference(left_value, right_value)
    if relative is not None:
        st.caption(t("cmp.relative", pct=f"{relative:+.1f}"))
    counts = comparison.replicate_stats([left_value, right_value])
    if counts["n"] == 2:
        st.caption(t("cmp.replicates_note"))


    # what actually differed: the result is not caused by one variable, so show them all
    pair = _condition_rows(details.get("mine", {}), details.get("theirs", {}))
    if pair is not None and not pair.empty:
        st.markdown(t("cmp.conditions_title"))
        st.dataframe(pair, hide_index=True, width="stretch")
        changed = [row["variable"] for row in pair.to_dict("records")
                   if row.get(t("cmp.differs")) == "•"]
        if changed:
            st.caption(t("cmp.conditions_changed", names=", ".join(changed)))
        else:
            st.caption(t("cmp.conditions_same"))
    st.info(t(f"cmp.headline_{compare.headline(outcome)}"))

    st.subheader(t("cmp.ai_title"))
    if ai.available():
        with st.spinner(t("cmp.ai_loading")):
            reading = ai.analyse(details.get("mine", {}), details.get("theirs", {}),
                                 [t("cmp." + item["code"] + ".claim", **dict(item["params"]))
                                  for item in outcome["findings"]],
                                 st.session_state.get(i18n.LANG_KEY, "en"))
        if reading:
            st.markdown(reading)
            st.caption(t("cmp.ai_hint"))
        else:
            st.caption(t("cmp.ai_off"))
    else:
        st.caption(t("cmp.ai_off"))

    if ai.available():
        with st.form("compare_question", clear_on_submit=False):
            question = st.text_input(t("cmp.ask_label"), placeholder=t("cmp.ask_ph"))
            asked = st.form_submit_button(t("cmp.ask_btn"))
        if asked and question.strip():
            context = {key: details.get(side, {}).get(key)
                       for side in ("mine", "theirs")
                       for key in ("sample_id", "formulation", "feedstock", "molar_ratio",
                                   "purity_wt_pct", "water_wt_pct", "temperature_C", "time_min",
                                   "biomass_g", "lignin_mg", "lignin_yield_pct")}
            context = {"first": {k: details.get("mine", {}).get(k) for k in context if k in
                                 details.get("mine", {})},
                       "second": {k: details.get("theirs", {}).get(k) for k in context if k in
                                  details.get("theirs", {})},
                       "differences": [t("cmp." + item["code"] + ".claim", **dict(item["params"]))
                                       for item in outcome["findings"]]}
            with st.spinner(t("cmp.ai_loading")):
                answer = ai.ask(question, context, st.session_state.get(i18n.LANG_KEY, "en"))
            history = st.session_state.setdefault("compare_qa", [])
            history.append({"q": question.strip(), "a": answer or t("cmp.ai_failed")})
        for item in reversed(st.session_state.get("compare_qa", [])[-3:]):
            st.markdown(f"**{item['q']}**")
            st.markdown(item["a"])

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
    """Kept for future navigation; the comparison screen is rendered in place instead.

    ``st.switch_page`` needs the page object created in the same script run. A page object kept from
    an earlier run does nothing at all, which is exactly the "button is dead" symptom, so this helper
    is not used for the paper -> comparison step.
    """
    if key == "compare":
        st.session_state["compare_inline"] = True
        st.rerun()
        return
    st.switch_page(page)


COLUMN_CHOICES = ["temperature_C", "time_min", "biomass_g", "lignin_mg", "lignin_yield_pct",
                  "replicate", "notes"] + [
    "stirring_rpm", "stirring_time_min", "solid_liquid_ratio", "ph", "catalyst_wt_pct",
    "particle_size_mm", "moisture_before_wt_pct", "ash_wt_pct", "recovery_wt_pct",
    "purity_of_lignin_pct"]

CHIP_CLASS = {"Draft": "draft", "In progress": "running", "Pending test": "pending",
              "Completed": "done", "Needs review": "review"}


def _status_label(status: str) -> str:
    mapping = {"Draft": "exp.draft", "In progress": "exp.running", "Pending test": "exp.pending",
               "Completed": "exp.done", "Needs review": "exp.review"}
    return t(mapping.get(status, "exp.running"))


def dashboard() -> None:
    """Where the researcher lands: what is running, what was just recorded, what needs a look."""
    st.markdown(t("dash.title"))
    st.caption(t("dash.sub"))
    user = auth.current_user()
    if not user:
        st.info(t("guide.signin_hint"))
        return
    frame = _cached_saved(user, _store_where())
    projects = auth.list_projects(user)
    papers = auth.papers_of(user)
    empty = frame is None or frame.empty

    counts = st.columns(3)
    counts[0].metric(t("dash.projects"), len(projects))
    counts[1].metric(t("dash.runs"), 0 if empty else len(frame))
    counts[2].metric(t("dash.papers"), len(papers))

    st.subheader(t("dash.recent"))
    if empty:
        st.caption(t("dash.no_runs"))
    else:
        recent = frame.copy()
        if "recorded_at" in recent.columns:
            stamps = pd.to_datetime(recent["recorded_at"], errors="coerce")
            recent = recent.assign(_at=stamps).sort_values("_at", ascending=False)
        keep = [value for value in ("sample_id", "project", "recorded_at")
                if value in recent.columns]
        st.dataframe(recent[keep].head(8), hide_index=True, width="stretch")

    st.subheader(t("dash.attention"))
    notes = _attention_notes(user, frame, papers)
    if notes:
        for note in notes:
            st.caption(f"- {note}")
    else:
        st.caption(t("dash.nothing"))

    st.divider()
    st.caption(t("dash.next"))


def _attention_notes(user: str, frame, papers: list) -> list:
    """Things worth a look, phrased as facts rather than judgements."""
    notes = []
    if frame is not None and not frame.empty and "project" in frame.columns:
        for project in frame["project"].fillna(auth.DEFAULT_PROJECT).unique():
            results = auth.project_result_variables(user, project)
            for name in results:
                if name not in frame.columns:
                    continue
                values = pd.to_numeric(frame[frame["project"] == project][name],
                                       errors="coerce").dropna()
                if len(values) > 1 and float(values.max()) - float(values.min()) > 0:
                    notes.append(t("dash.spread", project=project, name=name,
                                   low=f"{float(values.min()):.2f}",
                                   high=f"{float(values.max()):.2f}"))
    for paper in papers:
        counts = literature.review(paper.get("values") or [])
        if counts["extracted_awaiting_review"]:
            notes.append(t("dash.pending", title=paper.get("title") or paper.get("doi") or "",
                           n=counts["extracted_awaiting_review"]))
    return notes


def insights() -> None:
    """What the project's numbers say as a group, not one row at a time."""
    st.markdown(t("ins.title"))
    st.caption(t("ins.sub"))
    user = auth.current_user()
    if not user:
        st.info(t("guide.signin_hint"))
        return
    frame = _cached_saved(user, _store_where())
    if frame is None or frame.empty or "sample_id" not in frame.columns:
        st.info(t("res.empty_records"))
        return
    projects = [value for value in auth.list_projects(user)
                if value in set(frame["project"].fillna(auth.DEFAULT_PROJECT))]
    if not projects:
        st.info(t("res.empty_records"))
        return
    project = st.selectbox(t("res.project"), projects, key="ins_project")
    part = frame[frame["project"].fillna(auth.DEFAULT_PROJECT) == project]
    results = auth.project_result_variables(user, project)
    if not results:
        st.caption(t("ins.no_results"))
        return
    for name in results:
        values = pd.to_numeric(part.get(name), errors="coerce").dropna()
        if values.empty:
            continue
        stats = comparison.replicate_stats(list(values))
        st.subheader(name.replace("_", " "))
        columns = st.columns(3)
        columns[0].metric(t("ins.n"), stats["n"])
        columns[1].metric(t("ins.mean"), f"{stats['mean']:.3f}" if stats["mean"] is not None
                          else "—")
        columns[2].metric(t("ins.sd"), f"{stats['sd']:.3f}" if stats["sd"] is not None else "—")
        if stats["n"] < 2:
            st.caption(t("ins.one_run"))
        st.caption(t("ins.caution"))

    with st.expander(t("ins.rank"), expanded=False):
        _project_ranking(user, project)


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
        st.markdown(f"### {t('ws.new')}")
        st.caption(t("ws.how"))
        name = st.text_input(t("res.project_name"), placeholder=t("res.project_ph"),
                             key="new_project_name")
        upload = st.file_uploader(t("exp.start_from_file"), type=["csv", "xlsx", "xlsm", "xls"],
                                  key="new_project_file")
        incoming, mapping = None, {}
        if upload is not None:
            try:
                incoming = _read_any(upload.name, upload.getvalue())[0]
            except (ValueError, UnicodeError, pd.errors.ParserError) as exc:
                st.error(t("res.read_error", error=t(str(exc))))
            if incoming is not None and not incoming.empty:
                st.caption(t("exp.start_rows", rows=len(incoming), cols=len(incoming.columns)))
                if ai.available() and st.button(t("exp.read_columns"), key="read_columns"):
                    with st.spinner(t("exp.ai_thinking")):
                        pairs = ai.normalise_columns(
                            list(incoming.columns),
                            incoming.head(3).astype(str).to_dict("records"),
                            st.session_state.get(i18n.LANG_KEY, "en"))
                    st.session_state["column_map"] = pairs
                pairs = st.session_state.get("column_map") or []
                if pairs:
                    st.caption(t("exp.column_map_note"))
                    for item in pairs:
                        st.caption(f"· {item['original']} → `{item['key']}`")
                    mapping = {item["original"]: item["key"] for item in pairs}
        suggestion = st.session_state.get("ai_vars") or []
        if ai.available():
            if st.button(t("exp.ai_suggest"), key="ai_suggest_vars"):
                with st.spinner(t("exp.ai_thinking")):
                    suggestion = ai.suggest_variables(
                        name, st.session_state.get(i18n.LANG_KEY, "en"))
                st.session_state["ai_vars"] = suggestion
            if suggestion:
                st.caption(t("exp.ai_suggest_note"))
                ticked = []
                for item in suggestion:
                    label = (f"{item['key']} — {item['why']}" if item["why"]
                             else str(item["key"]))
                    if st.checkbox(label, value=False, key=f"suggest_{item['key']}"):
                        ticked.append(item["key"])
                if st.button(t("exp.ai_add"), key="ai_add_vars"):
                    current = list(st.session_state.get("new_project_vars") or [])
                    st.session_state["new_project_vars"] = list(
                        dict.fromkeys(current + ticked or [item["key"] for item in suggestion]))
                    st.rerun()
            else:
                st.caption(t("exp.ai_suggest_hint"))

        mapped_keys = list(mapping.values())
        options = list(dict.fromkeys(list(COLUMN_CHOICES) + [item["key"] for item in suggestion]
                                     + mapped_keys))
        default = (mapped_keys or [item["key"] for item in suggestion]
                   or list(auth.DEFAULT_VARIABLES))
        def _add_typed() -> None:
            # one entry is one variable: a name with spaces becomes underscores, it is never split
            typed = "_".join(str(st.session_state.get("new_var_typed", "")).strip().split())
            if typed:
                current = list(st.session_state.get("new_project_vars") or [])
                st.session_state["new_project_vars"] = list(dict.fromkeys(current + [typed]))
            st.session_state["new_var_typed"] = ""

        typed_row = st.columns([3, 1])
        typed_row[0].text_input(t("exp.variable_by_hand"), key="new_var_typed",
                                placeholder="e.g. shear_strength_MPa", label_visibility="collapsed")
        typed_row[1].button(t("exp.variable_add"), key="add_typed_var", on_click=_add_typed,
                            use_container_width=True)
        picked = st.multiselect(t("exp.variables"), options,
                                default=[value for value in default if value in options],
                                help=t("exp.variables_more_ph"), key="new_project_vars",
                                accept_new_options=True)
        if picked:
            st.caption(" · ".join(f"{value} {('(' + auth.unit_of(value) + ')') if auth.unit_of(value) else ''}"
                                  for value in picked))
        extra = ""
        if st.button(t("res.project_create"), type="primary", key="create_project_btn"):
            try:
                created = auth.create_project(user, name)
                wanted = list(picked) + [item.strip() for item in extra.split(",") if item.strip()]
                auth.set_project_variables(user, created, wanted or list(auth.DEFAULT_VARIABLES))
                if incoming is not None and not incoming.empty:
                    prepared = incoming.rename(columns=mapping) if mapping else incoming.copy()
                    prepared["project"] = created
                    if "recorded_at" not in prepared.columns:
                        prepared["recorded_at"] = time.strftime("%Y-%m-%d %H:%M")
                    auth.save_results(user, prepared, append=False)
            except ValueError as exc:
                st.error(t(str(exc)))
            else:
                st.session_state.pop("ai_vars", None)
                st.session_state.pop("column_map", None)
                st.session_state["ws_open"] = created
                st.session_state["project_wanted"] = created
                st.session_state["ws_mode"] = "open"
                st.rerun()
        return

    if mode == "add":
        if st.button("← " + t("ws.back"), key="ws_back_add"):
            st.session_state["ws_mode"] = "open"
            st.rerun()
        _record_tab(user, st.session_state.get("ws_open", auth.DEFAULT_PROJECT))
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

    action = st.columns([1, 2])
    if action[0].button(t("ws.new"), type="primary", use_container_width=True, key="ws_new"):
        st.session_state["ws_mode"] = "new"
        st.rerun()

    st.divider()
    st.markdown(f"#### {t('ws.recent')}")
    projects = auth.list_projects(user)
    states = auth.project_statuses(user)
    frame = auth.load_results(user)

    rows = None
    if frame is not None and not frame.empty:
        rows = frame.copy()
        if "project" not in rows.columns:
            rows["project"] = auth.DEFAULT_PROJECT
        rows["project"] = rows["project"].fillna(auth.DEFAULT_PROJECT)

    meta = auth.project_meta(user)
    grouped = []
    for name in projects:
        part = rows[rows["project"] == name] if rows is not None else None
        runs = 0 if part is None else len(part)
        last = ""
        if part is not None and not part.empty and "recorded_at" in part.columns:
            stamps = pd.to_datetime(part["recorded_at"], errors="coerce").dropna()
            last = stamps.max().strftime("%Y-%m-%d") if len(stamps) else ""
        information = meta.get(name, {})
        grouped.append({"name": name, "runs": runs, "last": last,
                        "status": states.get(name, "In progress"),
                        "created": information.get("created", ""),
                        "pinned": information.get("pinned", "")})
    # a pinned project comes first, then the one with the most recent run
    grouped.sort(key=lambda item: (item["pinned"] != "", item["pinned"], item["last"] != "",
                                   item["last"]), reverse=True)

    pending = st.session_state.get("ws_delete")
    if pending:
        count = next((item["runs"] for item in grouped if item["name"] == pending), 0)
        st.warning(t("ws.delete_warning", name=pending, runs=count))
        yes, no = st.columns(2)
        if yes.button(t("ws.delete_confirm"), type="primary", key="ws_delete_yes"):
            try:
                removed = auth.delete_project(user, pending, force=True)
            except ValueError as exc:
                st.error(t(str(exc)))
            else:
                st.session_state.pop("ws_delete", None)
                if st.session_state.get("ws_open") == pending:
                    st.session_state["ws_mode"] = "home"
                st.success(t("ws.delete_done", name=pending, runs=removed))
                st.rerun()
        if no.button(t("ws.delete_cancel"), key="ws_delete_no"):
            st.session_state.pop("ws_delete", None)
            st.rerun()

    for item in grouped[:5]:
        with st.container(border=True):
            head, tail = st.columns([3, 1])
            key = CHIP_CLASS.get(item["status"], "running")
            head.markdown(f'<div class="bm-status bm-status-{key}">'
                          f'{_status_label(item["status"])}</div>', unsafe_allow_html=True)
            head.markdown(f"**{item['name']}**")
            bits = [t("ws.runs", n=item["runs"]) if item["runs"] else t("ws.empty_project")]
            if item["created"]:
                bits.append(t("ws.created", date=item["created"]))
            if item["last"]:
                bits.append(t("ws.last", date=item["last"]))
            head.caption(" · ".join(bits))
            if tail.button(t("ws.open"), key=f"open_{item['name']}", use_container_width=True):
                st.session_state["ws_open"] = item["name"]
                st.session_state["ws_mode"] = "open"
                st.rerun()
            if tail.button(t("ws.pin"), key=f"pin_{item['name']}",
                           use_container_width=True):
                auth.pin_project(user, item["name"])
                st.rerun()
            if tail.button(t("ws.delete"), key=f"del_{item['name']}",
                           use_container_width=True):
                st.session_state["ws_delete"] = item["name"]
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


def _stored_values(user: str, name: str, columns: list) -> list:
    """Which of these variables already hold data, so removal can be described honestly."""
    frame = auth.load_results(user)
    if frame is None or frame.empty:
        return []
    if "project" in frame.columns:
        frame = frame[frame["project"].fillna(auth.DEFAULT_PROJECT) == name]
    held = []
    for column in columns:
        if column in frame.columns and frame[column].notna().any():
            held.append(f"{column} ({int(frame[column].notna().sum())})")
    return held


def _variables_editor(user: str, name: str) -> None:
    """Add, hide, remove and classify the variables this project records."""
    items = auth.variable_items(user, name)

    def _add(names: list) -> None:
        known = {item["name"] for item in items}
        fresh = []
        for value in names:
            clean = "_".join(str(value).strip().split())
            if clean and clean not in known:
                fresh.append({"name": clean, "unit": auth.unit_of(clean) or "",
                              "role": ai.role_of(clean), "hidden": False, "removed": False})
        if not fresh and not names:
            return
        guessed = []
        if fresh and ai.available():
            with st.spinner(t("exp.ai_thinking")):
                guessed = ai.classify_variables(name, "", [item["name"] for item in fresh])
        by_name = {item["name"]: item for item in guessed}
        merged = [dict(item, role=by_name.get(item["name"], {}).get("role") or item["role"],
                       unit=by_name.get(item["name"], {}).get("unit") or item["unit"])
                  for item in fresh]
        auth.set_variable_items(user, name, items + merged)
        st.rerun()

    if ai.available():
        if st.button(t("exp.ai_suggest_here"), key=f"vars_{name}_ai"):
            with st.spinner(t("exp.ai_thinking")):
                asked = ai.classify_variables(name, "", [
                    item["key"] for item in ai.suggest_variables(
                        name, st.session_state.get(i18n.LANG_KEY, "en"))])
            st.session_state[f"vars_{name}_ai_list"] = asked
        asked = st.session_state.get(f"vars_{name}_ai_list") or []
        if asked:
            st.caption(t("exp.ai_suggest_note"))
            ticked = [item["name"] for item in asked
                      if st.checkbox(f"{item['name']} — {item['role']}"
                                     + (f" — {item['why']}" if item.get("why") else ""),
                                     key=f"vars_{name}_ask_{item['name']}")]
            if st.button(t("exp.ai_add"), key=f"vars_{name}_add_ai"):
                _add(ticked or [item["name"] for item in asked])

    typed_row = st.columns([3, 1])
    typed_row[0].text_input(t("exp.variable_by_hand"), key=f"vars_{name}_typed",
                            placeholder="e.g. reaction_pressure_bar",
                            label_visibility="collapsed")
    typed_row[1].button(t("exp.variable_add"), key=f"vars_{name}_add_typed",
                        on_click=lambda: _add([st.session_state.get(f"vars_{name}_typed", "")]),
                        use_container_width=True)

    if not items:
        st.caption(t("exp.no_variables_yet"))
        return
    frame = pd.DataFrame([{
        "variable": item["name"],
        "display_name": item.get("display_name") or item["name"].replace("_", " "),
        "unit": item["unit"],
        "role": auth.ROLE_LABELS.get(item["role"], item["role"]),
        "priority": item.get("priority") or "",
        "formula": item.get("formula") or "",
        "hidden": item["hidden"],
        "remove": False,
    } for item in items])
    edited = st.data_editor(
        frame, hide_index=True, width="stretch", num_rows="fixed", key=f"vars_{name}_table",
        column_config={
            "variable": st.column_config.TextColumn(t("exp.col_variable"), disabled=True),
            "display_name": st.column_config.TextColumn(t("exp.col_display")),
            "unit": st.column_config.TextColumn(t("exp.col_unit")),
            "role": st.column_config.SelectboxColumn(
                t("exp.col_role"),
                options=[auth.ROLE_LABELS[value] for value in auth.VARIABLE_ROLES]),
            "priority": st.column_config.SelectboxColumn(
                t("exp.col_priority"), options=["primary", "secondary", ""]),
            "formula": st.column_config.TextColumn(t("exp.col_formula"),
                                                   help=t("exp.formula_help")),
            "hidden": st.column_config.CheckboxColumn(t("exp.col_hidden")),
            "remove": st.column_config.CheckboxColumn(t("exp.col_remove")),
        })
    going = [str(row["variable"]) for _, row in edited.iterrows() if bool(row["remove"])]
    if going:
        held = _stored_values(user, name, going)
        if held:
            st.warning(t("exp.remove_history", names=", ".join(held)))
    if st.button(t("exp.variables_save"), key=f"vars_{name}_save"):
        by_label = {auth.ROLE_LABELS[value]: value for value in auth.VARIABLE_ROLES}
        updated = []
        for (_, row), original in zip(edited.iterrows(), items):
            role = by_label.get(str(row["role"]), original["role"])
            updated.append({**original,
                            "display_name": str(row["display_name"] or original["name"]),
                            "unit": str(row["unit"] or ""),
                            "role": role,
                            "priority": str(row["priority"] or "") if role in auth.RESULT_ROLES
                            else "",
                            "formula": str(row["formula"] or "") if role == "derived" else "",
                            "hidden": bool(row["hidden"]),
                            "removed": bool(row["remove"]) or original.get("removed", False)})
        auth.set_variable_items(user, name, updated)
        st.success(t("exp.variables_saved"))
        st.rerun()

    st.caption(t("exp.hide_note"))


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

    with st.expander(t("exp.rename"), expanded=False):
        with st.form(f"rename_{name}"):
            fresh = st.text_input(t("res.project_name"), value=name)
            if st.form_submit_button(t("exp.rename_btn")):
                try:
                    renamed = auth.rename_project(user, name, fresh)
                except ValueError as exc:
                    st.error(t(str(exc)))
                else:
                    st.session_state["ws_open"] = renamed
                    st.session_state["project_wanted"] = renamed
                    st.rerun()

    if part.empty:
        st.info(t("exp.no_experiments"))
        if st.button(t("exp.add_run"), key=f"first_run_{name}", type="primary"):
            st.session_state["ws_open"] = name
            st.session_state["ws_mode"] = "add"
            st.rerun()
        return

    tab_overview, tab_formulation, tab_process, tab_results, tab_records = st.tabs(
        [t("exp.tab_overview"), t("exp.tab_formulation"), t("exp.tab_process"),
         t("exp.tab_results"), t("exp.tab_records")])

    latest = part.iloc[-1]
    with tab_overview:
        own = [value for value in auth.project_variables(user, name)
               if value not in ("sample_id", "recorded_at", "notes")]
        des_project = (any(value in own for value in ("des_hba", "des_hbd", "molar_ratio"))
                       or auth.formulation_stored(user, name))
        shows_yield = "lignin_yield_pct" in own
        shows_lignin = "lignin_mg" in own

        metrics = st.columns(3)
        if shows_yield:
            yields = pd.to_numeric(part.get("lignin_yield_pct"), errors="coerce").dropna()
            if len(yields) > 1 and float(yields.max()) - float(yields.min()) > 1e-9:
                metrics[0].metric(t("res.lignin_yield"),
                                  f"{float(yields.min()):.2f} – {float(yields.max()):.2f} %",
                                  help=t("exp.range_help", n=len(yields)))
            else:
                metrics[0].metric(t("res.lignin_yield"),
                                  f"{float(yields.iloc[-1]) if len(yields) else 0:.2f} %")
        if shows_lignin:
            recovered = pd.to_numeric(part.get("lignin_mg"), errors="coerce").dropna()
            if len(recovered) > 1 and float(recovered.max()) - float(recovered.min()) > 1e-9:
                metrics[1].metric(t("res.lignin_mg"),
                                  f"{float(recovered.min()):.1f} – {float(recovered.max()):.1f} mg",
                                  help=t("exp.range_help", n=len(recovered)))
            else:
                metrics[1].metric(t("res.lignin_mg"),
                                  f"{float(recovered.iloc[-1]) if len(recovered) else 0:.1f} mg")
        metrics[2].metric(t("ws.runs_label"), len(part))

        if des_project:
            heading = auth.project_formulation(user, name)
            st.caption(t("exp.header_line", hba=heading["des_hba"], hbd=heading["des_hbd"],
                         ratio=heading["molar_ratio"], runs=len(part)))
        # the columns are this project's own variables: a GFP project does not show lignin
        visible = auth.project_visible_variables(user, name)
        results = auth.project_result_variables(user, name)
        ordered = [value for value in results if value in visible] + \
                  [value for value in visible if value not in results]
        keep = ["sample_id"] + [value for value in ordered if value in part.columns]
        keep = list(dict.fromkeys(value for value in keep if value in part.columns))
        st.dataframe(part[keep] if keep else part, width="stretch", hide_index=True)
        st.caption(t("exp.overview_note"))
        st.divider()
        st.caption(t("exp.variables_here"))
        _variables_editor(user, name)

        with st.expander(t("exp.history"), expanded=False):
            lines = [line for line in auth.change_log(200)
                     if line.get("target") == name or line.get("kind") == "record"]
            if not lines:
                st.caption(t("exp.history_none"))
            for line in lines[:30]:
                st.caption(audit.describe(line))
            export_body = dataset.payload(
                name, auth.project_variable_items(user, name),
                (part.drop(columns=[c for c in ("_owner",) if c in part.columns])
                 .to_dict("records")))
            st.download_button(t("exp.export_json"), dataset.to_json(export_body),
                               f"{name.replace(' ', '_')}.json", "application/json",
                               key=f"export_{name}")
            st.caption(dataset.describe(export_body))
            if st.button(t("exp.recompute"), key=f"recompute_{name}"):
                frame = auth.load_results(user)
                if frame is not None and not frame.empty:
                    frame = frame.copy()
                    mask = frame["project"].fillna(auth.DEFAULT_PROJECT) == name
                    items = auth.project_variable_items(user, name)
                    changed = 0
                    for index in frame[mask].index:
                        before = frame.loc[index].to_dict()
                        after = derive.recompute(before, items)
                        for key, value in after.items():
                            if key in items and key not in before:
                                continue
                        differences = {key: {"before": before.get(key), "after": value}
                                       for key, value in after.items()
                                       if str(before.get(key)) != str(value)}
                        if differences:
                            for key, value in after.items():
                                if key in frame.columns:
                                    frame.at[index, key] = value
                            changed += 1
                    if changed:
                        auth.save_results(user, frame, append=False)
                        auth.record_change(user, "record", name, {},
                                           note=f"derived values recomputed for {changed} row(s)")
                        st.success(t("exp.recomputed", n=changed))
                        st.rerun()
                    else:
                        st.caption(t("exp.recompute_none"))

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
        _photos_section(user, part, name)

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
        st.session_state["ws_open"] = name
        st.session_state["ws_mode"] = "add"
        st.rerun()

def _photos_section(user: str | None, frame: pd.DataFrame, project: str | None = None) -> None:
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
                                           upload.type or "image/png", upload.getvalue(),
                                           project=project)
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
                stored = auth.image_content(user, int(row["id"]))
                label = row.get("category") or t("res.photos_no_category")
                caption = " · ".join(
                    value for value in (row.get("note"), row.get("filename"),
                                        f"{int(row.get('size') or 0) // 1024} KB") if value)
                # the thumbnail is small on purpose; the original is drawn at container width
                # inside the expander, so opening it shows every pixel instead of an upscaled 140px
                with st.expander(f"{label} — {caption}", expanded=False):
                    if stored:
                        st.image(stored[0], width="stretch")
                        st.caption(f"{row.get('filename')} · "
                                   f"{int(row.get('size') or 0) // 1024} KB · "
                                   f"{stored[1]}")
                    if row.get("note"):
                        st.markdown(row["note"])
                    if st.button(t("res.photos_delete"), key=f"del_image_{row['id']}"):
                        auth.remove_image(user, int(row["id"]))
                        st.rerun()


def _looks_duplicate(frame: pd.DataFrame, sample_id: str, lignin_mg: float,
                     biomass_g: float) -> bool:
    """True when the same run is already stored, so a double click cannot add it twice."""
    # the ID is not part of the identity: a double click can move the suggested ID on, while the
    # measurement behind it is still the same run
    wanted = (round(float(lignin_mg), 4), round(float(biomass_g), 4))
    if "sample_id" not in frame.columns:
        return False
    for _, row in frame.iterrows():
        try:
            other = (round(float(row.get("lignin_mg")), 4),
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
    # the next sample ID counts inside this project only: EXP-05 after EXP-04 of the same project
    if "project" in saved.columns and project:
        saved = saved[saved["project"].fillna(auth.DEFAULT_PROJECT) == project]
    # the next ID is decided by this project's rows: when the project changes, or when its rows
    # change (a run was just saved), put the right value in the field instead of keeping a stale one
    expected = _next_sample_id(saved)
    if (st.session_state.get("run_sample_project") != project
            or st.session_state.get("run_sample_expected") != expected
            or "run_sample" not in st.session_state):
        st.session_state["run_sample"] = expected
        st.session_state["run_sample_project"] = project
        st.session_state["run_sample_expected"] = expected
    note = st.session_state.pop("run_saved_note", None)
    if note:
        st.success(note)
    st.caption(t("res.new_hint"))
    own = auth.project_visible_variables(user, project)
    results = auth.project_result_variables(user, project)
    reserved = {"sample_id", "feedstock", "replicate", "notes", "recorded_at", "project",
                "des_hba", "des_hbd", "molar_ratio", "purity_wt_pct", "water_wt_pct",
                "lignin_yield_pct", "formulation"}
    # conditions first, then the measured outcome: the numbers you set, then the number you got
    measured = ([value for value in own if value not in reserved and value not in results]
                + [value for value in own if value in results and value not in reserved])
    left, right = st.columns(2)
    sample_id = left.text_input(t("res.sample_id"), key="run_sample")
    feedstock = (right.text_input(t("res.feedstock"), placeholder=t("res.feedstock_ph"),
                                  key="run_feedstock")
                 if "feedstock" in own else "")
    formulation = auth.project_formulation(user, project)
    # a DES formulation is only shown for a project that actually records one
    des_project = (any(value in own for value in ("des_hba", "des_hbd", "molar_ratio"))
                   or auth.formulation_stored(user, project))
    if des_project:
        st.caption(t("res.project_formulation", hba=formulation["des_hba"],
                     hbd=formulation["des_hbd"], ratio=formulation["molar_ratio"],
                     purity=formulation["purity_wt_pct"]))
    hba, hbd = formulation["des_hba"], formulation["des_hbd"]
    ratio, purity = formulation["molar_ratio"], formulation["purity_wt_pct"]
    water = formulation["water_wt_pct"]
    replicate = st.number_input(t("res.replicate"), min_value=1, value=1, step=1,
                                key="run_replicate")

    values = {}
    for chunk in range(0, len(measured), 3):
        columns = st.columns(3)
        for column, variable in zip(columns, measured[chunk:chunk + 3]):
            key = f"run_var_{variable}"
            unit = auth.unit_of(variable)
            label = f"{variable} ({unit})" if unit else variable
            if variable.endswith(("_pct", "_C", "_min", "_mg", "_g", "_rpm", "_mm",
                                  "_ratio", "_bar", "_mL", "_MPa", "_s", "_h")):
                values[variable] = column.number_input(label, min_value=0.0, value=0.0,
                                                      step=0.1, format="%.4f", key=key)
            else:
                values[variable] = column.text_input(label, key=key)
    notes = st.text_input(t("res.notes"), key="run_notes")
    submitted = st.button(t("res.save_run"), type="primary",
                                         use_container_width=True)

    biomass = values.get("biomass_g") or 0.0
    lignin = values.get("lignin_mg") or 0.0
    preview = _yield_pct(biomass, lignin) if ("biomass_g" in values and "lignin_mg" in values) else None
    label = (schema.build_formulation({"des_hba": hba, "des_hbd": hbd, "molar_ratio": ratio})
             if des_project else "")
    if des_project and label:
        st.caption(t("res.formulation_preview", label=label))
    if preview is not None:
        st.caption(t("res.yield_preview", pct=f"{preview:.2f}"))
    if not measured:
        st.warning(t("res.no_variables"))
    if submitted:
        if measured and all(
                (isinstance(value, str) and not value.strip())
                or (isinstance(value, (int, float)) and value == 0)
                for value in values.values()):
            st.warning(t("res.need_numbers") if ("biomass_g" in values and "lignin_mg" in values)
                       else t("res.need_some_value"))
            return
        if ratio <= 0 or not str(hba).strip() or not str(hbd).strip():
            st.warning(t("res.need_composition"))
            return
        already = _cached_saved(user, _store_where(), project)
        if already is not None and not already.empty and _looks_duplicate(
                already, sample_id, lignin, biomass):
            st.warning(t("res.duplicate_submit"))
            return
        row = {
            "sample_id": sample_id.strip() or _next_sample_id(saved),
            "formulation": label,
            "feedstock": feedstock.strip(),
            "lignin_yield_pct": preview,
            "replicate": int(replicate),
            "notes": notes.strip(),
            "recorded_at": time.strftime("%Y-%m-%d %H:%M"),
            "project": project,
        }
        if des_project:
            row.update({"des_hba": hba.strip(), "des_hbd": hbd.strip(),
                        "molar_ratio": float(ratio), "purity_wt_pct": float(purity),
                        "water_wt_pct": float(water)})
        row.update(values)
        # a derived variable is computed from the measurements, never typed by hand
        row = derive.recompute(row, auth.project_variable_items(user, project))
        auth.save_results(user, pd.DataFrame([row]), append=True)
        total = auth.load_results(user)
        shown = f"{preview:.2f}" if preview is not None else "—"
        st.session_state["run_saved_note"] = t("res.saved_run", sid=row["sample_id"], pct=shown,
                                                rows=0 if total is None else len(total))
        # advance the suggested ID and start the next run with a clean sheet
        # the widgets cannot be cleared after they were created in this run; the rerun picks the
        # advanced ID up from the project's rows instead
        st.session_state["run_sample_project"] = None
        st.rerun()


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
    own = auth.project_variables(user, project) if user else []
    ordered = [c for c in RECORD_COLUMNS if c in frame.columns]
    ordered += [c for c in own if c in frame.columns and c not in ordered]
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
                    for row_number, column, raw in (info.get("problems") or [])[:8]:
                        st.warning(t("res.import_bad_cell", row=row_number, column=column,
                                     raw=raw))
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
    _photos_section(user, frame, project)


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
    # the source radio keeps its value across pages; when the project changes, go back to the
    # project's own rows instead of silently showing the bundled sample
    if st.session_state.get("source_project") != project:
        st.session_state["source_project"] = project
        st.session_state["source"] = t("res.src_saved")

    sources = []
    if user:
        sources.append(("saved", t("res.src_saved")))
    # no bundled sample and no synthetic demo: showing a number that does not belong to this
    # project is worse than showing nothing
    sources += [("upload", t("res.src_upload"))]
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

