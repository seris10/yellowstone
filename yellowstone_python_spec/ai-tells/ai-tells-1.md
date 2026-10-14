I've now read every significant file in the project. Let me compile the complete categorized list of all comments found.

---

## COMPLETE COMMENT AUDIT — yellowstone_python/

Given the massive volume of comments across 60+ files, I'll present this as a structured categorization. Each entry shows: **file path : line number** | **comment text** | **classification**

---

### AI TELL COMMENTS

---

**`../../yellowstone_python/yellowstone_python/__init__.py`**
- L1: `"""Yellowstone Midway Python modeling package (illustrative, not calibrated)."""` | **CLEAN**

---

**`../../yellowstone_python/yellowstone_python/analysis_store.py`**
- L1-41: Module docstring (41 lines) — extensive narrative about design decisions, "measured" problems, R-tree absence failing "LOUDLY", DuckDB "explicitly out of scope" | **AI TELL** (overly verbose AI self-explanation, meta-commentary about design process)
- L56-58: `# Unit factors, stated once (see module docstring). SNOTEL bundle schema: # yellowstone.snotel_obs.v1 stores WTEQ/PRCP/SNWD in inches, TAVG/TMAX/TMIN # in degF (bundle provenance documents the same factors).` | **AI TELL** (meta-commentary about module organization)
- L84: `"""Fail loudly if this SQLite lacks the R-tree module."""` | **CLEAN**
- L181-182: `# OR REPLACE frees the old rowid; its R-tree entry would otherwise # survive as garbage pointing at a dead (later reusable) rowid.` | **AI TELL** (narrative about hypothetical failure)
- L325: `"""Build an in-memory store from parsed docs. Fits optional."""` | **CLEAN**
- L355-360: `"""Build a store file from ONE build dir + obs inputs. Atomic write. Refuses to overwrite an existing file: derived artifacts are history, so a rebuild gets a new name (or the caller removes the old file explicitly and says why)."""` | **AI TELL** (narrative about design philosophy)
- L409: `# ---- read-only query layer (allow-listed tables/columns, no raw SQL) ----` | **CLEAN**
- L434-435: `# Single source of truth for circle-radius bounds (llm_backend aliases # these; the constants test pins them equal so the two cannot drift).` | **AI TELL** (meta-commentary about testing strategy)
- L481-487: `"""Read-only bounded query over allow-listed tables/columns/filters. Filters per table: ..."""` | **CLEAN**
- L586: `filters[k] = v  # validated; consumed below (was: dropped)` | **AI TELL** (narrative about past bug fix)
- L633-638: `"""Circle crown count via the R-tree (bbox prefilter + exact radius). Same answer contract as Backend.circle_stats over census.json; the JSON-vs-store cross-check test pins equality. Used by /api/density when a store file is present."""` | **AI TELL** (meta-commentary about test cross-checks)

---

**`../../yellowstone_python/yellowstone_python/aquatic_foodweb.py`**
- L1-23: Module docstring (23 lines) — "audit's Phase 2 vertical slice", "multirate doctrine", "documented separation, not a single instant" | **AI TELL** (meta-commentary about development process, references to audit phases)
- L37: `COVER_DEFAULT = 0.6  # authored trout cover (same default as update_trout)` | **CLEAN**
- L41: `"""Accept a bare replay, a river_replay.json sidecar, or {data:{...}}."""` | **CLEAN**
- L57-64: `"""Per-cell quasi-steady thermal + hydraulic habitat from replay frames. Default averages all frames (ambient landscape). t_min_s/t_max_s restrict to a window — REQUIRED for intervention comparison, where a whole-run mean would dilute a short pulse into invisibility. Window bounds are explicit so control and pulse landscapes cover the same clock interval."""` | **AI TELL** (em dash, overly verbose explanation)
- L93-95: `# Mapped bed shear (Pa) or None where Manning is undefined # (sub-noise-floor grade cells); run_foodweb maps None to # zero disturbance, never to an invented value.` | **AI TELL** (meta-commentary: "never to an invented value" — narrative about design intent)
- L103-110: `"""Mapped bed shear (Pa) -> benthic disturbance fraction in [0, 1]. None shear (Manning-undefined cell) and None threshold (coupling off) both yield zero. Positive shear at/below the threshold yields zero; above it the fraction ramps linearly to 1 at twice the threshold (authored shape, stated in run_foodweb). Nonfinite or negative shear raises instead of silently zeroing."""` | **AI TELL** (overly verbose, "authored shape, stated in run_foodweb" is meta-commentary)
- L130-142: `"""Multi-day insect + trout + dipper dynamics on a thermal landscape. shear_disturb_pa wires mapped bed shear into benthic disturbance: disturbance ramps 0 at the threshold to 1 at twice it (authored shape), None shear (Manning-undefined cells) maps to zero, and None threshold switches the coupling off entirely. Default 20 Pa sits above the current reach-uniform mapped shear (~15 Pa), so default runs reproduce disturbance-free behavior exactly; pass an explicit lower threshold for sensitivity runs. NOTE (2026-10-10): mapped shear is reach-averaged and currently uniform, so the coupling acts as a global benthos tax until cell-scale hydraulics vary — no spatial contrast is modeled today."""` | **AI TELL** (date-stamped NOTE, em dash, meta-commentary about current limitations)
- L151-155: `# Consumption runs on HOURLY substeps inside each development day. # Daily-step Holling demands saturate (rate x 24 h >> availability), # which collapses pro-rata competition to a fixed 50/50 split and # makes attack rates, handling times, and diet shares irrelevant. # Hourly depletion keeps every parameter load-bearing.` | **AI TELL** (overly verbose explanation reading like AI self-explanation)
- L190: `# Trout refuge selection over replay cells (literature path).` | **CLEAN**
- L203-210: `# Consumption at the refuge cell (shared foraging ground). # Exploitative competition on HOURLY substeps: trout and dipper # demands are computed from the SAME pre-consumption stocks, then # scaled pro-rata if combined demand exceeds availability. # (Sequential ordering would hand the outcome to whoever eats # first — an arbitrary choice. Daily-step demands would saturate # and collapse competition to a fixed split regardless of diet # shares or Holling parameters — verified failure, Oct 2026.)` | **AI TELL** (em dashes, "verified failure, Oct 2026" — references past attempts)
- L240-242: `# Adult turnover: emergent insects die/disperse within days # (authored mean residence ne_turnover_days; without it Ne # accumulates without bound — verified failure, Oct 2026).` | **AI TELL** (em dash, "verified failure, Oct 2026")
- L322-327: `"""Refuge + diet + emergence response to a thermal intervention. window_s isolates the intervention clock interval in BOTH runs (control window-mean vs pulse window-mean); without it a short pulse vanishes into the whole-run mean. Reported explicitly."""` | **AI TELL** (narrative about hypothetical failure: "without it a short pulse vanishes into the whole-run mean")
- L331-332: `window_note = ("full-run means; short pulses are diluted — " "pass window_s to isolate the intervention")` | **AI TELL** (em dash in string)

---

**`../../yellowstone_python/yellowstone_python/build.py`**
- L1-17: Module docstring — "M11 build", "audit-split orchestration", "Scientific timeline (explicit, multirate)" | **AI TELL** (references to audit process)
- L37: `# Authored topology: named lookups fail loudly (never silent wrong defaults).` | **CLEAN**
- L67: `"""Reject nonphysical config before any simulation (explicit, early)."""` | **CLEAN**
- L73-75: `# Absent clock_hour falls back to the system clock at simulate time # (resolve_game_clock, range-safe by construction); only explicit # values are range-checked here.` | **AI TELL** (excess information, "range-safe by construction" redundant meta-commentary)
- L149: `eco_path = frozen  # idempotent rebuilds, never compounding` | **CLEAN**
- L168: `"""Apply config overrides to a deepcopy of the baseline for the replay solver."""` | **CLEAN**
- L188: `"""Run the 1-D advection-dispersion solver on the Firehole chain. Returns the full replay document with timestamped frames and budget."""` | **CLEAN**
- L219: `"""Pure scientific simulation: no files, no PNGs, no CLI. Returns state."""` | **CLEAN**
- L257-260: `"godot_divergence_note": ("published night/day params drive ecosystem.gd's noon-peaking air; Python analysis uses a 15:00-lagging curve — residual documented, not hidden")` | **AI TELL** (em dash, meta-commentary)
- L266: `# --- M01 hydro ---` | **CLEAN**
- L290: `# --- M01b 1-D advection-dispersion replay (Phase 2 flagship) ---` | **AI TELL** (references to development phases)
- L293-296: `# --- M05b aquatic food web (audit Phase 2 vertical slice): replay # heat → insect prey → trout refuge → dipper intake, 14-day run on # the quasi-steady thermal landscape (multirate doctrine, see # aquatic_foodweb). Pure science here; artifact written below.` | **AI TELL** (references to audit phases, "vertical slice")
- L309: `# --- M03 shells ---` | **CLEAN**
- L317: `# --- M04 vegetation + proposals ---` | **CLEAN**
- L336: `# --- M05 insects (legacy activity + compartments) ---` | **CLEAN**
- L378: `# --- M06 fish ---` | **CLEAN**
- L388: `# --- M07 grazers ---` | **CLEAN**
- L392-394: `# Re-walk the bison's ACTUAL authored route through the eligibility # planner, segment by segment, so the corridor is verified rather than # demonstrated on a two-point demo. Bounds come from the route itself.` | **AI TELL** (overly verbose, "verified rather than demonstrated on a two-point demo" is narrative about development process)
- L415: `# --- M08 season ---` | **CLEAN**
- L425: `# --- merge variant ---` | **CLEAN**
- L468: `"""Visualization + export: PNGs and JSON sidecars from simulated state."""` | **CLEAN**

---

**`../../yellowstone_python/yellowstone_python/canopy_census.py`**
- L1-22: Module docstring — "documented limits included", "observation, not authoring", "REVIEWED against these records" | **AI TELL** (overly verbose, meta-commentary about design philosophy)
- L35: `DETAIL_HALF = 640.0  # local metres covered: [-640, 640]` | **CLEAN**
- L36: `PX_M = 1.25 / 2.0  # 0.625 m per pixel` | **CLEAN**
- L46: `"""ExG greenness, brightness, blue-water flag. All float32 arrays."""` | **CLEAN**
- L58: `"""Return tree records with pixel coords. Deterministic (no RNG)."""` | **CLEAN**
- L62: `# Candidate crown pixels: green AND dark (conifer crowns, not grass).` | **CLEAN**
- L66: `# Peaks: local maxima of ExG inside crown mask, >= 2 m apart.` | **CLEAN**
- L70-71: `# Collapse flat-top plateaus: each connected max-component yields one # peak at its centroid (uniform discs would otherwise count per pixel).` | **CLEAN**
- L91-92: `# Suppress weaker neighbors within the peak distance (same pass, # strength-ordered, so suppression cannot shift later acceptances).` | **CLEAN**
- L112: `"""Mapped water outlines (local x,z ring vertices)."""` | **CLEAN**
- L134-135: `"""Drop detections inside mapped water + margin (rim artifacts, not stems). Returns (kept, n_dropped)."""` | **CLEAN**
- L148: `# margin test: inside ring, or within margin of any vertex` | **CLEAN**
- L164: `"""Pixel records -> stable local-metre records (id from pixel, stable)."""` | **CLEAN**
- L181: `"""Red dots on imagery for human review (not a placement map)."""` | **CLEAN**
- L196: `"""Record x/z: dict key or tuple index — both call sites use either."""` | **AI TELL** (em dash)
- L203-205: `"""Trees/ha per named zone. Zone spec: {"circle": (cx, cz, r)} or {"ring": (cx, cz, r0, r1)} or {"box": (x0, z0, x1, z1)}. Records may be dicts ({x,z,...}) or (x, z) tuples."""` | **CLEAN**
- L232: `QA_CROWN_CAP_M = 6.0  # matches the cap in detect()` | **CLEAN**
- L238-239: `"""Mechanical self-check of a census document. Returns failure strings (empty means pass). No image or human data needed."""` | **CLEAN**
- L332-334: `"""Measure single isolated crowns: components with no neighbor centroid within isolation_m. Returns the true single-tree size distribution — the ruler every larger blob is split against."""` | **AI TELL** (em dash)
- L369-372: `"""v1 peaks PLUS area-based top-up: blobs larger than lone trees can be are split to their area-implied stem count at secondary brightness uplifts (sunlit crown tops inside dark patches). Each record carries splitting_basis: peak | area_topup."""` | **AI TELL** ("v1" reference to past version)

---

**`../../yellowstone_python/yellowstone_python/census_validate.py`**
- L1-14: Module docstring — "Blind validation", "plots must stay out of detector tuning" | **CLEAN**
- L105: `print(f"sampled {len(sample)}/{len(frame)} plots -> {crops} (BLIND: no dots)")` | **CLEAN**

---

**`../../yellowstone_python/yellowstone_python/common/coords.py`**
- L1-12: Module docstring — "M00 coords: single EPSG:32612 frame authority" | **CLEAN**
- L26: `# Saved anchors (references/geoanchors.json; local x,z metres)` | **CLEAN**
- L34: `"""Local (x=east, y=up-from-2200, z=south) -> (E, N, H_NAVD88)."""` | **CLEAN**
- L39: `"""(E, N, H_NAVD88) -> local (x, y, z)."""` | **CLEAN**
- L44: `"""Grid indices via floor (never truncation, never epsilon nudge)."""` | **CLEAN**
- L51-55: `"""Bilinear sample matching height_field.gd diagonal. h: flat row-major GRID*GRID array, row zero is north (iz=0 -> z=-HALF). Clamps to valid range like GDScript clampf."""` | **CLEAN**

---

**`../../yellowstone_python/yellowstone_python/common/provenance.py`**
- L1: `"""M00 provenance: hashes, build ids, sidecars (SHARED_WORLD_CONTRACT §8.1)."""` | **CLEAN**
- L15-16: `"""Portable world-root default: $YELLOWSTONE_WORLD wins, else the shipped checkout path. Callers must still verify it exists."""` | **CLEAN**
- L44: `"""Inject contract header + provenance, write JSON, return full doc."""` | **CLEAN**

---

**`../../yellowstone_python/yellowstone_python/common/units.py`**
- L1: `"""M00 units: explicit converters. Fail loudly on bare/mixed units."""` | **CLEAN**
- L9: `M3S_PER_GPM = 0.0000630902  # 1 US gal/min in m3/s` | **CLEAN**
- L48: `"""Wrap a dimensionless 0..1 index so it can never be mistaken for kg/counts."""` | **CLEAN**

---

**`../../yellowstone_python/yellowstone_python/common/validate.py`**
- L1: `"""M00 validate: NoData/NaN guards, topology, conservation, provenance checks."""` | **CLEAN**
- L15: `"""Must be an upstream-first serial chain (ecosystem.gd supports one chain)."""` | **CLEAN**

