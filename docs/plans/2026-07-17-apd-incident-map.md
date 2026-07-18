# APD Incident Map Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Standalone `apd-incident-map` project that scrapes APD’s public incident DB into SQLite, geocodes with Nominatim (recent-first), exports static data, and ships a filterable MapLibre map — plus a midday daily pull automation.

**Architecture:** Python ETL (session ack → `search2.cfm` date windows → parse cards → upsert SQLite) + Nominatim cache queue + Vite/MapLibre static site reading exported JSON/meta. Historical backfill newest→oldest; daily job re-pulls last 7 days idempotently.

**Tech Stack:** Python 3.11+, httpx/urllib, BeautifulSoup, SQLite, pytest; Vite, TypeScript, MapLibre GL; Cursor Automation (cron ~12:00).

**Design:** @docs/plans/designs/2026-07-17-apd-incident-map-design.md

**Project root:** `../apd-incident-map` relative to `lukrative-media` (sibling directory). Create as its own git repo.

---

### Task 1: Scaffold sibling project

**Files:**
- Create: `apd-incident-map/README.md`
- Create: `apd-incident-map/pyproject.toml`
- Create: `apd-incident-map/.gitignore`
- Create: `apd-incident-map/src/apd/__init__.py`
- Create: `apd-incident-map/src/apd/__main__.py`

**Step 1: Create directory and git repo**

```bash
mkdir -p ../apd-incident-map/src/apd ../apd-incident-map/tests ../apd-incident-map/data ../apd-incident-map/scripts
cd ../apd-incident-map && git init
```

**Step 2: Write `.gitignore`**

Ignore `data/*.sqlite`, `data/*.sqlite-*`, `site/dist/`, `node_modules/`, `.venv/`, `__pycache__/`, `.env`.

**Step 3: Write minimal `pyproject.toml`**

Package name `apd`, deps: `beautifulsoup4`, `httpx`, `pytest`. Script entry: `apd = apd.__main__:main`.

**Step 4: README with design summary + commands**

Document: `apd pull`, `apd geocode`, `apd export`, historical vs daily.

**Step 5: Commit**

```bash
git add -A && git commit -m "chore: scaffold apd-incident-map project"
```

---

### Task 2: SQLite schema + upsert

**Files:**
- Create: `apd-incident-map/src/apd/db.py`
- Create: `apd-incident-map/tests/test_db.py`

**Step 1: Write failing tests for upsert by case_number and property JSON**

```python
def test_upsert_incident_idempotent(tmp_path):
    db = Database(tmp_path / "t.sqlite")
    row = sample_incident()
    db.upsert_incident(row)
    db.upsert_incident({**row, "area_command": "SOUTH WEST"})
    assert db.count_incidents() == 1
    assert db.get_incident(row["case_number"])["area_command"] == "SOUTH WEST"
```

**Step 2: Run test — expect FAIL**

Run: `pytest tests/test_db.py -v`

**Step 3: Implement `Database` with tables `incidents`, `geocode_cache`, `pull_runs`**

Fields per design doc (`location_raw`, `property` JSON, `source_hash`, etc.).

**Step 4: Tests PASS — commit**

```bash
git commit -m "feat: add sqlite schema and incident upsert"
```

---

### Task 3: HTML parser (golden fixtures)

**Files:**
- Create: `apd-incident-map/src/apd/parse.py`
- Create: `apd-incident-map/tests/fixtures/card_mail_theft.html` (saved from live `caseno=2026-5010278`)
- Create: `apd-incident-map/tests/fixtures/day_snippet.html` (optional multi-card)
- Create: `apd-incident-map/tests/test_parse.py`

**Step 1: Capture fixture HTML once (manual or script), commit fixtures**

**Step 2: Failing test — parse MAIL THEFT card**

Assert: case_number, report/offense datetimes, offenses==["MAIL THEFT"], location_raw contains PERRY, apt/city/zip, property==[{"status":"STOLEN","type":"OTHER"}], district_zone, area_command, census_tract.

**Step 3: Implement `parse_search_results(html) -> list[dict]`**

Normalize whitespace in `location_raw`; structured property pairs; multi-offense lists.

**Step 4: Tests PASS — commit**

```bash
git commit -m "feat: parse APD incident HTML cards"
```

---

### Task 4: CFM client (ack + date search)

**Files:**
- Create: `apd-incident-map/src/apd/client.py`
- Create: `apd-incident-map/tests/test_client.py` (mock httpx responses)

**Step 1: Failing tests with respx/httpx mock**

- ack POST then search GET returns fixture HTML
- ack bounce re-acks once

**Step 2: Implement `ApdClient`**

- Cookie jar session
- `acknowledge()`
- `search_window(start: date, numdays: int) -> str` HTML
- `lookup_case(caseno: str) -> str` HTML
- User-Agent identifying the app

**Step 3: Tests PASS — commit**

```bash
git commit -m "feat: add APD CFM session client"
```

---

### Task 5: Pull command (historical + last-N days)

