import math
from pathlib import Path
import sys

import os
os.environ["DESLAB_STORAGE"] = "file"  # tests must never touch a real database
import unittest
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from lab_core import calculate_recipe, merge_results, summarize, csv_bytes
from lab_plots import make_figure, figure_bytes


class LabTests(unittest.TestCase):
    def setUp(self):
        self.components = [
            dict(name="ChCl", mw=139.62, ratio=1, assay_pct=100, water_pct=0),
            dict(name="GA aqueous", mw=74.04, ratio=2, assay_pct=50, water_pct=50)]

    def test_active_mass_known_moles(self):
        result, totals = calculate_recipe(self.components, 287.70, added_water_g=10)
        self.assertAlmostEqual(result.iloc[0].weigh_g, 139.62)
        self.assertAlmostEqual(result.iloc[1].weigh_g, 296.16)
        self.assertAlmostEqual(result.iloc[1].moles, 2)
        self.assertAlmostEqual(totals["total_g"], 445.78)
        self.assertAlmostEqual(totals["known_water_g"], 158.08)

    def test_weighed_basis_and_ratio(self):
        result, totals = calculate_recipe(self.components, 10, "reagent", 2)
        self.assertAlmostEqual(result.weigh_g.sum(), 10)
        self.assertAlmostEqual(result.iloc[1].moles / result.iloc[0].moles, 2)
        self.assertAlmostEqual(totals["total_g"], 12)

    def test_impurity_is_not_automatically_water(self):
        self.components[0]["assay_pct"] = 98
        result, _ = calculate_recipe(self.components, 287.7)
        self.assertEqual(result.iloc[0].water_g, 0)
        self.assertAlmostEqual(result.iloc[0].weigh_g, 139.62 / .98)

    def test_invalid_inputs(self):
        for field, value in [("ratio", 0), ("mw", float("nan")), ("assay_pct", 0), ("water_pct", 110)]:
            with self.subTest(field=field):
                components = [dict(c) for c in self.components]
                components[0][field] = value
                with self.assertRaises(ValueError):
                    calculate_recipe(components, 10)
        with self.assertRaises(ValueError):
            calculate_recipe(self.components, 0)

    def test_merge_and_audited_summary(self):
        frame = merge_results([("a.csv", b"group,value\nA,1\nA,3\nA,bad\n"),
                               ("b.csv", b"group,value,extra\nB,5,x\n,2,y\nB,inf,z\n")])
        clean, summary, audit = summarize(frame, ["group"], "value")
        self.assertEqual(len(frame), 6)
        self.assertEqual(audit["excluded"], 3)
        self.assertEqual(len(clean), 3)
        a, b = summary.iloc[0], summary.iloc[1]
        self.assertEqual(a["n"], 2)
        self.assertEqual(a["mean"], 2)
        self.assertAlmostEqual(a["sd"], math.sqrt(2))
        self.assertTrue(pd.isna(b["sd"]))
        self.assertEqual(set(frame._source_file), {"a.csv", "b.csv"})

    def test_duplicate_headers_rejected(self):
        with self.assertRaises(ValueError):
            merge_results([("bad.csv", b"group,group\nA,2\n")])

    def test_demo_lignin_sd(self):
        content = (Path(__file__).resolve().parents[1] / "sample_data/demo_lignin.csv").read_bytes()
        frame = merge_results([("demo.csv", content)])
        clean, summary, _ = summarize(frame, ["formulation", "temperature_C", "time_min"], "lignin_yield_pct")
        self.assertEqual(len(summary), 3)
        self.assertEqual(summary.n.tolist(), [3, 3, 3])
        for got, want in zip(summary["mean"].tolist(), [1.25, 1.85, 0.8]):
            self.assertAlmostEqual(got, want)
        for sd in summary["sd"]:
            self.assertAlmostEqual(sd, 0.05)
        fig = make_figure(clean, summary, ["formulation"], "lignin_yield_pct", "Test", "Lignin yield (%)")
        self.assertTrue(figure_bytes(fig, "png").startswith(b"\x89PNG"))
        self.assertIn(b"<svg", figure_bytes(fig, "svg"))

    def test_my_des_runs_yield_consistency(self):
        """Real runs: the recorded yield must equal lignin_mg / (biomass_g * 10)."""
        content = (Path(__file__).resolve().parents[1] / "sample_data/my_des_runs.csv").read_bytes()
        frame = merge_results([("my_des_runs.csv", content)])
        clean, summary, audit = summarize(frame, ["formulation"], "lignin_yield_pct")
        self.assertEqual(audit["excluded"], 0)
        self.assertEqual(len(summary), 3)
        self.assertEqual(summary.n.tolist(), [1, 1, 1])
        self.assertTrue(summary.sd.isna().all(), "n=1 must leave sd empty")
        computed = clean["lignin_mg"] / (clean["biomass_g"] * 10)
        self.assertTrue((abs(computed - clean["lignin_yield_pct"]) < 0.005).all())
        expected = {"ChCl-GA 1:1": 26.0 / (2.3 * 10), "ChCl-GA 1:2": 56.0 / (2.88 * 10), "ChCl-GA 2:1": 15.2 / (1.9545 * 10)}
        for _, row in clean.iterrows():
            self.assertAlmostEqual(row["lignin_yield_pct"], expected[row["formulation"]], delta=0.005)

    def test_csv_export(self):
        output = csv_bytes(pd.DataFrame({"sample": ["=2+3"], "value": [-1.0]}))
        self.assertTrue(output.startswith(b"\xef\xbb\xbf"))
        self.assertIn(b"'=2+3", output)
        self.assertIn(b"-1.0", output)


if __name__ == "__main__":
    unittest.main()
