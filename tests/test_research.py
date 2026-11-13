import os
import tempfile
import unittest

import pandas as pd

import auth
import research


class NormalisationTests(unittest.TestCase):
    def test_names_become_lowercase_underscored(self):
        cases = {
            "Temperature_C": "temperature_c",
            "Lignin_mg": "lignin_mg",
            "Reaction Time": "reaction_time",
            "  Sample  ID  ": "sample_id",
            "木质素含量 (mg)": "mg",
        }
        for raw, expected in cases.items():
            self.assertEqual(research.normalise_name(raw), expected, raw)

    def test_duplicates_after_normalisation_are_dropped_not_merged(self):
        kept, dropped = research.normalise_variables(
            [{"name": "Temperature_C"}, {"name": "temperature_c"}, {"name": "pH"}])
        self.assertEqual([item["name"] for item in kept], ["temperature_c", "ph"])
        self.assertEqual(len(dropped), 1)
        self.assertIn("duplicate", dropped[0]["reason"])

    def test_reserved_names_are_refused(self):
        kept, dropped = research.normalise_variables([{"name": "sample_id"}, {"name": "mass_g"}])
        self.assertEqual([item["name"] for item in kept], ["mass_g"])
        self.assertEqual(len(dropped), 1)


class ImportPlanTests(unittest.TestCase):
    def frame(self):
        return pd.DataFrame([
            {"Sample ID": "A-1", "Temperature (°C)": 120, "Reaction Time": 3},
            {"Sample ID": "A-1", "Temperature (°C)": 130, "Reaction Time": 4},
            {"Sample ID": None, "Temperature (°C)": 140, "Reaction Time": 5},
        ])

    def test_rows_keep_provenance_and_normalised_keys(self):
        rows = research.sample_rows(self.frame(), {"Sample ID": "sample_id",
                                                   "Temperature (°C)": "temperature_c",
                                                   "Reaction Time": "reaction_time"})
        self.assertEqual(rows[0]["row"], 1)
        self.assertIn("temperature_c", rows[0]["values"])
        self.assertIsNone(rows[2]["values"]["sample_id"])

    def test_conflicts_are_reported_before_writing(self):
        rows = research.sample_rows(self.frame(), {"Sample ID": "sample_id"})
        conflicts = research.find_conflicts(rows, existing={"A-1"})
        self.assertIn("A-1", conflicts["inside_file"])
        self.assertTrue(conflicts["in_project"])
        self.assertEqual(conflicts["missing"], [3])

    def test_skip_and_rename_are_the_only_ways_out(self):
        rows = research.sample_rows(self.frame(), {"Sample ID": "sample_id"})
        ready, rejected = research.plan(rows, {
            "1": {"action": "skip"},
            "2": {"action": "rename", "sample_id": "A-2"},
        })
        self.assertEqual([item["values"]["sample_id"] for item in ready], ["A-2"])
        self.assertEqual(len(rejected), 2)  # skipped row + row without an id

    def test_missing_values_stay_missing(self):
        frame = pd.DataFrame([{"sample_id": "A-1", "lignin_mg": None, "pH": ""}])
        rows = research.sample_rows(frame)
        self.assertIsNone(rows[0]["values"]["lignin_mg"])
        self.assertIsNone(rows[0]["values"]["ph"])


class CreateProjectTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        os.environ["DESLAB_DATA_DIR"] = self.tmp.name
        os.environ["DESLAB_STORAGE"] = "file"
        auth.ensure_store()

    def tearDown(self):
        os.environ.pop("DESLAB_DATA_DIR", None)
        self.tmp.cleanup()

    def rows(self, ids):
        return [{"row": index + 1, "values": {"sample_id": sid, "temperature_c": 120}}
                for index, sid in enumerate(ids)]

    def test_a_project_can_be_created_without_a_file(self):
        result = research.create_project_with_data(
            "Chuanyu", "Empty project", "a description",
            [{"name": "temperature_C"}], [])
        self.assertEqual(result["imported"], 0)
        self.assertIn("Empty project", auth.list_projects("Chuanyu"))

    def test_rows_are_imported_with_their_sample_ids(self):
        result = research.create_project_with_data(
            "Chuanyu", "DES", "", [{"name": "temperature_C"}], self.rows(["A-1", "A-2"]))
        self.assertEqual(result["imported"], 2)
        stored = auth.load_results("Chuanyu")
        self.assertEqual(sorted(stored["sample_id"]), ["A-1", "A-2"])

    def test_a_duplicate_project_name_is_refused_before_writing(self):
        research.create_project_with_data("Chuanyu", "DES", "", [{"name": "ph"}], [])
        with self.assertRaises(ValueError):
            research.create_project_with_data("Chuanyu", "DES", "", [{"name": "ph"}], [])

    def test_duplicate_sample_ids_are_refused(self):
        with self.assertRaises(ValueError) as caught:
            research.create_project_with_data(
                "Chuanyu", "DES", "", [{"name": "ph"}], self.rows(["A-1", "A-1"]))
        self.assertIn("duplicate sample ids", str(caught.exception).lower())

    def test_a_project_without_variables_is_refused(self):
        with self.assertRaises(ValueError):
            research.create_project_with_data("Chuanyu", "DES", "", [], [])

    def test_a_failed_creation_leaves_no_partial_project(self):
        with self.assertRaises(ValueError):
            research.create_project_with_data(
                "Chuanyu", "DES", "", [{"name": "ph"}], self.rows(["", "A-2"]))
        self.assertNotIn("DES", auth.list_projects("Chuanyu"))


if __name__ == "__main__":
    unittest.main()
