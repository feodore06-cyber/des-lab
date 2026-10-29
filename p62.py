import io

path = r"C:\Users\User\Documents\Codex\2026-10-14\des-repository-fork-ai\outputs\des-lab\Hello.py"
text = io.open(path, encoding="utf-8").read()

start = text.index("def _gate(view):")
tail = '''def _gate(view):
    """Every page keeps its URL in every state; signed out it shows the sign-in form instead."""

    def run():
        if auth.current_user():
            view()
        else:
            auth.login_form(LOGO_URL)

    return run


def _front():
    """Signed out: the public page, or the form itself once somebody clicks "Start an experiment"."""
    if auth.current_user():
        views.workspace()
        return
    if st.query_params.get("view") == "signin" or st.session_state.get("show_signin"):
        if st.button(t("land.back"), key="back_to_landing"):
            st.session_state["show_signin"] = False
            st.query_params.clear()
            st.rerun()
        auth.login_form(LOGO_URL)
        return
    landing.landing(lambda: pd.read_csv(SAMPLE_CSV))


PAGES = {
    "experiments": st.Page(_front, title=t("nav.experiments"), default=True),
    "results": st.Page(_gate(views.results), title=t("nav.results"), url_path="results"),
    "calculator": st.Page(_gate(views.calculator), title=t("app.page_calc"), url_path="calculator"),
    "papers": st.Page(_gate(views.library), title=t("nav.papers"), url_path="papers"),
    "compare": st.Page(_gate(views.compare_page), title=t("nav.compare"), url_path="compare"),
    "profile": st.Page(_gate(views.guide), title=t("nav.profile"), url_path="guide"),
    "feedback": st.Page(_gate(views.feedback), title=t("app.page_feedback"), url_path="feedback"),
}

page = st.navigation(list(PAGES.values()), position="hidden")

if user:
    bar = st.columns([2.2, 1, 1, 1, 1, 1, 1, 1.4], vertical_alignment="center", gap="small")
    bar[0].markdown('<div class="bm-wordmark">BioMat Lab</div>', unsafe_allow_html=True)
    for column, key in zip(bar[1:6], ("experiments", "results", "calculator", "papers", "compare")):
        with column:
            st.page_link(PAGES[key], label=t(PAGES[key].title) if False else
                         {"experiments": t("nav.experiments"), "results": t("nav.results"),
                          "calculator": t("app.page_calc"), "papers": t("nav.papers"),
                          "compare": t("nav.compare")}[key])
    with bar[6]:
        st.page_link(PAGES["profile"], label=t("nav.profile"))
    with bar[7]:
        if st.button(t("app.logout"), key="logout", use_container_width=True):
            auth.logout()
            st.query_params.clear()
            st.rerun()

    if auth.hosted_mode() and not store.enabled():
        st.warning(t("app.hosted_warning"))

page.run()

if user:
    st.caption(t("app.sidebar_signed_in", user=user) + " · "
               + (t("app.sidebar_db") if store.enabled() else t("app.sidebar_records", user=user)))
'''

text = text[:start] + tail
io.open(path, "w", encoding="utf-8").write(text)
import ast
ast.parse(text)
print(text[-1800:])
