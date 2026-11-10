import unittest

import comparison as c


class ComparisonTests(unittest.TestCase):
    def test_hours_convert_to_minutes(self):
        self.assertEqual(c.convert(3, "h", "min"), 180.0)

    def test_milligrams_convert_to_grams(self):
        self.assertAlmostEqual(c.convert(500, "mg", "g"), 0.5)

    def test_incompatible_units_return_none(self):
        self.assertIsNone(c.convert(1, "g", "min"))

    def test_relative_difference_is_a_percentage_of_the_first_value(self):
        self.assertAlmostEqual(c.relative_difference(0.96, 2.30), 139.5833, places=3)

    def test_relative_difference_refuses_a_zero_base(self):
        self.assertIsNone(c.relative_difference(0, 5))

    def test_replicate_statistics_use_the_sample_standard_deviation(self):
        stats = c.replicate_stats([1.0, 1.2, 0.9])
        self.assertEqual(stats["n"], 3)
        self.assertAlmostEqual(stats["mean"], 1.0333, places=4)
        self.assertAlmostEqual(stats["sd"], 0.15275, places=4)

    def test_one_run_has_no_standard_deviation(self):
        stats = c.replicate_stats([1.0])
        self.assertEqual(stats["n"], 1)
        self.assertIsNone(stats["sd"])

    def test_conditions_split_into_identical_differing_and_missing(self):
        sections = c.condition_sections(
            {"temperature_C": 120, "mixing_method": "mill", "ph": None},
            {"temperature_C": 120, "mixing_method": "hotplate", "ph": 7.0})
        self.assertEqual(list(sections["identical"]), ["temperature_C"])
        self.assertEqual(list(sections["differing"]), ["mixing_method"])
        self.assertEqual(list(sections["missing"]), ["ph"])

    def test_ranking_puts_unmeasured_runs_last(self):
        ranked = c.rank([{"y": 1.0}, {"y": 3.0}, {"y": None}], "y")
        self.assertEqual([item["value"] for item in ranked], [3.0, 1.0, None])


if __name__ == "__main__":
    unittest.main()
