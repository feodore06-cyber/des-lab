# -*- coding: utf-8 -*-
"""The structured schema: parsing old labels, building new ones, upgrading rows."""
import os

os.environ["DESLAB_STORAGE"] = "file"  # tests must never touch a real database

import sys
import unittest
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import schema  # noqa: E402


class SchemaTests(unittest.TestCase):
    def test_the_three_real_labels_are_parsed(self):
        cases = {
            "ChCl-GA 1:1": ("ChCl", "Glyoxylic acid", 1.0),
            "ChCl-GA 1:2": ("ChCl", "Glyoxylic acid", 2.0),
            "ChCl-GA 2:1": ("ChCl", "Glyoxylic acid", 0.5),
        }
        for label, (hba, hbd, ratio) in cases.items():
            parsed = schema.parse_formulation(label)
            self.assertEqual(parsed["des_hba"], hba, label)
            self.assertEqual(parsed["des_hbd"], hbd, label)
            self.assertAlmostEqual(parsed["molar_ratio"], ratio, places=3, msg=label)

    def test_chinese_component_names_are_canonicalised(self):
        parsed = schema.parse_formulation("ChCl:乙醛酸 1:2")
        self.assertEqual(parsed["des_hba"], "ChCl")
        self.assertEqual(parsed["des_hbd"], "Glyoxylic acid")
        self.assertAlmostEqual(parsed["molar_ratio"], 2.0)

    def test_a_label_is_rebuilt_from_the_numbers(self):
        self.assertEqual(schema.build_formulation({"des_hba": "ChCl", "des_hbd": "Glyoxylic acid",
                                                   "molar_ratio": 2}), "ChCl:Glyoxylic acid 1:2")
        self.assertEqual(schema.build_formulation({"des_hba": "ChCl", "des_hbd": "Glyoxylic acid",
                                                   "molar_ratio": 0.5}), "ChCl:Glyoxylic acid 2:1")
        self.assertEqual(schema.build_formulation({"des_hba": "ChCl", "des_hbd": "Urea",
                                                   "molar_ratio": 2.5}), "ChCl:Urea 2.5")

    def test_backfill_upgrades_legacy_rows_without_touching_real_values(self):
        frame = pd.DataFrame([
            {"sample_id": "EXP-01", "formulation": "ChCl-GA 1:2"},
            {"sample_id": "EXP-02", "formulation": "ChCl-GA 1:1", "des_hba": "Urea",
             "des_hbd": "ChCl", "molar_ratio": 3.0},
        ])
        upgraded = schema.backfill(frame)
        self.assertEqual(upgraded.loc[0, "des_hba"], "ChCl")
        self.assertAlmostEqual(upgraded.loc[0, "molar_ratio"], 2.0)
        self.assertEqual(upgraded.loc[1, "des_hba"], "Urea", "existing values win")
        self.assertAlmostEqual(upgraded.loc[1, "molar_ratio"], 3.0)

    def test_an_unparseable_label_is_left_alone(self):
        parsed = schema.parse_formulation("deep eutectic solvent from the freezer")
        self.assertNotIn("molar_ratio", parsed)

    def test_empty_input_is_safe(self):
        self.assertEqual(schema.parse_formulation(""), {})
        self.assertEqual(schema.parse_formulation(None), {})
        self.assertEqual(schema.build_formulation({}), "")


if __name__ == "__main__":
    unittest.main(verbosity=2)
