# fixes-27: thermal curves, groundwater provider, and common helpers
Scope:
- yellowstone_python/yellowstone_python/thermal_curves.py (sha256 e8cb2d7c6880)
- yellowstone_python/yellowstone_python/groundwater_provider.py (sha256 3af32fc428d2)
- yellowstone_python/yellowstone_python/common/coords.py (sha256 6ee75dacc1be)
- yellowstone_python/yellowstone_python/common/hydro_units.py (sha256 f6fb8f12cfd2)
- yellowstone_python/yellowstone_python/common/provenance.py (sha256 5020f8157016)
- yellowstone_python/yellowstone_python/common/units.py (sha256 120f691827a6)
- yellowstone_python/yellowstone_python/common/validate.py (sha256 6ad2a444e6ce)
- yellowstone_python/yellowstone_python/weather_ingest/__init__.py (sha256 ce029f482ed6)

Callers read:
- yellowstone_python/replay/tests/test_thermal_curves.py
- yellowstone_python/fish.py (lines 54-78, 173-200)
- yellowstone_python/aquatic_foodweb.py (line 11, 343-391, 411-413)
- yellowstone_python/build.py (lines 11-13, 85-86, 107-111, 328-363, 909, 1055-1101)
- yellowstone_python/publish.py (lines 22, 24-50)
- yellowstone_python/validation/checks.py (line 4)
- yellowstone_python/exporters/to_ecosystem.py (line 37)
- yellowstone_python/canopy_census.py, census_validate.py, llm_backend.py, gen_flora.py, gen_trail_mask.py, review_proposals.py (all import default_world_root)
- yellowstone_python/replay/calibrate.py (line 354), replay/obs_frame.py (line 191)
- yellowstone_python/replay/river_transport.py (Source dataclass, lines 193-224)
- tests/test_coords.py, tests/test_units.py, tests/test_hydro_units.py, tests/test_groundwater_provider.py
- tools/check_terrain.py (line 44)
- yellowstone_python_spec/fish-spec.md (configured-vs-missing species table)
- research/fish-research.md (native-species inventory)
- yellowstone_midway/scripts/weather_snapshot_reader.gd (schema consumer, lines 27-47)

## Main problems

### 1. thermal_curves.py is science-grade dead code; aquatic_foodweb and build consume the piecewise-linear path in fish.py instead
Only `yellowstone_python/replay/tests/test_thermal_curves.py` imports `growth`, `feeding`, `survival`, `refuge_drive`, and `reproduction`. The simulation path at `yellowstone_python/aquatic_foodweb.py:11` imports `thermal_performance` from `fish.py`, not from `thermal_curves.py`. `aquatic_foodweb.py:343` evaluates `perf = thermal_performance(cell["temperature_c"], trout_species)` and `aquatic_foodweb.py:411-413` writes the final record through the same function. `build.py:107-111` and `build.py:1055-1101` validate species membership against `fish.THERMAL_SPECIES` and emit the piecewise-linear envelope. The fitted Gaussian and logistic curves at `thermal_curves.py:160-228` are never run outside tests. `thermal_curves.py:238` reports `status: "fitted_to_literature_anchors"` with per-endpoint provenance (study, DOI, anchors, RMSE, params), which is strictly richer than the piecewise-linear record at `fish.py:198-201`, yet no consumer reads it.
### Fix
Pick one and remove the duplicate shape. Either:
- route `aquatic_foodweb.py:343` and `aquatic_foodweb.py:411-413` through `thermal_curves.growth/feeding/survival/refuge_drive(...)` and merge the four envelopes into the dict the solver expects; delete `fish.thermal_performance` after. The fitted shapes stay fitted; the piecewise fallback stops shadowing them. Reference curve families: split Gaussian for growth (Elliott and Hurley 1999, "Daily energy intake and growth of piscivorous brown trout, Salmo trutta", Freshwater Biology 42:235-246), logistic UILT model (Beitinger, Bennett, McCauley 2000, "Temperature tolerances of North American freshwater fishes", Env. Biol. Fishes 58:237-275).
- or delete `thermal_curves.py` and `replay/tests/test_thermal_curves.py` entirely and keep the piecewise form.
Deciding either way is a scope call for the fish-spec owner, not a code call: do not keep both.
### Test
`tests/test_thermal_curve_wired.py::test_aquatic_foodweb_uses_curve_module` imports `yellowstone_python.aquatic_foodweb` and asserts the fitted-envelope keys (`anchors`, `rmse_vs_anchors`, `doi`) appear in a refuge-history record. If the delete path is chosen, assert `thermal_curves` import fails.

