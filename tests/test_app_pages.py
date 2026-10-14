# -*- coding: utf-8 -*-
"""用 streamlit.testing.v1.AppTest 无头运行三个页面，检查异常与关键数值。

AppTest.from_function 会在新的模块命名空间里重新执行函数源码，因此这里用
一层薄包装在运行期导入 views，让页面函数仍在 views 的全局命名空间中执行。
"""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from streamlit.testing.v1 import AppTest  # noqa: E402

TIMEOUT = 120


def page_calculator():
    import views
    views.calculator()


def page_results():
    import views
    views.results()


def page_guide():
    import views
    views.guide()


def run(page):
    at = AppTest.from_function(page, default_timeout=TIMEOUT)
    at.run()
    return at


def errors(at):
    return [str(e.value) for e in at.exception]


class AppPageTests(unittest.TestCase):
    def test_calculator_page_runs_and_balances(self):
        at = run(page_calculator)
        self.assertEqual(errors(at), [])
        self.assertEqual(at.title[0].value, "DES 配比计算")
        metrics = [m.value for m in at.metric]
        # 默认 10 g 有效组分基准：ChCl 1 : 乙醛酸(50% 水溶液) 2
        self.assertEqual(metrics[0], "15.1470 g")   # 4.853 g ChCl + 10.294 g 溶液
        self.assertEqual(metrics[1], "5.1470 g")    # 50% 溶液带入的水
        self.assertEqual(metrics[2], "33.98%")
        self.assertIn("下载配方 CSV", [b.label for b in at.download_button])

    def test_results_page_my_data(self):
        at = run(page_results)
        self.assertEqual(errors(at), [])
        at.radio[0].set_value("我的 DES 实验数据（3 组 · n=1）").run()
        self.assertEqual(errors(at), [])
        summary = at.dataframe[-1].value
        self.assertEqual(list(summary["n"]), [1, 1, 1])
        self.assertTrue(summary["sd"].isna().all(), "n=1 不应有标准差")
        self.assertEqual(list(summary["formulation"]), ["ChCl-GA 1:1", "ChCl-GA 1:2", "ChCl-GA 2:1"])
        for got, want in zip(summary["mean"], [1.13, 1.94, 0.78]):
            self.assertAlmostEqual(got, want, delta=0.005)
        self.assertIn("下载 PNG · 300 dpi", [b.label for b in at.download_button])
        self.assertIn("下载 SVG · 矢量图", [b.label for b in at.download_button])

    def test_results_page_demo_has_error_bars(self):
        at = run(page_results)
        at.radio[0].set_value("虚构示例（9 条 · 演示操作）").run()
        self.assertEqual(errors(at), [])
        summary = at.dataframe[-1].value
        self.assertEqual(list(summary["n"]), [3, 3, 3])
        for sd in summary["sd"]:
            self.assertAlmostEqual(sd, 0.05)

    def test_guide_page_runs(self):
        at = run(page_guide)
        self.assertEqual(errors(at), [])
        self.assertEqual(at.title[0].value, "使用说明")
        self.assertIn("下载我的实验数据 CSV", [b.label for b in at.download_button])


if __name__ == "__main__":
    unittest.main(verbosity=2)
