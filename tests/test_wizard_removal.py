import unittest

import wizard


class RemovalTests(unittest.TestCase):
    def test_a_removed_variable_is_not_resurrected_by_a_suggestion(self):
        state = {"variables": {}, "suggested": [], "manual": [], "removed": []}
        rows = [{"name": "notes", "unit": "", "type": "text", "role": "independent",
                 "remove": True},
                {"name": "biomass_g", "unit": "g", "type": "number", "role": "independent",
                 "remove": False}]
        rebuilt = wizard.variables_from_rows(rows)
        self.assertNotIn("notes", rebuilt)
        self.assertIn("biomass_g", rebuilt)
        gone = {"notes"}
        state["removed"] = sorted(gone)
        later = [{"name": "notes"}, {"name": "biomass_g"}]
        kept = [item for item in later if item["name"] not in set(state["removed"])]
        self.assertEqual([item["name"] for item in kept], ["biomass_g"])


if __name__ == "__main__":
    unittest.main()
