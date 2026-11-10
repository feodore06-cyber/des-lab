# Reviewing the running app with a real browser

Claude's normal web reader cannot review this app: the page HTML is an empty shell and the UI is
built in JavaScript after a WebSocket connects. That is why a URL alone returns nothing useful.

## What was measured

Headless Chrome, same URL, two runs:

| Command | Result |
|---|---|
| `chrome --headless=new --screenshot=out.png <url>` | **6.5 KB, blank image** (captured before the app rendered) |
| same, plus `--virtual-time-budget=20000 --run-all-compositor-stages-before-draw` | **58 KB, full sign-in page rendered** |

So the page works in Chrome; it only needs time to render. Any reader that does not execute
JavaScript will always see the blank version. This is a rendering problem, not a URL or key problem.

## The public sign-in page is verifiable from the command line

```powershell
& "C:\Program Files\Google\Chrome\Application\chrome.exe" `
  --headless=new --disable-gpu --hide-scrollbars --window-size=1440,1000 `
  --virtual-time-budget=20000 --run-all-compositor-stages-before-draw `
  --screenshot=login.png "https://appapppy-9ukmar4jdiggrjkenjyffk.streamlit.app/?view=signin"
```

Rendered result: A*STAR lockup, language switch, sign-in form, "Forgot password?", "Create a new
account". This confirms the deployed build is healthy.

## Authenticated pages need a session

The signed-in pages cannot be reached by any crawler, because the session lives in the browser. Two
safe ways to let a reviewer see them:

### Option A — Claude in Chrome (interactive review, recommended)

1. Install the **Claude in Chrome** extension from the Chrome Web Store.
2. Sign in to Claude in that browser profile; open the extension and accept the permissions it asks
   for (tab reading, navigation).
3. Open the app tab and sign in yourself — the reviewer works inside your existing session, so no
   credential is handed over and nothing is made public.
4. In Claude Code, connect the browser control (menu wording depends on your Claude Code version:
   look for "browser", "Chrome" or an MCP entry in `/config` or `/mcp`). If your version has no such
   option, use Option B.
5. Ask for the review with a concrete route list:
   `Projects → open a project → Overview / Formulation / Process / Results / Records`,
   `Compare (paper mode and two-run mode)`, `Recipe Calculator`, `Papers`, `Profile`.

Nothing in the application has to change for this. The extension acts on the tab you already have.

### Option B — screenshot pack (works today, no extension)

Run the app locally, sign in, and capture each page with headless Chrome using a persistent profile:

```powershell
# terminal 1
streamlit run Hello.py --server.port 8600 --server.headless true

# terminal 2 — same profile so the cookie survives between captures
$chrome = "C:\Program Files\Google\Chrome\Application\chrome.exe"
$profile = "$env:TEMP\biomat-review"
# 1) sign in once in a visible window
& $chrome --user-data-dir="$profile" "http://localhost:8600/?view=signin"
# 2) after signing in, capture pages headlessly with the same profile
& $chrome --headless=new --user-data-dir="$profile" --window-size=1440,1000 `
  --virtual-time-budget=20000 --run-all-compositor-stages-before-draw `
  --screenshot=page-projects.png "http://localhost:8600/"
```

`--user-data-dir` keeps the login between runs; `--virtual-time-budget` is what makes the capture
wait for the render. Use a **local** instance for this, so no production data is copied anywhere.

## What not to do

- Do not disable the login to let a reader in.
- Do not publish a demo account on the production app.
- Do not hand over cookies or the database URL.
- Do not add a `?debug=1` bypass.

## Known limitation

Streamlit Community Cloud serves static files under `/app/static/`, not at the domain root, so
`/robots.txt` cannot be served from this app. Public, machine-readable product information lives in
the separate static site under `public-site/` (deploy it with GitHub Pages).
