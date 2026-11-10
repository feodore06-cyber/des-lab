import unittest

import literature as lit


class LiteratureTests(unittest.TestCase):
    def test_a_number_is_taken_out_of_the_original_wording(self):
        value = lit.make_value("lignin_recovery_pct", "58.3 % of Klason lignin", "%",
                               page=5, section="Results")
        self.assertEqual(value["normalized"], 58.3)
        self.assertEqual(value["original"], "58.3 % of Klason lignin")
        self.assertEqual(value["status"], lit.EXTRACTED)

    def test_hours_become_minutes_only_when_the_unit_says_so(self):
        value = lit.make_value("time_min", "3 h", "min", page=4)
        self.assertEqual(value["normalized"], 3.0)
        self.assertEqual(value["unit"], "min")

    def test_a_value_without_a_number_is_recorded_as_not_reported(self):
        value = lit.make_value("temperature_C", "not stated", "°C", page=2)
        self.assertEqual(value["status"], lit.NOT_REPORTED)
        self.assertIsNone(value["normalized"])

    def test_a_value_without_a_source_has_no_provenance(self):
        value = lit.make_value("lignin_mg", "388", "mg")
        self.assertFalse(lit.has_provenance(value))

    def test_only_reviewed_values_may_be_compared(self):
        value = lit.make_value("lignin_mg", "388", "mg", page=3)
        self.assertFalse(lit.can_be_compared(value))
        accepted = lit.verify([value], "lignin_mg")
        self.assertTrue(lit.can_be_compared(accepted[0]))

    def test_a_correction_replaces_the_number_and_is_marked(self):
        values = [lit.make_value("lignin_mg", "38.8", "mg", page=3)]
        corrected = lit.verify(values, "lignin_mg", corrected="388")
        self.assertEqual(corrected[0]["normalized"], 388.0)
        self.assertEqual(corrected[0]["status"], lit.CORRECTED)

    def test_review_counts_what_still_needs_checking(self):
        values = [lit.make_value("a", "1", ""), lit.make_value("b", "n/a", ""),
                  lit.make_value("c", "3", "", page=2)]
        counts = lit.review(values)
        self.assertEqual(counts["total"], 3)
        self.assertEqual(counts["extracted_awaiting_review"], 2)
        self.assertEqual(counts["not_reported"], 1)
        self.assertEqual(counts["without_source"], 2)


if __name__ == "__main__":
    unittest.main()
