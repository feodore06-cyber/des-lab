# 🧪 DES Lab · 实验工作台

本机浏览器里使用的 DES（低共熔溶剂）实验小工具：**算配比 → 整理结果 → 画图导出**。
基于 [streamlit/hello](https://github.com/streamlit/hello)（Apache-2.0）改造，保留原许可证。

## 功能

| 页面 | 作用 |
| --- | --- |
| 🧪 DES 配比计算 | 输入 ChCl / GA 等组分的摩尔份数、摩尔质量、有效含量与独立水分，得到可追溯的称量清单（哪些是有效组分、哪些是试剂称量、哪些是试剂带入的水），可导出 `des_recipe.csv` |
| 📊 实验结果与图表 | 合并一个或多个 CSV，按实验条件分组统计（n、均值、样本标准差、极值），画均值柱状图 + ±1 SD 误差棒 + 原始数据点，导出 PNG（300 dpi）/ SVG / 汇总 CSV |
| 📖 使用说明与模板 | 使用步骤、虚构示例 CSV、我的实验数据 CSV、空白记录模板 |

配比部分刻意区分三件事：**摩尔比**（配方）、**试剂实际含量**（瓶签）、**含水量**（独立水分 + 额外加水）。
计算不会自动把"含量不足 100% 的差额"当作水——杂质不是水；水合物请直接用该水合物的摩尔质量。

## 运行

双击 `Start DES Lab.cmd`（首次会自动建 `.venv` 并安装依赖），浏览器打开 <http://127.0.0.1:8514>。
停止：双击 `Stop DES Lab.cmd`。

手动运行：

```powershell
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
.venv\Scripts\python -m streamlit run Hello.py --server.port 8514
```

## 实测数据示例

`sample_data/my_des_runs.csv` 已录入 3 组 ChCl:GA 实验（每组 n=1，故不显示误差棒）：

| sample_id | formulation | biomass_g | lignin_mg | lignin_yield_pct |
| --- | --- | --- | --- | --- |
| EXP-01 | ChCl-GA 1:1 | 2.3 | 26.0 | 1.13 |
| EXP-02 | ChCl-GA 1:2 | 2.88 | 56.0 | 1.94 |
| EXP-03 | ChCl-GA 2:1 | 1.9545 | 15.2 | 0.78 |

木质素得率 (%) = 木质素质量 (mg) ÷ [生物质质量 (g) × 1000] × 100% ＝ 木质素质量 (mg) ÷ [生物质质量 (g) × 10]

`sample_data/demo_lignin.csv` 是 9 条**完全虚构**的数据，只用于演示操作。

## 数据约定

- 每行 = 一次测量；同名列必须同单位；列名写清单位（如 `lignin_mg`、`lignin_yield_pct`）。
- Excel 先另存为 **CSV UTF-8**；中文 CSV 读取失败时把编码切换为 `gb18030`。
- 程序不换算单位、不填补缺失值、不自动删除重复行；非数值/缺失行会被排除并列出原因。
- 数据只在本机内存里处理，不上传、不落盘。

## 测试

```powershell
.venv\Scripts\python -m unittest discover -s tests -v
```

覆盖：配比质量守恒、称量基准、杂质≠水、非法输入、CSV 合并与统计（含 inf/缺失/重复表头）、
示例数据标准差、实测得率与 `lignin_mg / biomass_g / 10` 的一致性、CSV 公式注入转义、PNG/SVG 导出，
以及三个页面在 `streamlit.testing.v1.AppTest` 下无异常运行（共 13 项，全部通过）。

## 目录

```
Hello.py                    # 入口：st.set_page_config + st.navigation
views.py                    # 三个页面：配比计算 / 结果与图表 / 使用说明
lab_core.py                 # 配比计算、CSV 合并、分组统计（纯函数，便于测试）
lab_plots.py                # matplotlib 绘图（柱 + 误差棒 + 散点）
sample_data/                # demo_lignin.csv（虚构）/ my_des_runs.csv（实测）
tests/test_lab.py           # 计算与 IO 的 unittest
tests/test_app_pages.py     # 用 AppTest 无头跑三个页面
Start.ps1 / Stop.ps1
```

## 许可证

Apache License 2.0，见 [LICENSE](LICENSE)。原项目版权归 Streamlit Inc.，本仓库为其改造版本。
