# fixes-26 ledger
Doc: fixes/fixes-26-analysis-store-sqlite.md | read 2026-10-12 | targets: yellowstone_python/yellowstone_python/analysis_store.py sha256:fea25c966111 ; tools/build_store.py sha256:19f2c7e150a0 ; yellowstone_python/yellowstone_python/llm_backend.py sha256:93e7c4720df7 ; tests/test_analysis_store.py sha256:9bec034b92a0
Summary: 15 items: 15 implemented, 0 shortcut, 0 partial, 0 missing, 0 superseded, 0 conflicts (recounted from rows 2026-10-13)

| item | requirement (one line) | verdict | evidence file:line | note (one line) | cost cheap/medium/refactor |
|---|---|---|---|---|---|
| 1 | ingest_census: `INSERT OR REPLACE` path reachable; test_duplicate_stable_id passes | implemented | analysis_store.py:147-181; tests/test_analysis_store.py:369-386 | duplicate stable_id replaces old rtree row | cheap |
| 2 | Backend.store_path matches newest CHECKS.json; audit --audit-stores | implemented | llm_backend.py:store_path reads newest derived/<id>/CHECKS.json by mtime, matches analysis_*.sqlite whose meta.build_id equals that id (sqlite URI read-only); mtime fallback retained; audit --audit-stores already shipped by E2-a2 | mtime-selection path replaced by build-id match | medium |
| 3 | chmod store read-only after build; audit unknown tables | implemented | analysis_store.py:523-528; tests/test_analysis_store.py:456-485; notebooks/census_explorer.ipynb opens the store with file:...?mode=ro URI plus PRAGMA query_only=ON | out.chmod drops write bits after atomic replace; notebook now opens read-only; audit-side changes handed off (D3-c) | cheap |
| 4 | ingest_firehole hardens shape, rejects duplicate divergent epoch, non-finite | implemented | analysis_store.py:226-269 | _ingest_firehole_series validates list shape, uses _finite_float; duplicate-divergent raises | medium |
| 5 | ingest_replay requires geometry fields; nonpositive volume raises | implemented | analysis_store.py:184-224; tests/test_analysis_store.py:487-498 | required-field list enforced; nonpositive volume/length/width/depth and inverted s rejected | medium |
| 6 | _open does not flip query_only on caller-owned connection | implemented | analysis_store.py:620-628 | caller connection returned as-is; path only opens read-only URI | cheap |
| 7 | query ORDER BY uses explicit mapping; fits_reach champion first; index on nulls | implemented | analysis_store.py:576-589, 108; tests/test_analysis_store.py:521-537 | ORDER_BY dict spliced in; CREATE INDEX fits_reach_nulls_src_name added | cheap |
| 8 | query filter for evidence_class on census_trees | implemented | analysis_store.py:683-687; tests/test_analysis_store.py:540-559 | validates nonempty string, adds WHERE clause | cheap |
| 9 | circle count semantics named (center vs crown overlap) | implemented | analysis_store.py:808-862; tests/test_analysis_store.py:597-610 | census_center_count and census_crown_overlap_count defined; census_circle_count kept as alias | medium |
| 10 | fits_reach records fit window + n_train/n_holdout, nulls record k | implemented | analysis_store.py:94-108, 320-358; tests/test_analysis_store.py:501-519 | window_start/end_epoch, n_train/n_holdout, k columns added and populated | medium |
| 11 | ingest_snow_fit rejects wind_loss outside [0,1]; records holdout window | implemented | analysis_store.py:362-399; tests/test_analysis_store.py:574-591 | holdout_start_day/holdout_end_day columns added, isoformat validated | cheap |
| 12 | audit_provenance --derived-disk reports usage | implemented | tools/audit_provenance.py:144-152,239-277; tests/test_audit_provenance.py:131-146 | --derived-disk emits disk.bytes plus per-build subdir breakdown; stdout prints the top 10 build dirs by size | cheap |
| 13 | NoStoreError subclass distinguishes 503 from 500 | implemented | analysis_store.py:20-21, 624-626; llm_backend.py:query_store raises NoStoreError; do_GET catches NoStoreError and returns 503 | bare FileNotFoundError no longer falls through to 500 | cheap |
| 14 | centralize filter rejection messages | implemented | analysis_store.py:598-611 | _require_nonempty_string and _require_enum helpers reused in query branches | cheap |
| 15 | _velocity_of raises on missing; None not conflated with zero | implemented | analysis_store.py:125-139; tests/test_analysis_store.py:395-440 | missing velocity raises; test now uses full geometry | cheap |

## Cross-project issues
- Finding 2 and 10 touch llm_backend.py query_store and the fit JSON schema; coordinate with E1 (publish/build) before adding schema columns because build pipeline does not call the store.
- Finding 5 would surface replay docs that silently ingest today (volume_m3=0 masks ambiguity). Needs an audit of existing build dirs first.
- Finding 9 R-tree crown-overlap option is a schema change (store bbox as (x-c, x+c, z-c, z+c)); applies to new builds only.

## Scientific validity flags
- Finding 15 (missing velocity silently defaulted to 0 m/s) is now hard-failed; cells without velocity data were being treated as still water.
- Finding 11 wind_loss range check prevents dimensionless-vs-cm/inches confusion at ingest.
- Finding 4 duplicate-epoch divergence previously discarded one of two conflicting observations; now raises so operator sees the conflict.
