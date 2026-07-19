# apd-incident-map

Scrape Austin PD’s public [Incident Reports](https://services.austintexas.gov/police/reports/alt_search.cfm) database into SQLite, geocode with Nominatim (recent-first), and publish a static MapLibre map with filters.

**Source horizon:** ~18 months (CFM). Not a 3-year archive.

## Setup

```powershell
python -m venv .venv
.\.venv\Scripts\pip install -e ".[dev]"
cd site
npm install
```

## Commands

```powershell
# Last 7 offense-date days (idempotent upsert)
.\.venv\Scripts\apd pull --last-days 7

# Historical backfill (newest → oldest, resumable)
.\.venv\Scripts\apd pull --historical

# Geocode pending addresses (≤1 req/s; cache forever)
.\.venv\Scripts\apd geocode --budget 300

# Re-try addresses previously marked fail (after normalizer improvements)
.\.venv\Scripts\apd geocode --budget 300 --retry-fails

# Export site/public/data/{incidents,meta}.json
.\.venv\Scripts\apd export

# Map
cd site
npm run dev
```

Daily script: `scripts/daily.ps1` (or `scripts/daily.sh`).

Geocode backlog chunks (laptop or Cursor Cloud): `scripts/geocode_backfill.sh`  
`GEOCODE_BUDGET=2000 GEOCODE_RETRY_FAILS=1 APD_GIT_PUSH=1 ./scripts/geocode_backfill.sh`  
(~51k unique addresses ≈ many ~30–40 min chunks at 1 req/s; progress persists via committed export.)

## Filters

Offense types and ZIPs are built from **pulled data** (`meta.json`), not the outdated CFM offense dropdown.

## Design / plan

- `docs/plans/designs/2026-07-17-apd-incident-map-design.md`
- `docs/plans/2026-07-17-apd-incident-map.md`
- `docs/plans/designs/2026-07-18-geocode-address-normalize-design.md`

## Nominatim

Public Nominatim requires a descriptive User-Agent and ≤1 request/second. Results are cached in SQLite. Prefer recent incidents; historical geocoding only uses spare daily budget.

APD location strings are normalized before lookup (drop `BLOCK` / `SVRD` / NB–WB, rewrite `IH`→`I-`, `UNINCORP TRAVIS`→Travis County). Intersections try `A and B`, then the first leg, then drop-ZIP variants. `--budget` counts Nominatim HTTP calls. Use `--retry-fails` once after normalizer changes so old misses are re-queued.