### 2. groundwater_provider.py never runs MODFLOW and never computes Darcy flux; it is a hand-authored lateral emitter
`riv_reaches_to_sources` (lines 47-96) takes a `reaches` list whose `flow_m3_s` is already a number. There is no `K`, no `A`, no `dh/dL`, no stage/head gradient, no conductance. `synthetic_mf6_simulation` (lines 133-154) builds an unsolved `MFSimulation` object with hardcoded `k=1.0 m/s` (`line 150`), river stage 95.0 m, cell top 100 m, bottom 90 m, river bottom 94.0 m, yet never runs `sim.write_simulation()` or `sim.run_simulation()`. `line 1` declares "Synthetic MODFLOW laterals mapped to river Source dicts" and `line 7` tags STATUS = "synthetic_modeled_not_calibrated"; the module is a labeling layer, not a solver. No production module imports it (`rg groundwater_provider`: only `tests/test_groundwater_provider.py` and a comment at `param_registry.py:218,229`).
### Fix
Resolve the mismatch between claim and behavior. Options:
- Rename STATUS to `"authored_lateral_not_modeled"` and drop the "MODFLOW" docstring until an MF6 solve lands. Rename `riv_reaches_to_sources` to `authored_reaches_to_sources`; the RIV reference belongs on the solver path.
- Or build the solve. Add a `solve(sim) -> dict` that writes and runs MF6, reads the `RIV` budget per cell with `flopy.utils.binaryfile.CellBudgetFile(...).get_data(text='RIV')`, and converts to `flow_m3_s` per reach, with the sign convention stated: MF6 RIV budget is `Q = C * (h_riv - h_cell)` where positive Q is flow into the river from the aquifer (gaining reach), negative Q is loss to the aquifer (losing reach). Cite Langevin et al. 2017 "Documentation for the MODFLOW 6 Groundwater Flow Model", USGS Techniques and Methods 6-A55, chapter on the River package, equation 6-2.
### Test
`tests/test_groundwater_darcy.py::test_riv_sign_matches_mf6_budget` runs the synthetic sim at two head configurations (`strt=96.0` gaining, `strt=93.0` losing) and asserts the sign of the Q returned by the provider matches the sign of the `RIV` budget entry, and that losing reaches are either filtered or carried with explicit `direction="losing"`.

### 3. Groundwater provider sign convention mismatches the river Source contract silently
`riv_reaches_to_sources` passes `flow_m3_s` through `_finite(reach.get("flow_m3_s"), "flow_m3_s")` at `line 77` with no minimum, so a negative reach flow becomes a lateral dict with negative `flow_m3_s`. `yellowstone_python/replay/river_transport.py:220` validates `finite(self.flow_m3_s, "source flow", 0.0)` and rejects negatives at `Source` construction. The provider's `with_chainage` (lines 99-130) does catch negatives at `line 116` and raises, yet only when the chainage adapter is invoked. A caller that skips `with_chainage` and feeds `Source(**lateral)` directly gets a confusing "source flow must be >= 0" ValueError without the "losing reach has no river Source representation" context.
### Fix
Reject negative `flow_m3_s` at the first boundary, in `riv_reaches_to_sources` itself:
```python
flow = _finite(reach.get("flow_m3_s"), "flow_m3_s", 0.0)
```
Add a one-line docstring note at `line 55`: "Flow is positive out of the aquifer into the river. Losing reaches are refused at this layer; river Source carries inflow only." Cite MODFLOW 6 RIV budget sign (Langevin 2017, chapter 6).
### Test
`tests/test_groundwater_provider.py::test_losing_reach_rejected_at_mapping` asserts `riv_reaches_to_sources([_reach(flow_m3_s=-0.01)])` raises `ValueError` with "flow_m3_s" and "0.0" in the message, before the chainage adapter runs.

