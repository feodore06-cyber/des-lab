# -*- coding: utf-8 -*-
"""Click-through tests: the flows a person actually performs, in the order they perform them.

Every crash reported from the deployed app was a *click* away, not a unit-level problem: a page switch
that resolves only for file pages, and a widget key written after the widget existed. These tests press
the buttons and fail on any Streamlit exception.
"""
import os

os.environ["DESLAB_STORAGE"] = "file"  # tests must never touch a real database
os.environ["DESLAB_MAIL_DISABLE"] = "1"  # tests must never send mail

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


def fresh_at(user: str = "Chuanyu") -> AppTest:
    at = AppTest.from_file(str(ROOT / "Hello.py"), default_timeout=TIMEOUT)
    at.session_state["show_signin"] = True
    at.session_state[auth.SESSION_KEY] = user
    at.run()
    return at


def press(at: AppTest, label: str) -> AppTest:
    matches = [button for button in at.button if button.label == label]
    assert matches, f"no button labelled {label!r}; have {[b.label for b in at.button]}"
    matches[0].click()
    at.run()
    return at


def exceptions(at: AppTest) -> list:
    return [f"{type(e).__name__}: {str(e.value)[:160]}" for e in at.exception]


class PublicPageTests(unittest.TestCase):
    """Nothing that belongs to a record may appear before somebody signs in."""

    def test_the_public_page_shows_no_stored_data(self):
        os.environ["DESLAB_DATA_DIR"] = tempfile.mkdtemp()
        auth.ensure_store()
        auth.save_results("Chuanyu", pd.DataFrame([
            {"sample_id": "EXP-SECRET-1", "formulation": "ChCl:GA 1:2", "project": "wood",
             "lignin_yield_pct": 4.3219, "biomass_g": 2.88, "lignin_mg": 56.0,
             "recorded_at": "2026-10-30 09:00"}]), append=False)

        at = AppTest.from_file(str(ROOT / "Hello.py"), default_timeout=TIMEOUT)
        at.run()
        self.assertEqual(exceptions(at), [])
        visible = []
        for collection in (at.markdown, at.caption, at.text, at.dataframe, at.metric):
            for item in collection:
                visible.append(str(getattr(item, "value", "")))
                visible.append(str(getattr(item, "label", "")))
        blob = " ".join(visible)
        self.assertIn("Make experimental work clearer", blob)
        self.assertNotIn("EXP-SECRET-1", blob, "a saved sample ID must never reach the public page")
        self.assertNotIn("4.3219", blob, "a stored yield must never reach the public page")
        self.assertNotIn("ChCl:GA 1:2", blob, "a stored formulation must never reach the public page")


class NavigationTests(unittest.TestCase):
    """A button that opens the comparison must never look dead."""

    def setUp(self):
        os.environ["DESLAB_DATA_DIR"] = tempfile.mkdtemp()
        auth.ensure_store()
        auth.save_results("Chuanyu", pd.DataFrame([
            {"sample_id": "EXP-01", "project": "General", "lignin_yield_pct": 1.9,
             "molar_ratio": 2.0, "temperature_C": 80, "time_min": 60}]), append=False)

    def _papers_page(self):
        import papers

        def fake_search(query, limit=12, since=None, min_citations=0, sort="relevant"):
            return [{"title": "A DES lignin paper", "year": 2024, "venue": "Journal",
                     "authors": "A. Author", "citations": 12, "doi": "10.1/x",
                     "url": "https://doi.org/10.1/x",
                     "abstract": "Lignin yield reached 6.1 % at 90 C for 120 min, ratio 1:2.",
                     "score": 1.0}]

        papers.search = fake_search

        def entry():
            import views

            views.library()

        at = AppTest.from_function(entry, default_timeout=TIMEOUT)
        at.session_state[auth.SESSION_KEY] = "Chuanyu"
        at.run()
        return at

    def test_the_button_opens_the_comparison_rather_than_doing_nothing(self):
        at = self._papers_page()
        self.assertEqual(exceptions(at), [])
        fields = [item for item in at.text_input if item.label == "Topic, title or author"]
        self.assertTrue(fields, f"no query field on the paper screen: {[f.label for f in at.text_input]}")
        fields[0].set_value("des lignin").run()
        press(at, "Find papers")
        self.assertEqual(exceptions(at), [])
        self.assertIn("Compare with my data", [button.label for button in at.button])
        press(at, "Compare with my data")
        self.assertEqual(exceptions(at), [])
        markup = " ".join(str(item.value) for item in at.markdown)
        self.assertIn("Compare with a paper", markup,
                      "pressing the button must open the comparison screen")


