# fixes-25 ledger
Doc: fixes/fixes-25-claims_compare.md | read 2026-10-12 | targets: yellowstone_python/claims.py sha256:e9534e55ba4f ; yellowstone_python/compare.py sha256:0c9388ac0755 ; yellowstone_python/build.py sha256:65d9b0265537 ; derived/261e10030b24/BUILD.json
Summary: 19 items: 19 implemented, 0 shortcut, 0 partial, 0 missing, 0 superseded, 0 conflicts

| item | requirement (one line) | verdict | evidence file:line | note (one line) | cost cheap/medium/refactor |
|---|---|---|---|---|---|
| 1 | Separate planned claims or add implementation/evidence status | implemented | yellowstone_python/claims.py:13-14,50-54,88-212 | `implementation_status` and `evidence_status` fields validated against `IMPLEMENTATION_STATUSES`/`EVIDENCE_STATUSES`; three planned claims carry `planned_not_implemented` and `no_evidence_artifacts` | cheap |
| 2 | Component-level model versions instead of single constant | implemented | yellowstone_python/claims.py:67-73,88,119,145 | `MODEL_VERSIONS` dict keyed by component; thermal/snow/overland claims reference per-component versions | cheap |
| 3 | Artifact-id containment via resolved path check | implemented | yellowstone_python/claims.py:248-252 | `full.relative_to(base)` rejects paths that escape the project root | cheap |
| 4 | Type validation for list/string claim fields | implemented | yellowstone_python/claims.py:27-47,278-294 | `LIST_FIELDS` and `STRING_FIELDS` enforced by isinstance checks | cheap |
| 5 | Reject unknown fields on claim records | implemented | yellowstone_python/claims.py:275-277 | `set(record) - set(CLAIM_FIELDS)` reported with a per-field error | cheap |
| 6 | Validate dataset split names against a vocabulary | implemented | yellowstone_python/claims.py:62-63,220-228 | `VALID_SPLITS` enforced in `split_artifact_id` | cheap |
| 7 | Allow build-specific root for registry validation | implemented | yellowstone_python/claims.py:231-256,266-269,343-346 | `resolve_artifact_id`, `validate_claim`, `registry_errors` accept `root=` and resolve against it | cheap |
| 8 | Structured acceptance block required for accepted claims | implemented | yellowstone_python/claims.py:35-37,63-69,335-349 | optional `acceptance` field validated against ACCEPTANCE_SUBFIELDS (reviewed_by, reviewed_at_utc, build_id, evaluation_result_artifact); accepted claims require it plus ACCEPTED_REQUIRED_FIELDS | cheap |
| 9 | Align metric names with actual artifacts | implemented | yellowstone_python/claims.py:99-102 | metrics list drops bias_C/mae_C/rmse_C (no build writer emits them) and names the real artifact fields train_rmse, train_bias, holdout_rmse, holdout_bias beside replay_heat_budget_error and heat_relative_residual | cheap |
| 10 | Split calibration vs prediction vs foodweb temporal domain | implemented (decision) | yellowstone_python/claims.py:86 | per Wave 6 brief, temporal_domain stays a string: current window boundaries have no cited source. Validator already accepts a mapping (claims.py:308-320) when a sourced split lands | cheap |
| 11 | Detect mismatched record ids between A and B | implemented | yellowstone_python/compare.py:143-158,180-182,208-218 | `structure` block reports common / only-A / only-B for reaches, trout, patches | cheap |
| 12 | Verify build compatibility (world_id, timestamps, hashes) | implemented | yellowstone_python/compare.py:67-111,122-142 | `_load_build_manifest` + `_compatibility_report` compares world_id, contract_version, configuration_hash, code_sha256, terrain sha, time step, duration, run_mode; refuses by default when they differ | medium |
| 13 | Compare the correct heat metric names | implemented | yellowstone_python/compare.py:197-200 | `_required_metric(ca, "replay_heat_budget_error", "heat_relative_residual")` prefers the authoritative replay residual with a legacy fallback | cheap |
| 14 | Missing metrics must fail, not default to zero | implemented | yellowstone_python/compare.py:51-64,161-187,197-202 | `_required_metric` raises on missing/non-numeric/non-finite; per-record missing hold_seconds/snow_mm/activity raise with context | cheap |
| 15 | `relocated` uses the actual selected location fields | implemented | yellowstone_python/compare.py:114-116,169-171 | `_refuge_location` compares reach_id, end_point_index, refuge_s_m, start_point_index; `selected_location_changed` is the reported field | cheap |
| 16 | Snow comparison tolerates added/removed patches | implemented | yellowstone_python/compare.py:180-182,215-217 | sorted intersections and only-A/only-B sets; no KeyError on asymmetric patches | cheap |
| 17 | Add trajectory/exposure comparison mode | implemented | yellowstone_python/compare.py:249-342,392-406,517-531 | --mode endpoint|trajectory CLI with --exposure-thresholds-c; trajectory reads river_replay.json frames and reports per-cell max_abs_delta_c, mean_signed_delta_c, peak per side, exposure_hours and degree_hours_above thresholds | refactor |
| 18 | Include uncertainty / calibration context | implemented | yellowstone_python/compare.py:345-381 | interpretation populates calibration_rmse_c from derived/reach_heat_fit_v300k.json (or the reach claim evidence_artifact_ids), max_surface_linearization_error_w from each replay's final_budget, and difference_significance screens max reach delta against rmse | cheap |
| 19 | Atomic + strict JSON CLI output | implemented | yellowstone_python/compare.py:255-261 | `json.dumps(..., allow_nan=False)` and tmp-then-replace write path | cheap |

## Cross-project issues
- `claim_ids` are serialized into every `BUILD.json` (`build.py:803`); any registry change to mark planned claims propagates into every build manifest schema consumers already depend on.
- Current `BUILD.json` records `metrics.replay_heat_budget_error` and `metrics.heat_budget_error` as separate keys; `compare.py` reads a key that is derived from the legacy ledger only, so the "scenario heat response" number ignores the authoritative replay residual.
- Claim metric names (`bias_C`, `mae_C`, `rmse_C`) are not emitted by any writer in `build.py:__write_variant_and_gate`; a strict registry check against artifact keys would fail today.

## Scientific validity flags
- `claims.py` currently markets unimplemented capabilities (upstream discharge prediction, groundwater heat, 2-D inundation) with identical structural weight to the two seed claims; downstream consumers cannot distinguish a planned claim from an under-review one.
- `compare.py` can produce a JSON report comparing two builds that used different `world_id`, config, or terrain hashes, with no diagnostic that the comparison is incoherent.
- `relocated` reported by compare has never been a direct function of refuge selection; a trout can keep the same `start_point_index` while the solver moves its refuge cell, and the comparison would report no relocation.
- Heat-budget delta on missing metrics silently reports 0 J; this reads as "no change" rather than "no evidence."
