# -*- coding: utf-8 -*-
"""Run all three pages headlessly with streamlit.testing.v1.AppTest and check key numbers.

AppTest.from_function re-executes the function source in a fresh module namespace, so each
wrapper below imports views at run time and the page functions keep executing in views' globals.
"""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from streamlit.testing.v1 import AppTest  # noqa: E402

TIMEOUT = 120


def page_calculator():
    import views
    views.calculator()


def page_results():
    import views
    views.results()


def page_guide():
    import views
    views.guide()


def run(page):
    at = AppTest.from_function(page, default_timeout=TIMEOUT)
    at.run()
    return at


def errors(at):
    return [str(e.value) for e in at.exception]


class AppPageTests(unittest.TestCase):
    def test_calculator_page_runs_and_balances(self):
        at = run(page_calculator)
        self.assertEqual(errors(at), [])
        self.assertEqual(at.title[0].value, "DES Recipe Calculator")
        metrics = [m.value for m in at.metric]
        # default 10 g active basis: ChCl 1 : glyoxylic acid 2, both 98 wt% solids, no separate water
        self.assertEqual(metrics[0], "10.2041 g")   # 4.9520 g ChCl + 5.2521 g glyoxylic acid
        self.assertEqual(metrics[1], "0.0000 g")    # solids only: the missing 2% is impurity, not water
        self.assertEqual(metrics[2], "0.00%")
        self.assertIn("Download recipe CSV", [b.label for b in at.download_button])

    def test_results_page_my_data(self):
        at = run(page_results)
        self.assertEqual(errors(at), [])
        at.radio[0].set_value("My DES runs (3 conditions, n=1)").run()
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

    def test_guide_page_runs(self):
        at = run(page_guide)
        self.assertEqual(errors(at), [])
        self.assertEqual(at.title[0].value, "How to use")
        self.assertIn("Download my experiment data CSV", [b.label for b in at.download_button])

    def test_entry_page_branding_and_intro_once(self):
        at = AppTest.from_file(str(ROOT / "Hello.py"), default_timeout=TIMEOUT)
        at.run()
        self.assertEqual(errors(at), [])
        markup = "\n".join(str(m.value) for m in at.markdown)
        # the overlay element (not the stylesheet, which only mentions the selector)
        self.assertIn('id="dsh-splash"', markup, "the A*STAR intro should be injected on the first run")
        self.assertIn('<img src="app/static/astar_logo.png"', markup)
        at.run()  # a rerun in the same session must not replay the intro
        self.assertNotIn('id="dsh-splash"', "\n".join(str(m.value) for m in at.markdown))


if __name__ == "__main__":
    unittest.main(verbosity=2)
