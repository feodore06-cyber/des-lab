# -*- coding: utf-8 -*-
"""Excel reading: header detection, column mapping, merged cells and a computed yield."""
import io
import os

os.environ["DESLAB_STORAGE"] = "file"  # tests must never touch a real database

import sys
import unittest
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import excel_io  # noqa: E402


def workbook(rows, sheet="runs") -> bytes:
    buffer = io.BytesIO()
    pd.DataFrame(rows).to_excel(buffer, index=False, header=False, sheet_name=sheet)
    return buffer.getvalue()


LAB_SHEET = [
    ["Lignin extraction - DES pretreatment", None, None, None, None, None],
    ["recorded by Chuanyu, 2026-10", None, None, None, None, None],
    [None, None, None, None, None, None],
    ["样品编号", "配方", "生物质 (g)", "木质素 (mg)", "温度 (°C)", "时间 (min)"],
    ["EXP-01", "ChCl:GA 1:1", 2.3, 26.0, 80, 60],
    [None, None, 2.4, 27.0, 80, 60],
    ["EXP-02", "ChCl:GA 1:2", 2.88, 56.0, 80, 60],
]


class ExcelTests(unittest.TestCase):
    def test_header_is_found_below_titles_and_notes(self):
        result = excel_io.read_table(workbook(LAB_SHEET))
        self.assertEqual(result["sheet"], "runs")
        self.assertEqual(result["header_row"], 4, "header sits on the fourth Excel row")
        self.assertEqual(result["rows"], 3)

    def test_chinese_columns_are_mapped(self):
        result = excel_io.read_table(workbook(LAB_SHEET))
        mapping = result["mapping"]
        self.assertEqual(mapping["样品编号"], "sample_id")
        self.assertEqual(mapping["配方"], "formulation")
        self.assertEqual(mapping["生物质 (g)"], "biomass_g")
        self.assertEqual(mapping["木质素 (mg)"], "lignin_mg")
        self.assertEqual(mapping["温度 (°C)"], "temperature_C")
        self.assertEqual(mapping["时间 (min)"], "time_min")

    def test_merged_cells_are_filled_down_and_missing_yield_is_computed(self):
        frame = excel_io.read_table(workbook(LAB_SHEET))["frame"]
        self.assertEqual(list(frame["sample_id"]), ["EXP-01", "EXP-01", "EXP-02"])
        self.assertEqual(list(frame["formulation"]), ["ChCl:GA 1:1", "ChCl:GA 1:1", "ChCl:GA 1:2"])
        self.assertAlmostEqual(float(frame.loc[0, "lignin_yield_pct"]), 1.1304, places=3)
        self.assertAlmostEqual(float(frame.loc[2, "lignin_yield_pct"]), 1.9444, places=3)

    def test_english_headers_with_units_work_too(self):
        rows = [
            ["Sample ID", "Formulation", "Biomass (g)", "Lignin (mg)", "Replicate"],
            ["EXP-07", "ChCl:GA 1:2", 2.0, 40.0, 1],
            ["EXP-07", "ChCl:GA 1:2", 2.0, 42.0, 2],
        ]
        frame = excel_io.read_table(workbook(rows))["frame"]
        self.assertIn("biomass_g", frame.columns)
        self.assertIn("replicate", frame.columns)
        self.assertAlmostEqual(float(frame.loc[0, "lignin_yield_pct"]), 2.0, places=3)

    def test_an_unknown_column_is_kept_as_it_is(self):
        rows = [
            ["Sample ID", "Biomass (g)", "Lignin (mg)", "Operator initials"],
            ["EXP-08", 2.0, 30.0, "CY"],
        ]
        result = excel_io.read_table(workbook(rows))
        self.assertIn("Operator initials", result["frame"].columns)
        self.assertIn("Operator initials", result["unknown"])

    def test_a_sheet_without_a_header_is_refused(self):
        with self.assertRaises(ValueError):
            excel_io.read_table(workbook([[None], [None], ["x"]]))

    def test_the_second_sheet_is_picked_when_it_holds_the_table(self):
        buffer = io.BytesIO()
        with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
            pd.DataFrame([["notes"], ["nothing here"]]).to_excel(writer, sheet_name="cover", index=False, header=False)
            pd.DataFrame(LAB_SHEET).to_excel(writer, sheet_name="data", index=False, header=False)
        result = excel_io.read_table(buffer.getvalue())
        self.assertEqual(result["sheet"], "data")
        self.assertEqual(result["rows"], 3)


if __name__ == "__main__":
    unittest.main(verbosity=2)