### 4. thermal_curves.py's rainbow_trout cold-limb width is borrowed from the brown_trout fit without a scientific justification
`thermal_curves.py:28-37` fits rainbow growth with `rise_from=("brown_trout", "growth")`, lifting `sigma_rise_c` from the brown trout fit (`_fit_spec` at `line 180`). Rainbow trout and brown trout have different cold-side physiology: Hokanson et al. 1977 ("Effects of constant temperatures and diel temperature fluctuations on specific growth and mortality rates of rainbow trout", J. Fish. Res. Bd. Can. 34:639-648) reports rainbow optimum range 15-17 C and growth onset near 2 C; Elliott and Hurley 1999 reports brown zero-growth at 2.9 C. The `note` field at `line 36` ("cold limb width comes from the brown trout fit") is honest about the transfer yet the envelope at `line 238` still reports `status: "fitted_to_literature_anchors"`, which overstates what was anchored.
### Fix
Either anchor rainbow cold-limb with its own data point (Hokanson 1977 reports rainbow growth near zero at 2 C acclimation; add `(2.0, 0.0)` to `_SPECS[("rainbow_trout", "growth")]["points"]` and remove `rise_from`), or demote the envelope status to `"fitted_to_mixed_species_anchors"` when `rise_from` is present. Also widen `_envelope` at `line 238` to carry an explicit `cross_species_transfer` list naming the donor species.
### Test
`tests/test_thermal_curves.py::test_cross_species_transfer_declared` asserts `growth(14.0, "rainbow_trout")["provenance"]["cross_species_transfer"] == [{"species": "brown_trout", "param": "sigma_rise_c"}]` and the status reflects the transfer.

### 5. thermal_curves.py and fish.THERMAL_SPECIES configure brown and rainbow only; native YCT, Arctic grayling, and mountain whitefish have no profile
`thermal_curves.py:13` sets `SPECIES = tuple(sorted(THERMAL_SPECIES))` and `yellowstone_python_spec/fish-spec.md:36-38` records Yellowstone Cutthroat Trout, Arctic grayling, and mountain whitefish as "MISSING" from the thermal registry. `research/fish-research.md` names Yellowstone Cutthroat Trout as a park-core native with specific thermal tolerance (16.5-16.9 C critical per Rogers 2022 as cited in `fish-spec.md:36`). The current scope excludes the native baseline, so any claim framed as "trout thermal habitat" is a nonnative-species claim.
### Fix
Add `yellowstone_cutthroat` to `fish.THERMAL_SPECIES` with anchors from the fish-spec citation set (Rogers 2022 critical 16.5-16.9 C; Heinle 2025 growth; Johnstone 2003 cycling; Gresswell 2011 biology), and matching `_SPECS[("yellowstone_cutthroat", <endpoint>)]` entries. Mark `curve_shape_authored: True` in `fish.THERMAL_SPECIES_PROVENANCE["yellowstone_cutthroat"]` until laboratory curves are available. Hold Arctic grayling and mountain whitefish for a later fix tied to scope expansion past Firehole Falls.
### Test
`tests/test_fish_species_coverage.py::test_native_profile_present` asserts `"yellowstone_cutthroat" in THERMAL_SPECIES` and that `tc.SPECIES` contains it. `tests/test_thermal_curves.py::test_cutthroat_rogers_anchor` asserts `survival(16.9, "yellowstone_cutthroat")["value"] < 0.5`.

### 6. Elliott and Hurley 1999 brown growth is a model, not a Gaussian; the fit is to the published anchor points but not the published curve shape
`thermal_curves.py:17-26` fits a split Gaussian to three anchor points (2.9, 13.9, 18.7 C). Elliott and Hurley 1999 publish a specific functional form (equation 1 in that paper): a mass-and-ration-dependent growth rate that reduces, at reference ration, to a cubic polynomial in temperature with asymmetric limbs. A split Gaussian between the two zero-growth points is a different shape family. The anchor-point RMSE at `line 224` reports fit quality against three points, not against the published curve across its domain. The envelope status at `line 238` ("fitted_to_literature_anchors") lets a reader assume the shape class is Elliott's; it is not.
### Fix
Add a `curve_family` field to the envelope ("split_gaussian", "logistic_fall", "logistic_rise", "fall_gaussian") so the shape class is explicit alongside the anchor set. Add a one-line `anchor_only_fit: True` flag when fewer than five anchor points inside the published domain are used. For brown growth specifically, consider replacing the split Gaussian with a cubic that passes through (2.9, 0.0), (13.9, 1.0), (18.7, 0.0) with a derivative sign that matches Elliott's reported asymmetry; cite Elliott and Hurley 1999 equation 1.
### Test
`tests/test_thermal_curves.py::test_curve_family_declared` asserts `growth(14.0, "brown_trout")["provenance"]["curve_family"] == "split_gaussian"` and `anchor_only_fit == True`.

