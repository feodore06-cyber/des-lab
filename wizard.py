"""The multi-step create-project workflow: nothing is written until the last button."""

import streamlit as st

import pandas as pd

import ai
import auth
import columnmap
import excel_io
import i18n
import research
from i18n import t


def _state() -> dict:
    return st.session_state.setdefault("wizard", {"step": 1, "name": "", "description": "",
                                                  "frame": None, "info": None, "file": "",
                                                  "sheets": [], "sheet": "", "mapping": {},
                                                  "suggested": [], "manual": []})


def _goto(step: int) -> None:
    _state()["step"] = step
    st.rerun()


def _reset() -> None:
    st.session_state.pop("wizard", None)
    st.session_state.pop("wizard_mapping", None)
    st.session_state.pop("wizard_suggest", None)
    st.rerun()


def render(user: str, start_open: bool = False) -> None:

    if not st.session_state.get("wizard") and not start_open:
        # the form stays closed until the researcher asks for it, exactly as before
        if st.button(t("ws.new"), key="ws_new_project"):
            _state()
            st.rerun()
        return
    state = _state()
    step = int(state.get("step") or 1)
    st.markdown(f"### {t('wiz.title')}")
    st.caption(t("wiz.step", step=step, total=4))

    if step == 1:
        state["name"] = st.text_input(t("res.project_name"), value=state.get("name") or "",
                                      placeholder=t("res.project_ph"))
        state["description"] = st.text_area(t("wiz.description"),
                                           value=state.get("description") or "", height=90)
        clean = str(state["name"]).strip()
        if clean and clean in auth.list_projects(user):
            st.error(t("wiz.duplicate"))
        ready = bool(clean) and clean not in auth.list_projects(user)
        columns = st.columns([1, 1])
        if columns[1].button(t("wiz.next"), type="primary", key="wiz_next1", disabled=not ready):
            _goto(2)
        return

    if step == 2:
        upload = st.file_uploader(t("exp.start_from_file"),
                                  type=["csv", "xlsx", "xlsm", "xls"], key="wiz_file")
        if upload is not None and state.get("file") != upload.name:
            content = upload.getvalue()
            if excel_io.is_excel(upload.name):
                sheets = excel_io.read_workbook(content)
                names = [name for name, _ in sheets]
                state["sheets"] = names
                state["sheet"] = names[0] if names else ""
                name, frame = excel_io.frame_with_original_headers(
                    content, state["sheet"] or None)
                state["frame"] = frame
                state["info"] = {"sheet": name}
            else:
                state["frame"] = pd.read_csv(__import__("io").BytesIO(content),
                                             encoding="utf-8-sig")
                state["info"] = None
                state["sheets"] = []
                state["sheet"] = ""
            state["file"] = upload.name
            state["mapping"] = {}

        if state.get("sheets"):
            chosen = st.selectbox(t("wiz.sheet"), state["sheets"],
                                  index=state["sheets"].index(state["sheet"])
                                  if state.get("sheet") in state["sheets"] else 0)
            if chosen != state.get("sheet") and upload is not None:
                state["sheet"] = chosen
                name, frame = excel_io.frame_with_original_headers(upload.getvalue(), chosen)
                state["frame"] = frame
                state["info"] = {"sheet": name}
                st.rerun()

        frame = state.get("frame")
        if frame is not None and not frame.empty:
            st.caption(t("wiz.read", rows=len(frame), cols=len(frame.columns),
                         file=state.get("file") or "", sheet=state.get("sheet") or "-"))
            st.caption(t("wiz.columns") + " · " + " | ".join(str(c) for c in frame.columns))
            st.dataframe(frame.head(8), hide_index=True, width="stretch")
        else:
            st.caption(t("wiz.no_file"))
        columns = st.columns([1, 1, 1])
        if columns[0].button(t("wiz.back"), key="wiz_back2"):
            _goto(1)
        if columns[2].button(t("wiz.next"), type="primary", key="wiz_next2"):
            _goto(3)
        return

    if step == 3:
        frame = state.get("frame")
        columns_in = [str(c) for c in (frame.columns if frame is not None else [])]
        if not columns_in:
            st.caption(t("wiz.no_file_skip"))
        else:
            if ai.available() and st.button(t("exp.read_columns"), key="wiz_ai_cols"):
                with st.spinner(t("exp.ai_thinking")):
                    pairs = ai.normalise_columns(
                        columns_in,
                        frame.head(3).astype(str).to_dict("records"),
                        st.session_state.get(i18n.LANG_KEY, "en"))
                state["suggested_cols"] = pairs
                st.session_state["wizard_mapping"] = {
                    str(item["original"]): str(item.get("key") or
                                               research.normalise_name(item["original"]))
                    for item in (pairs or [])}
            proposals = columnmap.suggest_all(columns_in)
            clashes = columnmap.duplicates(proposals)
            rows = []
            for proposal in proposals:
                name = str(proposal["name"] or "")
                rows.append({"original": proposal["original"],
                             "standard": name,
                             "unit": proposal["unit"],
                             "type": proposal["data_type"],
                             "role": proposal["role"],
                             "confidence": proposal["confidence"],
                             "include": bool(name) and proposal["original"] not in
                             [item for names in clashes.values() for item in names[1:]]})
            edited = st.data_editor(pd.DataFrame(rows), hide_index=True, width="stretch",
                                    num_rows="fixed", key="wiz_map_table",
                                    column_config={
                                        "original": st.column_config.TextColumn(
                                            t("wiz.original"), disabled=True),
                                        "standard": st.column_config.TextColumn(t("wiz.standard")),
                                        "unit": st.column_config.TextColumn(t("exp.col_unit")),
                                        "type": st.column_config.SelectboxColumn(
                                            t("wiz.type"), options=["number", "text", "category"]),
                                        "role": st.column_config.SelectboxColumn(
                                            t("exp.col_role"),
                                            options=[auth.ROLE_LABELS[v] for v in auth.VARIABLE_ROLES]),
                                        "confidence": st.column_config.TextColumn(
                                            t("wiz.confidence"), disabled=True),
                                        "include": st.column_config.CheckboxColumn(t("wiz.include")),
                                    })
            st.caption(t("wiz.map_note"))
            if clashes:
                for name, originals in clashes.items():
                    st.warning(t("wiz.clash", name=name, columns=", ".join(originals)))
            mapping = {}
            by_label = {auth.ROLE_LABELS[v]: v for v in auth.VARIABLE_ROLES}
            for _, row in edited.iterrows():
                if not bool(row["include"]):
                    continue
                target = research.normalise_name(row["standard"])
                if not target:
                    continue
                mapping[str(row["original"])] = {
                    "name": target, "unit": str(row["unit"] or ""),
                    "data_type": str(row["type"] or ""),
                    "role": by_label.get(str(row["role"]), "independent")}
            state["mapping"] = mapping

        columns = st.columns([1, 1, 1])
        if columns[0].button(t("wiz.back"), key="wiz_back3"):
            _goto(2)
        if columns[2].button(t("wiz.next"), type="primary", key="wiz_next3"):
            _goto(4)
        return

    _summary(user)


