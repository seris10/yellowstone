# Adversarial review: Yellowstone LLM backend (fresh session prompt)

You are doing a hostile code review of a small local HTTP backend. Your job is to
break it, not praise it. Report only findings you have reproduced by execution.

## Scope (read these first, absolute paths)

- `/Users/kreed/Downloads/yellowstone_python/yellowstone_python/llm_backend.py` (~400 lines, the whole backend)
- `/Users/kreed/Downloads/yellowstone_python/tests/test_llm_backend.py` (its tests)
- `/Users/kreed/Downloads/yellowstone_python/README.md` (last section documents it)
- Data it reads (do not modify): `/Users/kreed/Downloads/yellowstone_midway/data/*.json`,
  `/Users/kreed/Downloads/yellowstone_python/derived/census.json` (~6 MB, 33,764 records)

## What it is

Stdlib-only (`ThreadingHTTPServer`, no dependencies) read-only JSON API on
`127.0.0.1`, plus a `--snapshot-out` static-bundle CLI. Endpoints:
`GET /api/snapshot /api/census/zones /api/density?x=&z=&r= /api/compare?x=&z=&r=`
`/api/placements/summary /api/ecosystem/summary /api/build/latest`, `POST /api/propose`
(dry-run planting review, must never write). It imports `canopy_census`,
`vegetation`, `pool_crust`, `review_proposals` from the same package for math only.

## Environment

- Interpreter with deps: `/opt/homebrew/bin/python3.13` (numpy/scipy/matplotlib/PIL/yaml/pytest)
- Workdir: `/Users/kreed/Downloads/yellowstone_python`
- Tests: `/opt/homebrew/bin/python3.13 -m pytest tests/test_llm_backend.py -q`
- Serve: `/opt/homebrew/bin/python3.13 -m yellowstone_python.llm_backend --serve --port 8765`

## Already found and fixed (do NOT re-report; find NEW issues)

1. `circle_stats` divided by zero on `r=0` (HTTP 500) and accepted negative radii.
2. `POST /api/propose` accepted centers kilometers outside the world (e.g. 99999,99999)
   and returned junk records that could flow into `placement_overrides.json`.
3. Missing guards: non-positive matching tolerance and `area_ha=0` in the sibling
   statistics module. (Different files, mentioned only so you don't duplicate.)

## How to attack it (verify every claim by running code)

1. **Math correctness**: is `circle_stats`/`compare`/`zones` right? Hand-check one zone
   against an independent computation. Is the deficit interpretation honest?
2. **Input validation**: fuzz every endpoint (`r=0`, negative, NaN, `inf`, strings,
   missing params, huge `count`/`radius_m`, unknown guilds, malformed POST bodies,
   wrong Content-Type, huge bodies). Anything 500? Anything returning plausible-but-wrong data (worse than a crash)?
3. **Read-only guarantee**: prove `POST /api/propose` cannot write — check every import
   it touches for file writes, and diff the data dir before/after hostile calls.
4. **Concurrency**: hammer it with parallel requests; the census cache uses a bare
   mtime check with no lock. Can you produce a torn read, a crash, or unbounded
   memory growth (each `/api/snapshot` re-hashes multi-MB files and reloads JSON)?
5. **Data-scale traps**: time `/api/snapshot` cold vs warm; check response sizes;
   confirm no endpoint loads `terrain.f32` or full census more than necessary.
6. **Test quality**: do the tests assert behavior or tautologies? Would they catch a
   regression that swaps observed/placed, drops a zone, or changes units? Write a
   failing-then-passing demonstration if you claim a gap (do not commit it without asking).
7. **Assumption drift**: the backend assumes file schemas (`position:[x,y,z]`,
   `kind: pine`, census `stable_id` format). Which assumptions are unchecked, and what
   happens when a file violates them (KeyError → 500? silent wrong numbers?)?

## Rules

- Do NOT edit any files. Report only.
- Every finding needs: severity (crash / wrong-data / perf / test-gap / assumption),
  `file:line`, a minimal repro command with observed output, and a concrete suggested fix.
- Rank findings by "an LLM acting on this output could corrupt game data" first.
- Distinguish "reproduced" from "suspected" — suspected-only items go in a separate short list.
- End with a one-paragraph verdict: fit for purpose as an LLM-facing accuracy tool, or not, and why.