### 7. common/coords.py mixes EPSG:32612 (WGS 84 UTM 12N) horizontal with NAVD88 orthometric vertical without naming the geoid model
`common/coords.py:23` sets `CRS = "EPSG:32612"` (WGS 84 UTM zone 12N) and `line 24` sets `VERTICAL_DATUM = "NAVD88"`. NAVD88 orthometric heights relate to ellipsoidal heights through a geoid model (GEOID12B, GEOID18, or the NGS replacement GEOID2022 scheduled for the NSRS modernization). The code names neither the geoid model nor the time-dependent reference epoch. For Yellowstone (~111.5 W, 44.5 N), WGS 84 UTM 12N and NAD 83 UTM 12N differ horizontally by roughly 1 m; a USGS data source tagged "UTM 12N" without specifying datum could land in either frame. The anchors at `line 27-30` carry no datum metadata.
### Fix
At module scope add `HORIZONTAL_DATUM = "WGS 84"` and `GEOID_MODEL = "GEOID12B"` (or whichever geoid the USGS LiDAR tiles for Yellowstone were built against; check `tools/prepare_world.py` and the DEM source metadata). Add a one-line docstring at `local_to_utm` naming all three: horizontal CRS, horizontal datum, vertical datum, geoid model. Cite National Geodetic Survey, "NGS Datum Sheet" and USGS 3DEP metadata for the Yellowstone tiles; NIST SP 811 does not cover geodetic datums.
### Test
`tests/test_coords.py::test_datum_metadata_present` asserts `HORIZONTAL_DATUM`, `GEOID_MODEL`, and `VERTICAL_DATUM` are string constants and that `local_to_utm.__doc__` names all three.

### 8. common/coords.py sample_height uses an epsilon nudge the sample_index docstring forbids
`common/coords.py:44` docstring: "Grid indices via floor (never truncation, never epsilon nudge)." `common/coords.py:56-57` body: `gx = min(max((x + HALF) / STEP, 0.0), float(GRID - 1) - 1e-5)`. The explicit `1e-5` subtraction is an epsilon nudge to keep `ix + 1` and `iz + 1` in range at the far edge; the sample_index function does not do this because it does not need the +1 neighbor. The two functions use different index-bounds strategies, and the shared docstring claim is contradicted by the second function. The 10-01 diagonal reference at `line 5` is to `scripts/height_field.gd::sample`, which should be re-read to confirm the Godot renderer uses the same clamp.
### Fix
Replace `float(GRID - 1) - 1e-5` with explicit clamp against `GRID - 2` to bound the floored index inside `[0, GRID - 2]`:
```python
gx = min(max((x + HALF) / STEP, 0.0), float(GRID - 2))
gz = min(max((z + HALF) / STEP, 0.0), float(GRID - 2))
ix = math.floor(gx)
iz = math.floor(gz)
fx = gx - ix
fz = gz - iz
```
Update the sample_index docstring to apply to sample_index only, and add a sample_height docstring that names its own clamp. Verify the result matches `scripts/height_field.gd::sample` at the four corners and both diagonal branches.
### Test
`tests/test_coords.py::test_sample_height_corner_no_epsilon` asserts `sample_height(h, HALF - 1e-9, HALF - 1e-9)` equals `h[-1]` without the epsilon artifact, and spot-checks against the GDScript reference at both diagonal branches.

