# -*- coding: utf-8 -*-
"""Run the pages headlessly with streamlit.testing.v1.AppTest.

AppTest.from_function re-executes the function source in a fresh module namespace, so each
wrapper below imports views at run time and the page functions keep executing in views' globals.
Record folders are redirected to a temporary directory through DESLAB_DATA_DIR.
"""
import os
import sys
import tempfile
import unittest
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from streamlit.testing.v1 import AppTest  # noqa: E402

import auth  # noqa: E402

TIMEOUT = 120
SAMPLE_RUNS = "Sample: my DES runs (3 conditions, n=1)"


def page_calculator():
    import views
    views.calculator()


def page_results():
    import views
    views.results()


def page_guide():
    import views
    views.guide()


def run(page, user="Chuanyu"):
    at = AppTest.from_function(page, default_timeout=TIMEOUT)
    if user:
        at.session_state[auth.SESSION_KEY] = user
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
        self.assertEqual(at.title[0].value, "DES Recipe Calculator")
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
        at.radio[0].set_value(SAMPLE_RUNS).run()
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
        at.radio[0].set_value("Fictitious demo (9 rows)").run()
        self.assertEqual(errors(at), [])
        summary = at.dataframe[-1].value
        self.assertEqual(list(summary["n"]), [3, 3, 3])
        for sd in summary["sd"]:
            self.assertAlmostEqual(sd, 0.05)

    def test_results_page_starts_empty_for_a_new_user(self):
        at = run(page_results)
        self.assertEqual(errors(at), [])
        self.assertEqual(at.radio[0].value, "My saved data", "saved data should be the default source")
        self.assertIn("Import the 3 recorded runs into my records", [b.label for b in at.button])

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
        self.assertIn("Import the 3 recorded runs into my records", [b.label for b in other.button])

    # ----------------------------------------------------------------------- guide
    def test_guide_page_shows_account_tools(self):
        at = run(page_guide)
        self.assertEqual(errors(at), [])
        self.assertEqual(at.title[0].value, "How to use")
        markup = " ".join(str(m.value) for m in at.markdown)
        self.assertIn("Signed in as", markup)
        self.assertIn("Chuanyu", markup)
        self.assertIn("Download my experiment data CSV", [b.label for b in at.download_button])
        self.assertIn("Change password", [b.label for b in at.button])
        self.assertIn("Add teammate", [b.label for b in at.button])

    # -------------------------------------------------------------------- entrance
    def test_entry_page_branding_and_intro_once(self):
        at = AppTest.from_file(str(ROOT / "Hello.py"), default_timeout=TIMEOUT)
        at.session_state[auth.SESSION_KEY] = "Chuanyu"
        at.run()
        self.assertEqual(errors(at), [])
        markup = "\n".join(str(m.value) for m in at.markdown)
        self.assertIn('id="dsh-splash"', markup, "the A*STAR intro should be injected on the first run")
        self.assertIn('<img src="app/static/astar_logo.png"', markup)
        at.run()  # a rerun in the same session must not replay the intro
        self.assertNotIn('id="dsh-splash"', "\n".join(str(m.value) for m in at.markdown))

    def test_login_gate_blocks_the_app_and_accepts_the_seeded_password(self):
        at = AppTest.from_file(str(ROOT / "Hello.py"), default_timeout=TIMEOUT)
        at.run()
        self.assertEqual(errors(at), [])
        self.assertEqual([t.value for t in at.title], [], "no page title before signing in")
        self.assertEqual(len(at.text_input), 2, "username + password fields")

        at.text_input[0].set_value("Thena")
        at.text_input[1].set_value("not-the-password")
        at.button[0].click().run()
        self.assertTrue(at.error, "a wrong password must be rejected")
        self.assertIsNone(session_user(at))

        at.text_input[0].set_value("Thena")
        at.text_input[1].set_value(auth.DEFAULT_PASSWORD)
        at.button[0].click().run()
        self.assertEqual(session_user(at), "Thena")
        self.assertEqual(at.title[0].value, "DES Recipe Calculator")


if __name__ == "__main__":
    unittest.main(verbosity=2)
