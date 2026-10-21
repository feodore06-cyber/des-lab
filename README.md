# 🧪 DES Lab · Experiment Workbench

A small local browser workbench for DES (deep eutectic solvent) experiments:
**work out a recipe → organise results → plot and export**.
Built on [streamlit/hello](https://github.com/streamlit/hello) (Apache-2.0); the original licence is kept.

The interface is **bilingual**: an **English / 中文** switch sits in the sidebar (and on the sign-in page), and
every label, caption, warning and error message follows it. The choice is kept for the browser session.

## What it does

| Page | Purpose |
| --- | --- |
| 🧪 DES Recipe Calculator | Enter molar ratios, molar masses, active content and separate water for each component (for example ChCl and glyoxylic acid) and get a traceable weighing list: which mass is active component, which is reagent to weigh, and how much water the reagent carries. Exports `des_recipe.csv`. |
| 📊 Results & Figures | Merge one or more CSVs, group by experimental condition and summarise (n, mean, sample SD, min, max), plot mean bars with ±1 SD error bars and the raw observations, export PNG (300 dpi) / SVG / summary CSV. |
| 🔍 Chemical Lookup | Type any chemical - English name, Chinese name or CAS number - and get the key data live from PubChem: name, formula, **molar mass M_r**, CAS, SMILES, H-bond donor/acceptor counts, XLogP, TPSA. One click adds it to the recipe as one molar part. Links like /lookup?q=choline%20chloride can be shared. Needs outbound internet; no API key. |
| 📖 Guide & Templates | Step-by-step usage, the fictitious demo CSV, your recorded run CSV and a blank record template. |

The calculator deliberately separates three things that are easy to mix up: the **molar ratio** (the formulation),
the **reagent assay** (what the bottle actually contains) and the **water** (separate water plus extra water added).
The presets use the actual reagents: **ChCl 98 wt%** and **glyoxylic acid 98 wt% as a solid** — glyoxylic acid is
not dosed as an aqueous solution here, so no water is carried in. A shortfall from 100% active content is **never**
silently treated as water — the missing 2% is impurity — and for a hydrate you should use the molar mass of that
hydrate instead of entering crystal water twice.

Purity is a first-class input, because it changes what you weigh:

- Type the real bottle assay per component into **Active content (wt%)**, or flip **Assume 100 wt% purity (ideal)**
  to force every reagent to 100% (the assay column then becomes read-only).
- The fourth metric, **Weighed above active mass**, shows the consequence: 98 wt% means you weigh
  `1 / 0.98 − 1 = 2.04 %` more reagent than the active mass it delivers. At 100 wt% it shows `0.00 %`.
- At 100 wt% with no extra water, **total prepared mass = target mass** exactly. That is expected, not a bug —
  the app says so explicitly instead of leaving you to wonder where the difference went.

> The assay changes how much you weigh; it never changes the molar ratio of the mixture you end up with.

[![Deploy to Streamlit](https://static.streamlit.io/badges/streamlit_badge_black_white.svg)](https://share.streamlit.io/deploy?repository=https://github.com/feodore06-cyber/des-lab&branch=main&mainModule=streamlit_app.py)

Public hosting, step by step: **[DEPLOY.md](DEPLOY.md)** (Streamlit Community Cloud / Render with a disk / Cloudflare tunnel).

## Running it

Double-click `Start DES Lab.cmd` (the first run creates `.venv` and installs dependencies), then open
<http://127.0.0.1:8514>. To stop it, double-click `Stop DES Lab.cmd`.

Manually:

```powershell
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
.venv\Scripts\python -m streamlit run Hello.py --server.port 8514
```

## Team accounts and per-user records

The app is shared by a team, so it asks who you are before showing anything. On first launch two accounts are
seeded — **Thena** and **Chuanyu** — both with the password `see DEPLOY.md - set it yourself (secrets / first sign-in)` (change them after the first sign-in).

- **Create a new account** straight from the sign-in page: a new teammate picks a name and password and is logged
  in immediately with an **empty** record folder of their own — no rows are inherited from anybody.
- Passwords are stored as **salted PBKDF2-HMAC-SHA256 hashes** in `user_data/users.json`; the plain text is never
  written anywhere and the whole `user_data/` folder is git-ignored.
- Each account owns a record folder, `user_data/records/<username>/`:
  - `results.csv` — experiments saved from the Results page,
  - `recipes/` — a timestamped copy of every weighing list you keep.
- Switching accounts switches folders: one teammate's rows are never visible to another.
- **Guide & Templates → Account & team** lets any signed-in teammate change their own password and add a newcomer.

> **Scope of this login.** It keeps records apart on one shared machine; it is not internet-grade authentication.
> Sign-up is open to anyone who can reach the page — fine on a lab machine, but do not expose it publicly without
> putting it behind a real identity provider.

## Look and feel

- Opening the app — or opening any page in a new browser session — plays a **~3 second A\*STAR intro**: the logo
  fades in over a blue→red progress bar, then the white overlay fades away and the app content fades in. It shows
  once per session and is shortened automatically for `prefers-reduced-motion` users.
- The theme uses the two colours sampled from the supplied logo: A\*STAR blue `#002F86` and red `#D8291B`.
- The exported figure follows the same palette: navy bars, dark error bars, red raw-data points on a light grid,
  with friendly axis defaults such as `Lignin yield (%)`.
- The logo lives in `static/astar_logo.png`, is served by Streamlit's static file serving
  (`[server] enableStaticServing = true`), and is also used as the sidebar mark and the browser favicon.
- `Hello.py` holds the stylesheet and the intro markup, `views.py` holds the page content, `lab_plots.py` the figure.

> The A\*STAR name and logo belong to A\*STAR. Keep the repository private, or follow A\*STAR's brand guidelines,
> before sharing or publishing it.

## Recorded runs (sample)

`sample_data/my_des_runs.csv` holds three ChCl:GA runs, one measurement per condition (so no error bars):

| sample_id | formulation | biomass_g | lignin_mg | lignin_yield_pct |
| --- | --- | --- | --- | --- |
| EXP-01 | ChCl-GA 1:1 | 2.3 | 26.0 | 1.13 |
| EXP-02 | ChCl-GA 1:2 | 2.88 | 56.0 | 1.94 |
| EXP-03 | ChCl-GA 2:1 | 1.9545 | 15.2 | 0.78 |

Lignin yield (%) = lignin mass (mg) ÷ [biomass mass (g) × 1000] × 100% = lignin mass (mg) ÷ [biomass mass (g) × 10].

`sample_data/demo_lignin.csv` is 9 rows of **entirely fictitious** data used to demonstrate the workflow.

## Experiment records

`data/` holds the lab record (this repository is **private**):

- `DES实验数据记录.xlsx` — four sheets: the run log (ChCl:GA 1:1 / 1:2 / 2:1 with biomass and lignin, yield computed
  by formula: 1.13% / 1.94% / 0.78%), records recovered from chat history (operations, supervisor instructions, plans,
  literature comparisons), analytical measurements (fibre dimensions, Sample E NMR) and notes. Sheet text is in Chinese.
- `Codex聊天记录_实验数据提取.md` — the full extraction report: which sessions were scanned, what was found, and what
  was **not** found (the three yields above exist only in the workbook, not in any chat log).

> The yields in the workbook are formulas. Edit values in Excel / LibreOffice and save; do not edit the sheet as text.

## Data conventions

- One row = one measurement; identically named columns must use identical units; put units in the column name
  (`lignin_mg`, `lignin_yield_pct`).
- Save Excel as **CSV UTF-8**; if a Chinese CSV fails to load, switch the encoding to `gb18030`.
- Units are never converted, missing measurements are never filled in, duplicate rows are never deleted automatically.
  Non-numeric or incomplete rows are excluded from the summary and listed with the reason.
- Everything runs in the local process; uploads are not persisted anywhere.
- The Chemical Lookup page sends your search term to PubChem (NCBI/NLM) over HTTPS; nothing else leaves the machine.

## Tests

```powershell
.venv\Scripts\python -m unittest discover -s tests -v
```

Covers accounts (salted hashes, wrong password, adding a teammate, sanitised folders), per-user record saving, mass
balance of the recipe, weighing bases, "impurity is not water", invalid inputs, CSV merging and summaries (including
inf / missing / duplicate headers), demo SD values, consistency of the recorded yields with `lignin_mg / biomass_g / 10`,
CSV formula-injection escaping, PNG/SVG export, the sign-in gate, and headless runs of all three pages through
`streamlit.testing.v1.AppTest` — 27 tests, all passing.

## Layout

```
Hello.py                    # entry: branding, A*STAR intro, sign-in gate, st.navigation
auth.py                     # accounts (PBKDF2 hashes) + per-user record folders
views.py                    # three pages: calculator / results & figures / guide
lab_core.py                 # recipe mass balance, CSV merging, grouped summary (pure functions)
lab_plots.py                # matplotlib figure: mean bars + error bars + raw points
static/astar_logo.png       # A*STAR logo (sidebar mark, browser favicon, intro animation)
sample_data/                # demo_lignin.csv (fictitious) / my_des_runs.csv (recorded)
data/                       # experiment workbook + chat-history extraction report
user_data/                  # git-ignored: users.json + records/<username>/ on this machine
tests/test_lab.py           # unittest for the calculation and IO layer
tests/test_app_pages.py     # headless page tests with AppTest (login gate, intro-once, per-user data)
tests/test_auth.py          # accounts, hashing and per-user record files
Start.ps1 / Stop.ps1
```

## Licence

Apache License 2.0, see [LICENSE](LICENSE). Original copyright Streamlit Inc.; this is a modified derivative.