### 9. common/hydro_units.py validation bounds are so wide they hide realistic data errors
`common/hydro_units.py:28` sets `AIR_RANGE_C = (-60.0, 60.0)`. The record US surface temperature is 56.7 C in Death Valley 1913 (NOAA/NCEI, revised 2012). Yellowstone's record low near the park is roughly -46 C at West Yellowstone 1933 (NOAA GHCN station USW00024159). `line 30` sets `WIND_RANGE_MPS = (0.0, 150.0)`. 150 m/s is a Category 5 hurricane; Yellowstone peak gusts observed near 40 m/s. The Godot consumer at `yellowstone_midway/scripts/weather_snapshot_reader.gd:45` enforces `wind_speed_mps` in `[0.0, 65.0]`, which disagrees with the Python validator. `line 26` sets `TEMPERATURE_RANGE_C = (-10.0, 45.0)` for water; negative water temperatures below 0 C are not physical for liquid water at ambient Firehole pressure. Goldstein 2001 (`yellowstone_python_spec/papers/Goldstein_2001_Firehole_salmonids.pdf`) reports max Firehole water temperatures near 30 C.
### Fix
Tighten and align with the Godot consumer and with observed Yellowstone extremes:
```python
AIR_RANGE_C = (-50.0, 40.0)          # NOAA GHCN West Yellowstone extremes with margin
WIND_RANGE_MPS = (0.0, 65.0)         # matches weather_snapshot_reader.gd
TEMPERATURE_RANGE_C = (0.0, 35.0)    # liquid water, Firehole peak per Goldstein 2001
```
Record the sources in a module-level docstring and in `UNIT_DOC`. Add a boolean `strict: bool = True` kwarg to the validators so a one-off ingest can relax the window when a documented exception applies.
### Test
`tests/test_hydro_units.py::test_bounds_align_with_godot_consumer` reads the `wind_speed_mps` bound from `yellowstone_midway/scripts/weather_snapshot_reader.gd` (or from a shared JSON schema) and asserts `WIND_RANGE_MPS == (0.0, 65.0)`. `tests/test_hydro_units.py::test_subzero_water_rejected` asserts `check_temperature_c(-1.0)` raises.

### 10. common/hydro_units.py UNIT_DOC mislabels irradiance as "pressure_flux"
`common/hydro_units.py:22` entry: `"pressure_flux": "watt/meter**2"`. W/m^2 is irradiance (radiant flux per unit area), not pressure flux. Pressure flux has dimensions Pa/s = kg/(m*s^3). The key is used in `_check_range("met shortwave_w_m2", row[4], SHORTWAVE_RANGE_W_M2, UNIT_DOC["pressure_flux"])` at `line 88`, so the key name travels into pint dimensionality checks and error strings.
### Fix
Rename the key to `irradiance` or `radiant_flux_density`:
```python
UNIT_DOC = {
    ...
    "irradiance": "watt/meter**2",
}
...
_check_range("met shortwave_w_m2", row[4], SHORTWAVE_RANGE_W_M2,
             UNIT_DOC["irradiance"])
```
Cite NIST SP 811, "Guide for the Use of the International System of Units (SI)", 2008 edition, table 6 (coherent derived units) and ISO 80000-7 for photometric and radiometric quantities.
### Test
`tests/test_hydro_units.py::test_unit_doc_names_irradiance` asserts `"irradiance" in UNIT_DOC` and `"pressure_flux" not in UNIT_DOC`.

### 11. common/units.py M3S_PER_GPM is close to the NIST equivalence but the source is not cited and the gallon kind is in a comment
`common/units.py:9` sets `M3S_PER_GPM = 0.0000630902` with inline comment "1 US gal/min in m3/s". The exact equivalence per NIST SP 811 appendix B is 1 US gal = 3.785411784 L exactly (231 cubic inches exactly, by 15 USC 205b), so 1 US gal/min = 6.30901964e-5 m^3/s. The code value rounds to 6.30902e-5, within 1 part in 10^6. The constant name does not say "US" and the function names (`gpm_to_m3s`, `m3s_to_gpm`) are ambiguous between US and imperial gallons (1 imperial gal = 4.54609 L exactly, so imperial gpm_to_m3s = 7.57682e-5 m^3/s, off by 20%).
### Fix
Rename the constant and functions to disambiguate, and cite the source:
```python
# NIST SP 811 app B: 1 US gal = 3.785411784 L exactly (231 in^3 exactly).
M3S_PER_US_GPM = 3.785411784e-3 / 60.0  # 6.30901964e-5 m3/s

def us_gpm_to_m3s(gpm: float) -> float:
    ...
```
Keep `gpm_to_m3s` as a deprecated alias that emits a warning and calls `us_gpm_to_m3s`, until callers update. Cross-check against USGS WaterWatch unit conversion table (USGS Water Resources Office of Information).
### Test
`tests/test_units.py::test_us_gpm_matches_nist_exact` asserts `abs(us_gpm_to_m3s(1.0) - 3.785411784e-3 / 60.0) < 1e-18`.

