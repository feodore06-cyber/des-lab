# -*- coding: utf-8 -*-
"""Run the pages headlessly with streamlit.testing.v1.AppTest.

AppTest.from_function re-executes the function source in a fresh module namespace, so each
wrapper below imports views at run time and the page functions keep executing in views' globals.
Record folders are redirected to a temporary directory through DESLAB_DATA_DIR.
"""
import os
import sys

os.environ["DESLAB_STORAGE"] = "file"
os.environ["DESLAB_MAIL_DISABLE"] = "1"  # tests must never send mail  # tests must never touch a real database
import tempfile
import unittest
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from streamlit.testing.v1 import AppTest  # noqa: E402

import auth  # noqa: E402
import i18n  # noqa: E402

TIMEOUT = 120
SAMPLE_RUNS = "Sample: my DES runs (3 conditions, n=1)"


def page_calculator():
    import views
    views.calculator()


def page_results():
    import views
    views.results()


def page_signup():
    import auth
    auth._signup_form()


def page_feedback():
    import views
    views.feedback()


def page_guide():
    import views
    views.guide()


def run(page, user="Chuanyu", lang=None):
    at = AppTest.from_function(page, default_timeout=TIMEOUT)
    if user:
        at.session_state[auth.SESSION_KEY] = user
    if lang:
        at.session_state[i18n.LANG_KEY] = lang
    at.run()
    return at


def open_signin(at):
    """The public page is the front door now; this clicks through to the form."""
    landing_text = " ".join(m.value for m in at.markdown)
    if "Sign in" in [button.label for button in at.button] and "Make experimental work clearer" in landing_text:
        press(at, "Start an experiment")
    return at


def press(at, label):
    """Click the first button with this label and rerun."""
    matches = [b for b in at.button if b.label == label]
    assert matches, f"no button labelled {label!r}, have {[b.label for b in at.button]}"
    matches[0].click()
    at.run()
    return at


def errors(at):
    return [str(e.value) for e in at.exception]


def session_user(at):
    try:
        return at.session_state[auth.SESSION_KEY]
    except KeyError:
        return None


