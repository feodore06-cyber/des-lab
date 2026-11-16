# BioMat Lab 使用教程（中文）

最后更新：2026-11-16 · 适用于当前线上版本（`appapppy-9ukmar4jdiggrjkenjyffk.streamlit.app`）

---

## 0. 一句话说明

BioMat Lab 有两条主线：**记录实验**（Projects）和**比较实验**（Compare）。其余页面都是为这两件事服务的。

---

## 1. 第一次进来该做什么

```
登录 → Projects（默认页）→ 右上角 [New project]
```

你会看到 **Step 1 of 4**。这是四步向导的第一屏：

| 字段 | 必填 | 说明 |
|---|---|---|
| Project name | **是** | 同一个账号下不能重名 |
| Description | 否 | 写上"我想弄清什么"，AI 建议变量会更准 |

> ⚠️ **`Next` 按钮是灰的，不是坏了** —— 只要 Project name 有内容，它立刻变蓝可点。页面现在会提示这句话。

---

## 2. 四步向导怎么走

### Step 1 · 项目信息

填名字（+ 描述）→ 点 `Next`。

### Step 2 · 导入已有数据（可选）

- 点 `Browse files` 上传 `CSV / XLSX / XLSM / XLS`
- Excel 有多个 sheet 时，会出现 **`Which sheet?`** 下拉框，选一个
- 上传后显示：`Read 120 rows × 8 columns from xxx.xlsx (sheet Sheet1)`
- 下面预览前 8 行
- **不想导入文件？直接点 `Next`**，这一步可跳过

### Step 3 · 列映射（有文件时才会出现内容）

这里把 Excel 的列名翻译成标准变量名。系统会**同时识别中文和英文**：

| 原始列名 | 标准名 | 单位 |
|---|---|---|
| 木质素含量 (mg) | `lignin_mg` | mg |
| Lignin Content (mg) | `lignin_mg` | mg |
| 温度 (°C) / Temperature (°C) | `temperature_c` | °c |
| 反应时间 (min) / Reaction Time | `time_min` | min |
| 生物质质量 (g) / Biomass Mass (g) | `biomass_g` | g |
| 样品编号 / Sample ID | `sample_id` | — |

表格每一行都能改：

- **取消勾选 `import`** → 这一列不导入（原始文件不受影响）
- **改 `standard`** → 重命名这个变量
- **改 `unit`** → 单位不对就改（默认**不会猜**，没写单位就留空）
- **改 `role`** → independent（条件）/ dependent（结果）/ derived（计算得出）
- `confidence` 是系统自检：`high` 可直接用，`medium`/`low` **请自己确认**
- 若两列会变成同一个名字，会出现黄色提示 `Both … would become lignin_mg`，取消其中一个

### Step 4 · 最后确认

上半部分显示：项目名、描述、变量清单（含单位/类型/角色）。
下半部分显示：`待导入 N 条记录，映射 M 列，排除 K 列`。

然后可以做三件事：

1. `Suggest variables with AI` → 勾选想要的 → `Add the ticked ones`（**不勾就一个都不加**）
2. 手动加变量：输入框写名字 → `Add`（空格自动变下划线，一次一个）
3. 都确认好 → **`Create project`**

> 如果文件里有重复的 Sample ID，这里会报错并**拒绝创建**（不会写一半）。同一文件里两行都是 `DUP` 时，你需要先改文件或在文件里区分它们。

---

## 3. 创建完成后

```
Projects → 你的项目卡片 → [Open project]
```

项目页有五个标签：

| 标签 | 用途 |
|---|---|
| **Overview** | 结果指标 + 实验表格 + **变量编辑区** + 修改记录 |
| Formulation | 这个项目的配方（DES 才有意义，其他项目不用管）|
| Process | 工艺步骤 |
| Results | 图表 |
| Records | 完整表格编辑、导入、照片、导出 |

### 记录一次实验

有两个入口，效果一样：

- 项目页 `Add another run`（在 Overview 底部）
- `Results` 页 → 选项目 → `Record a run`

表单字段**来自这个项目的变量**，不会出现无关字段。填完点 `Save this run`。

> Sample ID 会自动给出下一条（EXP-05 之类），也可以自己改。

---

## 4. 变量怎么改

**项目页 → Overview → 页面下方「Variables this project records」**

表格每行可编辑：

- `display_name` 显示名
- `unit` 单位
- `role` 角色（independent / controlled / dependent / derived / metadata）
- `priority` 主指标 / 次指标（只对结果有意义）
- `formula` 派生公式，例如 `lignin_mg / (biomass_g * 1000) * 100`
- `hidden` 隐藏（**只是不显示，数据还在**）
- `remove` 移除（**会提示这一列已有多少条历史数据**，数据不会被删）

改完点 `Save variables`。再点 `Recompute derived values` 可以按公式重算派生值。

---

## 5. 比较两次实验

```
Compare → Two of my own runs → 选 Project → 选 First run / Second run → [Compare]
```

结果按这个顺序显示：

1. **可比性判定**（能不能比）——四种状态
2. 结果数字（每个结果变量一行，含相对差异）
3. 条件对照表（相同 / 不同 / 缺失）
4. AI 解读（观察 → 可能原因 → 其他解释 → 局限）

**如果两边定义不同（例如 yield vs recovery），系统不会算差值**，会告诉你分母不一样、该怎么换算。

页面底部还有 `Rank every run in this project`：按任一结果变量给所有实验排名。

---

## 6. 和论文对比

```
Compare → A paper against my run
```

1. 选你的实验
2. 填论文标题或 DOI
3. **把论文里描述条件的那段原文粘贴进去**（这一栏最关键，Elsevier 的摘要常常抓不到）
4. 点 `Read the paper with AI` → 数值会自动填进下面的框
5. 逐个核对 → `Compare`

论文提取的数值会保存在 **Literature** 页，每个值都带页码/状态（待核对 / 已确认 / 用户更正 / 未报告）。**没写的值标"未报告"，不会编造。**

---

## 7. 常见困惑

| 现象 | 原因 / 怎么办 |
|---|---|
| `Next` / `Create project` 是灰的 | 项目名为空，或存在未解决的列冲突 |
| 上传后看到很多列都不认识 | 点 Step 3 的手动改 `standard`；中文列名专用词不在词库里时会被标 `low` |
| 变量名变成 `lignin_mg_2` | 两个原始列映射到同一个名字，系统没丢数据，第二列加了后缀——建议回 Step 3 取消其中一列 |
| 导入报 `duplicate sample IDs` | 文件里 Sample ID 重复，**系统拒绝写入**，先修文件 |
| 实验记完看不到 | 确认 `Overview` 选的是同一个项目 |
| 老界面在哪 | `New project` 页勾选 `Legacy project creation (single page)` |

---

## 8. 数据安全说明

- 只有登录后才能看到数据；每个账号只看到自己（导师看到自己 + 自己的实习生）
- `secret`、数据库地址、其他账号的密码不会出现在界面上
- 删除变量是**软删除**：从表格消失，但历史数值仍在记录里
- 所有派生值都保存了公式，可以随时重算