### 12. common/units.py c_to_k accepts temperatures below absolute zero
`common/units.py:13-14`:
```python
def c_to_k(c: float) -> float:
    return c + 273.15
```
`c_to_k(-500.0)` returns -226.85, which is below absolute zero and unphysical. The sibling `k_to_c` at `line 17-20` guards `k < 0`; the asymmetric guard lets an upstream error pass one way and fail the other.
### Fix
Add the symmetric guard:
```python
def c_to_k(c: float) -> float:
    if c < -273.15:
        raise UnitError(f"Celsius below absolute zero: {c}")
    return c + 273.15
```
Cite CODATA 2018, "Thermodynamic temperature: zero point of the Celsius scale is 273.15 K exactly" (SI brochure 9th ed., section 2.3.3).
### Test
`tests/test_units.py::test_c_below_absolute_zero_rejected` asserts `c_to_k(-273.16)` raises `UnitError`.

### 13. common/provenance.py write_sidecar is not atomic
`common/provenance.py:59-61`:
```python
p.parent.mkdir(parents=True, exist_ok=True)
p.write_text(json.dumps(doc, indent=2, sort_keys=True))
```
`Path.write_text` writes directly to the destination. An interrupted write leaves a partial JSON file at the published path. `build.py:909` uses an `_atomic_json_write(out / "weather.json", ...)` for the same payload class, so the atomic helper exists elsewhere in the tree. The audit brief tags "file I/O atomicity" as a correctness requirement.
### Fix
Use the write-rename pattern:
```python
import os, tempfile
p = Path(path)
p.parent.mkdir(parents=True, exist_ok=True)
with tempfile.NamedTemporaryFile(
    "w", delete=False, dir=p.parent, prefix=p.name + ".", suffix=".tmp"
) as handle:
    handle.write(json.dumps(doc, indent=2, sort_keys=True))
    handle.flush()
    os.fsync(handle.fileno())
    tmp = Path(handle.name)
os.replace(tmp, p)
```
`os.replace` is atomic within a filesystem on POSIX and Windows; `os.fsync` ensures the content is on disk before the rename.
### Test
`tests/test_provenance.py::test_write_sidecar_atomic` creates a scratch dir, monkeypatches `tempfile.NamedTemporaryFile` to raise after flush, and asserts the destination path either does not exist or contains the fully-formed previous version.

### 14. common/provenance.py build_id and code_rev are hard-coded, not read from the repo
`common/provenance.py:9` sets `CONTRACT_VERSION = "0.1.0"` and `line 47` defaults `code_rev = "yellowstone_python-0.1.0"`. Neither tracks the actual repo revision. A build output's `code_rev` is identical across every commit until an editor hand-updates the string. `build_id` at `line 38` hashes `{"config": config, "deps": dep_hashes}` and omits the source tree hash; two builds from different source commits with identical config and inputs collide on build_id.
### Fix
Resolve `code_rev` from `subprocess.run(["git", "-C", repo_root, "rev-parse", "HEAD"], ...)` at build time and pass it in through `write_sidecar(code_rev=...)` from `build.py`. Fold it into `build_id`:
```python
def build_id(config: dict, dep_hashes: dict, code_rev: str) -> str:
    return hashlib.sha1(
        json.dumps({"config": config, "deps": dep_hashes, "code_rev": code_rev},
                   sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()[:12]
```
Keep a fallback literal when git is absent (install from tarball), tagged `code_rev_source: "git" | "fallback"` in the sidecar.
### Test
`tests/test_provenance.py::test_build_id_depends_on_code_rev` asserts `build_id({}, {}, "a") != build_id({}, {}, "b")`.

