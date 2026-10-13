## Overall assessment

These scripts are **relevant to the broader model**, but they are not currently wired together in a scientifically or structurally reliable way.

The intended architecture appears to be:

```text
USGS / literature data
        ↓
fetch_yellowstone_tributaries.py
        ↓
tributary data artifact
        ↓
run_hot_lowflow_with_tributaries_v2.py
        ↓
thermal replay + landscape refuge cells
        ↓
aquatic_foodweb.compare_runs()
```

The current implementation instead mixes:

- real observations;
- unverified literature claims;
- hardcoded fallback values;
- fabricated geometry;
- solver-cell records;
- landscape refuge cells;
- and visual foodweb inputs.

Those need to be separated.

---

# Critical problems

## 1. `run_hot_lowflow_with_tributaries_v2.py` does not actually use `--tributary-cells`

The function hardcodes:

```python
for i, trib in enumerate(real_candidates[:2]):
```

Therefore this command-line argument is ignored:

```python
--tributary-cells 1
--tributary-cells 5
```

Only two cells are ever created.

### Fix

Pass the requested number:

```python
def create_tributary_refuge_cells(
    pulse_doc: dict,
    world: dict,
    tributary_data: dict,
    num_cells: int,
) -> dict:
    ...
    for i, trib in enumerate(real_candidates[:num_cells]):
```

Call:

```python
pulse_doc_with_tributaries = create_tributary_refuge_cells(
    pulse_doc,
    world,
    tributary_data,
    args.tributary_cells,
)
```

Validate:

```python
if not 1 <= args.tributary_cells <= 5:
    parser.error("--tributary-cells must be in [1, 5]")
```

---

## 2. `--real-data-only` is ignored

The CLI exposes:

```python
parser.add_argument("--real-data-only", action="store_true")
```

but the fallback is still used when the real file is missing:

```python
return get_fallback_tributary_data()
```

### Fix

```python
def load_real_tributary_data(
    *,
    allow_fallback: bool = True,
) -> dict:
    if not REAL_TRIBUTARY_DATA_PATH.exists():
        if not allow_fallback:
            raise FileNotFoundError(
                f"real tributary data not found at "
                f"{REAL_TRIBUTARY_DATA_PATH}"
            )
        return get_fallback_tributary_data()
```

Call:

```python
tributary_data = load_real_tributary_data(
    allow_fallback=not args.real_data_only
)
```

Also reject fallback data before publication when `--real-data-only` is set.

---

## 3. The script has a runtime error: `datetime` is not imported

This line is used:

```python
datetime.now(timezone.utc).isoformat()
```

but the file does not import:

```python
from datetime import datetime, timezone
```

Add:

```python
from datetime import datetime, timezone
```

---

## 4. Real-data schema does not match the consuming script

`fetch_yellowstone_tributaries.py` produces candidate records with values nested under:

```python
trib["analysis"]["mean_temperature_c"]
trib["analysis"]["mean_discharge_m3s"]
```

But `run_hot_lowflow_with_tributaries_v2.py` expects:

```python
trib.get("temperature_c")
trib.get("discharge_m3s")
trib.get("habitat_area_m2")
```

Those fields are not produced by the real-data fetcher.

Consequently, real candidates usually fall back to:

```python
temp_c = trib.get("temperature_c", 12.0 - i * 0.5)
discharge_m3s = trib.get("discharge_m3s", 1.5 - i * 0.3)
area_m2 = trib.get("habitat_area_m2", 27.0 - i * 9.0)
```

That means the script can claim to use real data while silently using authored defaults.

### Fix the adapter

Add a normalization function:

```python
def normalize_candidate(record: dict) -> dict:
    analysis = record.get("analysis", {})

    temperature = analysis.get("mean_temperature_c")
    discharge = analysis.get("mean_discharge_m3s")

    if temperature is None:
        raise ValueError(
            f"candidate {record.get('name', '?')} lacks "
            "mean_temperature_c"
        )

    return {
        "site_id": record["site_id"],
        "name": record["name"],
        "confluence_s_m": float(record["confluence_s_m"]),
        "temperature_c": float(temperature),
        "discharge_m3s": (
            None if discharge is None else float(discharge)
        ),
        "data_status": (
            "measured"
            if record.get("usgs_data") is not None
            else "documented_or_assumed"
        ),
        "provenance": record.get("provenance", {}),
    }
```