class PageTests(unittest.TestCase):
    def setUp(self):
        # cached reads are process-global; start every test with none
        try:
            import streamlit as st

            st.cache_data.clear()
        except Exception:
            pass
        self.tmp = tempfile.TemporaryDirectory()
        os.environ[auth.DATA_DIR_ENV] = self.tmp.name
        auth.ensure_store()

    def tearDown(self):
        os.environ.pop(auth.DATA_DIR_ENV, None)
        self.tmp.cleanup()

    # ------------------------------------------------------------------ calculator
    def test_calculator_page_runs_and_balances(self):
        at = run(page_calculator)
        self.assertEqual(errors(at), [])
        self.assertEqual(at.title[0].value, "Recipe Calculator")
        metrics = [m.value for m in at.metric]
        # default 10 g active basis: ChCl 1 : glyoxylic acid 2, both 98 wt% solids, no separate water
        self.assertEqual(metrics[0], "10.2041 g")   # 4.9520 g ChCl + 5.2521 g glyoxylic acid
        self.assertEqual(metrics[1], "0.0000 g")    # solids only: the missing 2% is impurity, not water
        self.assertEqual(metrics[2], "0.00%")
        self.assertEqual(metrics[3], "2.04%")       # 1 / 0.98 - 1: extra reagent weighed for the assay
        self.assertIn("Download recipe CSV", [b.label for b in at.download_button])
        self.assertIn("Save this weighing list to my records", [b.label for b in at.button])

    def test_calculator_ideal_purity_makes_total_equal_target(self):
        at = run(page_calculator)
        at.toggle[0].set_value(True).run()
        self.assertEqual(errors(at), [])
        metrics = [m.value for m in at.metric]
        self.assertEqual(metrics[0], "10.0000 g")   # 100 wt%: total prepared mass == target mass
        self.assertEqual(metrics[3], "0.00%")
        notes = " ".join(str(s.value).replace("**", "") for s in at.success)
        self.assertIn("total prepared mass = target mass", notes)
        weighing = next(t.value for t in at.dataframe if "Reagent to weigh (g)" in t.value.columns)
        self.assertTrue((abs(weighing["Reagent to weigh (g)"] - weighing["Active component (g)"]) < 1e-9).all())

    def test_calculator_saves_recipe_into_the_users_folder(self):
        at = run(page_calculator)
        at.button(key="save_recipe").click().run()
        self.assertEqual(errors(at), [])
        recipes = list((auth.user_dir("Chuanyu") / "recipes").glob("recipe_*.csv"))
        self.assertEqual(len(recipes), 1)
        self.assertEqual(list((auth.user_dir("Thena") / "recipes").glob("*")), [])

    # --------------------------------------------------------------------- results
    def test_results_page_sample_runs(self):
        at = run(page_results)
        self.assertEqual(errors(at), [])
        at.radio(key="source").set_value(SAMPLE_RUNS).run()
        self.assertEqual(errors(at), [])
        summary = at.dataframe[-1].value
        self.assertEqual(list(summary["n"]), [1, 1, 1])
        self.assertTrue(summary["sd"].isna().all(), "n=1 must leave sd empty")
        self.assertEqual(list(summary["formulation"]), ["ChCl-GA 1:1", "ChCl-GA 1:2", "ChCl-GA 2:1"])
        for got, want in zip(summary["mean"], [1.13, 1.94, 0.78]):
            self.assertAlmostEqual(got, want, delta=0.005)
        labels = [b.label for b in at.download_button]
        self.assertIn("Download PNG · 300 dpi", labels)
        self.assertIn("Download SVG · vector", labels)

    def test_results_page_demo_has_error_bars(self):
        at = run(page_results)
        at.radio(key="source").set_value("Fictitious demo (9 rows)").run()
        self.assertEqual(errors(at), [])
        summary = at.dataframe[-1].value
        self.assertEqual(list(summary["n"]), [3, 3, 3])
        for sd in summary["sd"]:
            self.assertAlmostEqual(sd, 0.05)

    def test_results_page_starts_empty_for_a_new_user(self):
        at = run(page_results)
        self.assertEqual(errors(at), [])
        self.assertEqual(at.radio(key="source").value, "My saved data", "saved data should be the default source")
        self.assertIn("Load the 3 example runs (Chuanyu's records) into my folder", [b.label for b in at.button])

    def test_results_page_reads_only_the_signed_in_users_records(self):
        rows = pd.DataFrame({"formulation": ["ChCl-GA 1:2"] * 3, "replicate": [1, 2, 3],
                             "biomass_g": [2.88] * 3, "lignin_mg": [56.0, 55.0, 57.0]})
        auth.save_results("Chuanyu", rows, append=False)
        at = run(page_results, user="Chuanyu")
        self.assertEqual(errors(at), [])
        self.assertEqual(at.metric[0].value, "3")
        # Thena has no file: her page must not show Chuanyu's rows
        other = run(page_results, user="Thena")
        self.assertEqual(errors(other), [])
        self.assertIn("Load the 3 example runs (Chuanyu's records) into my folder", [b.label for b in other.button])

    # ----------------------------------------------------------------------- guide
    def test_calculator_can_add_a_reagent_by_cas_number(self):
        import chem

        record = {"cid": 6209, "name": "Choline Chloride", "formula": "C5H14ClNO", "mw": 139.62,
                  "iupac": "", "smiles": "", "hbd": 1.0, "hba": 2.0, "xlogp": None, "tpsa": None,
                  "cas": "67-48-1", "url": "https://pubchem.ncbi.nlm.nih.gov/compound/6209"}
        saved = (chem.find_cids, chem.compound)
        chem.find_cids = lambda term: [6209] if term.replace(" ", "") == "67-48-1" else []
        chem.compound = lambda cid: record
        try:
            at = run(page_calculator)
            at.text_input(key="calc_find").set_value("67-48-1").run()
            at.button(key="calc_find_add").click().run()
            self.assertEqual(errors(at), [])
            rows = at.session_state["recipe_rows"]
            self.assertEqual(rows[-1]["name"], "Choline Chloride")
            self.assertAlmostEqual(rows[-1]["mw"], 139.62)
            # an unknown CAS must not add anything
            before = len(rows)
            chem.find_cids = lambda term: []
            at.text_input(key="calc_find").set_value("99-99-9").run()
            at.button(key="calc_find_add").click().run()
            self.assertEqual(len(at.session_state["recipe_rows"]), before)
            self.assertTrue(at.warning)
        finally:
            chem.find_cids, chem.compound = saved

    def test_calculator_shows_the_pubchem_details_of_an_added_reagent(self):
        import chem

        record = {"cid": 6209, "name": "Choline Chloride", "formula": "C5H14ClNO", "mw": 139.62,
                  "iupac": "2-hydroxyethyl(trimethyl)azanium;chloride", "smiles": "C[N+](C)(C)CCO.[Cl-]",
                  "hbd": 1.0, "hba": 2.0, "xlogp": -5.9, "tpsa": 20.2, "cas": "67-48-1",
                  "url": "https://pubchem.ncbi.nlm.nih.gov/compound/6209"}
        saved = (chem.find_cids, chem.compound)
        chem.find_cids = lambda term: [6209]
        chem.compound = lambda cid: record
        try:
            at = run(page_calculator)
            at.text_input(key="calc_find").set_value("67-48-1").run()
            at.button(key="calc_find_add").click().run()
            self.assertEqual(errors(at), [])
            values = [m.value for m in at.metric]
            self.assertIn("139.620 g/mol", values)
            self.assertIn("C5H14ClNO", values)
            self.assertIn("67-48-1", values)
            self.assertTrue(at.code, "the SMILES should be shown")
            labels = " ".join(str(e.label) for e in at.expander)
            self.assertIn("Choline Chloride", labels)
        finally:
            chem.find_cids, chem.compound = saved

    def test_settings_are_read_from_streamlit_secrets_not_only_env_vars(self):
        # Streamlit Cloud delivers secrets through st.secrets and never exports them as env vars
        auth.users_path().unlink(missing_ok=True)
        at = AppTest.from_file(str(ROOT / "Hello.py"), default_timeout=TIMEOUT)
        at.session_state["show_signin"] = True
        at.secrets["DESLAB_HOSTED"] = "1"
        at.secrets["DESLAB_INVITE_CODE"] = "secret-code-42"
        at.run()
        self.assertEqual(errors(at), [])
        press(at, "Create a new account")
        self.assertEqual(len(at.text_input), 4, "username + password + repeat + invite")
        self.assertIn("Invite code", [f.label for f in at.text_input])

    def test_a_fresh_hosted_deployment_still_offers_sign_up(self):
        # no users.json, hosted mode: the first account must still be creatable
        os.environ[auth.HOSTED_ENV] = "1"
        os.environ[auth.INVITE_ENV] = "code-123"
        auth.users_path().unlink(missing_ok=True)  # a brand new container has no users.json
        try:
            at = AppTest.from_file(str(ROOT / "Hello.py"), default_timeout=TIMEOUT)
            at.session_state["show_signin"] = True
            at.run()
            self.assertEqual(errors(at), [])
            self.assertTrue(any("No accounts are configured" in str(e.value) for e in at.error))
            labels = [b.label for b in at.button]
            self.assertIn("Create a new account", labels, "the sign-up button must be reachable")
            press(at, "Create a new account")
            self.assertEqual(len(at.text_input), 4, "username + password + repeat + invite")
            at.text_input[0].set_value("wei@example.com")
            at.text_input[1].set_value("wei-password")
            at.text_input[2].set_value("wei-password")
            at.text_input[3].set_value("code-123")
            press(at, "Create my account")
            self.assertEqual(errors(at), [])
            self.assertEqual(session_user(at), "wei@example.com", "the first account is created and signed in")
        finally:
            os.environ.pop(auth.HOSTED_ENV, None)
            os.environ.pop(auth.INVITE_ENV, None)

    def test_admins_see_the_account_list_and_others_do_not(self):
        admin = run(page_guide, user="Chuanyu")
        self.assertEqual(errors(admin), [])
        self.assertIn("Team", [s.value for s in admin.subheader])
        self.assertIn("New in 7 days", [m.label for m in admin.metric])
        usernames = set(str(v) for v in admin.dataframe[0].value.get("username", []))

        other = run(page_guide, user="Thena")
        self.assertEqual(errors(other), [])
        self.assertNotIn("New in 7 days", [m.label for m in other.metric])
        captions = " ".join(str(c.value) for c in other.caption)
        self.assertIn("Interns cannot manage accounts", captions)
        self.assertTrue(usernames, "the admin table should list the existing accounts")

    def test_a_reset_link_lets_the_user_set_a_new_password(self):
        auth.ensure_store()
        token = auth.create_reset_token("Thena")
        at = AppTest.from_file(str(ROOT / "Hello.py"), default_timeout=TIMEOUT)
        at.session_state["show_signin"] = True
        at.query_params["reset_token"] = token
        at.run()
        self.assertEqual(errors(at), [])
        self.assertIn("Reset password", " ".join(str(m.value) for m in at.markdown))
        at.text_input[0].set_value("a-fresh-password").run()
        at.text_input[1].set_value("a-fresh-password").run()
        press(at, "Set new password")
        self.assertEqual(errors(at), [])
        self.assertTrue(auth.verify("Thena", "a-fresh-password"))

    def test_an_admin_can_generate_a_reset_link_for_a_teammate(self):
        at = run(page_guide, user="Chuanyu")
        self.assertEqual(errors(at), [])
        press(at, "Create a reset link")
        self.assertEqual(errors(at), [])
        self.assertTrue(at.code, "the link should be shown to the admin")
        self.assertIn("reset_token=", at.code[0].value)

    def test_an_idle_session_signs_itself_out(self):
        import time as _time

        at = AppTest.from_file(str(ROOT / "Hello.py"), default_timeout=TIMEOUT)
        at.session_state["show_signin"] = True
        at.session_state[auth.SESSION_KEY] = "Chuanyu"
        at.session_state[auth.SESSION_SEEN] = _time.time() - (auth.SESSION_TIMEOUT_H + 1) * 3600
        at.run()
        self.assertEqual(errors(at), [])
        self.assertEqual([t.value for t in at.title], [], "an expired session sees the sign-in page")

    def test_signup_sends_one_welcome_mail_to_the_new_address(self):
        import mailer

        calls = []
        original = mailer.send_welcome
        mailer.send_welcome = lambda to, name: calls.append((to, name)) or True
        try:
            at = AppTest.from_function(page_signup, default_timeout=TIMEOUT)
            at.run()
            at.text_input[0].set_value("new.person@example.com").run()
            at.text_input[1].set_value("a-good-password").run()
            at.text_input[2].set_value("a-good-password").run()
            press(at, "Create my account")
            self.assertEqual(calls, [("new.person@example.com", "new.person")])
            self.assertTrue(auth.verify("new.person@example.com", "a-good-password"))
        finally:
            mailer.send_welcome = original

    def test_results_page_works_when_the_rows_come_from_the_database(self):
        # On a host there is no local CSV: the page must serialise the DataFrame instead of reading
        # a file path that only exists on a laptop (this was a real crash).
        import store as store_module

        rows = pd.DataFrame([{"formulation": "Chl-GA 1:2", "biomass_g": 2.88,
                              "lignin_mg": 56.0, "lignin_yield_pct": 1.94}])
        saved_load, saved_enabled, saved_path = auth.load_results, store_module.enabled, auth.results_path
        auth.load_results = lambda user: rows
        store_module.enabled = lambda: True
        auth.results_path = lambda user: (_ for _ in ()).throw(AssertionError("must not read a local file"))
        try:
            at = AppTest.from_function(page_results, default_timeout=TIMEOUT)
            at.session_state[auth.SESSION_KEY] = "Chuanyu"
            at.run()
            self.assertEqual([str(e.value)[:120] for e in at.exception], [])
            self.assertTrue(at.dataframe, "the merged table should render")
        finally:
            auth.load_results, store_module.enabled, auth.results_path = saved_load, saved_enabled, saved_path

    def test_pressing_save_twice_does_not_store_the_run_twice(self):
        at = run(page_results)
        self.assertEqual(errors(at), [])
        at.text_input(key="run_sample").set_value("EXP-DUP").run()
        at.number_input(key="run_biomass").set_value(2.5).run()
        at.number_input(key="run_lignin").set_value(40.0).run()
        press(at, "Save this run")
        press(at, "Save this run")
        saved = auth.load_results("Chuanyu")
        self.assertEqual(len(saved), 1, "a double submit must not duplicate the row")
        self.assertTrue(any("already saved" in str(w.value) for w in at.warning))

    def test_a_run_can_be_recorded_by_hand(self):
        at = run(page_results)
        self.assertEqual(errors(at), [])
        at.text_input(key="run_sample").set_value("EXP-09").run()
        at.text_input(key="run_hba").set_value("ChCl").run()
        at.text_input(key="run_hbd").set_value("Glyoxylic acid").run()
        at.number_input(key="run_ratio").set_value(2.0).run()
        at.number_input(key="run_biomass").set_value(2.88).run()
        at.number_input(key="run_lignin").set_value(56.0).run()
        at.number_input(key="run_replicate").set_value(1).run()
        press(at, "Save this run")
        self.assertEqual(errors(at), [])
        saved = auth.load_results("Chuanyu")
        self.assertIsNotNone(saved)
        self.assertEqual(len(saved), 1)
        row = saved.iloc[0]
        self.assertEqual(row["sample_id"], "EXP-09")
        self.assertAlmostEqual(float(row["lignin_yield_pct"]), 1.9444, places=3)
        # the structured, machine-readable fields are the point of the record form
        self.assertEqual(row["des_hba"], "ChCl")
        self.assertEqual(row["des_hbd"], "Glyoxylic acid")
        self.assertAlmostEqual(float(row["molar_ratio"]), 2.0)
        self.assertAlmostEqual(float(row["purity_wt_pct"]), 98.0)
        self.assertEqual(row["formulation"], "ChCl:Glyoxylic acid 1:2")

    def test_the_records_tab_offers_save_and_a_guarded_delete(self):
        at = run(page_results)
        labels = [b.label for b in at.button]
        self.assertIn("Save the table", labels)
        self.assertIn("Delete all my rows", labels)
        delete = [b for b in at.button if b.label == "Delete all my rows"][0]
        self.assertTrue(delete.disabled, "the destructive button starts disabled")
        self.assertIn("Download my records (CSV)", [b.label for b in at.download_button])

    def test_quality_warning_names_groups_without_replicates(self):
        at = run(page_results)
        at.radio(key="source").set_value(SAMPLE_RUNS).run()
        self.assertEqual(errors(at), [])
        warnings = " ".join(str(w.value) for w in at.warning)
        self.assertIn("n=1", warnings)

    def test_creating_an_intern_requires_a_typed_password(self):
        at = run(page_guide, user="Chuanyu")
        self.assertEqual(errors(at), [])
        labels = [field.label for field in at.text_input]
        self.assertIn("Intern's email or username", labels)
        self.assertIn("Initial password", labels, "the password field must be there, and be required")

        def field(label):
            return [item for item in at.text_input if item.label == label][0]

        field("Intern's email or username").set_value("intern.test@example.com").run()
        press(at, "Create the account")
        self.assertNotIn("intern.test@example.com", auth.load_users(), "no password, no account")
        self.assertTrue(at.error, "the missing password must be reported")

        field("Initial password").set_value("123").run()
        press(at, "Create the account")
        self.assertNotIn("intern.test@example.com", auth.load_users(), "a 3-character password is refused")

        field("Initial password").set_value("intern-password-1").run()
        press(at, "Create the account")
        self.assertIn("intern.test@example.com", auth.load_users())
        self.assertTrue(auth.verify("intern.test@example.com", "intern-password-1"))

    def test_signed_in_users_get_a_welcome_line(self):
        at = AppTest.from_file(str(ROOT / "Hello.py"), default_timeout=TIMEOUT)
        at.run()
        # the front page is the public page: it explains the product before asking for a sign-in
        markup = " ".join(m.value for m in at.markdown)
        self.assertIn("Make experimental work clearer", markup)
        press(at, "Start an experiment")
        at.text_input[0].set_value("Chuanyu")
        at.text_input[1].set_value(auth.DEFAULT_PASSWORD)
        press(at, "Sign in")
        self.assertEqual(errors(at), [])
        markup = " ".join(m.value for m in at.markdown)
        self.assertIn("Good to see you, Chuanyu", markup)

    def test_feedback_form_stores_a_report_and_admins_see_the_inbox(self):
        import feedback as feedback_mod

        at = AppTest.from_function(page_feedback, default_timeout=TIMEOUT)
        at.session_state[auth.SESSION_KEY] = "Chuanyu"
        at.run()
        self.assertEqual(errors(at), [])

        at.text_area[0].set_value("the M_r field is confusing on the calculator page").run()
        press(at, "Send feedback")
        self.assertEqual(errors(at), [])
        frame = feedback_mod.load_all()
        self.assertIsNotNone(frame)
        self.assertEqual(len(frame), 1)
        self.assertEqual(frame.iloc[0]["user"], "Chuanyu")
        self.assertIn("M_r field", frame.iloc[0]["message"])
        # the admin sees the inbox
        self.assertIn("Inbox (admins only)", [s.value for s in at.subheader])

    def test_feedback_inbox_is_hidden_from_non_admins(self):
        import feedback as feedback_mod

        feedback_mod.add("Thena", "bug", "export button does nothing", "Results")
        at = AppTest.from_function(page_feedback, default_timeout=TIMEOUT)
        at.session_state[auth.SESSION_KEY] = "Thena"
        at.run()
        self.assertEqual(errors(at), [])
        self.assertNotIn("Inbox (admins only)", [s.value for s in at.subheader])
        self.assertIn("only the administrators", " ".join(str(c.value) for c in at.caption))

    def test_feedback_requires_a_message(self):
        at = AppTest.from_function(page_feedback, default_timeout=TIMEOUT)
        at.session_state[auth.SESSION_KEY] = "Chuanyu"
        at.run()
        press(at, "Send feedback")
        self.assertTrue(at.warning, "an empty report should warn")

    def test_guide_page_shows_account_tools(self):
        at = run(page_guide)
        self.assertEqual(errors(at), [])
        self.assertEqual(at.title[0].value, "How to use")
        markup = " ".join(str(m.value) for m in at.markdown)
        self.assertIn("Signed in as", markup)
        self.assertIn("Chuanyu", markup)
        self.assertIn("Download my experiment data CSV", [b.label for b in at.download_button])
        self.assertIn("Change password", [b.label for b in at.button])
        self.assertIn("Create the account", [b.label for b in at.button])

    # -------------------------------------------------------------------- entrance
    def test_entry_page_branding_and_intro_once(self):
        at = AppTest.from_file(str(ROOT / "Hello.py"), default_timeout=TIMEOUT)
        at.session_state["show_signin"] = True
        at.session_state[auth.SESSION_KEY] = "Chuanyu"
        at.run()
        self.assertEqual(errors(at), [])
        markup = "\n".join(str(m.value) for m in at.markdown)
        self.assertIn('id="dsh-splash"', markup, "the intro should be injected on the first run")
        # institutional branding is opt-in: by default the splash shows our own mark
        self.assertIn("app/static/biomat_mark.png", markup)
        self.assertNotIn("astar_logo.png", markup,
                         "the A*STAR lockup must not be used without an explicit opt-in")
        at.run()  # a rerun in the same session must not replay the intro
        self.assertNotIn('id="dsh-splash"', "\n".join(str(m.value) for m in at.markdown))

    def test_signup_can_require_an_invite_code(self):
        os.environ[auth.INVITE_ENV] = "lab-code-2026"
        try:
            at = AppTest.from_file(str(ROOT / "Hello.py"), default_timeout=TIMEOUT)
            at.session_state["show_signin"] = True
            at.run()
            press(at, "Create a new account")
            self.assertEqual(len(at.text_input), 4, "username + password + repeat + invite")

            at.text_input[0].set_value("wei@example.com")
            at.text_input[1].set_value("wei-password")
            at.text_input[2].set_value("wei-password")
            at.text_input[3].set_value("wrong-code")
            press(at, "Create my account")
            self.assertTrue(at.error, "a wrong invite code must be refused")
            self.assertNotIn("wei@example.com", auth.load_users())

            at.text_input[3].set_value("lab-code-2026")
            press(at, "Create my account")
            self.assertEqual(session_user(at), "wei@example.com")
            self.assertIn("wei@example.com", auth.load_users())
        finally:
            os.environ.pop(auth.INVITE_ENV, None)

    def test_login_gate_blocks_the_app_and_accepts_the_seeded_password(self):
        at = AppTest.from_file(str(ROOT / "Hello.py"), default_timeout=TIMEOUT)
        at.session_state["show_signin"] = True
        at.run()
        self.assertEqual(errors(at), [])
        self.assertEqual([t.value for t in at.title], [], "no page title before signing in")
        self.assertEqual(len(at.text_input), 2, "username + password fields")
        # the form must not hint at a real account name
        for field in at.text_input:
            for name in ("Thena", "Chuanyu", "ChCl"):
                self.assertNotIn(name, str(getattr(field, "placeholder", "") or ""))
                self.assertNotIn(name, str(field.label or ""))

        # pressing Sign in with both fields empty explains what is missing
        self.assertIn("Create a new account", [b.label for b in at.button])
        press(at, "Sign in")
        self.assertTrue(at.warning, "empty fields should warn, not claim a wrong password")
        self.assertFalse(at.error)
        self.assertIsNone(session_user(at))

        at.text_input[0].set_value("Thena")
        at.text_input[1].set_value("not-the-password")
        press(at, "Sign in")
        self.assertTrue(at.error, "a wrong password must be rejected")
        self.assertIsNone(session_user(at))

        at.text_input[0].set_value("Thena")
        at.text_input[1].set_value(auth.DEFAULT_PASSWORD)
        press(at, "Sign in")
        self.assertEqual(session_user(at), "Thena")
        markup = " ".join(str(m.value) for m in at.markdown)
        self.assertIn("Good to see you, Thena", markup, "signing in lands on the workspace")

    def test_language_switch_translates_every_page(self):
        calc = run(page_calculator, lang="zh")
        self.assertEqual(errors(calc), [])
        self.assertEqual(calc.title[0].value, "配比计算")
        labels = [m.label for m in calc.metric]
        self.assertIn("配制总质量", labels)
        self.assertIn("比有效组分多称", labels)
        buttons = [b.label for b in calc.button]
        self.assertIn("把这张称量清单存进我的记录", buttons)
        self.assertIn("下载配方 CSV", [b.label for b in calc.download_button])

        res = run(page_results, lang="zh")
        self.assertEqual(errors(res), [])
        self.assertEqual(res.title[0].value, "实验结果与图表")
        self.assertEqual(res.radio(key="source").label, "数据来源")
        self.assertEqual(res.radio(key="source").value, "我保存的数据")

        guide = run(page_guide, lang="zh")
        self.assertEqual(errors(guide), [])
        self.assertEqual(guide.title[0].value, "使用说明")
        self.assertIn("团队", [s.value for s in guide.subheader])

    def test_language_switch_keeps_english_by_default(self):
        at = run(page_calculator)
        self.assertEqual(at.title[0].value, "Recipe Calculator")
        self.assertEqual(i18n.lang(), "en")

    def test_create_account_starts_with_an_empty_record_folder(self):
        at = AppTest.from_file(str(ROOT / "Hello.py"), default_timeout=TIMEOUT)
        at.session_state["show_signin"] = True
        at.run()
        self.assertEqual(errors(at), [])

        press(at, "Create a new account")
        self.assertEqual(errors(at), [])
        markup = chr(10).join(str(m.value) for m in at.markdown)
        self.assertIn("### Create account", markup)
        self.assertEqual(len(at.text_input), 3, "username + password + repeat")

        # mismatched passwords are refused
        at.text_input[0].set_value("wei@example.com")
        at.text_input[1].set_value("first-password")
        at.text_input[2].set_value("second-password")
        press(at, "Create my account")
        self.assertTrue(at.error)
        self.assertIsNone(session_user(at))
        self.assertNotIn("wei@example.com", auth.load_users())

        # a proper sign-up logs the new teammate in, with their own empty folder
        at.text_input[0].set_value("wei@example.com")
        at.text_input[1].set_value("wei-password")
        at.text_input[2].set_value("wei-password")
        press(at, "Create my account")
        self.assertEqual(errors(at), [])
        self.assertEqual(session_user(at), "wei@example.com")
        self.assertIn("Good to see you, wei", chr(10).join(str(m.value) for m in at.markdown))
        self.assertTrue(auth.user_dir("Wei").is_dir(), "record folder should exist immediately")
        self.assertIsNone(auth.load_results("Wei"), "a new account must start with no rows")
        self.assertIsNone(auth.load_results("Thena"), "and must not inherit anyone else's rows")


if __name__ == "__main__":
    unittest.main(verbosity=2)