def _summary(user: str) -> None:
    import streamlit as st

    state = _state()
    frame = state.get("frame")
    mapping = state.get("mapping") or {}

    variables = {}
    if frame is not None and not frame.empty:
        for original, spec in mapping.items():
            variables[spec["name"]] = {"name": spec["name"], "unit": spec.get("unit", ""),
                                       "data_type": spec.get("data_type", ""),
                                       "role": spec.get("role", "independent")}
    for item in state.get("suggested") or []:
        variables.setdefault(item["name"], {"name": item["name"], "unit": item.get("unit", ""),
                                            "data_type": "", "role": item.get("role", "dependent")})
    for item in state.get("manual") or []:
        variables.setdefault(item["name"], {"name": item["name"], "unit": item.get("unit", ""),
                                            "data_type": "", "role": "independent"})

    rows, conflicts = [], {}
    if frame is not None and not frame.empty and mapping:
        rename = {original: spec["name"] for original, spec in mapping.items()}
        rows = research.sample_rows(frame, rename)
        for entry in rows:
            for key, value in list(entry["values"].items()):
                if key in RESERVED_FOR_RUN:
                    continue
        conflicts = research.find_conflicts(rows, set())

    if not variables:
        # a project with nothing chosen still gets the standard starting set, as before
        variables = {name: {"name": name, "unit": auth.unit_of(name) or "",
                            "data_type": "", "role": ai.role_of(name)}
                     for name in auth.DEFAULT_VARIABLES}
    st.markdown(f"#### {t('wiz.review')}")
    st.caption(f"{t('res.project_name')}: **{state.get('name') or '—'}**")
    if state.get("description"):
        st.caption(f"{t('wiz.description')}: {state['description']}")
    if variables:
        st.dataframe(pd.DataFrame(list(variables.values())), hide_index=True, width="stretch")
    else:
        st.warning(t("wiz.need_variable"))
    st.caption(t("wiz.import_summary", rows=len(rows), mapped=len(mapping),
                 excluded=max(0, len(frame.columns) - len(mapping)) if frame is not None else 0))
    if conflicts.get("inside_file"):
        st.error(t("res.import_conflicts"))
        for sid, where in list(conflicts["inside_file"].items())[:5]:
            st.caption(t("res.conflict_inside", sid=sid, rows=", ".join(where)))
    if conflicts.get("missing"):
        st.warning(t("res.conflict_missing",
                     rows=", ".join(str(v) for v in conflicts["missing"][:10])))

    if ai.available():
        if st.button(t("exp.ai_suggest"), key="wiz_suggest"):
            with st.spinner(t("exp.ai_thinking")):
                state["suggested_raw"] = ai.suggest_variables(
                    state.get("name") or "", st.session_state.get(i18n.LANG_KEY, "en"))
        raw = state.get("suggested_raw") or []
        if raw:
            ticked = [item["key"] for item in raw
                      if item["key"] not in variables and st.checkbox(
                          f"{item['key']} — {item.get('why', '')}", key=f"wiz_tick_{item['key']}")]
            if st.button(t("exp.ai_add"), key="wiz_add_suggested"):
                state["suggested"] = [{"name": research.normalise_name(key), "unit": "",
                                       "role": "dependent"} for key in ticked]
                st.rerun()

    typed = st.text_input(t("exp.variable_by_hand"), key="wiz_typed",
                          placeholder="e.g. shear_strength_MPa")
    if st.button(t("exp.variable_add"), key="wiz_add_manual"):
        name = research.normalise_name(typed)
        if name and name not in variables:
            state["manual"] = list(state.get("manual") or []) + [
                {"name": name, "unit": auth.unit_of(name) or ""}]
            st.rerun()

    columns = st.columns([1, 1])
    if columns[0].button(t("wiz.back"), key="wiz_back4"):
        _goto(3)
    blocked = bool(conflicts.get("inside_file"))
    if columns[1].button(t("wiz.create"), type="primary", key="wiz_create",
                         disabled=blocked):
        source = {"file": state.get("file") or None, "sheet": state.get("sheet") or None}
        try:
            result = research.create_project_with_data(
                user, state.get("name") or "", state.get("description") or "",
                list(variables.values()), rows, source)
        except ValueError as exc:
            st.error(t(str(exc)))
        else:
            st.success(t("exp.created", name=result["project"],
                         variables=result["variables"], rows=result["imported"]))
            st.session_state["project_wanted"] = result["project"]
            _reset()


RESERVED_FOR_RUN = {"project", "_owner"}


def page() -> None:
    """Entry point for the navigation: the signed-in user runs the wizard here."""
    import auth

    user = auth.current_user()
    if not user:
        st.info(t("guide.signin_hint"))
        return
    render(user, start_open=True)