Do not invent discharge if it is absent. Require an explicit policy:

```python
if discharge is None:
    raise ValueError(
        "tributary discharge is required to create a thermal source"
    )
```

A tributary temperature without flow cannot be used for mixing.

---

# 5. The tributary cells are not real solver cells

The script appends records to:

```python
modified_doc["cells"]
```

but these cells are not solved by `river_transport.py`. Their temperatures are manually appended to each frame:

```python
new_temps.append(11.5)
```

This is especially problematic because the solver document now claims to contain cells that were never part of the numerical solution.

The new records have:

```python
"river_id": "river_5856_0"
```

and appear like ordinary river cells, but they are actually off-channel refuge pockets.

This conflicts with the coupling contract, which already distinguishes:

```python
"pocket_holding"
"conservation": "non_conservative"
```

## Correct design

Do not append refuge pockets to the solver’s `cells` array.

Instead, keep the thermal replay unchanged and add a separate landscape artifact:

```json
{
  "id": "firehole_tributary_pocket_01",
  "kind": "pocket",
  "river_id": "tributary",
  "conservation": "non_conservative",
  "temperature_c": 11.5,
  "flow_m3_s": 1.2,
  "position_xyz": [...],
  "chainage_m": 3500.0,
  "tributary_provenance": {...}
}
```

Then pass those pockets to the landscape/foodweb builder.

The main replay should contain:

```text
solver cells
solver frames
solver budget
```

The landscape document should contain:

```text
mainstem mapped cells
tributary pockets
provenance
```

That preserves the distinction between simulated and prescribed landscape state.

---

# 6. The frame temperatures are hardcoded incorrectly

Inside the frame update:

```python
for _ in range(len(tributary_cells)):
    new_temps.append(11.5)
```

Every tributary gets `11.5°C`, even if the candidate temperatures are different.

### Minimum fix

```python
new_temps = [
    float(cell["initial_c"])
    for cell in tributary_cells
]
```

But the better fix is not to append them to solver frames at all, as described above.

---

# 7. The generated geometry is not physically tied to the world

The code uses:

```python
"position_xyz": [
    confluence_s_m - 50.0,
    8.0,
    1500.0
]
```

This treats chainage as an x-coordinate and uses a hardcoded z-coordinate. That is not a valid mapping into the world coordinate system.

`river_world.py` already contains the correct geometry authority:

```python
channel.position_at(s_m)
```

The refuge-builder should use the actual mapped channel:

```python
channel = Channel(firehole_chain(world))
position = channel.position_at(confluence_s_m)
```

For a tributary pocket, offset from the mainstem using a documented local direction, not arbitrary coordinates.

At minimum:

```python
"position_status": "chainage_only_not_world_mapped"
```

if a real spatial position cannot be derived.

---

# 8. `q_out_m3_s = discharge_m3s * 2.5` is physically invalid

Current code:

```python
"q_out_m3_s": discharge_m3s * 2.5
```

This creates water from nowhere. It also contradicts the documented source discharge.

If the record is an off-channel holding pocket, it should not have a solver-style `q_in`/`q_out` balance at all.

If it is a real tributary reach, then:

```text
q_out = q_in
```

unless additional sources/sinks are explicitly modeled.

Use:

```python
"flow_m3_s": discharge_m3s,
"flow_status": "prescribed_tributary_inflow",
```

rather than inventing `q_out`.

---

# 9. The hydraulic diagnostics are fabricated

The generated record contains values such as:

```python
"froude_continuity": 0.08 + i * 0.02,
"velocity_manning_m_s": 0.5 + i * 0.1,
"bed_shear_pa": 5.0 - i * 0.5,
"travel_time_s": 8.0 + i * 5.0,
```

These are not calculated from the stated inputs and are not measurements.

