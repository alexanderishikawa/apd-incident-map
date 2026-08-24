# apd-incident-map

Data pipeline + static web map for Austin PD incident reports. Two components:
- `apd` — Python CLI ETL (`src/apd/`): scrape APD → geocode via Nominatim → export JSON.
- `apd-incident-map-site` — Vite + TypeScript + MapLibre static frontend (`site/`).

See `README.md` for the full command reference.

## Cursor Cloud specific instructions

- Python lives in a virtualenv at `.venv`. `README.md` shows Windows PowerShell paths (`.\.venv\Scripts\...`); on this Linux VM use `.venv/bin/` instead, e.g. `.venv/bin/apd export`, `.venv/bin/pytest`.
- `python3 -m venv` requires the `python3.12-venv` apt package (installed in the base image); it is a system dependency, not a pip package.
- Tests: `.venv/bin/pytest` (from repo root). They mock HTTP with `respx`, so they need no network.
- The site reads committed `site/public/data/incidents.json.gz` and `meta.json`. To (re)build that data offline from the committed seed, run `.venv/bin/apd seed` (loads gzipped or uncompressed export into a fresh SQLite DB at `data/incidents.sqlite`) then `.venv/bin/apd export`. Uncompressed `incidents.json` is gitignored (local-only). `data/*.sqlite` is gitignored and auto-created.
- `apd pull` (APD site) and `apd geocode` (Nominatim, ≤1 req/s) require outbound internet; they are only needed to refresh live data, not to run/view the map.
- Dev server: `cd site && npm run dev` serves on port 5173 (`npm run preview` → 4173, `npm run build` → `site/dist/`). Map background tiles load from `tile.openstreetmap.org`, so the OSM basemap needs outbound internet; incident markers/clusters and filters work regardless.
