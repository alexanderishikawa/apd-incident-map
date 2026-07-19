# Geocode Address Normalize Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Normalize APD address dialect into Nominatim query candidates with a best-effort fallback chain, keep cache keys stable, and support retrying existing `fail` rows before cloud backlog clearance.

**Architecture:** Pure functions build ordered query candidates from the existing `address_key()` string; `Geocoder` tries each candidate (1 req/s) until HIT or exhaustion; `--retry-fails` re-queues `status=fail` cache rows. Budget counts HTTP calls.

**Tech Stack:** Python 3, httpx, pytest, SQLite `geocode_cache`

**Design:** [designs/2026-07-18-geocode-address-normalize-design.md](designs/2026-07-18-geocode-address-normalize-design.md)

---

### Task 1: Failing tests for candidate generation

**Files:**
- Create: `tests/test_geocode.py`
- Modify: `src/apd/geocode.py` (only after tests fail)

**Step 1: Write failing tests for `nominatim_candidates`**

```python
from apd.geocode import nominatim_candidates

def test_block_stripped():
    cands = nominatim_candidates("500 BLOCK W 29TH ST, AUSTIN, 78705, TX")
    assert cands[0] == "500 W 29TH ST, AUSTIN, 78705, TX"

def test_svrd_and_dir_stripped():
    cands = nominatim_candidates("204 W BEN WHITE BLVD SVRD WB, AUSTIN, 78704, TX")
    assert "SVRD" not in cands[0].upper()
    assert " WB" not in cands[0].upper() and not cands[0].upper().endswith(" WB")

def test_unincorp_city():
    cands = nominatim_candidates("7400 DAFFAN LN, UNINCORP TRAVIS, 78724, TX")
    assert "Travis County" in cands[0]

def test_intersection_fallbacks():
    cands = nominatim_candidates("AIRPORT BLVD / OAK SPRINGS DR, AUSTIN, 78721, TX")
    assert any(" and " in c for c in cands)
    assert any(c.startswith("AIRPORT BLVD,") or c.startswith("AIRPORT BLVD ,") or "AIRPORT BLVD, AUSTIN" in c for c in cands)

def test_unknown_skips_http_candidates():
    assert nominatim_candidates("UNKNOWN, Austin, TX") == []

def test_ih_normalized():
    cands = nominatim_candidates("2723 S IH 35 SVRD NB, AUSTIN, 78741, TX")
    assert any("I-35" in c for c in cands)
```

**Step 2: Run tests to verify they fail**

Run: `.\.venv\Scripts\pytest tests/test_geocode.py -v`  
Expected: FAIL (import / function missing)

**Step 3: Commit**

```bash
git add tests/test_geocode.py
git commit -m "test: specify nominatim address candidate normalization"
```

---

### Task 2: Implement `nominatim_candidates`

**Files:**
- Modify: `src/apd/geocode.py`

**Step 1: Implement**

Add `nominatim_candidates(key: str) -> list[str]` per design:

- Parse street / city / optional zip / TX (split on `,`)
- Skip if street empty or `UNKNOWN`
- Clean street: drop BLOCK, SVRD, NB/SB/EB/WB; `IH\s*(\d+)` → `I-\1`; `US\s*(\d+)\s*HWY` → `US Highway \1`; `EXPY` → `Expressway`; collapse space
- Clean city: `UNINCORP TRAVIS` → `Travis County` (case-insensitive)
- Build candidates: full cleaned; if `/` in original street → `and` form + first-leg form; drop-ZIP variants last
- Dedupe preserving order

**Step 2: Run tests**

Run: `.\.venv\Scripts\pytest tests/test_geocode.py -v`  
Expected: PASS for candidate tests

**Step 3: Commit**

```bash
git add src/apd/geocode.py tests/test_geocode.py
git commit -m "feat: build Nominatim query candidates from APD addresses"
```

---

### Task 3: Fallback lookup + budget = HTTP calls

**Files:**
- Modify: `src/apd/geocode.py`
- Modify: `tests/test_geocode.py`

**Step 1: Write failing test with mock client**

Use httpx MockTransport or a tiny stub client that returns empty JSON for first N URLs and a HIT for a later query. Assert:

- `run(budget=10)` marks `ok` when HIT is on candidate 3
- `attempted` (or equivalent stats) equals number of HTTP GETs
- Cache key remains the **raw** address_key passed in (insert via pending from a fake incident or call internal resolve)

Also test: all candidates miss → `fail`; `UNKNOWN` → `fail` with `attempted == 0`.

**Step 2: Run test — expect FAIL**

**Step 3: Implement**

In `Geocoder.run`:

- For each pending key, `cands = nominatim_candidates(key)`
- If empty → upsert fail, continue (no HTTP)
- Else loop candidates; each `lookup_nominatim` increments attempted; break on HIT
- Exhaustion → fail

**Step 4: pytest PASS**

**Step 5: Commit**

```bash
git commit -m "feat: geocode via candidate fallback chain; budget counts HTTP"
```

---

### Task 4: `--retry-fails` CLI

**Files:**
- Modify: `src/apd/geocode.py` (`pending_keys` or `run` accept `retry_fails: bool`)
- Modify: `src/apd/__main__.py`
- Modify: `tests/test_geocode.py`

**Step 1: Failing test**

Seed DB: one incident + `geocode_cache` row `fail` for its key. With `retry_fails=False`, pending skips it. With `True`, it is attempted and can become `ok` via mock HIT.

**Step 2: Implement**

- `Geocoder.pending_keys(retry_fails: bool = False)`
- CLI: `p_geo.add_argument("--retry-fails", action="store_true")`
- Pass through to `run` / `pending_keys`

**Step 3: pytest PASS + commit**

```bash
git commit -m "feat: apd geocode --retry-fails to requeue cache misses"
```

---

### Task 5: README + smoke

**Files:**
- Modify: `README.md` (Nominatim section)

**Step 1: Document**

- Address cleanup + fallbacks
- `apd geocode --budget N --retry-fails`
- Note: run `--retry-fails` once locally before/during cloud backlog

**Step 2: Local smoke (optional if network ok)**

```powershell
.\.venv\Scripts\apd geocode --budget 20 --retry-fails
```

Spot-check a few former fails flipped to `ok` in sqlite.

**Step 3: Commit**

```bash
git commit -m "docs: geocode normalization and --retry-fails"
```

---

### Task 6: Stop — cloud backlog is separate

Do **not** start Cursor Cloud mass geocode in this plan. After merge, a follow-up plan/agent run can chunk `geocode --budget …` (+ initial `--retry-fails`) and commit exports.

---

## Verification checklist

- [ ] `pytest tests/test_geocode.py -v` green
- [ ] Full `pytest` still green
- [ ] Manual: BLOCK / SVRD / unincorp improve; UNKNOWN no HTTP
- [ ] Export join still uses same `address_key()`
