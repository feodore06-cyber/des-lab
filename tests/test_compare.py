# -*- coding: utf-8 -*-
"""The comparison engine: ranking of explanations, the maths, and the calm wording.

The rules matter more than the maths here: the first explanation offered must be the one that is
actually the most common reason two yields disagree (a different definition), and nothing may ever be
phrased as "you made a mistake".
"""
import os

os.environ["DESLAB_STORAGE"] = "file"  # tests must never touch a real database
os.environ["DESLAB_MAIL_DISABLE"] = "1"  # tests must never send mail

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import compare  # noqa: E402
import i18n  # noqa: E402

MINE = {"lignin_yield_pct": 1.94, "basis": "Lignin yield on dry biomass", "feedstock": "wood flour",
        "molar_ratio": 2.0, "purity_wt_pct": 98, "water_wt_pct": 0, "temperature_C": 80,
        "time_min": 60, "moisture_wt_pct": None, "replicates": 3}

THEIRS = {"lignin_yield_pct": 6.10, "basis": "Delignification of the biomass",
          "feedstock": "wheat straw", "molar_ratio": 1.0, "purity_wt_pct": 90, "water_wt_pct": 10,
          "temperature_C": 90, "time_min": 120, "moisture_wt_pct": None, "replicates": 1}


class RankingTests(unittest.TestCase):
    def test_a_definition_mismatch_is_named_first(self):
        result = compare.compare(MINE, THEIRS)
        self.assertEqual(result["findings"][0]["code"], "definition")

    def test_a_definition_mismatch_outranks_a_small_chemistry_gap(self):
        mine = dict(MINE, basis="Lignin yield on dry biomass")
        theirs = dict(THEIRS, basis="Purity of the recovered lignin")
        result = compare.compare(mine, theirs)
        codes = [item["code"] for item in result["findings"]]
        self.assertEqual(codes[0], "definition")

    def test_identical_conditions_mostly_agree(self):
        same = dict(MINE, lignin_yield_pct=1.95, basis=MINE["basis"], feedstock="wood flour",
                    molar_ratio=2.0, purity_wt_pct=98, water_wt_pct=0, temperature_C=80,
                    time_min=60, replicates=3, moisture_wt_pct=8)
        result = compare.compare(same, dict(same, lignin_yield_pct=1.94))
        self.assertEqual(compare.headline(result), "agree")
        self.assertLess(abs(result["delta"]), 0.05)

    def test_a_missing_yield_only_reports_the_conditions(self):
        result = compare.compare(MINE, {"feedstock": "wheat straw", "lignin_yield_pct": ""})
        self.assertIsNone(result["delta"])
        self.assertEqual(compare.headline(result), "missing")

    def test_every_finding_has_a_translated_sentence_in_both_languages(self):
        result = compare.compare(MINE, THEIRS)
        self.assertGreaterEqual(len(result["findings"]), 5)
        for item in result["findings"]:
            for suffix in ("claim", "why", "check", "step"):
                key = f"cmp.{item['code']}.{suffix}"
                self.assertIn(key, i18n.EN, key)
                self.assertIn(key, i18n.ZH, key)

    def test_the_wording_never_blames_the_reader(self):
        banned = ("you are wrong", "mistake", "incorrect", "failed", "error")
        result = compare.compare(MINE, THEIRS)
        for item in result["findings"]:
            for suffix in ("why", "step"):
                text = str(i18n.EN[f"cmp.{item['code']}.{suffix}"]).lower()
                for word in banned:
                    self.assertNotIn(word, text, f"{item['code']} uses blaming language: {word}")


class MathsTests(unittest.TestCase):
    def test_severity_rises_with_temperature_and_time(self):
        self.assertGreater(compare.severity(90, 60), compare.severity(80, 60))
        self.assertGreater(compare.severity(80, 120), compare.severity(80, 60))

    def test_severity_matches_the_classic_formula(self):
        # 80 C for 60 min: log10(R0) = log10(60) + (80-100)/14.75 -> R0 ~ 2.64
        self.assertAlmostEqual(compare.severity(80, 60), 2.6437, places=3)

    def test_severity_of_nonsense_is_zero_not_a_crash(self):
        self.assertEqual(compare.severity("hot", "a while"), 0.0)
        self.assertEqual(compare.severity(None, None), 0.0)

    def test_purity_correction_scales_the_ratio(self):
        self.assertAlmostEqual(compare.effective_ratio(2, 90), 1.8)
        self.assertAlmostEqual(compare.effective_ratio(1, 100), 1.0)

    def test_purity_correction_of_garbage_does_not_raise(self):
        self.assertEqual(compare.effective_ratio(None, None), 0.0)

    def test_the_relative_difference_is_reported(self):
        result = compare.compare({"lignin_yield_pct": 2.0}, {"lignin_yield_pct": 1.0})
        self.assertAlmostEqual(result["relative"], 100.0)
        self.assertAlmostEqual(result["delta"], 1.0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
