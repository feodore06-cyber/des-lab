# DES Lab · 实验工作台（中文说明）

一个在本机浏览器里运行的低共熔溶剂（DES）实验工作台：**算配比 → 记数据 → 出图**。
界面支持**中英文一键切换**（侧边栏和登录页上的 English / 中文 开关），这份文件是中文上手说明。

---

[![Deploy to Streamlit](https://static.streamlit.io/badges/streamlit_badge_black_white.svg)](https://share.streamlit.io/deploy?repository=https://github.com/feodore06-cyber/des-lab&branch=main&mainModule=streamlit_app.py)

Public hosting, step by step: **[DEPLOY.md](DEPLOY.md)** (Streamlit Community Cloud / Render with a disk / Cloudflare tunnel).

## 1. 怎么打开

1. 双击 **`Start DES Lab.cmd`**（第一次运行会自动建 `.venv` 并安装依赖，需要联网，约 1–3 分钟）。
2. 浏览器会自动打开 **http://127.0.0.1:8514**；没打开就手动输入这个地址。
3. 关掉网站：双击 **`Stop DES Lab.cmd`**。

> 只有这台电脑能访问。它不是一个公开网站，数据也不会上传到网上。

## 2. 登录

第一次启动会自带两个账号（团队成员各自登录，各自看到自己的记录）：

| 用户名 | 初始密码 |
| --- | --- |
| `Thena` | `see DEPLOY.md - set it yourself (secrets / first sign-in)` |
| `Chuanyu` | `see DEPLOY.md - set it yourself (secrets / first sign-in)` |

- 登录页下方有 **Create a new account**：新同事自己起用户名和密码，注册完直接登录，**记录文件夹是空的**，不会继承任何人的数据。
- 密码在磁盘上以 **加盐 PBKDF2 哈希** 保存，不存明文。
- 登录后到 **Guide & Templates → Account & team** 改自己的密码、并给新同事开账号。

## 3. 三个页面

| 页面 | 作用 |
| --- | --- |
| **DES Recipe Calculator** | 填摩尔比、摩尔质量、**纯度（Active content）**、水的含量，算出该称多少克。可以一键把称量表存进自己的记录。 |
| **Results & Figures** | 读自己的记录或上传 CSV，按实验条件分组统计（n、均值、标准差、极值），画均值柱 + 误差棒 + 原始点，导出 PNG / SVG / 汇总 CSV。 |
| **Chemical Lookup / 化学品查询** | 输入任意化学品（英文名、中文名或 CAS 号），实时从 PubChem 取名称、分子式、**摩尔质量 M_r**、CAS、SMILES、氢键供体/受体数、XLogP、TPSA；一键加进配方表（按 1 摩尔份）。链接可分享，例如 /lookup?q=choline%20chloride。需要能上网，不需要 API key。 |
| **Guide & Templates** | 使用说明、示例 CSV 下载、空白模板、账号管理。 |

### 关于纯度（重要）

- 98% 的瓶签：为了拿到同样多的有效组分，你**要多称 2.04%**（`1÷0.98−1`）。页面第 4 个数字 `Weighed above active mass` 就是显示这个。
- 100% 时"应称试剂 = 有效组分"，如果**没另外加水**，那么 `Total prepared mass` 就等于 `Target mass` —— **这是正常的，不是算错**，页面会明确写出来。
- 纯度只改变你称多少克，**不改变配出来的摩尔比**。
- 乙醛酸如果是**一水合物**，摩尔质量要用 92.05 而不是 74.04（看瓶子标签确认）。

## 4. 数据存在哪里

```text
user_data/
├── users.json                  # 账号（哈希，不是明文）
└── records/
    ├── Thena/
    │   ├── results.csv         # Results 页保存的实验数据
    │   └── recipes/*.csv       # 保存的称量表（带时间戳）
    └── Chuanyu/…
```

- 每个人的文件夹互相看不到。
- `user_data/` 已被 git 忽略：**实验数据和密码不会进 GitHub**。
- 想备份：直接复制整个 `user_data/` 文件夹（或里面的 CSV）。

## 5. 数据格式约定

- 一行 = 一次测量；列名写清单位（如 `biomass_g`、`lignin_mg`、`lignin_yield_pct`）。
- Excel 先另存为 **CSV UTF-8**；中文 CSV 读不进来时，把「文件编码」改成 `gb18030`。
- **木质素得率 (%) = 木质素质量(mg) ÷ [生物质质量(g) × 1000] × 100%**。
- 程序不换算单位、不补缺失值、不自动删重复；不完整的行会被排除并列出原因。

## 6. 常见问题

| 现象 | 处理 |
| --- | --- |
| 页面一片空白 | 先按 **Ctrl+Shift+R** 强制刷新；再确认 <http://127.0.0.1:8514/_stcore/health> 显示 `ok`（不显示说明服务没起来，重新双击 `Start DES Lab.cmd`）。 |
| 图表区空白等几秒 | 第一次画图要加载 matplotlib，属正常；之后会快很多。 |
| 上传中文 CSV 报错 | 文件编码选 `gb18030`。 |
| 忘记密码 | 删除 `user_data/users.json` 会重置为两个初始账号（**会丢账号，不会丢 records/ 里的数据**）。 |

## 7. 给学校 / 公司看的时候

- 代码与提交历史：**https://github.com/feodore06-cyber/des-lab**
- 仓库里含 **27 项自动化测试**（账号与哈希、数据隔离、配比质量守恒、图表导出、登录门禁、页面渲染），
  运行方式：`.venv\Scripts\python -m unittest discover -s tests -v`
- ⚠️ 这个登录只用于同一台电脑上区分同事的记录，**不是互联网级认证**；而且注册是开放的（任何能打开页面的人都能建账号），所以不要把它公开部署到互联网。要公开部署给外部使用，请接学校/公司的统一身份认证（SSO），或只放在实验室内网。
- A\*STAR 的名称与标志属于 A\*STAR；对外发布前请遵循其品牌规范。