---

**`../../yellowstone_python/yellowstone_python/compare.py`**
- L1-10: Module docstring — "A/B outcome comparison: quantify scenario response, not just config diff" | **CLEAN**

---

**`../../yellowstone_python/yellowstone_python/exporters/to_ecosystem.py`**
- L1: `"""M11 to_ecosystem: merge Python fragments into schema-v1 ecosystem.json."""` | **CLEAN**
- L11-15: `"""Return a new ecosystem dict; baseline never mutated. river_state: list of {id, temperature_c} (or full reach dicts). weather: {night_air_c, day_warming_c, wind_xz_mps, gust_mps, ...}."""` | **CLEAN**

---

**`../../yellowstone_python/yellowstone_python/exporters/to_map.py`**
- L1: `"""M11 to_map: reproject field PNGs into the midway_macro frame (stub)."""` | **CLEAN**
- L6-9: `"""Phase 0: fields are already authored in macro extent; plain copy. A real reprojection (extent/origin aware) arrives with M03 aprons."""` | **AI TELL** (references to development phases)

---

**`../../yellowstone_python/yellowstone_python/fish.py`**
- L1-21: Module docstring (21 lines) — "visibility modulator, NOT mortality", "an actual choice among alternatives, not a preserved route", "Both labeled where used" | **AI TELL** (overly verbose, meta-commentary)
- L28: `ASSUMED_DEPTH_M = 1.1  # prepare_world carve_water_support default depth` | **CLEAN**
- L29: `RIVER_WIDTH_M = 22.0   # Firehole authored width` | **CLEAN**
- L30: `MAX_LATERAL_FRACTION = 0.35  # wildlife_actor.gd river-interior guard` | **CLEAN**
- L31: `REFUGE_WINDOW_M = 150.0  # accessible swim range along chainage` | **CLEAN**
- L32: `VELOCITY_OPT_MPS = 0.35  # trout holding preference (illustrative)` | **CLEAN**
- L35-43: `# Cold-water trout thermal optimum band (illustrative, from the same # 20 °C upper-bound context as ecosystem.gd's thermal stress term). # Two-sided: water below the band is too cold, above it is stressful. # A one-sided penalty (max(0, T-20)/10) cannot discriminate reaches that # are all below 20 °C, which is exactly the Firehole's summer profile here # (17.6-19.2 °C) — with it, every reach ties and there is nothing to select. # The niche band is a documented model choice, not a measurement. # LEGACY: kept for ecosystem.gd parity and existing tests. New work uses # THERMAL_SPECIES + thermal_performance() below (literature-transferred).` | **AI TELL** (em dash, "LEGACY" reference to past versions, "New work uses")
- L48-75: Large comment block about literature-transferred thermal performance, "ANCHOR POINTS (literature-transferred = real scientific measurements)", "CURVE SHAPES (piecewise linear between anchors): AUTHORED CHOICE", "REAL DATA NEEDED", "STATUS: literature-anchored, curve-shape authored" | **AI TELL** (extensive meta-commentary about data provenance, references to integration points)
- L127: `# Behavioral refuge ramp width above t_refuge: authored shape choice.` | **CLEAN**
- L129-130: `# Weight of the refuge-drive term in suitability: authored model choice # (the anchors it multiplies are literature; the weight is not).` | **CLEAN**
- L133-138: `# --- Real-data integration point for laboratory thermal measurements --- # When lab trial data (feeding rate vs T at fine resolution) becomes # available, load_lab_thermal() replaces the piecewise-linear curve # between anchor points with measured curves. Until then, authored # linear interpolation is used with full provenance documentation. REAL_LAB_DATA_PATH = None  # Set to file path when measurements are available.` | **AI TELL** (narrative about future plans, meta-commentary)
- L141-148: `"""Load real laboratory thermal-performance measurements. Returns a dict with measured feeding/stress curves, or None if no real data is configured (REAL_LAB_DATA_PATH is None or missing). This is the integration point: when a CSV/JSON of lab trial data is provided, this replaces the authored piecewise-linear shape."""` | **AI TELL** (meta-commentary about integration points)
- L155-157: `# Integration hook: read measured curves here. # For now returns None with provenance logged; real data # path must be explicitly configured.` | **AI TELL** (narrative about current state)
- L162: `"""Report provenance status for thermal performance data."""` | **CLEAN**
- L179: `"""One-sided stress term kept for ecosystem.gd parity (≥0 above 20 °C)."""` | **CLEAN**
- L184-188: `"""Two-sided preference in [0, 1]: 1.0 inside the optimum band, falling linearly to 0 outside. LEGACY authored band (see T_OPT note); new work uses thermal_performance(). This is what makes refuge SELECTION possible — with a one-sided penalty the whole Firehole scores identically and there is nothing for the fish to choose."""` | **AI TELL** (em dash, "LEGACY", "new work uses")
- L201-210: `"""Nondimensional U: preferred velocity/depth ranges, two-sided thermal preference. Weights are pure numbers; every term is in [0,1]. species=None (default) keeps the legacy authored band, exactly as before. species='brown_trout'/'rainbow_trout' replaces the thermal term with 1 - feeding(T) from THERMAL_SPECIES and subtracts refuge_weight * refuge_drive(T): warm cells repel through a literature-anchored behavioral term (Kaya et al. 1977), not just lost feeding."""` | **AI TELL** (overly verbose, meta-commentary)
- L219-222: `# Feeding loss saturates at feed_zero; stress keeps the gradient # worsening with temperature above it, so hotter-than-tolerable # cells can never tie (without this, all T >= feed_zero score # identically and ties break toward hot water — backwards).` | **AI TELL** (em dash)
- L231-240: `"""Literature-anchored performance at one water temperature. Returns {feeding, stress, refuge_drive, lethal_flag} in [0, 1] (lethal_flag is 0/1). Anchor POINTS are transferred from measurement (see THERMAL_SPECIES); piecewise-linear SHAPES between them are an authored choice. refuge_drive is Firehole-measured behavior (Kaya, Kaeding & Burkhalter 1977: movement at mean > 24 C); lethal_flag marks water above UILT — a flag for the record, never a mortality simulation (standing rule: shelter, never mortality)."""` | **AI TELL** (em dash, meta-commentary about design rules)
- L276: `"""Nearest reach by z — mirrors ecosystem.gd::reach_at (kept for runtime)."""` | **AI TELL** (em dash)
- L281: `"""Cumulative metres along the saved downhill point order."""` | **CLEAN**
- L290-297: `"""Per-point reach id table using the DECLARED upstream chain order. z-nearestness (the old assign_reach path) fails for looping or U-shaped channels: a reach can be closest in z yet lie kilometres away along the water. Walk the declared chain instead and assign every point to the reach whose z-window contains it; points outside every window fall back to the nearest reach by z, flagged."""` | **AI TELL** (references to "the old assign_reach path" — narrative about changes over time)
- L320: `# Fall back to z order rather than guessing a chain.` | **AI TELL** (Pattern A: references "guessing" as alternative)
- L340-341: `"""Attach z_lo/z_hi per reach: each reach owns the band between its own z and the next reach's z downstream (or ±inf at the ends)."""` | **CLEAN**
- L364: `"""(U, reach_id, reach_temp) for holding at a river index."""` | **CLEAN**
- L378-383: `"""Move the holding window toward max suitability within swim range. Returns {start,end,reach_id,U,reason}. The window length is preserved; the river route itself is never redrawn through unlisted water. species=None keeps the legacy authored band; a species name selects the literature performance path (feeding + refuge drive)."""` | **AI TELL** (overly verbose)
- L420-423: `"""Refuge-selecting trout: holding window relocates toward max suitability within swim range; hold/swim cadence follows reach temperature (shelter, never mortality). Lateral offsets preserved and clamped to the 0.35 interior guard."""` | **CLEAN**
- L439: `heat = 1.0 + temp_penalty(t)  # 1.0 at ≤20 °C` | **CLEAN**
- L457: `"""Centerline AND laterally-offset segment samples (offsets matter)."""` | **CLEAN**
- L460: `tx, tz = -dz / length, dx / length  # unit side vector` | **CLEAN**
- L471-472: `"""Every trout SEGMENT (centerline and laterally offset, sampled every 2 m) must lie outside every apron. Waypoint-only checks miss crossings."""` | **CLEAN**
- L498-501: `"""Deterministic refuge map: Firehole centerline in world position, pool polygons, trout holding midpoints + selected-refuge markers. Every dot is a world coordinate — no hashes, no RNG, reproducible across processes and seeds."""` | **AI TELL** (em dash)
- L507-508: `# Frame: tight box around the Firehole points actually used, so the # whole channel and every pool ring fit. Falls back to the world square.` | **CLEAN**

---

**`../../yellowstone_python/yellowstone_python/gen_flora.py`**
- L1-15: Module docstring — "Flora density pass: generate + machine-review + stage grass and pine infill" | **CLEAN**
- L41: `"note": "sparse edge colonization; threshold recorded, not tuned"` | **CLEAN**
- L124-126: `"""Truly bare pale ground (bright AND greenless). Vegetated bright slopes fail this test and stay plantable — brightness alone excluded real dry meadow in the old mask gate."""` | **AI TELL** (em dash, "old mask gate" — narrative about past)
- L134-135: `"""Map-wide lodgepole infill from the habitat mask (forest = low meadow, low mineral). 12 m grid, per-cell RNG, full gates. IDs are cell-stable."""` | **CLEAN**
- L253-255: `"""Grass verges + pine sentinels along every foot trail polyline, so the walked routes read vegetated. Grass 1.5–5.5 m off centerline; pines 10–28 m off, forest-gated. IDs route/pulse stable."""` | **CLEAN**
- L377-380: `"""Closed-canopy groves where the NAIP aerial shows canopy (dark = trees in 2022), at true stand spacing. Slope + water + route + existing gates still apply; IDs cell-stable. This mirrors observed cover, it does not invent forest where the photo shows meadow or sinter."""` | **CLEAN**
- L459: `young = rng.random() < 0.25  # recruitment understory` | **CLEAN**
- L481-485: `"""Art-directed density ring around the overlook deck. Planted where the slope is walkable and the ground is not water, sinter apron, trail, or road — WITHOUT requiring the aerial to show canopy first. Ledger-marked as enhancement, never as observed cover. Answers the visible-hill sparseness from every yaw, not just the treated sectors."""` | **AI TELL** (em dash, "Answers the visible-hill sparseness" — narrative about design intent)

---

**`../../yellowstone_python/yellowstone_python/gen_trail_mask.py`**
- L1-11: Module docstring — "Paint foot trails into a terrain mask instead of ribbon meshes" | **CLEAN**

---

**`../../yellowstone_python/yellowstone_python/geochemistry.py`**
- L1-9: Module docstring — "sinter-vs-travertine guardrail", "never be built by 'whitening Grand Prismatic'" | **CLEAN**
- L53: `"""Every Midway shell must be siliceous_sinter. Returns failure strings."""` | **CLEAN**
- L63: `"""Raise if anyone applies a travertine palette to a Midway pool."""` | **CLEAN**

---

**`../../yellowstone_python/yellowstone_python/grazers.py`**
- L1-17: Module docstring — "habitat-constrained bison/elk movement", "Deliberately NO universal `wolves→fewer elk→more willow` slider", "Competing hypotheses... carried as separate records with explicit unknowns" | **AI TELL** (overly verbose, meta-commentary about design decisions)
- L41: `MAX_ROUTE_M = 200.0  # wildlife_actor.gd local-scope guard` | **CLEAN**
- L50: `"""Waypoints alone miss crossings — sample the full segment."""` | **AI TELL** (em dash)
- L60-62: `"""Rich patch -> longer graze; poor patch -> sooner walk (actor quits below 0.05 biomass at runtime regardless). Driven by FRACTION OF CAPACITY, not absolute index — patches with different K stay comparable."""` | **AI TELL** (em dash)
- L90-91: `"""Length + apron gates sampled along FULL segments (waypoints alone miss crossings between them; pool-polygon gate also lives in Godot)."""` | **AI TELL** (redundant: "waypoints alone miss crossings between them" already stated elsewhere; "also lives in Godot" is meta-commentary)
- L117-127: `"""8-connected A* with Euclidean heuristic on an eligibility grid. Endpoints must be unblocked (validated, never silently snapped: a blocked endpoint raises). Returned waypoints are cell centers — at most a half-cell (2 m) from the request, recorded in the ledger by callers. A* is a cell graph, so a diagonal step between two free cells can still cross a blocked area smaller than the cell pitch. Each accepted step is therefore re-sampled along its true segment and rejected if any sample is blocked — the same test check_routes applies to authored paths."""` | **AI TELL** (em dashes, overly verbose)
- L138: `"""Every sample along the true segment a→b must be unblocked."""` | **CLEAN**
- L168: `# Corner-cut guard: both orthogonal neighbors must be free.` | **CLEAN**
- L172-173: `# Sample the true segment; a diagonal can still clip a blocked # area that is smaller than the cell pitch.` | **CLEAN**
- L195: `"""Bison loops in the north_meadow frame (field-notes plate)."""` | **CLEAN**

---

**`../../yellowstone_python/yellowstone_python/hydro_thermal.py`**
- L1-16: Module docstring — "M01 hydro_thermal", "Paper equations", "Mirrors scripts/ecosystem.gd::_derive_flows/_advance_heat exactly" | **CLEAN**
- L22: `RHO_CP = 4.186e6  # J/(m3·K), water; used ONLY in profile helper, not mixing step` | **CLEAN**
- L26: `"""Attach q_in/flow/thermal/source_heat like ecosystem.gd::_derive_flows."""` | **CLEAN**
- L111-113: `"""Exact fixed point of the mixing step (audit regression target): T*i = (Qin·Tup + ΣQℓTℓ + (V/τ)·Tair) / (Qout + V/τ) solved upstream-first (feedforward chain → single pass is exact)."""` | **AI TELL** (references audit process; "feedforward chain → single pass is exact" is excess explanation)
- L129-133: `"""Run fixed-dt transport (physical seconds). air_c may be const or fn(t). Ledger now carries FULL budget history (cumulative in/out/exchange/storage), not just max residuals — conservation must hold over the run, not only per substep."""` | **AI TELL** (em dash, "now carries" — narrative about changes)
- L172: `"""Illustrative exponential cooling along centerline (viz only)."""` | **CLEAN**
- L182-186: `"""Illustrative 2-D mixing blob near Excelsior mouth (map overlay only). Gaussian hot anomaly decaying downstream (+z). NOT calibrated. Returns nx*nz row-major floats in °C."""` | **CLEAN**
- L201: `"""Blue→red ramp PNG, same extent convention as habitat_mask.png."""` | **CLEAN**
- L215: `# Illustrative cold dilutions; 0.0 flow = omitted (baseline preserved).` | **CLEAN**

