import unittest

import columnmap


class ColumnMapTests(unittest.TestCase):
    def test_chinese_headers_map_to_standard_names_with_units(self):
        cases = {
            "木质素含量 (mg)": ("lignin_mg", "mg"),
            "温度 (°C)": ("temperature_c", "°c"),
            "反应时间 (min)": ("time_min", "min"),
            "生物质质量 (g)": ("biomass_g", "g"),
        }
        for header, (name, unit) in cases.items():
            proposal = columnmap.suggest(header)
            self.assertEqual(proposal["name"], name, header)
            self.assertEqual(proposal["unit"], unit, header)
            self.assertEqual(proposal["confidence"], "high", header)

    def test_english_headers_give_the_same_result(self):
        pairs = [("Lignin Content (mg)", "木质素含量 (mg)"),
                 ("Temperature (°C)", "温度 (°C)"),
                 ("Reaction Time (min)", "反应时间 (min)"),
                 ("Biomass Mass (g)", "生物质质量 (g)")]
        for english, chinese in pairs:
            self.assertEqual(columnmap.suggest(english)["name"],
                             columnmap.suggest(chinese)["name"])

    def test_identifiers_are_certain_and_need_no_unit(self):
        for header in ("Sample ID", "样品编号"):
            proposal = columnmap.suggest(header)
            self.assertEqual(proposal["name"], "sample_id")
            self.assertEqual(proposal["role"], "metadata")
            self.assertEqual(proposal["confidence"], "high")

    def test_case_spaces_underscores_and_brackets_do_not_matter(self):
        for header in ("TEMPERATURE (°C)", "temperature  (°C)", "reaction_time  ( min )",
                       "Reaction_Time(min)"):
            self.assertIn(columnmap.suggest(header)["name"],
                          {"temperature_c", "time_min"}, header)

    def test_a_missing_unit_is_never_invented(self):
        proposal = columnmap.suggest("Moisture")
        self.assertEqual(proposal["name"], "moisture")
        self.assertEqual(proposal["unit"], "")
        self.assertNotEqual(proposal["confidence"], "high")
        self.assertTrue(columnmap.needs_review(proposal))

    def test_a_blank_header_gets_no_name(self):
        self.assertEqual(columnmap.suggest("")["name"], "")
        self.assertEqual(columnmap.suggest("   ")["name"], "")

    def test_two_headers_with_the_same_meaning_are_reported(self):
        clashes = columnmap.duplicates(
            columnmap.suggest_all(["Lignin (mg)", "木质素含量 (mg)", "温度 (°C)"]))
        self.assertIn("lignin_mg", clashes)
        self.assertEqual(len(clashes["lignin_mg"]), 2)


if __name__ == "__main__":
    unittest.main()