class WorkspaceFlows(unittest.TestCase):
    def setUp(self):
        os.environ["DESLAB_DATA_DIR"] = tempfile.mkdtemp()
        try:
            import streamlit as st

            st.cache_data.clear()
        except Exception:
            pass
        auth.ensure_store()
        auth.save_results("Chuanyu", pd.DataFrame([
            {"sample_id": "EXP-01", "formulation": "ChCl:Glyoxylic acid 1:2", "project": "wood",
             "des_hba": "ChCl", "des_hbd": "Glyoxylic acid", "molar_ratio": 2.0,
             "purity_wt_pct": 98.0, "water_wt_pct": 0.0, "biomass_g": 2.88, "lignin_mg": 56.0,
             "lignin_yield_pct": 1.9444, "temperature_C": 80.0, "time_min": 60.0, "replicate": 1,
             "recorded_at": "2026-10-30 09:00"},
            {"sample_id": "EXP-02", "formulation": "ChCl:Glyoxylic acid 1:1", "project": "straw",
             "des_hba": "ChCl", "des_hbd": "Glyoxylic acid", "molar_ratio": 1.0,
             "purity_wt_pct": 98.0, "water_wt_pct": 5.0, "biomass_g": 2.0, "lignin_mg": 40.0,
             "lignin_yield_pct": 2.0, "temperature_C": 90.0, "time_min": 120.0, "replicate": 1,
             "recorded_at": "2026-10-30 10:00"},
        ]), append=False)

    def test_the_workspace_renders_the_experiments(self):
        at = fresh_at()
        self.assertEqual(exceptions(at), [])
        markup = " ".join(str(m.value) for m in at.markdown)
        self.assertIn("Good to see you, Chuanyu", markup)

    def test_new_project_opens_a_name_form_without_leaving_the_page(self):
        at = fresh_at()
        at = press(at, "New project")
        self.assertEqual(exceptions(at), [], "the button must not raise StreamlitPageNotFoundError")
        labels = [field.label for field in at.text_input]
        self.assertIn("Project name", labels, "a new project starts with its name")

    def test_creating_a_project_does_not_instantiate_a_widget_twice(self):
        at = fresh_at()
        at = press(at, "New project")
        self.assertEqual(exceptions(at), [])
        fields = [field for field in at.text_input if field.label == "Project name"]
        self.assertTrue(fields, f"no project-name field; have {[f.label for f in at.text_input]}")
        fields[0].set_value("hot press").run()
        at = press(at, "Create project")
        self.assertEqual(exceptions(at), [], "a widget key must not be written after creation")
        self.assertIn("hot press", auth.list_projects("Chuanyu"),
                      "the project must exist after the click")

    def test_deleting_a_project_warns_before_it_removes_anything(self):
        """The screen must name what is at stake and touch nothing until it is confirmed.

        The cascade itself is verified in tests/test_projects.py, where the storage can be inspected
        directly; this test only covers what the person sees.
        """
        at = fresh_at()
        before = len(auth.load_results("Chuanyu"))
        at.button(key="del_wood").click()
        at.run()
        self.assertEqual(exceptions(at), [])
        warnings = " ".join(str(item.value) for item in at.warning)
        self.assertIn("cannot be undone", warnings, "the warning must say what is lost")
        self.assertIn("wood", warnings, "the warning must name the project")
        self.assertEqual(len(auth.load_results("Chuanyu")), before,
                         "nothing may be deleted before the confirmation")
        self.assertIn("Keep it", [button.label for button in at.button])

    def test_opening_an_experiment_shows_its_own_panel(self):
        at = fresh_at()
        at = press(at, "Open project")
        self.assertEqual(exceptions(at), [])
        markup = " ".join(str(m.value) for m in at.markdown)
        self.assertTrue("wood" in markup or "straw" in markup, "the experiment name should be shown")

    def test_the_experiment_report_has_the_five_tabs(self):
        at = fresh_at()
        at = press(at, "Open project")
        self.assertEqual(exceptions(at), [])
        labels = [tab.label for tab in at.tabs]
        for wanted in ("Overview", "Formulation", "Process", "Results", "Records"):
            self.assertIn(wanted, labels, f"missing tab {wanted}: {labels}")

    def test_the_report_shows_its_traceability_line_and_exports(self):
        at = fresh_at()
        at = press(at, "Open project")
        self.assertEqual(exceptions(at), [])
        captions = " ".join(str(item.value) for item in at.caption)
        self.assertIn("Last updated", captions, "every report must say when and by whom")
        downloads = [button.label for button in at.download_button]
        self.assertTrue(any("Excel" in label for label in downloads), downloads)

    def setUp(self):
        os.environ["DESLAB_DATA_DIR"] = tempfile.mkdtemp()
        try:
            import streamlit as st

            st.cache_data.clear()
        except Exception:
            pass
        auth.ensure_store()
        auth.save_results("Chuanyu", pd.DataFrame([
            {"sample_id": "EXP-01", "formulation": "ChCl:GA 1:2", "project": "wood",
             "molar_ratio": 2.0, "purity_wt_pct": 98.0, "water_wt_pct": 0.0, "biomass_g": 2.88,
             "lignin_mg": 56.0, "lignin_yield_pct": 1.9444, "temperature_C": 80.0,
             "time_min": 60.0, "replicate": 1, "recorded_at": "2026-10-30 09:00"},
            {"sample_id": "EXP-02", "formulation": "ChCl:GA 1:1", "project": "wood",
             "molar_ratio": 1.0, "purity_wt_pct": 98.0, "water_wt_pct": 5.0, "biomass_g": 2.0,
             "lignin_mg": 40.0, "lignin_yield_pct": 2.0, "temperature_C": 90.0,
             "time_min": 120.0, "replicate": 1, "recorded_at": "2026-10-30 10:00"},
        ]), append=False)

    def _page(self):
        def compare_entry():
            import views

            views.compare_page()

        at = AppTest.from_function(compare_entry, default_timeout=TIMEOUT)
        at.session_state[auth.SESSION_KEY] = "Chuanyu"
        at.run()
        return at

    def test_two_unrelated_runs_are_flagged_before_the_numbers(self):
        def compare_entry():
            import views

            views.compare_page()

        at = AppTest.from_function(compare_entry, default_timeout=TIMEOUT)
        at.session_state[auth.SESSION_KEY] = "Chuanyu"
        at.run()
        modes = [item for item in at.radio if item.label == "What to compare"]
        modes[0].set_value("Two of my own runs").run()
        press(at, "Compare")
        warnings = " ".join(str(item.value) for item in at.warning)
        self.assertTrue(warnings, "two runs that differ in ratio and water must be flagged")

    def test_two_of_my_own_runs_can_be_compared(self):
        at = self._page()
        self.assertEqual(exceptions(at), [])
        options = [choice for choice in at.radio if choice.label == "What to compare"]
        self.assertTrue(options, "the comparison needs a mode switch")
        options[0].set_value("Two of my own runs").run()
        self.assertEqual(exceptions(at), [])
        at = press(at, "Compare")
        self.assertEqual(exceptions(at), [])
        headings = " ".join(str(item.value) for item in at.subheader)
        self.assertIn("Possible explanations", headings)
        metric_labels = [str(item.label) for item in at.metric]
        self.assertTrue(any(label in ("EXP-01", "EXP-02") for label in metric_labels),
                        f"the comparison names the two runs it compares; metrics were {metric_labels}")
        body = " ".join(str(m.value) for m in at.markdown)
        self.assertNotIn("The paper", body, "no paper is involved in this mode")


if __name__ == "__main__":
    unittest.main(verbosity=2)