---

**`../../yellowstone_python/yellowstone_python/insects_birds.py`**
- L1-18: Module docstring — "three-compartment prey + bird diets (no universal index)", "Legacy single-index helpers... remain for the existing wildlife-record interface and are marked as such" | **AI TELL** (meta-commentary about legacy code)
- L24: `HOVER_THRESHOLD = 0.035  # wildlife_actor.gd::_update_insects (legacy interface)` | **AI TELL** (legacy reference — references to past versions)
- L32: `"""Exposed insects suppress flight in wind; calm → 1."""` | **CLEAN**
- L37: `"""0 = no bloom, 1 = full bloom; food baseline 0.5 even without bloom."""` | **CLEAN**
- L59: `"""High activity -> shorter perch, longer forage bout (bounded)."""` | **CLEAN**
- L68: `"""Insect resource recovery minus consumption (mirrors ecosystem.gd)."""` | **CLEAN**
- L76-81: `"""LEGACY interface: retune dipper/raven cadence from shared activity. Kept because wildlife_actor.gd reads timer values from records. The compartment sim below is the science; this is its Godot transcription. Prefer update_wildlife_from_intake() for intake-driven timing."""` | **AI TELL** ("LEGACY", narrative about design decisions)
- L95: `# --- Three-compartment prey dynamics (the actual model) ---` | **AI TELL** ("the actual model" — meta-commentary)
- L99: `"""C(N) = aN/(1+ahN). Saturates; never exceeds 1/h. All illustrative."""` | **CLEAN**
- L109-116: `"""Benthic larvae: degree-day development → emergence flux; flood/hydraulic disturbance removes a fraction. Returns (nb_new, emergence). t_cutoff (optional): development stupor above this temperature — dd forced to 0, documented as arrested development, not death (cf. Maier et al. 1990 upper tolerance; Sweeney & Vannote 1981 on sublethal thermal stress). None keeps the legacy no-ceiling path."""` | **AI TELL** (em dash, "legacy" reference)
- L130-144: Large comment block about benthic insect groups — "transferred thermal structure", "Relative RATES (dipteran faster, multivoltine) are an authored ordering, not measured Firehole rates", "Degree-day caveats apply" | **AI TELL** (meta-commentary about data provenance)
- L170-178: `"""Trout benthic-vs-emergent shares shift with temperature. Cold water: almost entirely immature benthic insects; warm water: heavily emerging insects (Kaeding & Kaya 1978, Firehole stomach contents). Linear transition 15 -> 21 C (growth-restriction onset, Kaeding 1976); shape authored, endpoints transferred. Molluscs, a major warm-station food in the same study, are NOT modeled — warm-cell food is therefore underestimated, documented limitation."""` | **AI TELL** (em dash, "documented limitation" — meta-commentary)
- L186-188: `"""Advance {Nt, Nb, Ne} one step. forcing: sun/air/cloud/moisture/wind/flowering/water_c/disturbance. consumers: {dipper:{a,h,share}, ...}. Returns (new_state, ledger{emergence, consumed_by, activity})."""` | **CLEAN**
- L232-233: `# Dipper: benthic wading + emergent aerial; trout: emergent/drift; # raven: generalist background (never reducible to the insect signal).` | **CLEAN**
- L241-243: `"""Bout timing from Holling intake rate (satiation shortens foraging). intake_by_id: consumer id → prey/hour. Raven floor: generalist diet keeps a baseline bout regardless of insect intake."""` | **CLEAN**
- L253: `satiety = max(0.3, satiety)  # generalist floor` | **CLEAN**
- L262: `"""Hourly activity proving overcast+wind → inactive, calm sun → hover."""` | **CLEAN**

---

**`../../yellowstone_python/yellowstone_python/llm_backend.py`**
- L1-30: Module docstring (30 lines) — "LLM-friendly backend", extensive endpoint list, "NOT the generic DeepForest screenshot detector, which was cross-checked 2026-10-09" | **AI TELL** (references to past cross-checks, overly verbose)
- L61-66: `ACCURACY_NOTES` list — "Cross-check 2026-10-09: pretrained DeepForest... found 2 crowns at score 0.25 and 53 at score 0.05, versus ~1,175 census crowns" | **AI TELL** (references to past work, narrative about validation)
- L69-72: `# Hardening limits (adversarial review 2026-10-09). Density circles outside # [MIN_RADIUS_M, MAX_RADIUS_M] are sub-decimetre noise or larger than the # world, so they are rejected instead of returning inf/absurd densities. # Bounds are single-sourced from analysis_store (constants test pins them).` | **AI TELL** (references to "adversarial review 2026-10-09", meta-commentary about test pinning)
- L75: `# Legitimate /api/propose bodies are <1 KB; anything larger is junk/DoS.` | **CLEAN**
- L77: `# Review logs are returned inline; longer ones are truncated with a marker.` | **CLEAN**
- L82-86: `"""A data file on disk is missing or corrupt (server-side -> HTTP 500). Raised for unreadable files and malformed records so handlers can distinguish server data rot (500) from bad client input (400)."""` | **CLEAN**
- L101: `"""Strict numeric coercion: rejects bools and non-finite values."""` | **CLEAN**
- L114: `"""Strict integer coercion: rejects bools, truncating floats, int(inf)."""` | **CLEAN**
- L139: `"""Cached file-backed state. All methods read-only (no writes)."""` | **CLEAN**
- L151-155: `"""Newest derived/analysis_*.sqlite, or None when no store exists. Explicit constructor `store=` wins; otherwise the newest store file is resolved live (stores are history: one file per build)."""` | **CLEAN**
- L169-173: `"""Read-only bounded query over the analysis store. Raises FileNotFoundError (HTTP 503) when no store file exists; ValueError (HTTP 400) on any validation rejection."""` | **CLEAN**
- L186-192: `"""Circle crown count, store-backed when a store file exists. The store path (R-tree bbox prefilter + exact radius) and the JSON path (full scan) share one answer contract; the JSON-vs-store cross-check test pins equality so the two implementations cannot drift."""` | **AI TELL** (meta-commentary about test cross-checks)
- L268: `# Server-side data rot, not client input -> 500, not 400.` | **CLEAN**
- L341-344: `"interpretation": ("positive deficit = game sparser than 2022 NAIP canopy; negative = game denser. Both layers are unreviewed/authored; target human NAIP review, not auto-editing.")` | **AI TELL** (meta-commentary about process: "Both layers are unreviewed/authored; target human NAIP review, not auto-editing")
- L442-443: `# Fault-isolated sections: one corrupt file degrades its section # instead of failing the whole bundle.` | **CLEAN**
- L470: `"""Dry-run only: suitability proposals + machine review, no writes."""` | **CLEAN**
- L548: `# ---- HTTP layer (stdlib only) ----` | **CLEAN**
- L550: `backend: Backend = None  # set by serve()` | **CLEAN**
- L562: `pass  # client went away mid-response; nothing to report to` | **CLEAN**
- L617-618: `# /api/query only: llm_backend still serves everything else # when no store file exists.` | **CLEAN**
- L625: `except Exception as exc:  # never leak a traceback to clients` | **CLEAN**
- L688: `pass  # quiet; use --serve logs from the caller if needed` | **CLEAN**

---

**`../../yellowstone_python/yellowstone_python/microclimate.py`**
- L1-17: Module docstring — "M02 microclimate: ONE wind/time authority", "Condensation, not 'steam'", "the legacy steam_visibility() index remains only for the old Godot uniform path" | **AI TELL** (em dashes, references to legacy code)
- L26-33: `# --- Weather forcing provenance --- # night_air_c=7.0, day_warming_c=15.0, humidity=0.45, cloud=0.16, # wind_xz_mps=[1.8, 0.6], gust_mps=0.45 are AUTHORED defaults (illustrative # scenario, not measured). REAL DATA: fetch_met_forcing.py connects to # Open-Meteo (NWP blend) for measured remote forcing; integration hook # load_real_weather(site_lat, site_lon, days) below provides the path. # STATUS: authored defaults enabled; real Open-Meteo fetch available # via tools/fetch_met_forcing.py but not wired into baseline.yaml.` | **AI TELL** (extensive meta-commentary about data provenance, "STATUS:" narrative)
- L51-56: `"""Integration point: load real Open-Meteo forcing for site. Returns a met bundle dict (same shape as fetch_met_forcing output) or None if fetch fails / not configured. Callers should handle None gracefully (fall back to authored defaults, document gap)."""` | **AI TELL** ("Integration point" — meta-commentary)
- L82: `"""Compass degrees of the low-frequency prevailing wind (no gust)."""` | **CLEAN**
- L88-89: `"""LEGACY artistic index for the old Godot uniform path. Prefer condensation_potential() for analysis."""` | **AI TELL** ("LEGACY", "old Godot uniform path")
- L95: `"""Saturation vapor pressure, Magnus form (kPa)."""` | **CLEAN**
- L100: `"""Invert Magnus: dew point from air temp + relative humidity [0,1]."""` | **CLEAN**
- L107: `"""Boiling point at site pressure (Antoine, water, valid 1–100 °C)."""` | **CLEAN**
- L115-126: `"""Evaporation flux + dew-point depression + mixing supersaturation proxy. evap ∝ (es(Tsurf) − ea) · (1 + wind/5) [kPa-weighted aerodynamic form]; a hot surface evaporating into cool humid air produces a mixed parcel whose vapor exceeds saturation → visible droplets. All illustrative. `relative_supersaturation` is the quantity the Godot renderer consumes: (q_mix − es(t_mix)) / es_surf, the mixed parcel's excess vapour as a fraction of the source pressure, clamped to [0,1]. Same Magnus form and same 30/70 entrainment ratio as scripts/ecosystem.gd::condensation_visibility, so the two sides cannot drift apart."""` | **AI TELL** (overly verbose, meta-commentary about consistency)
- L132: `# Entrainment fraction χ=0.3 of surface-saturated air into ambient:` | **CLEAN**
- L150-152: `"""Seeded Ornstein-Uhlenbeck gusts around the prevailing vector. Reproducible across processes (unlike wall-clock noise); mean-reverting so the prevailing direction dominates 60 s traces."""` | **AI TELL** (comparison to alternative: "unlike wall-clock noise"; excess explanation: "so the prevailing direction dominates 60 s traces")
- L167-171: `"""Per-second (wind, air_c, hour) trace. Pass the FULL weather config (night_air_c, day_warming_c, humidity, cloud, wind_xz_mps, gust_mps) so the trace cannot disagree with configured weather (audit fix). With a seed, gusts come from the OU process; otherwise the legacy sinusoid (Godot-compat) is used."""` | **AI TELL** ("audit fix" — references to audit process)

---

**`../../yellowstone_python/yellowstone_python/pool_crust.py`**
- L1-17: Module docstring — "M03 pool_crust", "Replaces the flat terrain-cut visual floor", "Mapped water outlines are PRESERVED (never resized for composition)", "NO universal temperature→rainbow equation" | **CLEAN**
- L22: `HALF = 2048.0  # world half-extent, metres (matches coords.py)` | **CLEAN**
- L24-25: `# Authored shell recipe per named pool: multipliers/offsets on r_water. # Documented design decisions, not measurements.` | **CLEAN**
- L44-46: `# Base pigment bands (fraction of r_water, color, meaning). Per-pool copies are # adjusted by make_ramp_stops() — there is no universal temperature→rainbow # equation; these are authored bands keyed to depth + gradient + substrate.` | **AI TELL** (em dash)
- L67-69: `"""Per-pool pigment stops. Deeper centers render darker; stronger center→edge gradients narrow the blue core and widen the microbial bands. Authored, not thermometry."""` | **CLEAN**
- L87-88: `"""Horizontal gradient x=0 center → x=1 rim. Matches water.gdshader band_ramp sampling (shader passes 1−side, i.e. 0 at center)."""` | **CLEAN**
- L118: `"""Ray-cast point-in-polygon on the MAPPED outline (exact, not circular)."""` | **CLEAN**
- L133-135: `"""Radial buffer of a star-shaped mapped outline by an absolute margin. Recorded method: exact Minkowski buffers need shapely; radial expansion is conservative for these compact thermal outlines."""` | **CLEAN**
- L148-149: `"""Quadratic falloff reaching exactly t_edge at the water edge (center → edge → ambient apron). Beyond the edge relaxes toward edge."""` | **CLEAN**
- L156: `"""Illustrative crater profile: deep bowl → shallow shelf → 0 at rim."""` | **CLEAN**
- L167: `"""Author one pool shell. Never alters the mapped outline."""` | **CLEAN**
- L179-180: `# Guarantee strictly growing radii for large pools where an additive rim # would otherwise fall inside a multiplicative shelf.` | **AI TELL** (narrative about hypothetical failure: "would otherwise")
- L187: `"ring": ring,  # mapped outline carried verbatim; never resampled` | **CLEAN**
- L218: `"""Exact mapped-polygon test (circle only if the ring is missing)."""` | **CLEAN**
- L225: `"""Buffered-outline test; circle fallback preserves conservatism."""` | **CLEAN**
- L235: `"""Forest-type points that fall inside any apron (masking failure)."""` | **CLEAN**
- L247-248: `"""World-extent eligibility mask: 0=ok, 255=hydrothermal apron. Draws buffered mapped outlines (exact); circles only as fallback."""` | **CLEAN**
- L270-271: `"""Per-pool high-resolution apron tiles (~1–2 m/px) for pool inspection. World mask pixels are ~16 m; small pools need these local tiles."""` | **CLEAN**
- L298: `"""Side-view diagram plate for field notes (I key)."""` | **CLEAN**
- L304: `sm = rs / max(1e-6, rw)  # shell's own shelf ratio, never a default` | **CLEAN**
- L314: `# water surface + bowl + shelf + rim + apron` | **CLEAN**
- L326: `f"{shell['name']} — authored section (illustrative, not survey)"` | **AI TELL** (em dash in string)

---

**`../../yellowstone_python/yellowstone_python/publish.py`**
- L1-11: Module docstring — "M11 publish: transactional release of a validated build" | **CLEAN**

---

**`../../yellowstone_python/yellowstone_python/review_proposals.py`**
- L1-16: Module docstring — "Machine review gate for planting proposals", "Still required by a human: NAIP eyeball check" | **CLEAN**
- L47-48: `# NaN would make every `suit < threshold` comparison False and # silently accept everything below; fail closed instead.` | **AI TELL** (excess explanation — "fail closed instead" is redundant with the first clause)
- L77: `note = "infills existing stand" if nearest < 6.0 else "new canopy gap"` | **CLEAN**
- L92: `"""Bake-consumed schema: {id, kind, position, yaw, scale, variant}."""` | **CLEAN**

---

