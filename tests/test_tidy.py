import unittest

import tidy


class TidyTests(unittest.TestCase):
    def items(self):
        return [{"name": "yield_pct", "role": ""},
                {"name": "temperature_C", "role": ""},
                {"name": "sample_id", "role": ""},
                {"name": "biomass_g", "role": ""},
                {"name": "time_min", "role": ""},
                {"name": "reaction_time_h", "role": ""}]

    def test_identifiers_come_first_and_results_last(self):
        ordered = [item["name"] for item in tidy.tidy(self.items())["items"]]
        self.assertEqual(ordered[0], "sample_id")
        self.assertEqual(ordered[-1], "yield_pct")

    def test_units_are_filled_from_the_name(self):
        result = {item["name"]: item["unit"] for item in tidy.tidy(self.items())["items"]}
        self.assertEqual(result["temperature_c"], "°c")
        self.assertEqual(result["time_min"], "min")
        self.assertEqual(result["biomass_g"], "g")
        self.assertEqual(result["yield_pct"], "%")

    def test_two_time_variables_are_flagged(self):
        duplicates = tidy.tidy(self.items())["duplicates"]
        self.assertIn("time", duplicates)
        self.assertEqual(sorted(duplicates["time"]), ["reaction_time_h", "time_min"])

    def test_moving_a_row_changes_the_order_and_the_positions(self):
        moved = tidy.move([{"name": "a"}, {"name": "b"}, {"name": "c"}], "c", -1)
        self.assertEqual([item["name"] for item in moved], ["a", "c", "b"])
        self.assertEqual([item["position"] for item in moved], [0, 1, 2])

    def test_moving_past_the_edge_changes_nothing(self):
        items = [{"name": "a"}, {"name": "b"}]
        self.assertEqual(tidy.move(items, "a", -1), items)
        self.assertEqual(tidy.move(items, "b", 1), items)


if __name__ == "__main__":
    unittest.main()