This is dangerous because downstream code may interpret them as model outputs.

### Fix

Either calculate them from a real hydraulic function or omit them:

```python
"hydraulics": {
    "status": "not_computed",
    "warnings": [
        "No surveyed tributary geometry or slope supplied"
    ]
}
```

A provenance label does not make fabricated numbers valid.

---

# 10. `fetch_yellowstone_tributaries.py` contains likely source/identity problems

The documented list includes names and site IDs that should be independently verified. Several entries appear inconsistent with a Firehole tributary inventory, for example:

```python
"Arrow Creek at Tower Falls"
"Lamar River at River Bend"
"Gibbon River at Gibbon Falls"
```

These are not automatically tributaries of the Firehole modeled reach.

The script claims:

```text
Find cold lateral inflows that join the Firehole River system
```

but uses a hardcoded list without proving:

- the gauge is on the relevant stream;
- the stream joins the Firehole;
- the confluence lies within the modeled chain;
- the site ID matches the named stream;
- the supplied chainage is derived from geometry.

## Required change

Every candidate should pass an explicit association check:

```python
{
    "site_id": "...",
    "stream_name": "...",
    "target_river_id": "river_...",
    "confluence_node_id": "...",
    "confluence_s_m": ...,
    "association_method": "world_endpoint_topology|GIS_join|manual_review",
    "association_status": "verified|unverified|rejected"
}
```

Do not include a candidate in `cold_refuge_candidates` unless:

```text
association_status == "verified"
```

A temperature gauge alone does not prove a confluence.

---

# 11. `fetch_usgs_site_data()` has a timestamp parsing bug

Current code:

```python
dt = datetime.fromisoformat(
    epoch_text.replace('Z', '+00:00')
)
epoch = dt.replace(tzinfo=timezone.utc).timestamp()
```

If the input already includes an offset, `replace(tzinfo=UTC)` overwrites the actual timezone rather than converting it.

Use:

```python
dt = datetime.fromisoformat(
    epoch_text.replace("Z", "+00:00")
)

if dt.tzinfo is None:
    raise ValueError(
        "USGS timestamp lacks timezone"
    )

epoch = dt.astimezone(timezone.utc).timestamp()
```

---

# 12. USGS data quality handling is too weak for calibration/refuge claims

The fetcher checks ranges, but not:

- duplicate timestamps;
- timestamp ordering;
- measurement qualifiers;
- provisional status;
- gaps;
- observation frequency;
- whether temperature and discharge periods overlap;
- whether the site is actually a tributary.

Add:

```python
def validate_series_pairs(
    pairs: list[list[float]],
    label: str,
) -> None:
    times = [float(pair[0]) for pair in pairs]

    if any(
        later <= earlier
        for earlier, later in zip(times, times[1:])
    ):
        raise ValueError(
            f"{label} timestamps must be strictly increasing"
        )
```

Also report coverage:

```python
{
    "start_epoch_unix": ...,
    "end_epoch_unix": ...,
    "n_points": ...,
    "nominal_interval_s": ...,
    "max_gap_s": ...,
    "coverage_fraction": ...
}
```

The current test:

```python
temp_range > 20.0
```

is not a sound universal validity rule. Real thermal events can exceed that, while a smooth but wrong series can pass it. Treat it as a warning, not an automatic rejection.

---

# 13. `analyze_usgs_data()` does not implement the stated hot-low-flow criterion

The script says it will determine which runs are below 24°C under hot-lowflow conditions, but it computes:

```python
mean_temperature_c < 24.0
min_temperature_c <= 16.0
cold_refuge_potential_c >= 0.8
```

over the full fetched window.

It does not condition the analysis on:

```text
low discharge
hot mainstem
specific season
```

### Better analysis

Join temperature and discharge by time, then evaluate only rows satisfying:

```python
mainstem_temperature >= hot_threshold
mainstem_discharge <= lowflow_threshold
```

Or, if tributary flow itself is the relevant condition:

```python
tributary_discharge <= tributary_lowflow_threshold
```

Return:

```python
{
    "condition": {
        "mainstem_temperature_min_c": 24.0,
        "mainstem_discharge_max_m3_s": 3.0
    },
    "n_qualified_observations": ...,
    "fraction_below_threshold": ...,
    "max_temperature_c": ...,
    "status": "measured_window_not_generalized"
}
```

Without this, the candidate selection does not support the stated scientific claim.

---

# 14. The confluence chainage values are not integrated with `river_world.py`

`river_world.py` derives chainage from:

```python
Channel(firehole_chain(world))
```

and validated endpoint geometry.

`fetch_yellowstone_tributaries.py` supplies hardcoded values:

```python
"confluence_s_m": 3500.0
```

These values are not checked against:

- `channel.length_m`;
- feature boundaries;
- actual confluence nodes;
- `SOURCE_LINKS`;
- world river endpoints.

Add a validation step:

```python
def validate_confluence_chainages(
    tributaries: list[dict],
    channel,
) -> None:
    for record in tributaries:
        s = float(record["confluence_s_m"])

        if not 0.0 <= s <= channel.length_m:
            raise ValueError(
                f"{record['name']} confluence lies outside "
                f"the modeled channel"
            )
```

But chainage-range validation alone is not enough. The correct source of truth should be the world topology.

---

# 15. `channel_geometry.py` is relevant but currently over-applies USGS measurements

In `analyze()`:

```python
usgs_result = _usgs_mean_depth(usgs_data) if usgs_data else None
```

The same USGS measurement profile is applied to every Firehole feature:

```python
if usgs_result and usgs_result["depth_m"] > 0.2:
    profiles[fid] = usgs_result
```

That is not valid unless the gauge represents all modeled features, which it does not.

The `--usgs-site` argument is also not used to select or spatially map measurements.

## Fix

Use USGS measurements only for:

- the feature containing the gauge;
- a statistically justified regional prior;
- or a clearly labeled calibration constraint.

For other reaches:

```python
profiles[fid] = {
    **dem_result,
    "usgs_cross_check": None,
}
```

Also add:

```python
"applicability": {
    "usgs_site": args.usgs_site,
    "applies_to_features": [...]
}
```

The current output can be consumed by `river_world.py`, but its scientific applicability is overstated.

---

# 16. DEM-derived cross sections have important limitations

This code uses:

```python
water_y = pts[idx][1] + ...
```

That assumes the world river centerline y-coordinate is the water-surface elevation. If `world.json` contains authored geometry elevation rather than surveyed water stage, the derived depth is not reliable.

Also:

```python
wetted = [(o, d) for o, d in points if d > 0.0]
```

removes below-water samples and integrates across gaps. A transect with a dry depression or bank artifact can produce an unrealistic polygon.

At minimum, report:

```python
{
    "n_transects_attempted": ...,
    "n_transects_valid": ...,
    "valid_fraction": ...,
    "water_surface_source": "world_centerline_y_authored",
    "bathymetry_status": "not_measured"
}
```

The result should be treated as a prior, not a measured bathymetric profile.

---

# 17. The fallback tributary data are not acceptable for a “real data” pipeline

The fallback contains:

```python
"Fairy Creek Tributary"
"Glacier Creek Tributary"
```

with authored values. That is fine for a visual test, but not for a script whose purpose is:

```text
Discover actual values, do not invent
```

Separate modes:

```text
strict:
    fail if real data/geometry are unavailable

illustrative:
    allow fallback and label artifact clearly
```

Do not write a normal-looking output with only a nested fallback label. Put the status at the top level:

```json
{
  "status": "authored_fallback_not_real_data",
  "scientific_use": "prohibited",
  "visual_use": "allowed"
}
```

---

# 18. The correct architecture

## Data acquisition

`fetch_yellowstone_tributaries.py` should produce only a validated evidence artifact:

```text
tributary observations
stream identity
gauge identity
time coverage
temperature/discharge series
confluence association
provenance
quality flags
```

It should not create game cells.

## Geometry

`channel_geometry.py` should produce:

```text
mainstem cross-section priors
gauge applicability
DEM uncertainty
feature-level profiles
```

It should not be used to imply surveyed bathymetry where none exists.