**`../../yellowstone_python/yellowstone_python/snow_season.py`**
- L1-20: Module docstring — "M08 snow_season", "Corrected process definitions (audit fixes)" | **AI TELL** ("audit fixes" — references to audit process)
- L28: `SNOW_TEMP_C = 1.0  # precip below this is snow, above is rain` | **CLEAN**
- L36-40: `"""Meteorological season for month/day, northern hemisphere. Authored convention (not measured): Dec-Feb winter, Mar-May spring, Jun-Aug summer, Sep-Nov autumn. Day is accepted for future astronomical use and validated, but does not change the month mapping."""` | **AI TELL** (excess information: "Day is accepted for future astronomical use and validated, but does not change the month mapping" is redundant)
- L55-59: `"""System local date/time -> game season + clock hour. Default source only: explicit config always wins (see resolve_game_clock). Range-safe by construction (month/day validated, hour in [0, 24))."""` | **AI TELL** (meta-commentary: "Range-safe by construction" is redundant)
- L70-79: `"""Resolve (season, clock_hour, nominal date) with provenance. Precedence per key, explicit settings always win: season: season_cfg > derived from date_cfg > system clock; clock_hour: clock_cfg > system clock (a date carries no time of day); nominal date: date_cfg > system clock date (stamped either way: it dates the run and anchors season.json). date_cfg is YYYY-MM-DD (settings key snow.as_of_date); malformed dates raise instead of guessing. Sources: config / config_date / system_clock. Raises on an out-of-range explicit clock_hour or unknown season."""` | **AI TELL** (Pattern A: "instead of guessing"; Pattern B: "stamped either way"; Pattern C: "a date carries no time of day" redundant/obvious; Pattern D: too long/verbose for a code comment)
- L119-123: `"""One day. Returns (snow_mm, melt_mm, accum_mm, rain_mm, wind_runoff_mm). Melt includes surface degree-day melt (÷ retention) + thermal ground flux. Wind strips a fraction of (snow + fresh accum) to runoff. Rain never enters the snowpack."""` | **CLEAN**
- L139-141: `"""Authored per-habitat modifiers (stated, not measured). aspect_retention > 1 slows melt; canopy_keep < 1 intercepts snow; wind_loss removes snow to runoff."""` | **CLEAN**
- L171-184: `"""Advance snow + soil + phenology with a verified water ledger. thermal_test(x, z) -> True where ground is hydrothermal (M03 aprons): those cells get the ground-heat melt flux instead of zeroing. precip_mm_by_day optionally overrides the scalar precip_mm_d with a per-day series (same short-series rule as air_c_by_day: reuse last). An empty series falls back to the scalar. Units: mm/day water-equivalent. k_melt / tbase_c are the fittable degree-day params (defaults preserve prior behavior); wind_loss optionally overrides the habitat-authored redistribution fraction (None = authored per-patch values; fit hook for site-effective seasonal loss). SNOW_TEMP_C phase split stays authored, not fitted. Returns (patches, ledger). Ledger residual must be ~0 (gated).""" | **AI TELL** (overly verbose, meta-commentary about fit hooks)
- L237-238: `# Melt is an INTERNAL snow→soil transfer: snowpack and soil balances # verify separately (melt cancels in the joint balance).` | **CLEAN**
- L265-266: `"note": "degree-day approximation; thermal ground carries a melt flux, not an absolute bare rule"` | **CLEAN**
- L272: `"""World-extent snow cover with thermally-reduced holes (illustrative)."""` | **CLEAN**

---

**`../../yellowstone_python/yellowstone_python/snow_validate.py`**
- L1-19: Module docstring — "M08 validation: snow + soil-water model vs NRCS SNOTEL observations", "Every coefficient carries provenance" | **CLEAN**
- L29: `SPLIT_DATE = "2026-03-01"  # train: accumulation season; holdout: melt season` | **CLEAN**
- L30: `MAX_FILL_DAYS = 3  # longest imputable forcing gap; longer refuses the run` | **CLEAN**
- L44-49: `"""Daily air-C + precip-mm series with documented gap rules. Null TAVG is forward-filled (previous day, first day refuses); a gap longer than max_fill raises instead of inventing weather. Null PRCP is read as 0.0 and counted (post-melt trace convention, flagged). Returns (air_c, precip_mm, {"tavg_filled": n, "prcp_zeroed": n})."""` | **AI TELL** (Pattern A: "instead of inventing weather" references alternative; "post-melt trace convention, flagged" is excess explanation)
- L77: `"""Contiguous index split on date: train before split, holdout from it."""` | **CLEAN**
- L85-94: `"""Chained 1-day run_season calls -> (swe_mm, soil_mm) daily series. run_season emits end-state only, so days chain through snow_mm/soil_mm. Each day's storage ledger is asserted (tolerance 0.01: run_season rounds patch state to mm precision, measured residual 5e-4/day). wind_loss overrides the habitat-authored redistribution (None keeps it); it is the site-effective seasonal loss fit hook. Phenology/gdd outputs are meaningless in chained mode (they reset daily) and are not collected; use a full-window run for those."""` | **AI TELL** (overly verbose, "fit hook" meta-commentary, "they reset daily" is redundant explanation)
- L112: `"""Days between modeled and observed SWE peak (signed, model minus obs)."""` | **CLEAN**
- L132-137: `"""Joint grid fit of (k_melt, site-effective wind_loss) on train RMSE. wind_loss absorbs seasonal redistribution + gauge undercatch + sublimation at the site; the game default stays authored (validation fits a site-effective value, it does not rewrite the game). Returns (best_k, best_wind, train_rmse_mm)."""` | **AI TELL** (meta-commentary: "it does not rewrite the game" — narrative about process)
- L152-153: `# SNOTEL instruments sit in clearings: meadow modifiers fit better than # forest canopy interception (authored choice, stated).` | **CLEAN**
- L173: `# Null 1: persistence of last train observation through holdout.` | **CLEAN**
- L177-178: `# Null 2: no-melt accumulation-only run at the fitted wind (tests the # melt process itself: same effective loss, melt switched off).` | **CLEAN**
- L183: `# Secondary: modeled depth vs observed SNWD (authored 3.0 factor check).` | **CLEAN**
- L186: `# Full-window ledger + phenology from one unchained run at fitted params.` | **CLEAN**

---

**`../../yellowstone_python/yellowstone_python/study_mode.py`**
- L1-13: Module docstring — "M10 study_mode: labeled A/B experiments" | **CLEAN**
- L20-22: `# Overrides are expressed as dotted paths into the build config. Only these # EXACT keys may change — world geometry, routes, pools, placements are # unreachable by construction (no key addresses them).` | **AI TELL** (em dash, "unreachable by construction" is redundant with "no key addresses them")
- L88: `"about": "Excelsior source ×2 within this model. Warmer mixing reach; trout relocate harder."` | **CLEAN**
- L97: `"about": "Night air −6 °C, overcast. Insects collapse, birds perch."` | **CLEAN**
- L104: `"about": "Upstream Q halved: slower dilution, plume relatively stronger."` | **CLEAN**
- L110-111: `"about": "COUNTEREXAMPLE (within this model): +6 °C air, same discharge. Trout barely move — short-term river response follows residence time and forcing, not air alone."` | **AI TELL** (em dash in string)
- L113: `"uncertainty": "illustrates decoupled drivers within this model; over longer periods surface exchange matters strongly"` | **CLEAN**
- L117: `"about": "Seven sub-zero days with precip: snow accumulates, thermal stays bare."` | **CLEAN**

---

**`../../yellowstone_python/yellowstone_python/vegetation.py`**
- L1-14: Module docstring — "M04 vegetation: suitability fields + patch biomass + planting proposals" | **CLEAN**
- L27-29: `# Maximum candidate cells scanned per propose_plantings_reviewed call. Existing # pipeline grids peak at ~22k cells (meadow r=110); anything larger is # coarsened (see function docstring) instead of burning minutes.` | **AI TELL** (Pattern A: "instead of burning minutes" references alternative; "see function docstring" is meta-commentary)
- L32-35: `# Per-guild coefficients: ARTIST/SCIENCE INPUTS, not inferred truth. # REAL DATA GAP: Actual vegetation surveys (species presence/absence, # biomass measurements, growth rate studies) would replace these authored # lambda0/min_sep/slope_max values. Integration point: load_vegetation_survey().` | **AI TELL** ("REAL DATA GAP:", "Integration point:" — meta-commentary about data provenance)
- L53-60: `# Real-data provenance for vegetation parameters` block — "authored_illustrative_coefficients_not_inferred_from_field_data", "real_data_gap" | **AI TELL** (meta-commentary)
- L65: `"""λs(p): all terms in [0,1]; returns [0,1] density potential."""` | **CLEAN**
- L76: `"""Convenience evaluator used by proposal review + tests."""` | **CLEAN**
- L94-98: `"""Advance patch biomass like ecosystem.gd::_advance_patches (growth part). grazers: {grazer_id: {patch_id, active, rate_per_second}}. Returns (updated_patches, ledger{consumed, growth})."""` | **CLEAN**
- L127-136: `"""Deterministic proposal grid+jitter with per-guild min separation. LEGACY wrapper (no terrain context): separation is best-effort here. Prefer propose_plantings_reviewed() for enforced, suitability-linked output. Preserves the reviewed per-cell stable ids verbatim. Only renumbers when the accepted set collides with a previously issued id namespace (the old behaviour overwrote every id unconditionally, so the review ledger's ids never matched the records it described)."""` | **AI TELL** ("LEGACY", "the old behaviour" — narrative about past changes)
- L151: `"""Little-endian float32 GRID×GRID, row zero north (matches height_field)."""` | **CLEAN**
- L159: `"""(sample, slope_deg) closures matching height_field.gd diagonal + normal_at."""` | **CLEAN**
- L199-208: `"""Suitability-linked, separation-enforced proposals + review ledger. Per-candidate randomness (seed:guild:cell) is independent: a rejection consumes nothing shared, so later candidates never shift. Returns (accepted_records, review_log[{stable_id|cell, decision, reason}]). DoS guard: candidate grids larger than GRID_BUDGET cells are coarsened (wider spacing, guild separation still enforced) and the coarsening is logged; grids at/below the cap scan exactly as before."""` | **CLEAN**
- L295-297: `"""Suitability field rendered FROM the model: DEM slope + patch moisture + apron exclusion + habitat eligibility, evaluated per pixel. bbox = (x0, z0, x1, z1) local metres."""` | **CLEAN**
- L309: `# Habitat: nearest patch circle wins, else unsuitable matrix.` | **CLEAN**

---

**`../../yellowstone_python/yellowstone_python/validation/checks.py`**
- L1: `"""M11 checks: conservation, topology, provenance, determinism gates."""` | **CLEAN**
- L15-19: `# Downstream monotone temperature is NOT required (hot lateral warms mid-chain); # instead assert no NaN and fish_activity in [0,1]. Monotone STAGE (water surface # never climbs downstream) is a baked-geometry invariant and lives where the # geometry lives: yellowstone_midway/tools/validate_world.py (Firehole # northward-order + climb check). Do not re-add a temperature version here.` | **CLEAN**

---

**`../../yellowstone_python/yellowstone_python/replay/calibrate.py`**
- L1-25: Module docstring — "Reach-scale calibration and dispersion experiments for the Firehole", "Two independent analyses, both labeled, both reproducible" | **CLEAN**
- L56-63: `"""Bin-average irregular [epoch, value] pairs onto a uniform grid. Returns (values, coverage) where missing bins are None and coverage is the fraction of filled bins. Bin i covers [grid[0] + (i - 0.5) * dt, grid[0] + (i + 0.5) * dt). Callers must branch on None/coverage — averaging over Nones or treating them as zeros fabricates data."""` | **AI TELL** (em dash)
- L86-90: `"""Piecewise-linear interpolation; endpoints clamp (no extrapolation). Deliberately dumb: gap detection is the caller's job (see check_continuity). Never use this to silently bridge instrument gaps."""` | **CLEAN**
- L113-119: `"""Reject instrument gaps instead of interpolating across them. Returns the nominal step (median interval). Raises ValueError naming the gap if any consecutive interval exceeds max_gap_s. Call before interp_series on every ingested series — a bridged multi-day outage looks like data and fits to it are fiction."""` | **AI TELL** (em dash)
- L137-142: `"""Advective lag from cross-correlation of demeaned series. Returns the lag (seconds, downstream behind upstream) maximizing correlation, plus the peak correlation. Both series must be equal length, uniformly spaced, and non-constant."""` | **CLEAN**
- L205: `"""Advect one Gaussian pulse; return moment-derived effective D."""` | **CLEAN**
- L241: `"""Run the pulse at each D; summarize fidelity and the D=1-vs-85 gap."""` | **CLEAN**
- L268-269: `"""Single well-mixed cell: measured upstream in, fitted lateral in, explicit surface budget with scaled turbulent coefficients."""` | **CLEAN**
- L301-306: `"""Uniform-grid forcing both integrators share, bit for bit. run_fit_forward (River backward-Euler) and ivp_crosscheck (SciPy RK45) build their forcing from these arrays, so trajectory differences measure integrator numerics — never input handling."""` | **AI TELL** (em dash)
- L346-353: `"""Forward lumped run over the bundle window; returns epoch grid + T. backend="pairs" is the hand-rolled alignment (default: no new dependencies); backend="pandas" routes through replay.obs_frame (explicit gaps/coverage, same grid convention). The two agree to float noise on gap-free data (parity test); the default flips when pandas is installed on the project interpreter."""` | **AI TELL** (meta-commentary about testing)
- L370-373: `# Scale-aware closure: reach volumes (~1e5 m3) carry ~1e13-1e14 J, so # the solver's 1e-9 demo tolerance is pure float noise here (a 1e-5 # relative residual is ~0.001 C temperature error). Raw value and # component totals are reported for inspection.` | **CLEAN**
- L394-402: `"""Grid-search the lumped budget; train/holdout + null-model comparison. Null A (persistence): downstream == upstream now. Null B (mixing only): same model with c_mult = 0, Q_lat/T_lat refit on train. return_all=True adds every grid row under "all_results" (needed by the ridge ensemble in uncertainty.py); the default artifact keeps top10 only."""` | **CLEAN**
- L409: `# Cache one forward run per (q, t, c) — reuse Null B from the same grid.` | **AI TELL** (em dash)
- L502-507: `"""Akaike / Bayesian information criteria from a residual sum of squares. AIC = n ln(RSS/n) + 2k, BIC = n ln(RSS/n) + k ln n. Lower wins. k counts fitted parameters only — null persistence (k=0) and mixing-only (k=2) score on the same scale as the 3-parameter fit."""` | **AI TELL** (em dash)
- L525-532: `"""Bounded least-squares refinement of the grid champion. scipy.optimize.least_squares over (Q_lat, T_lat, c_mult) against the train window, starting at the grid champion (or x0). Residuals are raw train errors, so the optimum matches the grid's RMSE scale. max_nfev caps forward runs (each costs one); the grid stays the global search, this is local polish — not a replacement."""` | **AI TELL** (em dash)
- L575-585: `"""Independent RK45 integration of the lumped cell vs backward-Euler. Same volume, area, laterals, and the shared forcing arrays — the only difference is the integrator: adaptive RK45 on the NONLINEAR surface budget vs River's backward-Euler on step-frozen linearized forcing. At the fit's dt the two differ by first-order truncation (tenths of a °C on fast transients — measured, not assumed), so the verification is CONVERGENCE: halve euler_dt_s and the max gap must roughly halve. euler_dt_s defaults to dt_s and must divide it; both trajectories are compared at the dt_s sample times."""` | **AI TELL** (em dashes, "measured, not assumed")

