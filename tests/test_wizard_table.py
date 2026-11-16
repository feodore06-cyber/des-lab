import unittest

import wizard


class VariableTableTests(unittest.TestCase):
    def test_edited_unit_type_and_role_survive(self):
        rows = [{"name": "reaction_time_min", "unit": "min", "type": "number",
                 "role": "independent", "remove": False}]
        result = wizard.variables_from_rows(rows)
        item = result["reaction_time_min"]
        self.assertEqual(item["unit"], "min")
        self.assertEqual(item["data_type"], "number")
        self.assertEqual(item["role"], "independent")

    def test_ticking_remove_drops_the_variable(self):
        rows = [{"name": "keep_me", "unit": "g", "type": "number", "role": "independent",
                 "remove": False},
                {"name": "drop_me", "unit": "", "type": "text", "role": "covariate",
                 "remove": True}]
        result = wizard.variables_from_rows(rows)
        self.assertIn("keep_me", result)
        self.assertNotIn("drop_me", result)

    def test_a_row_without_a_name_is_ignored(self):
        self.assertEqual(wizard.variables_from_rows([{"name": "", "remove": False}]), {})


if __name__ == "__main__":
    unittest.main()
