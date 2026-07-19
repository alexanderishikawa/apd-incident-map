# Geocode address normalization — Design

**Date:** 2026-07-18  
**Status:** Approved  
**Parent:** [2026-07-17-apd-incident-map-design.md](2026-07-17-apd-incident-map-design.md)

## Problem

Nominatim rejects a large share of APD location strings as written. Among early attempts, ~32% cached as `fail` (101 fail / 214 ok). Failures cluster on APD dialect, not random API errors:

- `BLOCK` (e.g. `500 BLOCK W 29TH ST`)
- Service roads / directions (`SVRD`, `NB`/`SB`/`EB`/`WB`)
- Highway shorthand (`IH 35`, `US 183 HWY`, `MOPAC EXPY`)
- Intersections (`AIRPORT BLVD / OAK SPRINGS DR`)
- City field `UNINCORP TRAVIS`
- Rare junk (`UNKNOWN`)

Live probes showed many MISS→HIT flips after cleanup (drop `BLOCK`/`SVRD`, rewrite city). Intersections and some I-35 service-road pins still miss after a single clean query.

Across ~51k distinct addresses: ~13% contain `BLOCK`, ~9% slash intersections, ~7% `SVRD`. Burning the cloud backlog **without** normalization would permanently cache many avoidable fails (current code treats `fail` as terminal).

## Goals

1. Normalize APD addresses into Nominatim-friendly query candidates before lookup.
2. Best-effort fallback chain so hard addresses still get a usable point when possible.
3. Keep cache keys stable so export/joins do not break.
4. Allow one-shot retry of existing `fail` rows through the new chain.
5. Count Nominatim HTTP calls against `--budget` (predictable cloud runs).

## Non-goals

- Paid geocoders
- Changing incident `address_raw` in SQLite
- Perfect intersection geometry (centroid / first-leg approx is acceptable)
- Cloud backlog automation in this design (follows after normalize lands)

## Approach (approved): ordered fallback chain

**Cache key:** unchanged — still `address_key()` from incident fields (street, city, zip, TX).

**Lookup:** build ordered, deduped candidate queries; call Nominatim at ≤1 req/s until first HIT or candidates exhausted → then `fail`.

### Candidate generation (`normalize_apd_address` → `list[str]`)

For input cache key `STREET, CITY, [ZIP,] TX`:

1. **Skip junk:** if street is empty / `UNKNOWN` / clearly non-address → return `[]` (immediate fail, no HTTP).
2. **Base clean street:**
   - Remove `\bBLOCK\b`
   - Remove `\bSVRD\b`, `\bNB\b`, `\bSB\b`, `\bEB\b`, `\bWB\b`
   - `IH\s*(\d+)` → `I-\1`
   - Soften `US\s*(\d+)\s*HWY` → `US Highway \1`
   - `EXPY` → `Expressway` (or strip if paired with Mopac cleanup)
   - Collapse whitespace
3. **City clean:** `UNINCORP TRAVIS` (and similar) → `Travis County`
4. **Candidate A — full cleaned:** `cleaned_street, cleaned_city, zip?, TX`
5. **Candidate B — intersection `and`:** if original street had `/`, also emit `leg1 and leg2, city, zip?, TX` (if not identical to A)
6. **Candidate C — first leg only:** if `/` present, `leg1_cleaned, city, zip?, TX`
7. **Candidate D — drop ZIP:** same as best prior form but without ZIP (last resort)

Deduplicate while preserving order.

### Geocoder behavior

- `lookup_nominatim` stays one HTTP call; `Geocoder.run` / new helper tries candidates in order.
- Budget increments **per HTTP request**, not per address.
- First HIT → `upsert_geocode(..., status="ok", lat, lon)`.
- All miss or empty candidate list → `fail`.
- Exceptions on a candidate: treat that candidate as miss and continue to next (optional: on hard HTTP 429/403, abort run). Prefer not marking permanent `fail` on transport errors if no candidates were exhausted cleanly — v1 may keep current “exception → fail” for simplicity unless tests show otherwise; prefer **continue to next candidate on empty JSON, fail only after all candidates**.

### Retry fails

- CLI: `apd geocode --retry-fails`  
  When set, pending queue includes keys with `status=fail` (still recent-first with other pending).
- Successful retry overwrites cache to `ok`.
- Still-missing stays `fail`.

### Cloud backlog (out of this change, sequenced after)

Cursor Cloud Agent chunked runs using raised `--budget`, after normalize + optional `--retry-fails` on existing fails. Do not start mass geocode until this ships.

## Files (expected)

- Modify: `src/apd/geocode.py` — normalize + fallback lookup
- Modify: `src/apd/__main__.py` — `--retry-fails`
- Create: `tests/test_geocode.py` — candidate lists + fallback HIT behavior
- Docs: brief note in README Nominatim section

## Success criteria

- `500 BLOCK W 29TH ST, …` geocodes via cleaned candidate
- `… SVRD NB` arterials often succeed after strip
- `UNINCORP TRAVIS` succeeds via Travis County
- Slash intersections attempt `and` then first-leg fallback
- `UNKNOWN` does not call Nominatim
- `--budget 3` with 2-candidate miss then HIT on 3rd counts 3 attempts
- Existing fails re-attempted only when `--retry-fails` is passed
- Cache key / export join behavior unchanged for already-`ok` rows

## Approval

Approved 2026-07-18 (fallback option 2: best-effort chain).