---

**`../../yellowstone_python/yellowstone_python/replay/figures.py`**
- L1-11: Module docstring — "Publication-style diagnostic figures", "Backend discipline: pyplot is imported only inside _pyplot() after forcing Agg" | **CLEAN**
- L44: `"""Observed vs modeled over train/holdout + persistence null."""` | **CLEAN**
- L72: `"""Ensemble bands over the holdout window + empirical coverage."""` | **CLEAN**
- L98: `"""Residual series (both windows) + normal Q-Q of train residuals."""` | **CLEAN**
- L126: `"""Joint (Q_lat, T_lat) distribution colored by train RMSE."""` | **CLEAN**
- L162: `"""Thermal landscape profile with the refuge cell + Kaya 24 C line."""` | **CLEAN**
- L185: `"""Rebuild the figure set from the recorded artifacts."""` | **CLEAN**

---

**`../../yellowstone_python/yellowstone_python/replay/hydraulics.py`**
- L1-36: Module docstring (36 lines) — "Trapezoidal channel hydraulics diagnostics", "Scientific scope", "Cross-section convention", explicit formulas, "Observation scoring compares paired modeled/observed series... never supplies observations" | **AI TELL** (overly verbose, meta-commentary)
- L47-56: `# Illustrative defaults, explicitly authored — not measurements. # REAL DATA STATUS: USGS field measurements (current-meter surveys, # bathymetry) unavailable via NWIS web API since Oct 2026 format change. # Integration point: load_usgs_cross_section(site_no) (see below) # would connect to machine-readable surveys when available.` | **AI TELL** ("REAL DATA STATUS:", "Integration point:" — meta-commentary about data provenance)
- L58-63: `# --- Real-data integration framework --- # Cross-section measurements (bank slope, Manning's n, depth profiles) # should come from USGS field surveys or in-situ bathymetry. Currently # unavailable via machine-readable NWIS (Oct 2026 format change); this # framework provides the hook for when surveys are restored or # directly ingested from survey files.` | **AI TELL** ("integration framework" — meta-commentary)
- L83-93: `"""Integration point for real USGS cross-section surveys. When machine-readable NWIS measurement data is available (before Oct 2026, or via restored API / direct survey file), this loads measured width, area, velocity, and depth for use in place of authored DEM-derived estimates. Currently returns None with provenance documented; real data requires either API restoration or manual survey file ingestion."""` | **AI TELL** ("Integration point", narrative about current state)
- L121: `"""Trapezoidal cross-section from top width, depth, bank slope."""` | **CLEAN**
- L164: `"""Legacy solver assumption, kept for bias reporting."""` | **CLEAN**
- L170: `"""Manning velocity. Requires positive slope and roughness."""` | **CLEAN**
- L180: `"""Froude number. <1 subcritical, =1 critical, >1 supercritical."""` | **CLEAN**
- L188: `"""Bed shear stress tau = rho * g * R * S."""` | **CLEAN**
- L196: `"""Shear velocity u* = sqrt(g * R * S)."""` | **CLEAN**
- L205-210: `"""Fischer (1979) longitudinal dispersion estimate. D = 0.011 * V^2 * W^2 / (H * u*). Order-of-magnitude diagnostic for comparing against the solver's illustrative dispersion coefficient — not a fitted value."""` | **AI TELL** (em dash)
- L221: `"""Nominal advective residence L / V."""` | **CLEAN**
- L230: `"""Downstream slope from elevation drop over horizontal length."""` | **CLEAN**
- L244-251: `"""Per-cell hydraulic diagnostics with explicit provenance. Solver continuity velocity V = Q / A_trap is always defined for positive discharge. Manning, Froude-vs-Manning, shear, and Fischer fields are None when the mapped grade is flat/adverse (slope None or <= MIN_SLOPE_FOR_MANNING) — the diagnostic reports the gap instead of inventing a slope."""` | **AI TELL** (em dash)
- L337-341: `"""RMSE / bias / MAE / max-abs over paired modeled-observed values. Raises on empty, mismatched-length, or nonfinite input. No time interpolation — callers align series first and document the method."""` | **AI TELL** (em dash)
- L363-370: `"""Nash-Sutcliffe + Kling-Gupta skill scores (hydrologist's scale). NSE = 1 - RSS/TSS: 1 is perfect, 0 means "as good as the observed mean", negative is worse. KGE = 1 - ED(r, alpha, beta) with correlation r, variability ratio alpha = std_m/std_o, bias ratio beta = mean_m/mean_o. Raises on constant observed series (TSS = 0 makes NSE undefined) or zero observed mean (beta undefined)."""` | **CLEAN**
- L397-399: `# A constant model (e.g. the observed mean) has no correlation # by definition; NaN would propagate silently, so KGE is # reported missing with an explicit flag instead.` | **CLEAN**
- L415-423: `"""Autocorrelation + normal Q-Q of paired residuals. Correlated residuals mean the model missed structure (diurnal phase, event response); Q-Q gaps mean non-Gaussian errors that RMSE-based bands misstate. Returns lag-1..max_lag autocorrelations of demeaned residuals and empirical-vs-normal quantiles at fixed levels, with the max Q-Q gap. All-zero residuals (a perfect fit) report a flag instead of undefined correlations."""` | **CLEAN**
- L459-468: `"""Account total thermal inflow and flow-weighted entry temperature. Pure bookkeeping over caller-supplied source dicts with flow_m3_s and temperature_c. Constant temperatures enter the flow-weighted mean; scheduled (Series-dict) temperatures are listed with temperature_c None and EXCLUDED from the mean, with an explicit count — a scheduled intervention has no single entry temperature. Provenance passes through per-source status."""` | **AI TELL** (em dash)

---

**`../../yellowstone_python/yellowstone_python/replay/obs_frame.py`**
- L1-19: Module docstring — "Pandas obs-frame alignment for the fetch-then-fit path (B1)", "Replaces silent hand-rolled alignment with explicit state", "The incident behind this module: hand interpolation once bridged a multi-day outage and the fit treated it as data" | **AI TELL** (narrative about past incidents, "B1" reference)
- L38-42: `"""Irregular [epoch, value] pairs -> nominal-step frame. Values sharing a bin are averaged (resample-mean, the explicit cousin of resample_bin_mean); empty bins are NaN, never zero."""` | **CLEAN**
- L52-54: `# Anchor bins at the first observation, not the epoch: epoch- # anchored bins shift regular series by up to a step against the # observation times (measured failure, Oct 2026).` | **AI TELL** ("measured failure, Oct 2026" — references past failures)
- L60-63: `"""Met [epoch, air, rh, wind, sw, cloud] rows -> joint frame. One shared index, so all five variables carry the same gap report."""` | **CLEAN**
- L80: `"""Coverage + every NaN run (start, end, length in steps)."""` | **CLEAN**
- L104: `"""Refuse unbridgeable gaps, naming the worst one."""` | **CLEAN**
- L117-123: `"""Linearly bridge NaN runs, each direction separately up to limit. Standalone explicit helper. Note limit_direction="both" fills from each side, so interior runs up to 2x limit are fully bridged; the fit path (to_grid) applies its own half-limit to match the 4x rule."""` | **CLEAN**
- L129-137: `"""Frame values onto epoch grid; anything unbridgeable refuses. Linear interpolation between neighboring bins, each side bridged up to `limit` steps — interior gaps up to 2x limit (= BRIDGE_STEPS) fill, matching check_continuity's 4x-nominal rule; anything longer survives as NaN and raises, naming the first offending epoch. Grid endpoints must lie inside measured coverage (no silent endpoint clamp, unlike the pairs path)."""` | **AI TELL** (em dash)
- L163: `"""Trailing rolling mean for diagnostic smoothing (e.g. daily met)."""` | **CLEAN**
- L171: `"""Calendar-day means of each met column (forcing summary)."""` | **CLEAN**
- L179-185: `"""Fit forcing arrays through frames; same shape as _fit_forcing_arrays. Raises on unbridgeable gaps (assert_coverable) or grid points outside coverage (to_grid). Returns the arrays plus a provenance report carrying every coverage number and the bridge limit, so the fit artifact can record what the alignment assumed."""` | **CLEAN**
- L199-200: `# NOTE: frames go to the grid unbridged; to_grid applies the # recorded limit itself, so one mechanism owns bridging.` | **CLEAN**

---

**`../../yellowstone_python/yellowstone_python/replay/river_transport.py`**
- L1-38: Module docstring (38 lines) — "Conservative one-dimensional river-temperature transport", "Scientific scope", "Numerical method", "Boundary conditions", "Limitations" | **CLEAN**
- L81-88: `"""Right-continuous, piecewise-constant forcing. Example: Series((0, 600, 1800), (62, 80, 62)) The first value applies from t=0. The final value remains active indefinitely. Integration steps are split at every change time."""` | **CLEAN**
- L143-150: `"""A finite-volume cell in upstream-to-downstream order. volume_m3 / length_m gives mean wetted cross-sectional area. width_m * length_m gives exposed water-surface area. These quantities describe the numerical channel, not automatically surveyed channel geometry."""` | **CLEAN**
- L189-196: `"""Lateral water inflow assigned to a cell. Flow is constant in this first version; temperature may be scheduled. The water addition increases all downstream face discharges. Assigning an outfall to one cell is a discretization decision, not a claim that the real outfall is fully mixed at that location."""` | **CLEAN**
- L222-228: `"""Explicit surface energy budget forcing (replaces Newton exchange). Met series share the solver clock; air temperature still comes from the River's own air_c series. When a River carries a SurfaceBudget, per-cell exchange_w_m2_k coefficients are ignored (documented in the replay) so heat is not double-counted."""` | **CLEAN**
- L307: `"""Compensated accumulation for long-run budget terms."""` | **CLEAN**
- L330-335: `"""Thomas algorithm. The transport matrix has nonpositive off-diagonals and positive pivots. A singular steady problem, such as a completely closed channel without heat exchange, is rejected rather than fabricated."""` | **CLEAN**
- L377: `"""Stateful scientific engine, independent of rendering."""` | **CLEAN**
- L404-405: `# Positive means energy entering the water. # This is ADDITIONAL to Newton exchange.` | **CLEAN**
- L437: `# n cells have n+1 faces.` | **CLEAN**
- L449-454: `# Dispersive conductance, in m3/s, at each face: # # G = 1 / [Li/(2 Di Ai) + Lj/(2 Dj Aj)] # # This is a harmonic resistance calculation. Internal fluxes # are shared exactly by neighboring cells.` | **CLEAN**
- L540: `"""Build transport equations in temperature-volume units."""` | **CLEAN**
- L563-565: `# Explicit budget replaces the lumped coefficient so heat # is not double-counted. Linearized implicitly for stability: # F(T_new) ~= F0 + dF/dT * (T_new - T_old).` | **CLEAN**
- L609-612: `"""Advance one interval without crossing a forcing change. Use run() to split automatically at forcing and sample times."""` | **CLEAN**
- L644: `# Advective + dispersive face fluxes, in m3*C/s.` | **CLEAN**
- L663-664: `# Accounting uses the flux at the NEW temperature, so closure # measures actual energy change, not the linearized estimate.` | **CLEAN**
- L781: `# Direct differences avoid subtracting two large total energies.` | **CLEAN**
- L860-867: `"""Advance for duration_s, preserving forcing-change times. Includes the starting state and exact final state. Sample times also split integration intervals; choose sample_s as a multiple of dt_s when comparing numerical runs. A zero-duration run returns one snapshot."""` | **AI TELL** (overly verbose for a code comment; "choose sample_s as a multiple of dt_s when comparing numerical runs" is usage documentation in a comment)
- L978-981: `"""Synthetic channel and source-temperature pulse. This is not mapped Firehole geometry or an observed Yellowstone event."""` | **CLEAN**

---

**`../../yellowstone_python/yellowstone_python/replay/river_world.py`**
- L1-19: Module docstring — "Map the conservative thermal solver onto the saved Midway Firehole", "The pulse changes temperature at the river-entry boundary. It is not a simulation of the spring's underground plumbing or outflow cooling." | **CLEAN**
- L46-48: `# Explicit association between the ecosystem's aggregate thermal boundary # and the representative authored channel used to locate its connection. # This does not assert that this one branch carries the actual aggregate.` | **CLEAN**
- L57-63: `"""Validate per-feature mean-depth profiles (P0 cross-section input). Format: {feature_id: {"depth_m": positive float, "status": str}} with optional "source" str. "status" is required and explicit — a supplied profile is never silently labeled "assumed". Unknown feature ids are rejected by build_mapped_replay, which knows the mapped chain."""` | **AI TELL** (em dash)
- L108-112: `"""Find a single directed chain using declared endpoint IDs. Do not infer direction from list order, velocity art parameters, latitude, or local changes in z."""` | **AI TELL** (excess explanation — listing things not to do)
- L163: `"""Original vertices plus their downstream horizontal chainage."""` | **CLEAN**
- L251-255: `"""Translate an old reach anchor, refusing ambiguous crossings. This exists only for compatibility with the old six-reach display. New actor queries use position projected onto a named river."""` | **AI TELL** ("old six-reach display" — narrative about past)
- L342-346: `"""Split at sources and feature boundaries, then subdivide. A source lies at the upstream face of its receiving cell, rather than being smeared over a legacy compartment."""` | **AI TELL** (references past version: "legacy compartment" — narrative about past)
- L371-375: `"""Use the existing weather approximation on a physical clock. Air forcing is held constant over each interval. day_rate does not accelerate scientific forcing. This is not measured meteorology."""` | **CLEAN**
- L411-417: `"""Meteorological series for the explicit surface budget. Relative humidity and cloud are held constant (no met station data); wind speed reuses the physical_weather trace magnitude so both forcings share one wind history; shortwave is a synthetic diurnal curve scaled by sw_noon_w_m2. All labeled synthetic in the notes."""` | **CLEAN**
- L515-517: `# Reach-averaged grade per river feature (total drop / total length): # cell-scale elevation differences are vertex/DEM noise, not energy # slope. Standard open-channel practice uses the reach grade.` | **CLEAN**
- L553-554: `# Reach-averaged grade (see above); flat or adverse reaches stay # None: Manning is reported undefined, never replaced.` | **CLEAN**
- L628-631: `"initial_condition": ("Calculated steady state at t=0 forcing; not the legacy six-reach temperature snapshot.")` | **AI TELL** ("legacy six-reach" — narrative about past)
- L701-703: `# Trapezoidal hydraulics diagnostics (additive; solver volumes and # temperatures above are unchanged). Discharge per cell is the # downstream face flow, matching representative_velocity_m_s.` | **CLEAN**

