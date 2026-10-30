# -*- coding: utf-8 -*-
"""Deleting a project: it refuses at first, then removes everything when confirmed.

Written before the implementation on purpose: the last attempt at this feature damaged the module it
edits, so the behaviour is pinned down here first.
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

import auth  # noqa: E402


class DeleteProjectTests(unittest.TestCase):
    def setUp(self):
        os.environ["DESLAB_DATA_DIR"] = tempfile.mkdtemp()
        auth.ensure_store()
        auth.create_project("Thena", "hot press")
        auth.set_project_variables("Thena", "hot press", ["temperature_C", "shear_strength_MPa"])
        auth.set_project_formulation("Thena", "hot press", {
            "des_hba": "ChCl", "des_hbd": "Lactic acid", "molar_ratio": 5.0,
            "purity_wt_pct": 90.0, "water_wt_pct": 10.0})
        auth.save_results("Thena", pd.DataFrame([
            {"sample_id": "EXP-01", "project": "hot press", "lignin_yield_pct": 1.9},
            {"sample_id": "EXP-02", "project": "hot press", "lignin_yield_pct": 2.1},
            {"sample_id": "EXP-09", "project": "other", "lignin_yield_pct": 3.3},
        ]), append=False)

    def test_a_project_with_experiments_is_not_deleted_silently(self):
        with self.assertRaises(ValueError) as caught:
            auth.delete_project("Thena", "hot press")
        self.assertIn("2", str(caught.exception), "the message should name how many rows are at risk")
        self.assertIn("hot press", auth.list_projects("Thena"))
        self.assertEqual(len(auth.load_results("Thena")), 3, "a refused delete must change nothing")

    def test_confirming_removes_the_project_and_only_its_own_rows(self):
        removed = auth.delete_project("Thena", "hot press", force=True)
        self.assertEqual(removed, 2)
        self.assertNotIn("hot press", auth.list_projects("Thena"))
        left = auth.load_results("Thena")
        self.assertEqual(left["sample_id"].tolist(), ["EXP-09"], "another project's row must survive")

    def test_deleting_takes_the_formulation_and_variables_with_it(self):
        auth.delete_project("Thena", "hot press", force=True)
        self.assertEqual(auth.project_formulation("Thena", "hot press"),
                         dict(auth.DEFAULT_FORMULATION), "the formulation falls back to the default")
        self.assertEqual(auth.project_variables("Thena", "hot press"),
                         list(auth.DEFAULT_VARIABLES))

    def test_an_empty_project_still_deletes_without_force(self):
        auth.create_project("Thena", "empty one")
        auth.delete_project("Thena", "empty one")
        self.assertNotIn("empty one", auth.list_projects("Thena"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
