import io
import ast

base = r"C:\Users\User\Documents\Codex\2026-10-14\des-repository-fork-ai\outputs\des-lab"
path = base + r"\views.py"
text = io.open(path, encoding="utf-8").read()

# ---- 1. the variables editor moves to its own tab ---------------------------------------------
start = text.index('        st.divider()\n        st.caption(t("exp.variables_here"))\n        _variables_editor(user, name)')
end = text.index('        with st.expander(t("exp.history")', start)
old = text[start:end]
text = text[:start] + '''        st.caption(t("exp.variables_moved"))
''' + text[end:]

# ---- 2. the tab itself ------------------------------------------------------------------------
old = '''    with tab_formulation:'''
new = '''    with tab_variables:
        st.caption(t("exp.variables_here"))
        _variables_editor(user, name)
        with st.expander(t("exp.history"), expanded=False):
            lines = [line for line in auth.change_log(200)
                     if line.get("target") == name or line.get("kind") == "record"]
            if not lines:
                st.caption(t("exp.history_none"))
            for line in lines[:30]:
                st.caption(audit.describe(line))

    with tab_formulation:'''
assert old in text, "the tab list changed"
text = text.replace(old, new, 1)

old = '''    tab_overview, tab_formulation, tab_process, tab_results, tab_records = st.tabs('''
new = '''    tab_overview, tab_variables, tab_formulation, tab_process, tab_results, tab_records = st.tabs('''
if old not in text:
    # the tabs are created with a list
    marker = '["Overview"'
    assert 'st.tabs(' in text
    old_line_start = text.index("st.tabs(", text.index("tab_overview") - 400)
print("editor moved")
io.open(path, "w", encoding="utf-8").write(text)
ast.parse(text)
