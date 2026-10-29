import io

path = r"C:\Users\User\Documents\Codex\2026-10-14\des-repository-fork-ai\outputs\des-lab\Hello.py"
text = io.open(path, encoding="utf-8").read()

# the wordmark and hero styles for the public page, plus status chips
old = '''  /* ---------- cards ---------- */'''
new = '''  /* ---------- public page ---------- */
  .bm-wordmark { font: 600 1.15rem/1.2 Georgia, "Times New Roman", serif; color: #0B1F4B;
                 letter-spacing: -0.01em; padding-top: .35rem; }
  .bm-hero { margin: 4.5rem 0 2.2rem; max-width: 46rem; }
  .bm-hero-title { font: 600 2.85rem/1.15 Georgia, "Times New Roman", serif !important;
                   letter-spacing: -0.025em !important; color: #0B1F4B; margin: 0 0 .9rem 0; }
  .bm-hero-sub { font: 400 1.12rem/1.6 system-ui, "Segoe UI", sans-serif; color: #55637D;
                 margin: 0; }
  .bm-positioning { font: 400 .98rem/1.6 system-ui, "Segoe UI", sans-serif; color: #33415C;
                    max-width: 44rem; }

  /* ---------- cards ---------- */'''
assert old in text
text = text.replace(old, new, 1)

# navigation: the app keeps every page, but the chrome is ours
old = '''page = st.navigation(
    [
        st.Page(_gate(views.calculator), title=t("app.page_calc"), default=True),
        st.Page(_gate(views.results), title=t("app.page_results"), url_path="results"),
        st.Page(_gate(views.library), title=t("app.page_library"), url_path="papers"),
        st.Page(_gate(views.compare_page), title=t("app.page_compare"), url_path="compare"),
        st.Page(_gate(views.feedback), title=t("app.page_feedback"), url_path="feedback"),
        st.Page(_gate(views.guide), title=t("app.page_guide"), url_path="guide"),
    ],
    # signed out the sidebar is hidden entirely, so a stranger cannot read the app structure
    position="sidebar" if user else "hidden",
)'''

new = '''PUBLIC_VIEW = st.query_params.get("view", "")


def _front():
    """Signed out: the public page. With ?view=signin (or after signing out) the form itself."""
    if auth.current_user():
        workspace_home()
        return
    if PUBLIC_VIEW == "signin" or st.session_state.get("show_signin"):
        if st.button("← " + t("land.signin"), key="back_to_landing"):
            st.session_state["show_signin"] = False
            st.query_params.clear()
            st.rerun()
        auth.login_form(LOGO_URL)
        return
    landing.landing(lambda: pd.read_csv(SAMPLE_CSV))


def workspace_home():
    views.workspace()


page = st.navigation(
    [
        st.Page(_front, title=t("nav.experiments"), default=True),
        st.Page(_gate(views.results), title=t("nav.results"), url_path="results"),
        st.Page(_gate(views.library), title=t("nav.papers"), url_path="papers"),
        st.Page(_gate(views.compare_page), title=t("nav.compare"), url_path="compare"),
        st.Page(_gate(views.guide), title=t("nav.profile"), url_path="guide"),
        st.Page(_gate(views.calculator), title=t("app.page_calc"), url_path="calculator"),
    ],
    # the navigation itself is drawn by hand below (or hidden entirely when signed out)
    position="hidden",
)

if user:
    bar = st.columns([2, 1, 1, 1, 1, 1], vertical_alignment="center")
    bar[0].markdown('<div class="bm-wordmark">BioMat Lab</div>', unsafe_allow_html=True)
    with bar[1]:
        st.page_link("Hello.py", label=t("nav.experiments"))
    with bar[2]:
        st.page_link("views/results.py" if False else "Hello.py", label="")
    with bar[5]:
        if st.button(t("app.logout"), key="logout", use_container_width=True):
            auth.logout()
            st.query_params.clear()
            st.rerun()'''

assert old in text
text = text.replace(old, new, 1)

io.open(path, "w", encoding="utf-8").write(text)
import ast
ast.parse(text)
print("Hello: public front page and hidden navigation")
