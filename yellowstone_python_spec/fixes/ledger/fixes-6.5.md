# fixes-6.5 ledger
Doc: fixes/fixes-6.5.md | read 2026-10-12 | targets: yellowstone_python/yellowstone_python/microclimate.py sha256:0ebbb16da902 ; yellowstone_python/yellowstone_python/overland_flow.py sha256:4143b33a8ffc ; yellowstone_python/yellowstone_python/pool_crust.py sha256:532c72dd294d ; yellowstone_python/tests/test_microclimate.py ; yellowstone_python/tests/test_overland.py ; yellowstone_python/tests/test_pools.py
Summary: 5 items: 5 implemented, 0 shortcut, 0 partial, 0 missing, 0 superseded, 0 conflicts (recounted from rows 2026-10-13)

| item | requirement (one line) | verdict | evidence file:line | note (one line) | cost cheap/medium/refactor |
|---|---|---|---|---|---|
| 1 | fetch_real_weather and load_weather_bundle exist and are distinct | implemented | microclimate.py:41-47, 254-262, tests/test_microclimate.py:249-256 | both names present and distinct; load_real_weather is a deprecated alias that emits DeprecationWarning; test_weather_loader_names_are_distinct landed | cheap |
| 2 | run_overland reports effective configuration keyed by soil | implemented | overland_flow.py:216-228 configuration block with soil, soil_map, infiltration, downsampling; tests/test_overland.py:74-86 `test_soil_parameter_changes_effective_configuration` asserts soil propagates and clay ponds > sandy | tests gated by `@needs_hydrosim`; configuration + output both differ by soil | medium |
| 3 | _downsample uses all source cells (final row and column survive) | implemented | overland_flow.py:81-104 per-destination `r0,r1 = r*src//dst, (r+1)*src//dst` block-mean covers [1024,:] and [:,1024]; tests/test_overland.py:29-37 asserts a 1025->256 spike at [1024,1024] survives | 1025->256 case verified; `test_downsample_rejects_bad_sizes` enforces guards | cheap |
| 4 | bundle_weather uses actual timestamp (not row index) | implemented | microclimate.py:273-343, tests/test_microclimate.py:272-320 | timestamp_utc=datetime (timezone-required) added; epoch_s_utc kept; hour= deprecated with DeprecationWarning; single time argument enforced | medium |
| 5 | render_apron_tiles fills the apron buffer, not only outline | implemented | pool_crust.py:418-422 `dr.polygon(buf, fill=255); dr.polygon(ring, fill=200)`; tests/test_pools.py:165-187 `test_render_apron_tiles_fills_the_apron` asserts center=200 and apron ring=255 | matches recommended pattern (apron fill first, water overlay) | cheap |

## Cross-project issues
- `load_real_weather` alias in microclimate.py:252 keeps the deprecated name alive; callers (including llm_backend.py:206) still import it, so the clean two-name contract from fixes-6.5 is only superficially present.
- bundle_weather's `hour=` parameter remains supported for backward compatibility and interprets `hour` as UTC offset from the first row's day (microclimate.py:274-276); callers reading bundles that span multiple days can select the wrong row.
- hydrology_provider._compute (hydrology_provider.py:203) imports `_downsample` from overland_flow; coupling means any _downsample schema change affects both the overland and the hydrology snapshot paths.

## Scientific validity flags
- Block-mean downsampling preserves full source extent but averages across a 4x4 to 32x32 block, smoothing basin edges; the coarse DEM used by hydrology is not conservation-preserving at the pool margin.
- bundle_weather sets `day_warming_c=0.0` and takes the hourly air temperature as the absolute value (microclimate.py:296-297,315); any downstream model relying on diurnal structure must reconstruct it or operate on absolute hourly snapshots only.
- render_apron_tiles bakes an authored buffered polygon mask with pixel values 200/255; downstream consumers that threshold at an intermediate value will see jagged quantization at the apron boundary rather than a measured gradient.
- The `test_soil_parameter_changes_effective_configuration` test (tests/test_overland.py:86) relies on clay Ksat < sandy loam producing deeper ponded depth; the inequality holds for this terrain fixture but is not a universal physics guarantee.