**Files:**
- Create: `apd-incident-map/src/apd/pull.py`
- Create: `apd-incident-map/tests/test_pull.py`
- Modify: `apd-incident-map/src/apd/__main__.py`

**Step 1: Failing tests**

- Window iteration newest→oldest stops after N empty days
- Upsert counts recorded in `pull_runs`
- `--last-days 7` only touches that range

**Step 2: Implement CLI**

```bash
apd pull --last-days 7 --db data/incidents.sqlite
apd pull --historical --db data/incidents.sqlite
```

Use `numdays=6` chunks; sleep briefly between requests; resume skipping successful `pull_runs`.

**Step 3: Live smoke (optional, manual): pull 1 day — expect ~200–350 rows**

**Step 4: Commit**

```bash
git commit -m "feat: add historical and daily pull commands"
```

---

### Task 6: Geocode queue (Nominatim, recent-first)

**Files:**
- Create: `apd-incident-map/src/apd/geocode.py`
- Create: `apd-incident-map/tests/test_geocode.py`

**Step 1: Failing tests**

- Address key normalization stable
- Budget stops after N lookups
- Priority: newest offense_datetime first
- Cache hit skips HTTP

**Step 2: Implement**

- ≤1 req/s; valid User-Agent + contact email in README/env
- Query Nominatim with city/state bias `Austin, Texas`
- Write `geocode_cache`; join on export

**Step 3: Commit**

```bash
git commit -m "feat: nominatim geocode queue with cache"
```

---

### Task 7: Export for static site

**Files:**
- Create: `apd-incident-map/src/apd/export.py`
- Create: `apd-incident-map/tests/test_export.py`

**Step 1: Failing test — export writes `incidents.json` + `meta.json`**

`meta.json` must include sorted distinct `offenses`, `zips`, `zones`, `area_commands`, `last_pulled_at`, counts.

**Step 2: Implement export to `site/public/data/`**

Include lat/lon when geocode ok; `geocode_status` otherwise.

**Step 3: Commit**

```bash
git commit -m "feat: export incidents and filter meta for site"
```

---

### Task 8: Vite + MapLibre map with filters

**Files:**
- Create: `apd-incident-map/site/package.json`
- Create: `apd-incident-map/site/vite.config.ts`
- Create: `apd-incident-map/site/index.html`
- Create: `apd-incident-map/site/src/main.ts`
- Create: `apd-incident-map/site/src/map.ts`
- Create: `apd-incident-map/site/src/filters.ts`
- Create: `apd-incident-map/site/src/styles.css`

**Step 1: Scaffold Vite TS app; add maplibre-gl**

**Step 2: Load `/data/incidents.json` + `meta.json`**

**Step 3: Filter panel**

- Date range (offense)
- Multi-select offenses (from meta)
- Multi-select zips (from meta)
- Zone + area command
- Text search (address / case)
- Show ungeocoded in list

**Step 4: Map clusters + popup fields**

**Step 5: Footer status (last pull, geocode %)**

**Step 6: Commit**

```bash
git commit -m "feat: add MapLibre site with filter panel"
```

---

### Task 9: Daily script + README runbook

**Files:**
- Create: `apd-incident-map/scripts/daily.sh` (or `daily.ps1` for Windows)
- Modify: `apd-incident-map/README.md`

**Step 1: Script runs pull → geocode --budget 300 → export**

**Step 2: Document backfill, hosting (Pages/Cloudflare), Nominatim etiquette**

**Step 3: Commit**

```bash
git commit -m "chore: add daily pull script and runbook"
```

---

### Task 10: Cursor Automation draft

**Files:** none in repo (Automations editor)

**Step 1: Draft automation**

- Name: APD incident daily pull  
- Trigger: cron daily 12:00 (user local)  
- Repo: `apd-incident-map`  
- Instructions: checkout; run daily script; commit `site/public/data/*` if changed; summarize row counts / errors  

**Step 2: Open Automations editor with prefill after user confirms**

**Step 3: User finishes any deferred git/publish settings in editor**

---

### Task 11: First live historical pull (ops)

**Step 1: Run `apd pull --historical` overnight-friendly; monitor `pull_runs`**

**Step 2: Run geocode with budget until recent week is mostly plotted**

**Step 3: `apd export` + `npm run build` in `site/`; verify filters (ZIP, MAIL THEFT)**

**Step 4: Note commit of sample export only if data license/size OK — prefer gitignoring large JSON and publishing via CI artifact/Pages from Actions**

---

## Verification checklist

- [ ] Parser fixtures cover MAIL THEFT + multi-offense + intersection address  
- [ ] `pull --last-days 7` twice → stable counts (idempotent)  
- [ ] Offense/ZIP filter options come from data, not CFM dropdown  
- [ ] Map plots geocoded points; ungeocoded appear in list  
- [ ] Daily automation dry-run succeeds  

## Out of scope reminders

- No NL chat agent  
- No paid geocoder  
- No open-data backfill past CFM cliff  