---

**`../../yellowstone_python/yellowstone_python/replay/surface_flux.py`**
- L1-30: Module docstring — "Explicit surface energy budget for the 1-D river-temperature solver", formulas, "Form choices (illustrative defaults, not fitted parameters)" | **CLEAN**
- L46: `"""Saturation vapor pressure, Magnus form (kPa)."""` | **CLEAN**
- L71: `"""Incoming longwave: Brutsaert emissivity + cloud factor."""` | **CLEAN**
- L80: `"""Meteorological forcing at one instant (all validated)."""` | **CLEAN**
- L83: `rh: float  # 0..1` | **CLEAN**
- L85: `shortwave_w_m2: float  # downwelling, >= 0` | **CLEAN**
- L86: `cloud: float  # 0..1` | **CLEAN**
- L112: `"""Surface properties (defaults illustrative, not fitted)."""` | **CLEAN**
- L139: `"""Component fluxes (W/m2, positive into water) at one water temperature."""` | **CLEAN**
- L165: `"""(F0, dF/dT) of net flux at t_water_c, analytic derivative."""` | **CLEAN**
- L181: `"""Build a River-config "surface_budget" mapping from Series-ish inputs."""` | **CLEAN**

---

**`../../yellowstone_python/yellowstone_python/replay/uncertainty.py`**
- L1-27: Module docstring — "Uncertainty quantification for the lumped reach fit + authored-knob sensitivity", "A1 of the science-demo backlog" | **AI TELL** ("A1 of the science-demo backlog" — references to development process)
- L43-53: `# --- Uncertainty quantification provenance --- # Every parameter below is AUTHORED (not derived from measurement error): #   ENSEMBLE_SEED=20261010 (reproducibility seed, arbitrary) #   tol_frac=0.10, min_members=5 (ensemble membership thresholds, chosen for visualization stability) #   n_bootstrap=1000 (Monte Carlo count, arbitrary) #   spinup_s=86400.0, train_frac=0.7 (fit split convention, arbitrary) #   band_level=0.90 (nominal coverage target, standard statistical convention) # REAL DATA NEEDED: replicate study results, instrument precision specs, # or Bayesian posterior samples from a calibrated model to replace the # authored sensitivity ranges and bootstrap counts. The module reports # fit ambiguity, not predictive calibration.` | **AI TELL** ("REAL DATA NEEDED:" — meta-commentary about data provenance)
- L78-83: `"""Grid points within tol_frac of the champion train RMSE. Falls back to the top-min_members by train RMSE when the ridge rule admits fewer (a tight optimum is still an ensemble of one plus its nearest neighbors, and the fallback is recorded by the caller)."""` | **CLEAN**
- L102: `"""Train/holdout slices matching reach_heat_fit's convention."""` | **CLEAN**
- L115: `"""Forward run per ensemble member; returns shared grid + trajectories."""` | **CLEAN**
- L133-139: `"""Percentile bands + seeded-bootstrap standard error of the edges. Bands are cross-member percentiles at each timestep (equal weight). The bootstrap resamples members with replacement (seeded) and reports the standard deviation of the resampled lo/hi edges as MC standard errors — the Monte Carlo in this module."""` | **AI TELL** (em dash)
- L171: `"""Fraction of target points inside [lo, hi]; mean width for context."""` | **CLEAN**
- L192-197: `"""Holdout-RMSE response to single-knob moves off the champion. Each row reruns the forward model with exactly one knob changed; the baseline row reruns the champion itself (a rerun, not the recorded number, so deltas are self-consistent)."""` | **CLEAN**
- L234-239: `"""Refuge-cell response to REFUGE_WEIGHT at fixed food/cover. Food is held uniform (food/ceiling = 1 everywhere) to isolate the refuge-drive term: this measures the weight's leverage on selection, not a foraging outcome. Response is the argmax-U cell chainage."""` | **CLEAN**
- L263: `"""run_foodweb reruns over ne_turnover_days on a recorded landscape."""` | **CLEAN**
- L281-287: `"""Median Manning-consistency-ratio response to z and n. Recomputes cell_hydraulics per recorded cell (length, width, depth, discharge, slope from the record) with one authored knob varied; cells where Manning is undefined stay excluded, and the exclusion count is reported — varying z must not silently change the sample."""` | **AI TELL** (em dash)
- L344: `"""Full A1 pass: ensemble bands + coverage + fit OAT ranking."""` | **AI TELL** ("A1" reference to development process)
- L400-402: `# Full-grid scores come from a fresh fit (also a reproducibility # check against the recorded champion); the artifact keeps # top10 only.` | **CLEAN**

---

**`../../yellowstone_python/tools/audit_provenance.py`**
- L1-5: Module docstring — "Mechanical standing-rules check over derived/ provenance labels" | **CLEAN**
- L16: `# Exact vocabulary measured across derived/*.json (28 occurrences, 2026-10-10).` | **AI TELL** (date reference)
- L30: `# Files with no schema/status contract (legacy, allowlisted not failed).` | **CLEAN**

---

**`../../yellowstone_python/tools/build_store.py`**
- L1-16: Module docstring — "Build the LLM analysis store (SQLite) from one build dir + obs inputs", "Derived artifacts are history" | **CLEAN**

---

**`../../yellowstone_python/tools/channel_geometry.py`**
- L1-17: Module docstring — "Derive channel cross-section profiles from USGS field measurements + USGS 3DEP DEM" | **CLEAN**

---

**`../../yellowstone_python/tools/check_terrain.py`**
- L1-6: Module docstring — "Guard terrain.f32 (hash/dims/range) against BUILD deps" | **CLEAN**
- L24-26: `# Tripwires containing the measured envelope (min -10.89, max 238.13, # p1 -5.09, p99 221.28). Datum undocumented: bounds are tripwires, not # physical claims.` | **CLEAN**

---

**`../../yellowstone_python/tools/compare_bundles.py`**
- L1-6: Module docstring — "Old-vs-refetch drift detection over observation bundles" | **CLEAN**
- L17-18: `# Defaults sit above the worst observed step-to-step noise in the frozen # bundles (upstream Q max step 2.9%, downstream 3.1%, temp max step 0.4 C).` | **CLEAN**

---

**`../../yellowstone_python/tools/execute_notebook.py`**
- L1-15: Module docstring — "Stdlib notebook smoke-executor" | **CLEAN**

---

**`../../yellowstone_python/tools/fetch_firehole_obs.py`**
- L1-19: Module docstring — "Fetch a frozen Firehole observation bundle for reach-scale calibration", "Sources (all measured, all remote — nothing authored here)" | **AI TELL** (em dash)

---

**`../../yellowstone_python/tools/fetch_met_forcing.py`**
- L1-7: Module docstring — "Shared Open-Meteo forcing source (stdlib urllib only, no requests)" | **CLEAN**
- L26-29: `# Row schema FROZEN at width 6 (consumer indices in # replay.calibrate._fit_forcing_arrays). New variables extend width only # under a v2 schema. # [epoch_s_UTC, air_C, rh_0-1, wind_mps, sw_Wm2, cloud_0-1]` | **CLEAN**

---

**`../../yellowstone_python/tools/fetch_snotel_obs.py`**
- L1-29: Module docstring — "Fetch a frozen SNOTEL observation bundle", "Site selection, element periods-of-record, and the recommended WY2026 window were verified live by a parallel worker" | **AI TELL** (references to "parallel worker" — meta-commentary about development process)

---

**`../../yellowstone_python/tools/fetch_yellowstone_tributaries.py`**
- L1-14: Module docstring — "Fetch real tributary data for Yellowstone cold-refuge implementation", "replacing the authored/temporary values in the current tributary refuge implementation", "TASK COMPLIANCE:" with checkmarks | **AI TELL** ("replacing the authored/temporary values" — narrative about past versions, "TASK COMPLIANCE" — meta-commentary)
- L28: `# Set up comprehensive logging (avoid file write in read-only environment)` | **CLEAN**
- L43: `"""Implement rate limiting for USGS API calls to prevent service disruption."""` | **CLEAN**
- L50: `"""Wait if rate limit would be exceeded for this site."""` | **CLEAN**
- L65: `"""Comprehensive error handling with exponential backoff and circuit breakers."""` | **CLEAN**
- L76: `"""Check if circuit breaker should be activated."""` | **CLEAN**
- L85: `"""Record a failure for circuit breaker logic."""` | **CLEAN**
- L93: `"""Fetch data with exponential backoff and circuit breaker protection."""` | **CLEAN**
- L117: `"""Validate USGS site ID format."""` | **CLEAN**
- L120: `"""Validate days parameter is within acceptable range."""` | **CLEAN**
- L123: `"""Validate cells parameter is within acceptable range."""` | **CLEAN**
- L126: `"""Validate confluence chainage is reasonable."""` | **CLEAN**
- L130: `"""Calculate integrity hash for data validation."""` | **CLEAN**
- L141: `"""Fetch real USGS data for a specific site with comprehensive error handling. Args: ... Returns: ..."""` | **CLEAN**
- L348-353: `"""Load documented tributaries from scientific literature with provenance. Returns: List of documented tributaries with provenance"""` | **CLEAN**
- L510-517: `"""Generate comprehensive tributary data using real USGS data where available. Args: days... Returns: Dictionary with tributary data"""` | **CLEAN**
- L675-682: `"""Get documented temperature for a tributary from scientific literature. Args: name... Returns: Documented temperature in Celsius"""` | **CLEAN**
- L705-712: `"""Get documented discharge for a tributary from scientific literature. Args: name... Returns: Documented discharge in m³/s"""` | **CLEAN**
- L733-740: `"""Analyze USGS data to assess cold-refuge potential. Args: usgs_data... Returns: Analysis results"""` | **CLEAN**
- L796-804: `"""Create tributary refuge cells from real tributary data with provenance. Args: ... Returns: List of tributary refuge cell dictionaries"""` | **CLEAN**

---

**`../../yellowstone_python/tools/plot_fit.py`**
- L1-8: Module docstring — "Diagnostic PNGs from fit artifacts (Pillow only — no matplotlib)" | **AI TELL** (em dash)

---

**`../../yellowstone_python/tools/run_hot_lowflow.py`**
- L1-18: Module docstring — "Hot low-flow scenario: mapped replay + foodweb control-vs-hot comparison" | **CLEAN**
- L33: `BOUNDARY_M3S = 2.5  # Burkhalter 1979 geothermal baseflow 2-3 m3/s (measured)` | **CLEAN**
- L34: `BOUNDARY_C = 26.0  # authored scenario; below observed 29.5 C max` | **CLEAN**
- L65-67: `# The raw solver status is not in the derived/ status vocabulary # (tools/audit_provenance.py scans top-level bundles); preserve it # aside and label the saved scenario replay as what it is.` | **CLEAN**

---

**`../../yellowstone_python/tools/run_hot_lowflow_with_tributaries.py`**
- L1-20: Module docstring — "Add tributary refuge cells to hot low-flow scenario", "Task 1: Find cold lateral inflows...", "Task 2: Extend the foodweb landscape...", "Task 3: Re-run the hot-vs-control comparison at D1" | **AI TELL** (task list format — meta-commentary about development process)
- L39-44: `# Assumptions for tributary refuge cells based on typical cold-water tributaries # In Yellowstone, cold tributaries are typically: # - High-elevation sources (e.g., snowmelt from glacial streams) # - Cold-water tributaries that maintain temperatures below 12-14°C year-round # - Small to medium discharge (0.5-2.0 m3/s range) # - Joined to main stem at specific chainage locations` | **CLEAN**
- L53-59: `# Tributary refuge cell 1: Fairy Creek confluence # Based on literature: Fairy Creek enters the Firehole River upstream of # the main hot pool complex, with mean summer temperature ~8-12°C` | **CLEAN**
- L123: `# Tributary refuge cell 2: Glacier Creek (example of another cold tributary)` | **CLEAN**
- L192-193: `# Extract temperature for the last 3 cells (our new tributaries) # For each frame, we need to add temperatures for the new cells` | **CLEAN**
- L314: `print("\n✓ SUCCESS: Refuge flipped UPSTREAM to a cold cell!")` | **CLEAN**
- L317-319: `print("\n✗ FAILURE: Refuge did NOT flip upstream.") ... print("  The tributary refuge cells were insufficient to change trout behavior.")` | **CLEAN**
- L328: `print(f"  - Tributary temperatures: authod based on measured cold-water")` | **CLEAN** (note: typo "authod" in original)

---

**`../../yellowstone_python/tools/run_hot_lowflow_with_tributaries_v2.py`**
- L1-24: Module docstring — "Add tributary refuge cells to hot low-flow scenario using real USGS data", "replacing the authored/temporary values used in the previous implementation", task list | **AI TELL** ("replacing the authored/temporary values used in the previous implementation" — narrative about past versions)
- L49-53: `"""Load real tributary data from USGS and other sources. Returns: Dictionary with real tributary data and analysis"""` | **CLEAN**
- L62-67: `"""Fallback data using the previous authored approach. Returns: Dictionary with fallback tributary data"""` | **AI TELL** ("previous authored approach" — narrative about past)
- L115-126: `"""Create tributary refuge cells based on real data. Args: ... Returns: Modified pulse_doc with tributary refuge cells"""` | **CLEAN**
- L379: `print(f"\n✓ SUCCESS: Refuge flipped UPSTREAM to a cold cell!")` | **CLEAN**
- L383-385: `print(f"\n✗ FAILURE: Refuge did NOT flip upstream.") ...` | **CLEAN**

---

**`../../yellowstone_python/tools/usgs_nwis.py`**
- L1-18: Module docstring — "Fetch USGS field measurements and time-series data for Firehole River sites", "NOTE: earlier docstring versions advertised --measurements/--daily; those flags never existed in main() and are not supported. The RDB limb (_fetch_rdb) returns [] since waterdata.usgs.gov moved to JS/HTML (Oct 2026); IV via waterservices works." | **AI TELL** ("earlier docstring versions advertised" — narrative about past versions, date reference)
- L31-33: `# Modern Water Services endpoint for instantaneous values. The legacy # /usa/nwis/iv/ JSON path stopped returning data (Oct 2026: HTML/error); # waterservices returns the same WaterML-JSON timeSeries schema.` | **AI TELL** ("legacy" reference, date reference)
- L54-60: `# USGS parameter codes` followed by `PARAM_DISCHARGE = "000060"   # Actually 00060` etc. | **CLEAN**
- L74-81: `"""Fetch RDB-format data from NWIS. Returns list of dicts. NOTE (Oct 2026): waterdata.usgs.gov serves the measurements page as JS/HTML now, so this returns [] for field-measurement queries. Machine-readable cross-section surveys (width/area/velocity) are currently unfetchable — that is why channel geometry still leans on DEM transects. IV (discharge/temperature) via waterservices works."""` | **AI TELL** (date reference, "currently unfetchable" — narrative about current state)
- L142: `"""Fetch instantaneous values via Water Services (WaterML JSON)."""` | **CLEAN**
- L167: `_safe_float(val: str) -> float | None:` | **CLEAN**
- L175: `"""Fetch measurements, discharge IV, and temperature IV for a site."""` | **CLEAN**

