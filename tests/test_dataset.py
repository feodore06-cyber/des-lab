import os
import tempfile
import unittest

import auth
import dataset
import literature as lit


class DatasetTests(unittest.TestCase):
    def test_every_exported_column_should_have_a_definition(self):
        body = dataset.payload("DES", [{"name": "lignin_yield_pct", "role": "dependent"}],
                               [{"sample_id": "EXP-01", "lignin_yield_pct": 1.87}])
        self.assertIn("Every exported column", dataset.describe(body))

    def test_an_undefined_column_is_named(self):
        body = dataset.payload("DES", [], [{"sample_id": "EXP-01", "mystery": 5}])
        self.assertIn("mystery", dataset.describe(body))

    def test_the_export_carries_the_definition_of_each_variable(self):
        body = dataset.payload("DES", [{"name": "lignin_yield_pct", "role": "dependent",
                                        "unit": "%", "formula": "mg/(g*1000)*100",
                                        "definition": "recovered / biomass"}], [])
        item = body["variables"][0]
        self.assertEqual(item["formula"], "mg/(g*1000)*100")
        self.assertEqual(item["role"], "dependent")


class ScenarioTests(unittest.TestCase):
    """PRD acceptance scenarios A-F, exercised through the real code paths."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        os.environ["DESLAB_DATA_DIR"] = self.tmp.name
        os.environ["DESLAB_STORAGE"] = "file"
        auth.ensure_store()

    def tearDown(self):
        os.environ.pop("DESLAB_DATA_DIR", None)
        self.tmp.cleanup()

    def test_scenario_a_a_new_project_gets_roles_and_results(self):
        auth.create_project("Chuanyu", "DES extraction")
        auth.set_project_variables("Chuanyu", "DES extraction",
                                   ["temperature_C", "lignin_mg", "lignin_yield_pct"])
        items = auth.variable_items("Chuanyu", "DES extraction")
        self.assertEqual(items[0]["role"], "independent")
        self.assertEqual(items[2]["role"], "dependent")
        self.assertEqual(auth.project_result_variables("Chuanyu", "DES extraction"),
                         ["lignin_yield_pct"])

    def test_scenario_b_another_domain_has_no_lignin_fields(self):
        auth.create_project("Chuanyu", "GFP purification")
        auth.set_project_variables("Chuanyu", "GFP purification",
                                   ["ph_buffer", "imidazole_elution_mM", "gfp_yield_percent"])
        names = auth.project_variables("Chuanyu", "GFP purification")
        self.assertNotIn("lignin_mg", names)
        self.assertNotIn("biomass_g", names)
        self.assertEqual(auth.project_result_variables("Chuanyu", "GFP purification"),
                         ["gfp_yield_percent"])

    def test_scenario_f_hiding_a_variable_keeps_its_history(self):
        import pandas as pd

        auth.create_project("Chuanyu", "DES")
        auth.set_project_variables("Chuanyu", "DES", ["temperature_C", "lignin_mg"])
        auth.save_results("Chuanyu", pd.DataFrame([
            {"sample_id": "EXP-01", "project": "DES", "temperature_C": 110,
             "lignin_mg": 56.0}]), append=False)
        items = auth.variable_items("Chuanyu", "DES")
        items[1]["hidden"] = True
        auth.set_variable_items("Chuanyu", "DES", items)
        self.assertNotIn("lignin_mg", auth.project_visible_variables("Chuanyu", "DES"))
        stored = auth.load_results("Chuanyu")
        self.assertEqual(float(stored.iloc[0]["lignin_mg"]), 56.0)

    def test_scenario_d_literature_values_keep_their_source(self):
        value = lit.make_value("lignin_recovery_pct", "58.3 % of Klason lignin", "%",
                               page=5, section="Results")
        self.assertTrue(lit.has_provenance(value))
        self.assertEqual(value["status"], lit.EXTRACTED)


if __name__ == "__main__":
    unittest.main()