### 15. weather_ingest/__init__.py is an orphan package: a one-line docstring, no code, no callers
`weather_ingest/__init__.py` contents:
```python
"""Weather ingest: met bundle -> Godot weather snapshot (schema v1)."""
```
The directory contains only `__init__.py`. `rg weather_ingest` finds no production or test imports. Build-time weather production actually runs through `yellowstone_python/microclimate.py` (`build.py:19,328,329,352-365,909`), which writes `weather.json`. The subpackage's claim contradicts the behavior.
### Fix
Pick one. Either delete `weather_ingest/` outright, or move the `microclimate.load_weather_bundle` and `bundle_weather` functions into `weather_ingest/` and reroute `build.py:329` to the new path. The second option is a refactor, not a fix; the first is one `trash` call.
### Test
`tests/test_package_layout.py::test_no_orphan_packages` imports every subpackage under `yellowstone_python/` and asserts each exports at least one non-dunder name, which fails for `weather_ingest` until it is removed or populated.

### 16. common/validate.py check_heat_ledger silently accepts two different residual field names
`common/validate.py:36-42`:
```python
def check_heat_ledger(ledger: dict, tol: float = 1e-6) -> list[str]:
    resid = ledger.get("residual", ledger.get("heat_budget_error"))
    if resid is None or abs(resid) > tol:
        return [f"heat residual {resid} exceeds tol {tol}"]
    w = ledger.get("water_budget_error_m3", 0.0) or 0.0
    if abs(w) > tol:
        return [f"water residual {w} exceeds tol {tol}"]
    return []
```
Two names ("residual" and "heat_budget_error") for the same quantity hide a naming drift between producers. A ledger that supplies both with contradictory values returns only the first. Water residual tolerance is in m^3 yet shares the same scalar `tol` as the heat residual (dimensions of joules or watts per the producer convention), which is a dimensionally inconsistent single-threshold check.
### Fix
Pick the canonical name, deprecate the other, and separate the tolerances:
```python
def check_heat_ledger(ledger: dict, heat_tol_j: float = 1e-6,
                      water_tol_m3: float = 1e-6) -> list[str]:
    if "heat_budget_error_j" not in ledger:
        return ["ledger missing heat_budget_error_j"]
    resid = ledger["heat_budget_error_j"]
    ...
```
Then update producers in `yellowstone_python/replay/river_transport.py` and callers surfaced by `rg heat_budget_error` to emit the canonical key. Carry a one-release alias that warns.
### Test
`tests/test_validate.py::test_two_residual_names_rejected` asserts a ledger with both "residual" and "heat_budget_error_j" fields logs an error naming the deprecated key.

### 17. common/validate.py assert_finite misses non-float NaN carriers
`common/validate.py:7-11`:
```python
def assert_finite(name: str, value: float) -> float:
    if value is None or (isinstance(value, float) and
                         (math.isnan(value) or math.isinf(value))):
        raise ValueError(f"{name} is missing/non-finite ...")
    return value
```
A string, a Decimal, a numpy integer, or a numpy generic that is not a Python float bypasses the check. A `numpy.float32('nan')` is not a Python float either on some numpy versions.
### Fix
Convert and test, in that order:
```python
def assert_finite(name: str, value) -> float:
    if value is None:
        raise ValueError(f"{name} is missing")
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} is not numeric: {value!r}") from exc
    if not math.isfinite(result):
        raise ValueError(f"{name} is not finite: {value!r}")
    return result
```
This also returns a plain `float`, which is what every caller expects.
### Test
`tests/test_validate.py::test_assert_finite_rejects_nonfloat_nan` passes `numpy.float32("nan")`, a Decimal `"NaN"`, and the string `"nan"` and asserts each raises.