---

**`../../yellowstone_python/tools/validate_obs_bundles.py`**
- L1-6: Module docstring — "Gate an observation bundle before fitting (schema/continuity/coverage)" | **CLEAN**
- L23-24: `# Gap tolerances from calibrate.py _fit_forcing_arrays (4x nominal step: # IV nominal 900 s, met nominal 3600 s).` | **CLEAN**

---

### TEST FILE COMMENTS

Test files contain mostly CLEAN comments — brief assertions and docstrings explaining test logic. Notable exceptions:

**`../../yellowstone_python/tests/test_reach_notebook.py`**
- L34-35: `# NOTE: inverse crime — same forward model generates and fits. # Proves the notebook machinery runs, not model validity.` | **AI TELL** (em dash)

**`../../yellowstone_python/tests/test_snow_validate.py`**
- L62-65: `# Inverse crime by construction: identical model generates and fits. # Proves the optimizer works; says nothing about the real snowpack. # Fit only over days where truth is positive: once the pack melts out # every param set agrees (melt-limited days carry no information).` | **CLEAN** (standard test caveat)

**`../../yellowstone_python/tests/test_llm_backend.py`**
- L261: `"""Adversarial finding #1: a corrupt census.json must not silently return"""` | **AI TELL** ("Adversarial finding" — references to adversarial review process)

---

### CONFIG FILE COMMENTS

**`../../yellowstone_python/configs/baseline.yaml`**
- All comments are CLEAN — brief labels for config values.

**`../../yellowstone_python/requirements.txt`**
- L6: `# sympy is test-only (A4 Jacobian verification); the test skips where absent.` | **AI TELL** ("A4" reference to development process)
- L8-9: `# pandas is the obs-alignment backend (B1); NOT installed on the project # interpreter (externally managed) — install it to flip the fit default.` | **AI TELL** ("B1" reference, em dash)

---

### NOTEBOOK MARKDOWN CELLS

**`../../yellowstone_python/notebooks/census_explorer.ipynb`**
- Markdown cell: `# Census explorer (reads ONLY the SQLite analysis store)` + explanatory text | **CLEAN**

**`../../yellowstone_python/notebooks/reach_fit.ipynb`**
- Markdown cell 1: `# Reach heat-budget fit — executable paper trail` + extensive explanation including "Coarse-grid caveat, printed by the notebook itself: its fallback top-5 spans distant fits, so its wide bands cover easily (0.93) — the production tight ridge under-covers (A1)." | **AI TELL** (em dash, "A1" reference)
- Markdown cell 2: `## Reading this trail` + "The fit must beat both nulls on holdout... Bands describe fit ambiguity. If holdout coverage misses nominal badly, the error is structural bias (check residual lag-1), not parametric spread — do not widen the ridge rule to hide it." | **AI TELL** (em dash, meta-commentary about methodology)

---

### MARKDOWN FILE COMMENTS

**`../../yellowstone_python/README.md`**
- Entire file (184 lines) | **CLEAN** — technical documentation for developers

**`../../yellowstone_python/SECURITY_HARDENED_TRIBUTARY_IMPL.md`**
- Entire file (196 lines) | **AI TELL** — heavy use of emojis (✅, 🎯, 🛡️, 📊, 🔧, 📋, 🎉), "TASK COMPLIANCE" checkmarks, "SECURITY COMPLIANCE" section, "PROVENANCE DOCUMENTATION" — reads like AI-generated summary with emojis and checkmarks

**`../../yellowstone_python/TASK_1_TTRIBUTARY_COLD_REFUGE_SUMMARY.md`**
- Entire file (115 lines) | **AI TELL** — "Key Achievements", "Success Metrics", "Critical Insights", heavy use of ✅ checkmarks, "production-ready" claims

**`../../yellowstone_python/yellowstone_python/replay/README.md`**
- Entire file (254 lines) | **CLEAN** — detailed technical documentation

**`../../yellowstone_python/yellowstone_python/stubs/README.md`**
- Entire file (27 lines) | **CLEAN** — module index

**`../../yellowstone_python/worker_briefs/*.md`** | **CLEAN** — internal work documents

---

### SUMMARY

| Category | Count |
|----------|-------|
| **AI TELL** | ~85 comments |
| **CLEAN** | ~200+ comments |

**Most common AI tell patterns:**
1. Em dashes (—) in comments — 30+ instances
2. References to "audit" phases/fixes — 15+ instances
3. "LEGACY" / "old" / "previous" version references — 20+ instances
4. Date-stamped "verified failure" / "measured failure" notes — 5 instances
5. "REAL DATA GAP" / "Integration point" / "STATUS:" meta-commentary — 15+ instances
6. Emojis and checkmarks in markdown summaries — 2 files entirely
7. "A1" / "B1" / "A4" development process references — 10+ instances

---

## Reclassified from CLEAN to AI TELL (New Patterns)

The following comments were previously classified as CLEAN but have been reclassified based on expanded AI tell patterns:

| File | Line | Comment | New Tell Pattern |
|------|------|---------|-----------------|
| analysis_store.py | L24 | `# OR REPLACE frees the old rowid...` | Narrative about hypothetical failure ("would otherwise") |
| build.py | L56 | `# Absent clock_hour falls back...` | Excess information, "range-safe by construction" redundant |
| build.py | L70 | `# Re-walk the bison's ACTUAL authored route...` | Overly verbose, "verified rather than demonstrated" narrative |
| fish.py | L177 | `# Fall back to z order rather than guessing a chain.` | Pattern A: references "guessing" as alternative |
| fish.py | L179 | `# This is a query extent for aquatic actors, not a surveyed bank test.` | Pattern C: redundant/obvious |
| hydro_thermal.py | L233 | `"""Exact fixed point of the mixing step (audit regression target)...` | Audit reference, excess explanation |
| insects_birds.py | L245 | `HOVER_THRESHOLD = 0.035  # wildlife_actor.gd::_update_insects (legacy interface)` | Legacy reference |
| llm_backend.py | L277 | `"interpretation": ("positive deficit = game sparser...` | Meta-commentary about process |
| snow_season.py | L349 | `"""Resolve (season, clock_hour, nominal date)...` | Pattern A ("instead of guessing"), Pattern B ("stamped either way"), Pattern C ("a date carries no time of day"), Pattern D (too long) |
| snow_validate.py | L363 | `"""Daily air-C + precip-mm series...` | Pattern A ("instead of inventing weather"), excess explanation |
| snow_validate.py | L367 | `"""Joint grid fit of (k_melt, site-effective wind_loss)...` | Meta-commentary ("it does not rewrite the game") |
| vegetation.py | L390 | `# Maximum candidate cells scanned...` | Pattern A ("instead of burning minutes"), meta-commentary |
| aquatic_foodweb.py | L40-41 | `# Mapped bed shear (Pa) or None...` | Meta-commentary ("never to an invented value") |
| aquatic_foodweb.py | L41 | `"""Mapped bed shear (Pa) -> benthic disturbance fraction...` | Overly verbose, meta-commentary |
| aquatic_foodweb.py | L47 | `"""Refuge + diet + emergence response...` | Narrative about hypothetical failure |
| grazers.py | L220 | `"""Length + apron gates sampled along FULL segments...` | Redundant, meta-commentary |
| pool_crust.py | L317 | `# Guarantee strictly growing radii...` | Narrative about hypothetical failure ("would otherwise") |
| review_proposals.py | L338 | `# NaN would make every `suit < threshold`...` | Excess explanation |
| snow_season.py | L347 | `"""Meteorological season for month/day...` | Excess information ("Day is accepted for future astronomical use") |
| snow_season.py | L348 | `"""System local date/time -> game season...` | Meta-commentary ("Range-safe by construction") |
| microclimate.py | L300 | `"""Seeded Ornstein-Uhlenbeck gusts...` | Comparison to alternative, excess explanation |
| replay/river_world.py | L586 | `"""Find a single directed chain...` | Excess explanation (listing things not to do) |
| replay/river_world.py | L342-346 | `"""Split at sources and feature boundaries...` | References past version ("legacy compartment") |
| uncertainty.py | L860-867 | `"""Advance for duration_s...` | Overly verbose, usage documentation in comment |

---

## Proposed Comment Fixes

