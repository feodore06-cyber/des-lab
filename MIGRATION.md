# Moving the database to a faster region

Supabase cannot move a project between regions, so the move is: create a new project in the closer
region, copy the data, then point the app at the new URL. `migrate_db.py` does the copy.

**Why do it:** the app talks to the database on almost every interaction. A project in Sydney answers
a query in ~200 ms from Singapore; a Singapore project answers in ~20 ms. Combined with the connection
pool (a query used to cost 2.6 s because every call opened a new connection, now ~0.2 s), this is the
difference between "feels laggy" and "feels instant".

---

## 1. Create the new project (you, ~2 minutes)

1. <https://supabase.com/dashboard> -> **New project**
2. **Region: `Southeast Asia (Singapore)`** - this is the whole point
3. Name it something like `biomat-lab-sg`
4. Save the database password somewhere safe
5. Wait until the project is ready (about 2 minutes)

## 2. Copy the connection string (you, 1 minute)

Project -> **Connect** -> **Session pooler** -> copy the URI. It looks like:

```
postgresql://postgres.abcdefgh:PASSWORD@aws-0-ap-southeast-1.pooler.supabase.com:5432/postgres
```

If the password contains `@`, write it as `%40`.

## 3. Copy the data (me, one command)

```powershell
cd "C:\Users\User\Documents\Codex\2026-10-14\des-repository-fork-ai\outputs\des-lab"

$env:DESLAB_SOURCE = "postgresql://...the OLD (Sydney) URL..."
$env:DESLAB_TARGET = "postgresql://...the NEW (Singapore) URL..."

.\.venv\Scripts\python.exe migrate_db.py --dry-run   # shows what would be copied
.\.venv\Scripts\python.exe migrate_db.py             # real copy
.\.venv\Scripts\python.exe migrate_db.py --verify    # row counts on both sides must match
```

The script copies `accounts` (including roles, supervisors and expiry dates), `records` (every
experiment row) and `reset_tokens`, keeps all columns, and refuses to write into a target that already
has accounts unless `--force` is passed. A `--verify` run compares the row counts so a half-finished
copy cannot go unnoticed.

## 4. Point the app at the new database (both of us)

**Local** - `.streamlit/secrets.toml`:

```toml
[database]
url = "postgresql://...NEW..."
```

**Cloud** - <https://share.streamlit.io> -> the app -> ⋮ -> Settings -> Secrets: replace the
`[database] url` line, then Save (the app reboots).

## 5. Check it, then retire the old project

1. Open the app, sign in, open **Results** - the rows must be there
2. **Guide -> Where your records live** must say `connected ... rows`
3. Only then pause/delete the old Sydney project in Supabase

## 6. Measure the difference (optional)

```powershell
.\.venv\Scripts\python.exe -c "import os,sys,time,statistics; sys.path.insert(0,'.'); os.environ['DESLAB_DATABASE_URL']='<new url>'; import store; store.count(); t=[time.perf_counter() or 0 for _ in []]; ts=[]; [ (lambda s: (store.count(), ts.append((time.perf_counter()-s)*1000)))(time.perf_counter()) for _ in range(5)]; print('median %.0f ms' % statistics.median(ts))"
```

Before the move the same measurement reports about 200 ms per query; in Singapore it should be well
under 50 ms.

---

## Rollback

Nothing is deleted until step 5. If anything looks wrong, put the old URL back in the secrets - the
old project is untouched and still holds every row.
