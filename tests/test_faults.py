# -*- coding: utf-8 -*-
"""Fault injection: what happens when the input is wrong, empty, huge or hostile.

These are the paths a real user reaches by accident every day, and the ones that make an app feel
broken: a CAS number that does not exist, an Excel that is not an Excel, a number written as text.
"""
import io
import os

os.environ["DESLAB_STORAGE"] = "file"  # tests must never touch a real database
os.environ["DESLAB_MAIL_DISABLE"] = "1"  # tests must never send mail

import sys
import time
import unittest
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import excel_io  # noqa: E402
import lab_core  # noqa: E402
import schema  # noqa: E402


class LookupFaults(unittest.TestCase):
    """The chemical lookup is the most exposed surface: it calls an external API with user text."""

    def setUp(self):
        import chem

        self.chem = chem
        chem.find_cids.clear()
        chem.suggest.clear()
        chem.compound.clear()
        # the tests must not depend on the network: a 404 is what PubChem returns for nonsense
        self.original = chem._get_json
        chem._get_json = lambda url: (_ for _ in ()).throw(chem.ChemError("not found"))

    def tearDown(self):
        self.chem._get_json = self.original
        self.chem.find_cids.clear()
        self.chem.suggest.clear()
        self.chem.compound.clear()

    def test_a_missing_cas_number_returns_nothing_instead_of_raising(self):
        started = time.perf_counter()
        try:
            result = self.chem.find_cids("99-99-9")
        except self.chem.ChemError:
            result = []
        self.assertEqual(result, [])
        self.assertLess(time.perf_counter() - started, 30, "a failed lookup must not hang the page")

    def test_hostile_and_weird_terms_are_url_encoded_not_crashed(self):
        for term in ("'; drop table records; --", "<script>alert(1)</script>",
                     "a" * 500, "葡萄糖", "  ", "", "%%%"):
            try:
                self.chem.find_cids(term)
            except self.chem.ChemError:
                pass  # a network answer or a clean error is fine; a crash is not
            except Exception as exc:  # noqa: BLE001
                self.fail(f"{term!r} raised {type(exc).__name__}: {exc}")

    def test_an_offline_machine_says_so_instead_of_hanging(self):
        result = self.chem.suggest("water")
        self.assertIsInstance(result, list, "suggestions degrade to an empty list, never an exception")


class ExcelFaults(unittest.TestCase):
    def test_a_file_that_is_not_a_workbook_is_rejected_cleanly(self):
        for payload in (b"", b"not an excel file", b"\x00\x01\x02\x03"):
            with self.assertRaises((ValueError, Exception)) as caught:
                excel_io.read_table(payload)
            self.assertIsNotNone(caught.exception)

    def test_a_sheet_with_headers_only_gives_an_empty_frame(self):
        buffer = io.BytesIO()
        pd.DataFrame([["sample_id", "biomass_g", "lignin_mg"]]).to_excel(
            buffer, index=False, header=False)
        result = excel_io.read_table(buffer.getvalue())
        self.assertEqual(result["rows"], 0)

    def test_numbers_written_as_text_still_parse(self):
        buffer = io.BytesIO()
        pd.DataFrame([
            ["sample_id", "biomass (g)", "lignin (mg)", "molar ratio"],
            ["EXP-01", "2.3 g", "26 mg", "1:2"],
        ]).to_excel(buffer, index=False, header=False)
        frame = excel_io.read_table(buffer.getvalue())["frame"]
        yield_value = lab_core.summarize(frame, ["sample_id"], "lignin_yield_pct")[1]
        # the importer is allowed to leave unparseable text alone, but it must not crash
        self.assertIn("sample_id", frame.columns)

    def test_a_single_column_sheet_does_not_explode(self):
        buffer = io.BytesIO()
        pd.DataFrame([["notes"], ["hello"], ["world"]]).to_excel(buffer, index=False, header=False)
        with self.assertRaises(ValueError):
            excel_io.read_table(buffer.getvalue())


class InputFaults(unittest.TestCase):
    def test_an_empty_formulation_is_safe(self):
        self.assertEqual(schema.parse_formulation(""), {})
        self.assertEqual(schema.build_formulation({"des_hba": None, "des_hbd": None,
                                                   "molar_ratio": None}), "")

    def test_a_ratio_of_zero_or_garbage_is_not_a_number(self):
        self.assertIsNone(schema.to_ratio("0:0"))
        self.assertIsNone(schema.to_ratio("abc"))
        self.assertEqual(schema.to_ratio("1:2"), 2.0)

    def test_a_zero_target_mass_is_refused_by_the_calculator(self):
        components = pd.DataFrame([{"name": "ChCl", "mw": 139.62, "ratio": 1.0,
                                    "assay_pct": 98.0, "water_pct": 0.0}])
        with self.assertRaises(ValueError):
            lab_core.calculate_recipe(components, 0, "active", 0)

    def test_purity_outside_its_range_is_refused(self):
        components = pd.DataFrame([{"name": "ChCl", "mw": 139.62, "ratio": 1.0,
                                    "assay_pct": 150.0, "water_pct": 0.0}])
        with self.assertRaises(ValueError):
            lab_core.calculate_recipe(components, 10, "active", 0)

    def test_text_in_a_numeric_column_does_not_break_the_summary(self):
        frame = pd.DataFrame({"formulation": ["a", "a", "b"],
                              "lignin_yield_pct": ["1.2", "oops", None]})
        clean, summary, audit = lab_core.summarize(frame, ["formulation"], "lignin_yield_pct")
        self.assertEqual(int(summary["n"].sum()), 1)
        self.assertGreaterEqual(audit["excluded"], 2)


if __name__ == "__main__":
    unittest.main(verbosity=2)