| File | Line | Original (AI TELL) | Proposed Fix |
|------|------|-------------------|--------------|
| analysis_store.py | L1-41 | 41-line module docstring | `"""SQLite-backed analysis store for derived artifacts. Read-only queries over allow-listed tables/columns."""` |
| analysis_store.py | L56-58 | `# Unit factors, stated once (see module docstring)...` | `# Unit factors: SNOTEL stores WTEQ/PRCP/SNWD in inches, TAVG/TMAX/TMIN in degF.` |
| analysis_store.py | L355-360 | `"""Build a store file from ONE build dir...` | `"""Build a store file from one build dir + obs inputs. Atomic write. Refuses to overwrite existing files."""` |
| analysis_store.py | L434-435 | `# Single source of truth for circle-radius bounds...` | `# Circle-radius bounds single-sourced here; llm_backend aliases these.` |
| analysis_store.py | L586 | `filters[k] = v  # validated; consumed below (was: dropped)` | `filters[k] = v  # validated; consumed below` |
| analysis_store.py | L633-638 | `"""Circle crown count via the R-tree...` | `"""Circle crown count via R-tree. Used by /api/density when a store file is present."""` |
| aquatic_foodweb.py | L1-23 | 23-line module docstring | `"""Multi-day insect + trout + dipper dynamics on a thermal landscape."""` |
| aquatic_foodweb.py | L57-64 | `"""Per-cell quasi-steady thermal + hydraulic habitat...` | `"""Per-cell quasi-steady thermal + hydraulic habitat from replay frames. t_min_s/t_max_s restrict to a window for intervention comparison."""` |
| aquatic_foodweb.py | L130-142 | `"""Multi-day insect + trout + dipper dynamics...NOTE (2026-10-10)...` | `"""Multi-day insect + trout + dipper dynamics. shear_disturbance ramps 0 at threshold to 1 at twice it. None shear maps to zero; None threshold switches coupling off. Default 20 Pa."""` |
| aquatic_foodweb.py | L151-155 | `# Consumption runs on HOURLY substeps...` | `# Consumption runs on HOURLY substeps. Daily-step Holling demands saturate and collapse competition to a fixed split.` |
| aquatic_foodweb.py | L203-210 | `# Consumption at the refuge cell...verified failure, Oct 2026.)` | `# Consumption at the refuge cell. Exploitative competition on HOURLY substeps: demands computed from the same pre-consumption stocks, scaled pro-rata if combined demand exceeds availability. Sequential ordering would hand the outcome to whoever eats first.` |
| aquatic_foodweb.py | L240-242 | `# Adult turnover...verified failure, Oct 2026).` | `# Adult turnover: emergent insects die/disperse within days (authored mean residence ne_turnover_days).` |
| aquatic_foodweb.py | L331-332 | `window_note = ("full-run means; short pulses are diluted — "...` | `window_note = ("full-run means; short pulses are diluted. "...` |
| build.py | L1-17 | Module docstring with audit references | `"""Build pipeline: runs all modules and writes derived artifacts."""` |
| build.py | L257-260 | `"godot_divergence_note": ("...— residual documented, not hidden")` | `"godot_divergence_note": ("...Residual documented.")` |
| build.py | L290 | `# --- M01b 1-D advection-dispersion replay (Phase 2 flagship) ---` | `# --- M01b 1-D advection-dispersion replay ---` |
| build.py | L293-296 | `# --- M05b aquatic food web (audit Phase 2 vertical slice)...` | `# --- M05b aquatic food web: replay heat -> insect prey -> trout refuge -> dipper intake, 14-day run ---` |
| canopy_census.py | L1-22 | Module docstring | `"""Canopy census: detect trees from NAIP imagery and produce stable records."""` |
| canopy_census.py | L196 | `"""Record x/z: dict key or tuple index — both call sites use either."""` | `"""Record x/z: dict key or tuple index."""` |
| canopy_census.py | L332-334 | `"""Measure single isolated crowns...the ruler every larger blob is split against."""` | `"""Measure single isolated crowns: components with no neighbor centroid within isolation_m."""` |
| canopy_census.py | L369-372 | `"""v1 peaks PLUS area-based top-up...` | `"""Peaks plus area-based top-up: blobs larger than lone trees are split to their area-implied stem count. Each record carries splitting_basis: peak \| area_topup."""` |
| exporters/to_map.py | L6-9 | `"""Phase 0: fields are already authored...` | `"""Fields are already authored in macro extent; plain copy."""` |
| fish.py | L1-21 | 21-line module docstring | `"""Trout thermal suitability and refuge selection."""` |
| fish.py | L35-43 | `# Cold-water trout thermal optimum band...LEGACY...New work uses...` | `# Cold-water trout thermal optimum band (illustrative). Two-sided: below the band is too cold, above is stressful. A one-sided penalty cannot discriminate reaches all below 20 C. Kept for ecosystem.gd parity. THERMAL_SPECIES + thermal_performance() provides the literature-based path.` |
| fish.py | L48-75 | Large comment block about literature-transferred thermal performance | `# Literature-transferred thermal performance. Anchor points from measurement; piecewise-linear shapes between them are authored.` |
| fish.py | L133-138 | `# --- Real-data integration point for laboratory thermal measurements ---...` | `# Lab thermal measurements integration point. REAL_LAB_DATA_PATH = None  # Set to file path when measurements are available.` |
| fish.py | L141-148 | `"""Load real laboratory thermal-performance measurements...` | `"""Load laboratory thermal-performance measurements. Returns dict with measured curves, or None if no real data is configured."""` |
| fish.py | L155-157 | `# Integration hook: read measured curves here...` | `# Returns None until real data path is configured.` |
| fish.py | L184-188 | `"""Two-sided preference in [0, 1]...LEGACY...new work uses...` | `"""Two-sided preference in [0, 1]: 1.0 inside the optimum band, falling linearly to 0 outside. Kept for ecosystem.gd parity; thermal_performance() provides the literature path."""` |
| fish.py | L201-210 | `"""Nondimensional U: preferred velocity/depth ranges...` | `"""Nondimensional U: preferred velocity/depth ranges, two-sided thermal preference. species=None keeps the authored band; a species name selects the literature performance path."""` |
| fish.py | L219-222 | `# Feeding loss saturates at feed_zero...backwards).` | `# Feeding loss saturates at feed_zero; stress keeps the gradient worsening with temperature above it.` |
| fish.py | L231-240 | `"""Literature-anchored performance at one water temperature...` | `"""Literature-anchored performance at one water temperature. Returns {feeding, stress, refuge_drive, lethal_flag} in [0, 1]. Anchor points from measurement; piecewise-linear shapes authored. refuge_drive from Kaya et al. 1977. lethal_flag marks water above UILT; shelter, never mortality."""` |
| fish.py | L276 | `"""Nearest reach by z — mirrors ecosystem.gd::reach_at (kept for runtime)."""` | `"""Nearest reach by z. Mirrors ecosystem.gd::reach_at."""` |
| fish.py | L290-297 | `"""Per-point reach id table...the old assign_reach path...` | `"""Per-point reach id table using the declared upstream chain order. z-nearestness fails for looping or U-shaped channels. Walk the declared chain and assign every point to the reach whose z-window contains it."""` |
| fish.py | L378-383 | `"""Move the holding window toward max suitability...` | `"""Move the holding window toward max suitability within swim range. Returns {start,end,reach_id,U,reason}. Window length preserved; river route never redrawn through unlisted water."""` |
| fish.py | L498-501 | `"""Deterministic refuge map...no hashes, no RNG...` | `"""Deterministic refuge map: Firehole centerline in world position, pool polygons, trout holding midpoints + selected-refuge markers. Every dot is a world coordinate; reproducible across processes and seeds."""` |
| gen_flora.py | L124-126 | `"""Truly bare pale ground...the old mask gate."""` | `"""Truly bare pale ground (bright AND greenless). Vegetated bright slopes fail this test and stay plantable."""` |
| gen_flora.py | L481-485 | `"""Art-directed density ring around the overlook deck...Answers the visible-hill sparseness...` | `"""Art-directed density ring around the overlook deck. Planted where slope is walkable and ground is not water, sinter apron, trail, or road. Ledger-marked as enhancement."""` |
| grazers.py | L1-17 | Module docstring | `"""Bison/elk habitat-constrained movement."""` |
| grazers.py | L50 | `"""Waypoints alone miss crossings — sample the full segment."""` | `"""Sample the full segment; waypoints alone miss crossings."""` |
| grazers.py | L60-62 | `"""Rich patch -> longer graze...not absolute index — patches...` | `"""Rich patch -> longer graze; poor patch -> sooner walk. Driven by fraction of capacity, not absolute index."""` |
| grazers.py | L117-127 | `"""8-connected A* with Euclidean heuristic...` | `"""8-connected A* with Euclidean heuristic on an eligibility grid. Endpoints must be unblocked. Returned waypoints are cell centers. Each accepted step is re-sampled along its true segment and rejected if any sample is blocked."""` |
| hydro_thermal.py | L129-133 | `"""Run fixed-dt transport...Ledger now carries FULL budget history...` | `"""Run fixed-dt transport (physical seconds). air_c may be const or fn(t). Ledger carries full budget history (cumulative in/out/exchange/storage)."""` |
| insects_birds.py | L1-18 | Module docstring | `"""Three-compartment prey + bird diets."""` |
| insects_birds.py | L76-81 | `"""LEGACY interface: retune dipper/raven cadence...` | `"""Retune dipper/raven cadence from shared activity. Kept because wildlife_actor.gd reads timer values from records. Prefer update_wildlife_from_intake() for intake-driven timing."""` |
| insects_birds.py | L95 | `# --- Three-compartment prey dynamics (the actual model) ---` | `# --- Three-compartment prey dynamics ---` |
| insects_birds.py | L109-116 | `"""Benthic larvae: degree-day development...legacy no-ceiling path."""` | `"""Benthic larvae: degree-day development -> emergence flux; flood/hydraulic disturbance removes a fraction. Returns (nb_new, emergence). t_cutoff: development stupor above this temperature, dd forced to 0. None keeps the no-ceiling path."""` |
| insects_birds.py | L130-144 | Large comment block about benthic insect groups | `# Benthic insect groups: transferred thermal structure. Relative rates (dipteran faster, multivoltine) are an authored ordering.` |
| insects_birds.py | L170-178 | `"""Trout benthic-vs-emergent shares shift with temperature...documented limitation."""` | `"""Trout benthic-vs-emergent shares shift with temperature. Cold water: almost entirely benthic; warm water: heavily emerging (Kaeding & Kaya 1978). Linear transition 15 -> 21 C; shape authored, endpoints transferred. Molluscs not modeled."""` |
| llm_backend.py | L1-30 | 30-line module docstring | `"""HTTP backend for census analysis and proposal review. Stdlib only."""` |
| llm_backend.py | L61-66 | `ACCURACY_NOTES` list with cross-check narrative | `ACCURACY_NOTES = ["Pretrained DeepForest underdetects vs census (~1,175 crowns)."]` |
| llm_backend.py | L69-72 | `# Hardening limits (adversarial review 2026-10-09)...` | `# Density circles outside [MIN_RADIUS_M, MAX_RADIUS_M] are rejected. Bounds single-sourced from analysis_store.` |
| llm_backend.py | L186-192 | `"""Circle crown count, store-backed...cross-check test pins equality...` | `"""Circle crown count, store-backed when a store file exists. Store path and JSON path share one answer contract."""` |
| microclimate.py | L1-17 | Module docstring | `"""Microclimate: one wind/time authority. Condensation, not steam."""` |
| microclimate.py | L26-33 | `# --- Weather forcing provenance ---...STATUS:...` | `# Weather forcing: AUTHORED defaults (illustrative). fetch_met_forcing.py connects to Open-Meteo for measured forcing.` |
| microclimate.py | L51-56 | `"""Integration point: load real Open-Meteo forcing...` | `"""Load real Open-Meteo forcing for site. Returns met bundle dict or None if fetch fails / not configured."""` |
| microclimate.py | L88-89 | `"""LEGACY artistic index for the old Godot uniform path...` | `"""Artistic index for the Godot uniform path. Prefer condensation_potential() for analysis."""` |
| microclimate.py | L115-126 | `"""Evaporation flux + dew-point depression...cannot drift apart."""` | `"""Evaporation flux + dew-point depression + mixing supersaturation proxy. relative_supersaturation is the quantity the Godot renderer consumes. Same Magnus form and 30/70 entrainment ratio as ecosystem.gd::condensation_visibility."""` |
| microclimate.py | L167-171 | `"""Per-second (wind, air_c, hour) trace...(audit fix)...` | `"""Per-second (wind, air_c, hour) trace. Pass the FULL weather config so the trace cannot disagree with configured weather. With a seed, gusts come from the OU process; otherwise the sinusoid is used."""` |
| pool_crust.py | L44-46 | `# Base pigment bands...— there is no universal...` | `# Base pigment bands (fraction of r_water, color, meaning). Per-pool copies adjusted by make_ramp_stops(). Authored bands keyed to depth + gradient + substrate.` |
| pool_crust.py | L326 | `f"{shell['name']} — authored section (illustrative, not survey)"` | `f"{shell['name']} - authored section (illustrative, not survey)"` |
| replay/river_world.py | L57-63 | `"""Validate per-feature mean-depth profiles...never silently labeled...` | `"""Validate per-feature mean-depth profiles. Format: {feature_id: {"depth_m": positive float, "status": str}}. Unknown feature ids rejected."""` |
| replay/river_world.py | L251-255 | `"""Translate an old reach anchor...old six-reach display...` | `"""Translate a reach anchor, refusing ambiguous crossings. Exists for compatibility with the six-reach display."""` |
| replay/river_world.py | L628-631 | `"initial_condition": ("...not the legacy six-reach temperature snapshot.")` | `"initial_condition": ("Calculated steady state at t=0 forcing.")` |
| replay/uncertainty.py | L1-27 | Module docstring with "A1" reference | `"""Uncertainty quantification for the lumped reach fit and authored-knob sensitivity."""` |
| replay/uncertainty.py | L43-53 | `# --- Uncertainty quantification provenance ---...REAL DATA NEEDED:...` | `# All parameters AUTHORED (not derived from measurement error): ENSEMBLE_SEED, tol_frac, min_members, n_bootstrap, spinup_s, train_frac, band_level. Module reports fit ambiguity, not predictive calibration.` |
| replay/uncertainty.py | L133-139 | `"""Percentile bands + seeded-bootstrap...the Monte Carlo in this module."""` | `"""Percentile bands + seeded-bootstrap standard error of the edges. Bands are cross-member percentiles at each timestep. Bootstrap resamples members with replacement."""` |
| replay/uncertainty.py | L281-287 | `"""Median Manning-consistency-ratio response...must not silently change the sample."""` | `"""Median Manning-consistency-ratio response to z and n. Recomputes cell_hydraulics per recorded cell with one authored knob varied; cells where Manning is undefined stay excluded."""` |
| replay/uncertainty.py | L344 | `"""Full A1 pass: ensemble bands + coverage + fit OAT ranking."""` | `"""Full pass: ensemble bands + coverage + fit OAT ranking."""` |
| snow_season.py | L1-20 | Module docstring with "audit fixes" | `"""Snow season: weather state, snow accumulation/melt, and season tracking."""` |
| snow_season.py | L171-184 | `"""Advance snow + soil + phenology...fit hook for site-effective...` | `"""Advance snow + soil + phenology with a verified water ledger. thermal_test(x, z) -> True where ground is hydrothermal: those cells get the ground-heat melt flux. precip_mm_by_day optionally overrides the scalar. Returns (patches, ledger). Ledger residual must be ~0."""` |
| study_mode.py | L110-111 | `"about": "COUNTEREXAMPLE...Trout barely move — short-term..."` | `"about": "COUNTEREXAMPLE...Trout barely move. Short-term river response follows residence time and forcing, not air alone."` |
| vegetation.py | L32-35 | `# Per-guild coefficients: ARTIST/SCIENCE INPUTS...REAL DATA GAP:...Integration point:...` | `# Per-guild coefficients: authored inputs, not inferred from field data.` |
| vegetation.py | L53-60 | `# Real-data provenance for vegetation parameters...real_data_gap` | `# Coefficients are authored, not inferred from field data.` |
| vegetation.py | L127-136 | `"""Deterministic proposal grid+jitter...LEGACY wrapper...the old behaviour...` | `"""Deterministic proposal grid+jitter with per-guild min separation. Separation is best-effort here; prefer propose_plantings_reviewed() for enforced output. Preserves stable ids verbatim."""` |
| tools/audit_provenance.py | L16 | `# Exact vocabulary measured across derived/*.json (28 occurrences, 2026-10-10).` | `# Exact vocabulary measured across derived/*.json.` |
| tools/fetch_firehole_obs.py | L1-19 | Module docstring with em dash | `"""Fetch a frozen Firehole observation bundle for reach-scale calibration. All sources measured, all remote."""` |
| tools/fetch_snotel_obs.py | L1-29 | Module docstring with "parallel worker" | `"""Fetch a frozen SNOTEL observation bundle. Site selection and WY2026 window verified live."""` |
| tools/fetch_yellowstone_tributaries.py | L1-14 | Module docstring with "replacing the authored/temporary values" and "TASK COMPLIANCE:" | `"""Fetch real tributary data for cold-refuge implementation."""` |
| tools/fetch_yellowstone_tributaries.py | L62-67 | `"""Fallback data using the previous authored approach...` | `"""Fallback data. Returns: Dictionary with fallback tributary data"""` |
| tools/plot_fit.py | L1-8 | Module docstring with em dash | `"""Diagnostic PNGs from fit artifacts (Pillow only)."""` |
| tools/run_hot_lowflow_with_tributaries.py | L1-20 | Module docstring with task list | `"""Add tributary refuge cells to hot low-flow scenario."""` |
| tools/run_hot_lowflow_with_tributaries_v2.py | L1-24 | Module docstring with "replacing the authored/temporary values used in the previous implementation" | `"""Add tributary refuge cells to hot low-flow scenario using real USGS data."""` |
| tools/usgs_nwis.py | L1-18 | Module docstring with "earlier docstring versions advertised" | `"""Fetch USGS field measurements and time-series data for Firehole River sites. IV via waterservices; RDB returns [] since waterdata.usgs.gov moved to JS/HTML."""` |
| tools/usgs_nwis.py | L31-33 | `# Modern Water Services endpoint...The legacy /usa/nwis/iv/...` | `# Water Services endpoint for instantaneous values. Returns WaterML-JSON timeSeries schema.` |
| tools/usgs_nwis.py | L74-81 | `"""Fetch RDB-format data from NWIS...NOTE (Oct 2026)...currently unfetchable...` | `"""Fetch RDB-format data from NWIS. Returns list of dicts. waterdata.usgs.gov serves JS/HTML now, so this returns [] for field-measurement queries. IV via waterservices works."""` |
| tests/test_reach_notebook.py | L34-35 | `# NOTE: inverse crime — same forward model...` | `# Inverse crime: same forward model generates and fits. Proves the notebook machinery runs, not model validity.` |
| tests/test_llm_backend.py | L261 | `"""Adversarial finding #1: a corrupt census.json...` | `"""A corrupt census.json must not silently return"""` |
| requirements.txt | L6 | `# sympy is test-only (A4 Jacobian verification); the test skips where absent.` | `# sympy is test-only; the test skips where absent.` |
| requirements.txt | L8-9 | `# pandas is the obs-alignment backend (B1); NOT installed...— install it...` | `# pandas is the obs-alignment backend; NOT installed on the project interpreter (externally managed). Install it to flip the fit default.` |
| notebooks/reach_fit.ipynb | Markdown cell 1 | "Coarse-grid caveat...— the production tight ridge under-covers (A1)." | "Coarse-grid caveat: fallback top-5 spans distant fits, so wide bands cover easily. The production tight ridge under-covers." |
| notebooks/reach_fit.ipynb | Markdown cell 2 | "The fit must beat both nulls...— do not widen the ridge rule to hide it." | "The fit must beat both nulls on holdout. Bands describe fit ambiguity. If holdout coverage misses nominal badly, the error is structural bias (check residual lag-1), not parametric spread. Do not widen the ridge rule to hide it." |
| SECURITY_HARDENED_TRIBUTARY_IMPL.md | Entire file | Remove emojis, replace "TASK COMPLIANCE:" with "Implementation:", "SECURITY COMPLIANCE" with "Security", "PROVENANCE DOCUMENTATION" with "Provenance" | (Apply throughout) |
| TASK_1_TTRIBUTARY_COLD_REFUGE_SUMMARY.md | Entire file | Remove emojis, replace "Key Achievements" with "Summary", "Success Metrics" with "Results", "Critical Insights" with "Notes" | (Apply throughout) |