## Thermal solver

`river_world.py` / `river_transport.py` should use:

```text
verified lateral source geometry
prescribed or scheduled Q and T
```

A tributary with measured flow and temperature may become a solver source. An unmeasured cold refuge should not.

## Landscape/foodweb

`run_hot_lowflow_with_tributaries_v2.py` should create:

```text
non-solver prescribed tributary pockets
```

with:

```text
temperature
flow or refuge-size proxy
position
source/provenance
conservation = non_conservative
```

Those are passed into the landscape coupling layer, not appended to thermal solver cells.

---

# 19. Suggested normalized tributary schema

Use one schema between the fetcher and consumers:

```json
{
  "schema": "yellowstone.tributary_evidence.v1",
  "status": "measured_remote_not_validated",
  "retrieved_at_utc": "2026-07-15T22:20:00Z",
  "records": [
    {
      "id": "tributary_001",
      "name": "verified stream name",
      "usgs_site_id": "06000000",
      "target_river_id": "river_5856_0",
      "confluence": {
        "chainage_m": 3500.0,
        "status": "verified",
        "method": "world_endpoint_topology"
      },
      "observations": {
        "temperature_c": {
          "times_epoch_unix": [],
          "values": []
        },
        "discharge_m3_s": {
          "times_epoch_unix": [],
          "values": []
        }
      },
      "summary": {
        "mean_temperature_c": 11.5,
        "cold_fraction_below_24_c": 0.98,
        "mean_discharge_m3_s": 1.2
      },
      "quality": {
        "temperature_coverage_fraction": 0.96,
        "discharge_coverage_fraction": 0.90,
        "max_gap_s": 7200,
        "status": "usable_for_screening"
      },
      "provenance": {}
    }
  ]
}
```

Then create two different downstream products:

### Solver source

```json
{
  "id": "tributary_001",
  "cell_id": "firehole_cell_00080",
  "flow_m3_s": 1.2,
  "temperature_c": 11.5,
  "status": "prescribed_screening_forcing"
}
```

### Landscape pocket

```json
{
  "id": "pocket_tributary_001",
  "river_id": "tributary",
  "conservation": "non_conservative",
  "chainage_m": 3500.0,
  "temperature_c": 11.5,
  "flow_m3_s": 1.2,
  "tributary_provenance": {}
}
```

These should not be the same object.

---

# Priority fixes

## Immediate runtime fixes

1. Import `datetime` in `run_hot_lowflow_with_tributaries_v2.py`.
2. Honor `--tributary-cells`.
3. Honor `--real-data-only`.
4. Normalize the real tributary schema.
5. Stop hardcoding `11.5°C` into all frames.
6. Fix the output path handling.
7. Validate candidate fields before creating cells.

## Scientific fixes

8. Verify every gauge/stream identity.
9. Verify every confluence using world topology.
10. Remove fabricated hydraulic diagnostics.
11. Do not apply one USGS cross-section to every mainstem feature.
12. Condition refuge analysis on hot/low-flow observations.
13. Separate measured, documented, and authored data.

## Architectural fixes

14. Keep prescribed pockets out of the thermal solver’s `cells`.
15. Use `river_world.py` as the geometry authority.
16. Use `channel_geometry.py` as geometry evidence, not proof of bathymetry.
17. Add scheduled source-flow support before wiring time-varying runoff or tributary discharge.
18. Produce one normalized tributary evidence schema.

## Bottom line

The scripts are relevant, but the current wiring creates a misleading result:

```text
real-looking tributary metadata
    ↓
partly ignored fields
    ↓
authored fallback temperature/flow/geometry
    ↓
fake solver cells appended to replay frames
    ↓
foodweb comparison
```

The safer pipeline is:

```text
verified USGS evidence
    ↓
validated stream/confluence association
    ↓
explicit decision:
    ├── prescribed solver source
    └── non-solver landscape pocket
    ↓
foodweb/thermal coupling with provenance
```

Until that separation is implemented, the output should be labeled as an **illustrative refuge visualization**, not a calibrated or measured tributary refugia simulation.