# APD Incident Map — Design

**Date:** 2026-07-17  
**Status:** Approved  
**Implementation home:** standalone sibling project `apd-incident-map/` (next to `lukrative-media`), not inside the monorepo app tree.

## Goals

1. Full historical pull of the APD public Incident Reports DB (`services.austintexas.gov/police/reports`) for whatever horizon the source still holds (~18 months; **not** 3 years — CFM returns empty before ~2025-01).
2. Daily, idempotent pull of the last 7 offense-date days (~12:00 local) to catch late-filed reports.
3. Static, deployable incident map with a filter panel (no NL agent chat in v1).

## Non-goals (v1)

- Open-data hybrid / 3-year SODA backfill
- Natural-language query chat
- Paid geocoders (Mapbox/Google)
- Live on-demand scraping from the map UI
- Officer narratives (not present on public cards)

## Source facts (validated)

- Entry: ack session on `alt_search.cfm` → `search2.cfm`
- Freest query: date window only  
  `startdate=YYYY-MM-DD&numdays=0..6&choice=criteria&Submit=Submit`
- `numdays` clamped to 0–6; offense-date oriented search
- Public card fields: case #, report/offense datetimes, offenses[], location, census tract, district, area command, property pairs
- Offense dropdown on advance search is incomplete (e.g. no MAIL THEFT); filters must use vocabulary from pulled data
- Area Command letter codes in the form are largely unreliable; do not depend on them for coverage
- Incapsula + ColdFusion session cookies required

## Architecture (Approach A)

```text
CFM HTML  →  Python ETL  →  SQLite  →  export JSON/meta  →  Vite + MapLibre static site
                ↑
         Nominatim cache (recent-first geocode queue)
```

Daily Cursor Automation runs midday: pull 7 days → geocode budget → export → commit/publish data artifacts.

## Repo layout

```text
apd-incident-map/
  README.md
  pyproject.toml
  src/apd/
    client.py      # session ack + search2 pulls
    parse.py       # HTML → incident dicts
    db.py          # SQLite schema + upsert
    pull.py        # historical + daily windows
    geocode.py     # Nominatim queue
    export.py      # SQLite → site/public/data
  data/            # gitignored sqlite
  site/            # Vite + MapLibre
  scripts/daily.sh
  tests/
```

## Data model

### `incidents` (PK / upsert: `case_number`)

| Field | Notes |
|-------|--------|
| case_number | e.g. `2026-5010278` |
| report_datetime | parsed from card |
| offense_datetime | parsed from card |
| offenses | JSON array of strings |
| location_raw | full Offense Location line (whitespace-normalized) |
| address_raw, apt, city, zip | parsed from location |
| district_zone | card "District" (e.g. `1`) |
| area_command | card text (e.g. `SOUTH WEST`) |
| census_tract | string |
| property | JSON array of `{status, type}` e.g. `[{"status":"STOLEN","type":"OTHER"}]` |
| source_hash | hash of canonical payload for change detection |
| pulled_at | timestamp |

Optional later: `raw_html` blob — **not** in v1 unless re-parse pain appears.

### `geocode_cache`

`address_key` (normalized), lat, lon, status (`ok`/`fail`/`pending`), provider (`nominatim`), updated_at

### `pull_runs`

window_start, window_end, status, rows_upserted, error, finished_at

## Pipelines

### Historical backfill

- Walk newest → oldest in 7-day windows until empty / cliff
- Resumable via `pull_runs`
- Geocode does not block pull; separate queue prioritizes recent ungeocoded rows; older addresses only when budget remains

### Daily (~12:00 local)

1. `pull --last-days 7` (idempotent upsert)
2. `geocode --budget N` (recent-first; spare capacity → backfill)
3. `export` → `site/public/data/`
4. Automation commits/publishes if git-hosted

### Geocode policy

- Public Nominatim ≤ 1 req/s; identify User-Agent; cache all results
- Failures remain list-visible without map points

## Map + filters (static site)

- MapLibre + OSM/compatible tiles
- Filters (from export `meta.json` + row scan): date range, **offense types from DB**, **ZIP**, zone, area command, text (address/case)
- Checkbox: show ungeocoded in side list
- Clusters when zoomed out
- Footer: last pull time, geocode coverage
- Deploy: GitHub Pages / Cloudflare Pages (choose at publish time)

## Automation

- Cursor Automation: daily ~12:00 local
- Scope: sibling repo `apd-incident-map`
- Instructions: run daily script; commit data export changes; report counts/errors

## Risks / mitigations

| Risk | Mitigation |
|------|------------|
| Source drops history / WAF blocks | Soft retries; alert on zero-row days; keep local SQLite |
| Export size large | Monthly shards or gzip; revisit if needed |
| Nominatim slow / policy | Recent-first; capped daily budget; optional self-host later |
| Parser drift | Golden HTML fixtures in tests; `source_hash` detects field changes |

## Example structured row

```json
{
  "case_number": "2026-5010278",
  "report_datetime": "Thu, Jul-16-2026 18:03",
  "offense_datetime": "Wed, Jul-15-2026 22:00",
  "offenses": ["MAIL THEFT"],
  "location_raw": "2301 PERRY AVE, Apt # 103, AUSTIN 78704",
  "address_raw": "2301 PERRY AVE",
  "apt": "103",
  "city": "AUSTIN",
  "zip": "78704",
  "district_zone": "1",
  "area_command": "SOUTH WEST",
  "census_tract": "13.12",
  "property": [{"status": "STOLEN", "type": "OTHER"}]
}
```

## Approval

- Approach A (SQLite + Python ETL + static map): approved
- CFM-only ~18 mo: approved
- Nominatim recent-first: approved
- Filter panel (incl. ZIP + DB-derived offenses): approved
- Schema with `location_raw` + structured `property`: approved
- Midday daily automation: approved
