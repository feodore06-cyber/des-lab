import unittest

import comparability as c

ROW = {"feedstock": "oak sawdust", "lignin_yield_pct": 2.3, "lignin_recovery_pct": 58.8}

YIELD = {"name": "lignin_yield_pct", "unit": "%",
         "definition": "recovered lignin divided by dry biomass, times 100",
         "formula": "lignin_mg / (biomass_g * 1000) * 100"}
RECOVERY = {"name": "lignin_recovery_pct", "unit": "%",
            "definition": "recovered lignin divided by the Klason lignin present, times 100",
            "formula": "lignin_mg / (biomass_g * 1000 * klason_lignin_pct / 100) * 100"}


class ComparabilityTests(unittest.TestCase):
    def test_a_yield_and_a_recovery_are_not_comparable(self):
        verdict = c.check(ROW, ROW, YIELD, RECOVERY)
        self.assertEqual(verdict["status"], c.NOT_COMPARABLE)
        self.assertTrue(verdict["blocking"])
        self.assertIn("denominator", verdict["blocking"][0])

    def test_the_same_metric_from_one_run_each_is_comparable_with_caveats(self):
        self.assertEqual(c.check(ROW, ROW, YIELD, YIELD)["status"], c.CAVEATS)

    def test_the_same_metric_with_replicates_is_directly_comparable(self):
        self.assertEqual(c.check(ROW, ROW, YIELD, YIELD, replicates=3)["status"], c.DIRECTLY)

    def test_a_missing_unit_of_meaning_is_insufficient_information(self):
        bare = {"name": "x", "unit": "%"}
        self.assertEqual(c.check(ROW, ROW, bare, bare)["status"], c.INSUFFICIENT)

    def test_different_units_block_the_comparison(self):
        other = dict(YIELD, unit="fraction")
        self.assertEqual(c.check(ROW, ROW, YIELD, other)["status"], c.NOT_COMPARABLE)

    def test_the_conversion_note_names_the_basis_to_change(self):
        note = c.conversion_note(YIELD, RECOVERY)
        self.assertIn("denominator", note)
        self.assertIn("biomass", note)
        self.assertIn("klason", note)


if __name__ == "__main__":
    unittest.main()
