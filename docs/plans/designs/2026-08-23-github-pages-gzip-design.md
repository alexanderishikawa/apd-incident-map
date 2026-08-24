# GitHub Pages + gzip export

**Date:** 2026-08-23  
**Status:** Approved (for now; not a long-term data store)

## Why GitHub anyway

Laptop Task Scheduler already pulls/geocodes. The map is a static Vite app. GitHub Pages is the fastest public URL without a new host account.

Raw `incidents.json` is ~88MB (GitHub warns at 50MB, blocks at 100MB). Gzip is ~11MB. GitHub Pages serves `.json.gz` as a download, not `Content-Encoding: gzip`, so the browser must decompress.

## Pipeline

1. `apd export` writes `incidents.json` (local/seed convenience), `incidents.json.gz` (committed), and `meta.json`.
2. Git tracks `incidents.json.gz` + `meta.json`. Uncompressed JSON is gitignored.
3. Site fetches `./data/incidents.json.gz` and inflates with `DecompressionStream`.
4. `apd seed` loads `.json` if present, else `.gz`.
5. Noon `daily.ps1`: seed → pull 7d → geocode 300 → export → commit/push those two data files.
6. GitHub Actions builds `site/` and deploys Pages: `https://alexanderishikawa.github.io/apd-incident-map/`.
7. Repo is public (required for free Pages).

## Out of scope

- History rewrite to purge old 88MB blobs
- GitHub Actions scrape
- Custom domain