# Wiring and rendering
- `thermal_curves.py` has no production consumer. `aquatic_foodweb.py` evaluates `fish.thermal_performance` and the piecewise-linear path serializes into the final ecosystem artifacts. Godot renders the piecewise shape through `yellowstone_midway/scripts/python_river_replay.gd` and `wildlife_actor.gd`, both of which read values already materialized into ecosystem.godot.json; neither Godot script reads the richer provenance envelope from `thermal_curves.py`. The orphan status is confirmed by `rg thermal_curves`: hits only in `replay/tests/test_thermal_curves.py`.
- `groundwater_provider.py` has no production consumer. `rg groundwater_provider --type py` finds `tests/test_groundwater_provider.py`, `replay/tests/test_river_world.py:204` (test only), and `param_registry.py:218,229` (prose only). The build does not include a groundwater lateral set; a scan for flopy, MODFLOW, or RIV in `yellowstone_python/build.py` returns zero hits.
- `common/coords.py` is read only by `tests/test_coords.py`. The build does not use the local-UTM converters directly. `tools/prepare_world.py` is named in the module docstring as the sibling that must stay in sync; verifying that sync is out of scope for this fixes doc.
- `common/hydro_units.py` is wired in: `build.py:85` enforces hydro boundary units, `replay/calibrate.py:354` and `replay/obs_frame.py:191` validate observation bundles.
- `common/provenance.py` is widely wired: 10 production modules import from it, and `publish.py:22` reads `CONTRACT_VERSION` and `WORLD_ID`.
- `common/units.py` is read only by `tests/test_units.py`. No production module imports `gpm_to_m3s`, `c_to_k`, `label_index`, or `require_fraction`. The dimensionless-index wrapping at `line 47-51` is advertised in docstrings yet no caller invokes it.
- `common/validate.py` is wired through `validation/checks.py:4` and `exporters/to_ecosystem.py:37`.
- `weather_ingest/__init__.py` has no production consumer and no implementation. The Godot consumer `yellowstone_midway/scripts/weather_snapshot_reader.gd` reads `weather.json` written by `build.py:909`, built from `microclimate.py`, not from this subpackage.

# Comment-style violations
| file:line | text | rule |
| common/coords.py:10 | "H is NAVD88 orthometric, not ellipsoidal GPS height" | AGENTS.md section 2 "No `X, not Y` contrasts" |
| common/coords.py:44 | "Grid indices via floor (never truncation, never epsilon nudge)." | AGENTS.md section 2 "No hypothetical-failure narratives (`never silently`...)" |
| common/units.py:48 | "Wrap a dimensionless 0..1 index so it can never be mistaken for kg/counts." | AGENTS.md section 2 "No hypothetical-failure narratives" and "No `X, not Y` contrasts" |
| common/hydro_units.py:15 | "Unit registry documentation. Canonical hydro units across ingestion." | AGENTS.md section 2 one-sentence module comments are acceptable; the "Canonical" claim is a mild "Every"-style comprehensiveness assertion; NOT VERIFIED whether it crosses the section 2 threshold |
| common/provenance.py:19-20 | "Portable world-root default: $YELLOWSTONE_WORLD wins, else the sibling checkout. Callers must still verify it exists." | AGENTS.md section 2 docstrings are "one or two lines" (this is one line split across two for width, so arguably compliant); addressing the reader ("Callers must") is a mild violation |
| thermal_curves.py:1 | "Fitted per-endpoint trout thermal curves from literature anchors." | compliant |
| groundwater_provider.py:103-105 | "Losing reaches (negative flow) are rejected: river Sources carry inflow only." | compliant |

# Priority order
1. Finding 2 (groundwater MF6 claim vs behavior) - refactor (either rename plus delete solver scaffolding, or build the solve)
2. Finding 15 (weather_ingest orphan package) - cheap (`trash yellowstone_python/weather_ingest/`)
3. Finding 1 (thermal_curves orphan vs fish.thermal_performance duplicate) - refactor (consolidation decision plus rewire)
4. Finding 9 (hydro_units bounds hide errors) - cheap (tighten constants, align with Godot)
5. Finding 3 (groundwater sign-convention gate) - cheap (one-line min=0 in `_finite`)
6. Finding 13 (write_sidecar not atomic) - cheap (write-rename helper)
7. Finding 10 (irradiance mislabel) - cheap (rename key)
8. Finding 12 (c_to_k symmetric guard) - cheap (one if)
9. Finding 7 (coords datum metadata) - cheap (add constants plus docstring)
10. Finding 17 (assert_finite robustness) - cheap (rewrite body)
11. Finding 11 (M3S_PER_GPM NIST citation and US-gallon disambiguation) - medium (rename plus alias)
12. Finding 16 (heat_ledger dual-name residual) - medium (needs producer updates)
13. Finding 8 (coords sample_height epsilon vs docstring) - medium (clamp replacement plus GDScript cross-check)
14. Finding 14 (build_id and code_rev tracking) - medium (git call plus sidecar field)
15. Finding 4 (rainbow cross-species cold-limb transfer disclosure) - cheap (envelope field plus anchor)
16. Finding 6 (curve_family declaration and Elliott shape class) - medium (new provenance field plus optional cubic)
17. Finding 5 (native species profile for YCT) - refactor (new anchors plus curve specs plus tests)
