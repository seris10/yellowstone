# Spec: tools/audit_provenance.py — mechanical standing-rules check over derived/

Status: spec (authored 2026-10-10, pycl-2). Transferred claims cite file:line verified 2026-10-10; authored claims marked [AUTHORED].
No code written; no deletions. Target: `tools/audit_provenance.py` in `../../yellowstone_python/`.

## 1. Purpose + non-goals

Purpose: mechanical check that every `derived/*.json` artifact honors the standing provenance rules — schema string present, status present and spelled from the in-use vocabulary, `write_sidecar` wrapper shapes where applicable — and reports failures vs the build's existing fail-only model. Today `check_provenance` (`yellowstone_python/common/validate.py:45-51`) checks only key PRESENCE, and `write_sidecar` (`yellowstone_python/common/provenance.py:41-58`) accepts ANY status string (no enum). Three artifacts carry NO status at any depth (`sinter_grass_cull`, `sinter_tree_cull_2026-10-09.json`, `usgs_06036805.json`); the sidecar default `"illustrative, not calibrated"` (comma, `provenance.py:43`) appears NOWHERE in `derived/` (closest stored is `illustrative_not_calibrated`, aquatic only).

Non-goals: no rewriting artifacts to add status (audit reports; a later session backfills); no warning level (repo has none — `CHECKS.json` has only `passed/failures`, `build.py:571-633`); no semantic review of whether a label is TRUE (mechanical spelling/presence only).

## 2. CLI (`--help` text drafted)

```
usage: audit_provenance.py [--dir PATH] [--out PATH] [--strict]

Audit provenance labels over derived/ artifacts. Exit 0: all artifacts pass.
Exit 1: one or more failures (report still written to --out when given).
Exit 2: bad invocation.

options:
  --dir PATH   artifact directory (default: derived)
  --out PATH   write audit report JSON (atomic .tmp+replace)
  --strict     also fail on nested-status anomalies (default: top-level only)
```

House pattern: `sys.path.insert`, `argparse`, `raise SystemExit(main())` (`tools/cross_sections.py:23,148,174-175`).

## 3. Inputs / outputs with exact schemas

Input: every top-level `derived/*.json` (16 files today). Per-file expectations derived from measurement (transferred):
- Must carry a `schema` key matching `yellowstone.<name>.v1` — EXCEPT `usgs_06036805.json` (keys `discharge_iv, fetched_at, measurements, site, temperature_iv`; no schema) and `llm_snapshot.json` (keys `accuracy_notes, census, contract, ecosystem, generated_utc, latest_build, limitations, placements, sources, world_id`; no top-level status). These two are allowlisted as legacy, not failed [AUTHORED].
- Must carry top-level `status` — EXCEPT the two legacy files above. Known-missing today (will fail until backfilled): `sinter_grass_cull_2026-10-09.json`, `sinter_tree_cull_2026-10-09.json`.

Status vocabulary actually in use (exact, all 8 distinct strings measured across 28 occurrences — audit matches against THIS list, not a guessed enum):
1. `measured_remote_not_calibrated` (firehole, snotel tops)
2. `fitted_not_validated_single_window` (all fit tops + nested)
3. `illustrative_not_calibrated` (aquatic top only)
4. `numerical_experiment_not_field_validation` (dispersion top)
5. `detection unreviewed; pool-rim artifacts excluded; not a placement authority` (census top)
6. `authored_illustrative_effective_mixing_volume` (nested, lsfit/uq)
7. `authored_illustrative_effective_mixing_volume; see sensitivity in parameter_notes` (nested, reach_fit ×4)
8. `Illustrative, dimensioned observational model. ...` (nested, llm_snapshot only)

Output report schema `yellowstone.provenance_audit.v1` [AUTHORED]: `{schema, status: <audit's own label, see §5>, dir, n_files, passed: bool, failures: [{file, rule, found}], legacy_allowlist: [files]}`.

## 4. Algorithm / rules in numbered steps

1. Enumerate `--dir/*.json` top level only (sorted). Non-JSON or unreadable → failure `unreadable`.
2. For each file: parse; record top-level `schema` (absent → `missing-schema` unless allowlisted).
3. Record top-level `status` (absent → `missing-status` unless allowlisted).
4. If `status` present: exact-match against the §3 vocabulary list. No match → `unknown-status` (fail) — with `--strict`, also apply steps 2-4 to every nested `status` at any depth.
5. `write_sidecar`-shape check [AUTHORED, mechanical]: if file carries `contract_version`, require all of `world_id, code_rev, parameter_provenance, sources` (the six keys `check_provenance` enforces, `common/validate.py:45-51`); missing → `incomplete-sidecar`.
6. Cross-check `fetched_at_utc` pointers where applicable (informational, never failing): fit artifacts embedding a bundle timestamp must match a `derived/*obs*.json` `fetched_at_utc` (today all reach fits pin `2026-10-10T01:02:29...`, snow fit pins `2026-10-10T06:31:26...`). Mismatch → `stale-bundle-pointer` failure [AUTHORED].
7. Write report atomically; exit 0 iff zero failures.

## 5. Provenance plan

The audit report's own `status`: `measured_remote_not_calibrated` is wrong (it measures nothing remote) and `fitted_*` is wrong (it fits nothing) — use `authored_standing_rules_check` [AUTHORED, new string, documented here as the first of its kind]. Report lists `legacy_allowlist` explicitly so allowlisting is auditable, not silent.

## 6. Error handling

| Failure mode | Exit | Message |
|---|---|---|
| Bad flags / missing dir | 2 | `parser.error` |
| Unreadable file | 1 | `unreadable: <file>: <exc>` |
| Missing/unknown schema/status | 1 | `<rule>: <file>: found <value>` |
| `--out` unwritable | 1 | verdict to stdout (same fallback as validate_obs_bundles) |

## 7. Tests (synthetic/offline only)

1. `test_all_live_pass_except_known` — run over a fixture dir copying the §3 expectations: assert exactly the known-missing files fail (`sinter_*` ×2) and legacy two pass via allowlist. (Runs against fixture COPIES, not live `derived/`, so backfills don't break it.)
2. `test_unknown_status_fails` — fixture with `status: calibrated` → `unknown-status`.
3. `test_comma_default_flagged` — fixture with `status: "illustrative, not calibrated"` (the sidecar default) → `unknown-status` (documents that the code default matches nothing stored).
4. `test_incomplete_sidecar_fails` — `contract_version` without `sources` → `incomplete-sidecar`.
5. `test_stale_pointer_fails` — fit fixture with non-matching bundle timestamp → `stale-bundle-pointer`.
6. `test_strict_nested` — nested bad status passes default, fails `--strict`.
7. `test_report_atomic` — `--out` written via `.tmp`+replace, parses, schema `yellowstone.provenance_audit.v1`.

## 8. Acceptance criteria

- [ ] Vocabulary list in code cites this spec's 8 strings; no other status spellings accepted without a spec update.
- [ ] Live `derived/` run reported (informational): expect exactly `sinter_*` missing-status + legacy allowlist of 2; anything else is a finding, not a code bug.
- [ ] No artifact modified; suite green.

## 9. Effort + dependencies

Effort: S (~120 lines + tests; pure stdlib). Dependencies: none. Follow-up (NOT this tool): backfill `status` into `sinter_*` + decide `usgs_06036805.json` schema — separate session, listed as open.
