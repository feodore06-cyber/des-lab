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
from pathlib import Path

import pandas as pd
import streamlit as st

import auth
import chem
import feedback as feedback_mod
import store
import i18n
import mailer
from i18n import t
from lab_core import calculate_recipe, csv_bytes, merge_results, summarize
from lab_plots import figure_bytes, make_figure

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
    st.caption(t("calc.step"))
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


def results():
    st.caption(t("res.step"))
    st.title(t("res.title"))
    st.write(t("res.intro"))
    user = auth.current_user()

    sources = []
    if user:
        sources.append(("saved", t("res.src_saved")))
    sources += [("sample", t("res.src_sample")), ("demo", t("res.src_demo")), ("upload", t("res.src_upload"))]
    source_label = st.radio(t("res.source"), [label for _, label in sources], horizontal=True, key="source")
    source = dict((label, key) for key, label in sources)[source_label]

    if source == "saved":
        saved = auth.load_results(user)
        if saved is None or saved.empty:
            st.info(t("res.empty"))
            if st.button(t("res.load_example"), key="import_runs"):
                auth.save_results(user, pd.read_csv(MY_CSV), append=False)
                st.rerun()
            return
        # The rows may come from the database, where no local file exists, so serialise them here
        # instead of reading a CSV path that only exists on a laptop.
        location = "database" if store.enabled() else str(auth.results_path(user))
        st.caption(t("res.loaded", rows=len(saved), path=location))
        files = [(f"{auth.folder_name(user)}_results.csv", csv_bytes(saved))]
        encoding, data_kind = "utf-8-sig", "user_saved"
    elif source == "sample":
        st.info(t("res.sample_info"))
        files = [("my_des_runs.csv", MY_CSV.read_bytes())]
        encoding, data_kind = "utf-8-sig", "my_experiments"
    elif source == "demo":
        st.warning(t("res.demo_warning"))
        files = [("demo_lignin.csv", DEMO_CSV.read_bytes())]
        encoding, data_kind = "utf-8-sig", "synthetic_demo"
    else:
        uploads = st.file_uploader(t("res.uploader"), type="csv", accept_multiple_files=True)
        encoding = st.selectbox(t("res.encoding"), ["utf-8-sig", "gb18030"], help=t("res.encoding_help"))
        if not uploads:
            st.info(t("res.upload_hint"))
            return
        files = [(f.name, f.getvalue()) for f in uploads]
        data_kind = "user_uploaded"

    try:
        frame = merge_results(files, encoding)
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
    if duplicate_count:
        st.warning(t("res.dupes"))
    with st.expander(t("res.raw"), expanded=False):
        st.dataframe(frame, hide_index=True, width="stretch")
        st.download_button(t("res.download_merged"), csv_bytes(frame), "merged_results.csv", "text/csv")
        if user and data_kind == "user_uploaded":
            st.divider()
            st.caption(t("res.save_path", path=auth.results_path(user)))
            modes = [("append", t("res.save_append")), ("replace", t("res.save_replace"))]
            save_label = st.radio(t("res.save_mode"), [label for _, label in modes], horizontal=True, key="save_mode")
            if st.button(t("res.save_button"), key="save_results"):
                append = dict((label, key) for key, label in modes)[save_label] == "append"
                path = auth.save_results(user, frame, append=append)
                st.success(t("res.saved_n", rows=len(frame), path=path))

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
        clean, summary, audit = summarize(frame, groups, measurement)
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
    st.subheader(t("res.summary"))
    st.dataframe(summary, hide_index=True, width="stretch")
    st.caption(t("res.summary_caption"))
    summary_export = summary.assign(measurement=measurement, data_kind=data_kind)
    st.download_button(t("res.download_summary"), csv_bytes(summary_export), "summary.csv", "text/csv")
    if len(summary) > 30:
        st.info(t("res.too_many"))
        return
    a, b = st.columns(2)
    title = a.text_input(t("res.fig_title"),
                         value=t("res.fig_title_demo") if data_kind == "synthetic_demo" else t("res.fig_title_real"))
    ylabel = b.text_input(t("res.yaxis"), value=_y_label(measurement), key=f"ylabel_{measurement}")
    fig = make_figure(clean, summary, groups, measurement, title, ylabel)
    st.pyplot(fig, width="stretch")
    st.caption(t("res.fig_caption"))
    a, b = st.columns(2)
    a.download_button(t("res.download_png"), figure_bytes(fig, "png"), "experiment.png", "image/png")
    b.download_button(t("res.download_svg"), figure_bytes(fig, "svg"), "experiment.svg", "image/svg+xml")


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
            detail = store.ping()
        except Exception as exc:
            st.error(t("store.error", error=str(exc).splitlines()[0][:200]))
        else:
            st.success(t("store.database") + " · " + detail)
    else:
        st.info(t("store.local"))

    st.divider()
    st.subheader(t("guide.account"))
    user = auth.current_user()
    if not user:
        st.info(t("guide.signin_hint"))
        return
    st.markdown(t("guide.signed_in", user=user, path=auth.user_dir(user)))

    st.divider()
    st.subheader(t("guide.accounts"))
    if auth.is_admin(user):
        rows = []
        try:
            if store.enabled():
                rows = store.accounts_rows()
            else:
                rows = [{"username": name, "created": entry.get("created", ""),
                         "last_login": entry.get("last_login", "")}
                        for name, entry in auth.load_users().items()]
        except Exception as exc:
            st.error(t("guide.accounts_error", error=str(exc).splitlines()[0][:160]))
        if rows:
            week_ago = pd.Timestamp.now() - pd.Timedelta(days=7)
            recent = sum(1 for row in rows
                         if row["created"] and pd.to_datetime(row["created"], errors="coerce") >= week_ago)
            active = sum(1 for row in rows if row["last_login"] and row["last_login"] != "never")
            a, b, c = st.columns(3)
            a.metric(t("guide.accounts_total"), len(rows))
            b.metric(t("guide.accounts_recent"), recent)
            c.metric(t("guide.accounts_active"), active)
            st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")
            st.caption(t("guide.accounts_hint"))
        else:
            st.info(t("guide.accounts_none"))
    else:
        st.caption(t("guide.accounts_admin_only"))
    st.caption(t("guide.records_note"))

    st.subheader(t("guide.mail"))
    if auth.is_admin(user):
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
    else:
        st.caption(t("guide.accounts_admin_only"))

    st.subheader(t("guide.resets"))
    if auth.is_admin(user):
        st.caption(t("guide.resets_hint"))
        names = sorted(auth.load_users())
        if names:
            with st.form("admin_reset"):
                who = st.selectbox(t("guide.resets_pick"), names, key="reset_who")
                if st.form_submit_button(t("guide.resets_create")):
                    token = auth.create_reset_token(who)
                    st.session_state["last_reset_link"] = auth.reset_link(token) if token else ""
            link = st.session_state.get("last_reset_link")
            if link:
                st.code(link, language="text")
                st.caption(t("guide.resets_link"))
    else:
        st.caption(t("guide.accounts_admin_only"))

    left, right = st.columns(2)
    with left:
        st.markdown(t("guide.change"))
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
    with right:
        st.markdown(t("guide.add"))
        with st.form("add_teammate", clear_on_submit=True):
            name = st.text_input(t("guide.username"), placeholder=t("guide.username_ph"))
            initial = st.text_input(t("guide.initial_pw"), type="password")
            if st.form_submit_button(t("guide.add_btn")):
                try:
                    auth.add_user(name, initial)
                    st.success(t("guide.added", user=name.strip()))
                except ValueError as exc:
                    st.error(t(str(exc)))


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

