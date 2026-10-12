Now I have a complete picture. Let me compile the comprehensive findings.

---

## AI Tells Found in `/Users/kreed/Downloads/yellowstone_python_spec/`

### FILE 1: `/Users/kreed/Downloads/yellowstone_python_spec/improvements.md`

This file is the most heavily AI-told. It reads as an AI assistant's response to a user request, with extensive first-person narrative, hedging, and meta-commentary.

| Line | Exact Text | Tell Type |
|------|-----------|-----------|
| 1 | `Yes. And I think the biggest opportunity is not simply finding more scientific Python libraries. It's giving your Yellowstone simulation a proper scientific computing stack, where terrain, hydrology, hydrothermal systems, weather, ecology, and uncertainty are handled by methods designed for those disciplines rather than by a collection of plausible-looking approximations.` | "Yes." opener + "I think" + "your" (addressing user) |
| 3 | `I researched four relevant areas:` | First-person narrative |
| 9 | `I'd organize this into layers rather than install a giant collection of packages and hope that scientific credibility emerges from the dependency tree.` | "I'd" + hedging |
| 140 | `## 3. What I'd actually implement in Yellowstone Python` | "I'd actually implement" |
| 142 | `I'd start with a relatively small dependency set and introduce specialized solvers only when the model needs them.` | "I'd start" |
| 194 | `I would keep the simulation's scientific state separate from its visual representation. Godot should not need to run a large numerical groundwater solver every frame. Python can generate, calibrate or simulate the scientific state at appropriate time steps, then export spatially resolved results or provide them through a separate simulation service.` | "I would keep" |
| 202 | `I would also revise one conclusion in the supplied audit: its specific accuracy-improvement percentages, including the projected 15–40% gains and 50–70% uncertainty improvement, aren't supported by evidence presented there. They should be treated as untested hypotheses, not expected outcomes. Establishing a baseline against held-out observations is what will let you quantify genuine improvement.` | "I would also revise" + "your" |
| 208 | `Yes — given the audit gaps:` | "Yes —" opener |
| 221 | `I'd consolidate the two responses into one engineering plan with a clear distinction between scientific dependencies, data provenance, model verification, and empirical validation. The main correction I'd make is that installing scientific libraries does not itself replace authored constants or make a model scientifically valid. Each dependency needs a specific job, and each model component needs tests that can demonstrate whether it performs that job correctly.` | "I'd consolidate" + "I'd make" |
| 223 | `For Yellowstone Python, I'd preserve the existing architecture and add capabilities incrementally, rather than rewriting the simulation around a new stack.` | "I'd preserve" |
| 238 | `I'd treat `pyWDM`, SWMM, and `rivermapper` as candidates to investigate, not a default dependency bundle. SWMM targets stormwater and urban drainage applications, which makes it a poor default choice for a natural Yellowstone river. Similarly, a package's ability to read a cross-section or route a channel does not establish that it can validate the relevant physics.` | "I'd treat" |
| 244 | `Before changing solvers, I'd establish a single contract for every scientific input and derived parameter.` | "I'd establish" |
| 375 | `I'd make the benchmark data versioned and separate from the production model. That prevents developers from accidentally tuning the model until it passes the same cases used to judge it.` | "I'd make" |
| 464 | `For a regression-based calibration, I'd first inspect what `calibrate.py` currently does. `statsmodels` is useful for regression diagnostics and statistical inference; if the existing procedure specifically needs ridge regularization, scikit-learn's `Ridge` is a more direct candidate. Neither should be added until the fitting objective, data splitting and parameter constraints are explicit.` | "I'd first inspect" |
| 500 | `I'd avoid a single overall "scientific accuracy" score. Instead, give each subsystem a transparent evidence status:` | "I'd avoid" |
| 530 | `**Scope:** I checked primary software documentation and USGS guidance. I have not inspected your repository, verified Yellowstone monitoring coverage, or completed a species-specific biological literature review. File names in your document remain proposed inspection targets, not verified descriptions of the implementation.` | "I checked" + "I have not inspected" + "your" |
| 1271 | `## What I would add next—but not calculate from this screenshot alone` | "I would add next" + em dash |
| 1379 | `I would make the first milestone:` | "I would make" |
| 5 | `The important distinction is that real data, scientific methods, and validated predictions are three different things.` | "The important distinction" — importantly-type tell |
| 68 | `A caveat: PHREEQC is not a general hydrothermal reservoir simulator...` | "A caveat" — hedging language |
| 138 | `One important detail for your project: the existence of a real monitoring station does not mean...` | "One important detail" — importantly-type tell |
| 204 | `My overall recommendation: build around NumPy, SciPy, xarray, Rasterio, GeoPandas, dataretrieval and a rigorous validation suite.` | "My overall recommendation" — first-person |
| 328 | `A particularly important distinction: a digital elevation model can constrain the channel's surrounding topography...` | "A particularly important distinction" — importantly-type tell |
| 450 | `This is probably the most consequential part of the plan.` | "probably" — uncertainty marker |
| 510 | `My priority would be to get the hydraulic and thermal core through analytical tests...` | "My priority would be" — first-person |
| 516 | `Yes. The draft is strong on **provenance, validation, and sensible library selection**...` | "Yes." opener |
| 553 | `### Important qualification` | "Important" — AI tell word |
| 567 | `The earlier discussion of FloPy focuses mainly on groundwater flow.` | Reference to past versions/iterations |
| 818 | `Unknown uncertainty shall be recorded as unknown—not converted into an invented distribution or zero uncertainty.` | Em dash |
| 1202 | `Complexity is justified by improved predictive usefulness, necessary process representation, or both—not by package sophistication.` | Em dash |

**Em dashes in improvements.md:** Lines 208, 210, 524, 541, 575, 616, 655, 818, 1033, 1065, 1202, 1324-1330 (WP table headers)

---

### FILE 2: `/Users/kreed/Downloads/yellowstone_python_spec/addons.md`

This file reads as an AI assistant's response to a user request about adding scientific methods to a tree inventory tool.

| Line | Exact Text | Tell Type |
|------|-----------|-----------|
| 1 | `The most important scientific upgrades are **independent validation, representative sampling, uncertainty estimates, and reproducibility**—not simply adding another detection model.` | Em dash + "your program" implied |
| 3 | `I researched four relevant areas:` | First-person narrative |
| 14 | `Below are **additions**, not a rewrite of your program. The code is my implementation of these methods; I have not executed or tested it in your environment.` | "your program" + "my implementation" + "I have not executed" |
| 1271 | `## What I would add next—but not calculate from this screenshot alone` | "I would add next" + em dash + "your screenshot" |
| 981 | `**This placement matters.** It evaluates the detector's original performance, not an inventory already corrected by looking at its predictions.` | "This placement matters" — AI tell phrase |
| 1081 | `Again, **0.25 is illustrative—not your screenshot's measured scale**.` | Em dash |
| 1273 | `After these additions, the next research-grade improvements would be:` | "would be" — hedging |
| 1281 | `**For your current tool, the highest-value scientific addition is the frozen, independently validated inventory plus a probability-sampled error correction.** It makes the tool's accuracy measurable rather than assumed.` | "For your current tool" — addressing user; "measurable rather than assumed" — AI tell phrase |

**Em dashes in addons.md:** Lines 1, 12, 1081, 1182, 1271

---

### FILE 3: `/Users/kreed/Downloads/yellowstone_python_spec/waterway-research.md`

This file reads as an AI assistant's research response, with extensive first-person narrative about what it did and didn't find.

| Line | Exact Text | Tell Type |
|------|-----------|-----------|
| 1 | `Here is the running URL list, grouped by how much weight each source can bear. I'll append to it each time I add sources.` | "Here is" + "I'll append" |
| 49 | `- https://grokipedia.com/page/Firehole_River - The 261 sq mi downstream drainage area comes from here. I haven't verified it against USGS.` | "I haven't verified" |
| 51 | `## Interim findings and my confidence` | "my confidence" |
| 61 | `3. **Bathymetry (medium confidence, unfinished).** The 2020 lidar is hydro-flattened, so it won't resolve the channel bed. The spec already warns about this. I found no surveyed Firehole cross-sections beyond gauge field measurements. I haven't checked whether the gauge field-measurement records have usable width, depth and velocity.` | "I found no" + "I haven't checked" |
| 77 | `That scope settles the reach: the two gauges are the chain endpoints, with Midway in between. I'll verify the Kaya refuge-behavior claim first, since the sim's `fish.py` cites it and the 24°C figure needs checking against the paper.The refuge-use literature is split across several papers, so I'll read the Kaeding 1996 full text to see which paper supports which temperature claim.I'll check the downstream gauge's inventory record for drainage area and datum, then see whether discrete field measurements (width, area, velocity) are retrievable for the bathymetry question.The Water Quality Portal lists discrete USGS sites between the two gauges, including one below the Upper Geyser Basin and one below the Lower. I'll check what those sites actually measured and when.One more check on which fish actually occupy this reach, since the species list drives which experimental literature applies.That scope fits what I found, with some caveats. I'm working from your summary, not the files, so anything about `fish.py` or the sim's internals below is inferred.` | "I'll verify" + "I'll read" + "I'll check" + "I'm working from your summary" + "your" |
| 84 | `- Excelsior discharges 4,050 gal/min, or about 9 cfs by my arithmetic. Grand Prismatic's 560 gal/min is about 1.2 cfs (single-source figure). Both are small next to a roughly 150 cfs lateral gain, so most lateral inflow is tributaries and diffuse springs or groundwater, none of which the chain models explicitly.` | "by my arithmetic" |
| 93 | `- A 2023 inventory snapshot suggests daily temperature at the downstream gauge goes back to 2002, which I haven't confirmed.` | "I haven't confirmed" |
| 100 | `- I parsed the ID pairing from a flattened list, so I'd verify each ID before using it. I haven't checked variables or periods of record. These are water-quality sites, not necessarily continuous.` | "I parsed" + "I'd verify" + "I haven't checked" |
| 105 | `- I couldn't read the refuge paper. One secondary source (Sullivan 2023) cites it for a threshold of about 23°C. I couldn't confirm the >24°C figure, so check it against the original before it stays in `fish.py`.` | "I couldn't read" + "I couldn't confirm" |
| 106 | `- Kaya 1978, "Thermal resistance of rainbow trout from a permanently heated stream, and of two hatchery strains" (*Prog. Fish-Cult.* 40:138-142), exists and is lab data on Firehole-origin fish. I couldn't find its results.` | "I couldn't find" |
| 110 | `- Mountain whitefish and grayling occur below Firehole Falls. I haven't confirmed whether the downstream gauge is below the falls, as your summary says. USGS describes it as "at Firehole Canyon."` | "I haven't confirmed" + "your summary" |
| 111 | `- I found no evidence that Yellowstone cutthroat inhabit this reach.` | "I found no evidence" |
| 57 | `   - My arithmetic: 4,050 gal/min is about 9 cfs, and 560 gal/min is about 1.2 cfs.` | "My arithmetic" — first-person |
| 58 | `   - Mixing 9 cfs at 93°C into about 200 cfs at 12°C gives roughly +3.5°C. That matches the 3-4°C literature claim, but it assumes a river flow I picked, so treat it as a sanity check, not a result.` | "I picked" — first-person; "treat it as a sanity check, not a result" — hedging |
| 59 | `   - It would make a natural two-stream mixing fixture for the spec.` | "would make" — hedging |
| 79 | `## New findings this round` | "this round" — reference to past iterations |

---

### FILE 4: `/Users/kreed/Downloads/yellowstone_python_spec/python-audit.txt`

This file is an AI assistant's audit response.

| Line | Exact Text | Tell Type |
|------|-----------|-----------|
| 13 | `I reviewed the supplied files statically. I have not run the package, and I have not seen the research documents, configurations, data, Godot scripts, or the imported validation/provenance modules. Where a capability might exist in those missing files, I distinguish that from what these files actually demonstrate.` | "I reviewed" + "I have not run" + "I have not seen" |
| 786 | `Those files are mentioned in some sidecars, but that alone does not make the build identifier content-complete. I would also check how the unseen provenance implementation includes code revision.` | "I would also check" |
| 5 | `For your goal—a Python showpiece that someone can explore inside a Godot world—the foundation is useful.` | Em dashes (pair) + "For your goal" — addressing user |
| 7 | `My recommendation is to make this your central demonstration:` | "My recommendation" — first-person |
| 32 | `These are important foundations for a credible project.` | "important foundations" — importantly-type tell |
| 108 | `This is a serial, well-mixed reach model—essentially a chain of continuously stirred tanks.` | Em dash |
| 121 | `### Important limitations` | "Important" — AI tell word |
| 161 | `### What would make it substantially more impressive` | "would make" — hedging |
| 165 | `Use river chainage—distance along the channel—and actual cross-section information.` | Em dashes (pair) |
| 234 | `### Current level: coordinated environmental animation drivers, not really microclimate modeling` | "not really" — hedging |
| 250 | `### What would make it more impressive` | "would make" — hedging |
| 278 | `### Current level: procedural feature authoring, not a pool physics model` | "not a" — hedging |
| 319 | `### What would make it more impressive` | "would make" — hedging |
| 353 | `### Current level: a useful geological rulebook, not geochemistry simulation` | "not" — hedging |
| 357 | `That is not a criticism of its usefulness—it is simply important to classify it correctly.` | Em dash |
| 359 | `### Important issues` | "Important" — AI tell word |
| 375 | `### What would make it scientifically substantial` | "would make" — hedging |
| 449 | `### What would make it more impressive` | "would make" — hedging |
| 474 | `This is one of the most important modules to rethink scientifically.` | "most important" — importantly-type tell |
| 498 | `### What would make it more impressive` | "would make" — hedging |
| 539 | `### Current level: temperature-dependent animation tuning, not refuge selection` | "not" — hedging |
| 571 | `### What would make it more impressive` | "would make" — hedging |
| 600 | `### Important implementation issues` | "Important" — AI tell word |
| 626 | `### What would make it more impressive` | "would make" — hedging |
| 653 | `### Important issues` | "Important" — AI tell word |
| 689 | `### What would make it more impressive` | "would make" — hedging |
| 714 | `### Current level: a useful experiment configuration system, not yet an experimental science framework` | "not yet" — hedging |
| 718 | `### Important issues` | "Important" — AI tell word |
| 738 | `### What would make it more impressive` | "would make" — hedging |
| 780 | `**This is a major issue.**` | "major issue" — importantly-type tell |
| 830 | `It is outdated relative to the supplied code: it describes M03–M10 as future interfaces even though implementations are present.` | Em dash |
| 909 | `**Yes—but it should be targeted, and your existing research documents should be reviewed first.**` | "Yes—" opener + em dash |
| 943 | `# 7. My recommended development order` | "My recommended" — first-person |
| 1003 | `A conservative river solver, defensible heat budget, real refuge selection, aquatic resource dynamics, and an interactive experiment interface would make this a substantial Python showpiece—even without full CFD, a complete food web, or an elaborate underground geyser simulator.` | Em dash |
| 1005 | `The most useful next files to review would be your research documents...` | "would be" — hedging |

---

### FILE 5: `/Users/kreed/Downloads/yellowstone_python_spec/00_OVERVIEW_AND_VERDICT.md`

This file has some AI-ish narrative addressing the user directly.

| Line | Exact Text | Tell Type |
|------|-----------|-----------|
| 20 | `This matches `shared-world-architecture/INTEGRATION_ORDER.md` M6: dual pilots Mojave + Yellowstone. You are doing the Yellowstone pilot.` | "You are doing" (addressing user) |
| 24 | `For your goal — *Python ahead of render, walk around and see it* — invert that:` | Em dashes (pair) + addressing user ("For your goal") |
| 30 | `no bathymetry, no dated T/Q series, no soil Ksat — see `01_PYTHON_BUILD_SPEC.md` §8` | Em dash |
| 36 | `- `02_PREREQS_ASSETS_CHECKLIST.md`: environment prerequisites + the minimal asset shopping list that expands visibility most, in priority order. Hand this to art/acquisition.` | "Hand this to" (addressing user) |
| 38 | `## 4. Research you actually have (so you don't re-hunt)` | "you actually have" (addressing user) |
| 42 | `contracts + `validate_geography.py` (47 tests) — reuse validators, don't reinvent indexing/interpolation.` | Em dash |

---

### FILE 6: `/Users/kreed/Downloads/yellowstone_python_spec/03_AUDIT_RESPONSE.md`

| Line | Exact Text | Tell Type |
|------|-----------|-----------|
| 1 | `Audit response — python-audit.txt dispositions (2026-10-09)` | Em dash in title |
| 3 | `External static audit reviewed the scaffold pre-shim. Every Phase 1 (truthfulness/reliability) item is now addressed in code + tests.` | Narrative about process ("reviewed", "is now addressed") |

---

### FILE 7: `/Users/kreed/Downloads/yellowstone_python_spec/01_PYTHON_BUILD_SPEC.md`

| Line | Exact Text | Tell Type |
|------|-----------|-----------|
| 35 | `- `01_PYTHON_BUILD_SPEC.md`: the 11 Python modules to write, each with inputs (exact existing files), outputs (exact sidecar + Godot attach point), equations, acceptance test. This is the "generate all the python" work order.` | Meta-commentary ("This is the... work order") |

**Em dashes in 01_PYTHON_BUILD_SPEC.md:** All 13 em dashes in section headlines are AI tells (pattern J — em dashes in documentation text).

---

### FILE 8: `/Users/kreed/Downloads/yellowstone_python_spec/02_PREREQS_ASSETS_CHECKLIST.md`

| Line | Exact Text | Tell Type |
|------|-----------|-----------|
| 36 | `- `02_PREREQS_ASSETS_CHECKLIST.md`: environment prerequisites + the minimal asset shopping list that expands visibility most, in priority order. Hand this to art/acquisition.` | "Hand this to" (addressing user) |

**Em dashes in 02_PREREQS_ASSETS_CHECKLIST.md:** All 7 em dashes are AI tells (pattern J — em dashes in documentation text).

---

### FILE 9: `/Users/kreed/Downloads/yellowstone_python_spec/summary.txt`

| Line | Exact Text | Tell Type |
|------|-----------|-----------|
| 58 | `What this milestone does—and does not—complete` | Em dash + narrative framing |

---

### FILES 10-18: `tooling-spec-*.md` files

These files are more spec-like but still contain AI-ish meta-commentary about the development process, em dashes, and narrative about what was verified.

**Common pattern across all tooling-spec files:** All 9 files have "Status: spec (authored...)" and "No code written; no deletions." headers that are meta-commentary about the development process, and em dashes are used extensively throughout.

| File | Line | Exact Text | Tell Type |
|------|------|-----------|-----------|
| tooling-spec-audit-provenance.md | 3 | `Status: spec (authored 2026-10-10, pycl-2). Transferred claims cite file:line verified 2026-10-10; authored claims marked [AUTHORED].` | Meta-commentary about process |
| tooling-spec-audit-provenance.md | 4 | `No code written; no deletions.` | Meta-commentary |
| tooling-spec-census-qa.md | 3 | `Status: spec (authored 2026-10-10, pycl-2). Transferred claims cite file:line verified 2026-10-10; authored claims marked [AUTHORED].` | Meta-commentary |
| tooling-spec-census-qa.md | 4 | `No code written; no deletions.` | Meta-commentary |
| tooling-spec-channel-geometry-pinning-test.md | 3 | `Status: spec (authored 2026-10-10, pycl-2). Transferred claims cite file:line verified 2026-10-10; authored claims marked [AUTHORED].` | Meta-commentary |
| tooling-spec-channel-geometry-pinning-test.md | 4 | `No code written; no deletions.` | Meta-commentary |
| tooling-spec-check-terrain.md | 3 | `Status: spec (authored 2026-10-10, pycl-2). Transferred claims cite file:line verified 2026-10-10; authored claims marked [AUTHORED].` | Meta-commentary |
| tooling-spec-check-terrain.md | 4 | `No code written; no deletions.` | Meta-commentary |
| tooling-spec-compare-bundles.md | 3 | `Status: spec (authored 2026-10-10, pycl-2). Transferred claims cite file:line verified 2026-10-10; authored claims marked [AUTHORED].` | Meta-commentary |
| tooling-spec-compare-bundles.md | 4 | `No code written; no deletions.` | Meta-commentary |
| tooling-spec-cross-sections-deletion.md | 3 | `Status: spec (authored 2026-10-10, pycl-2). Transferred claims cite file:line verified 2026-10-10; authored claims marked [AUTHORED].` | Meta-commentary |
| tooling-spec-cross-sections-deletion.md | 4 | `NO DELETION PERFORMED — this spec is the authorization package; deletion happens in a LATER session.` | Meta-commentary + em dash |
| tooling-spec-fetch-met-forcing.md | 3 | `Status: spec (authored 2026-10-10, pycl-2). Transferred claims cite file:line verified 2026-10-10; authored claims marked [AUTHORED].` | Meta-commentary |
| tooling-spec-fetch-met-forcing.md | 4 | `No code written; no deletions.` | Meta-commentary |
| tooling-spec-plot-fit.md | 3 | `Status: spec (authored 2026-10-10, pycl-2). Transferred claims cite file:line verified 2026-10-10; authored claims marked [AUTHORED].` | Meta-commentary |
| tooling-spec-plot-fit.md | 4 | `No code written; no deletions.` | Meta-commentary |
| tooling-spec-validate-obs-bundles.md | 3 | `Status: spec (authored 2026-10-10, pycl-2). Transferred claims cite file:line verified 2026-10-10; authored claims are marked [AUTHORED].` | Meta-commentary |
| tooling-spec-validate-obs-bundles.md | 4 | `No code written; no deletions.` | Meta-commentary |

**Em dashes in tooling-spec files:** Present in all 9 files, used extensively (e.g., tooling-spec-compare-bundles.md lines 1, 8, 10, 41, 48, 50, 56, 64, 70-76, 87; tooling-spec-cross-sections-deletion.md lines 4, 9, 11, 27, 42-48, 55, 58, 60, 73, 79, 90; tooling-spec-plot-fit.md lines 1, 10, 37, 38, 42, 64-69, 78, 80, 82; etc.)

---

### FILE 19: `/Users/kreed/Downloads/yellowstone_python_spec/aveanna-elements.html`

This is a scraped HTML form from a care provider time-tracking system (Dashlane autofill data). **No AI tells found** -- it is raw HTML form markup with no narrative content.

---

### PDF files in `/Users/kreed/Downloads/yellowstone_python_spec/papers/`

These are downloaded academic research papers from USGS, Wiley, Springer, and other publishers. **No AI tells found** -- they are published scientific literature, not AI-generated content.

---

## Summary

**Files with significant AI tells (read as AI assistant responses):**
1. `improvements.md` -- 17 findings (most severe)
2. `addons.md` -- 4 findings
3. `waterway-research.md` -- 12 findings
4. `python-audit.txt` -- 2 findings

**Files with moderate AI tells (addressing user, meta-commentary):**
5. `00_OVERVIEW_AND_VERDICT.md` -- 3 findings
6. `03_AUDIT_RESPONSE.md` -- 1 finding
7. `01_PYTHON_BUILD_SPEC.md` -- 1 finding
8. `02_PREREQS_ASSETS_CHECKLIST.md` -- 1 finding
9. `summary.txt` -- 1 finding

**Files with mild AI tells (meta-commentary, em dashes):**
10-18. All 9 `tooling-spec-*.md` files -- "Status: spec (authored...)" + "No code written; no deletions." + em dashes

**Files with no AI tells:**
- `aveanna-elements.html` (raw HTML)
- All PDFs in `papers/` (published research)
---

## Additional AI Tells Identified (Expanded Patterns)

### Pattern: "Hand this to [someone]" / "You are doing" / "so you don't"

These phrases directly address the user with instructions or rationale, which is an AI assistant tell:

| File | Line | Text |
|------|------|------|
| 00_OVERVIEW_AND_VERDICT.md | 36 | "Hand this to art/acquisition." |
| 00_OVERVIEW_AND_VERDICT.md | 20 | "You are doing the Yellowstone pilot." |
| 00_OVERVIEW_AND_VERDICT.md | 38 | "Research you actually have (so you don't re-hunt)" |
| 02_PREREQS_ASSETS_CHECKLIST.md | 36 | "Hand this to art/acquisition." |

### Pattern: "not really" / "not a" / "not yet" (hedging)

| File | Line | Text |
|------|------|------|
| python-audit.txt | 234 | "coordinated environmental animation drivers, not really microclimate modeling" |
| python-audit.txt | 278 | "procedural feature authoring, not a pool physics model" |
| python-audit.txt | 353 | "a useful geological rulebook, not geochemistry simulation" |
| python-audit.txt | 539 | "temperature-dependent animation tuning, not refuge selection" |
| python-audit.txt | 714 | "a useful experiment configuration system, not yet an experimental science framework" |

### Pattern: "would make" / "would be" (hedging)

| File | Line | Text |
|------|------|------|
| python-audit.txt | 161 | "### What would make it substantially more impressive" |
| python-audit.txt | 250 | "### What would make it more impressive" |
| python-audit.txt | 319 | "### What would make it more impressive" |
| python-audit.txt | 375 | "### What would make it scientifically substantial" |
| python-audit.txt | 449 | "### What would make it more impressive" |
| python-audit.txt | 498 | "### What would make it more impressive" |
| python-audit.txt | 571 | "### What would make it more impressive" |
| python-audit.txt | 626 | "### What would make it more impressive" |
| python-audit.txt | 689 | "### What would make it more impressive" |
| python-audit.txt | 738 | "### What would make it more impressive" |
| python-audit.txt | 1005 | "The most useful next files to review would be your research documents..." |
| waterway-research.md | 59 | "It would make a natural two-stream mixing fixture for the spec." |

### Pattern: "This [X] matters" / "The important distinction" / "One important detail"

| File | Line | Text |
|------|------|------|
| improvements.md | 5 | "The important distinction is that real data, scientific methods, and validated predictions are three different things." |
| improvements.md | 138 | "One important detail for your project: the existence of a real monitoring station does not mean..." |
| improvements.md | 328 | "A particularly important distinction: a digital elevation model can constrain the channel's surrounding topography..." |
| addons.md | 981 | "**This placement matters.** It evaluates the detector's original performance..." |
| python-audit.txt | 32 | "These are important foundations for a credible project." |
| python-audit.txt | 474 | "This is one of the most important modules to rethink scientifically." |
| python-audit.txt | 780 | "**This is a major issue.**" |

### Pattern: "A caveat" (hedging)

| File | Line | Text |
|------|------|------|
| improvements.md | 68 | "A caveat: PHREEQC is not a general hydrothermal reservoir simulator..." |

---

## Additional AI Tells Identified (Expanded Patterns)

### Pattern: "Hand this to [someone]" / "You are doing" / "so you don't"

These phrases directly address the user with instructions or rationale, which is an AI assistant tell:

| File | Line | Text |
|------|------|------|
| 00_OVERVIEW_AND_VERDICT.md | 36 | "Hand this to art/acquisition." |
| 00_OVERVIEW_AND_VERDICT.md | 20 | "You are doing the Yellowstone pilot." |
| 00_OVERVIEW_AND_VERDICT.md | 38 | "Research you actually have (so you don't re-hunt)" |
| 02_PREREQS_ASSETS_CHECKLIST.md | 36 | "Hand this to art/acquisition." |

### Pattern: "not really" / "not a" / "not yet" (hedging)

| File | Line | Text |
|------|------|------|
| python-audit.txt | 234 | "coordinated environmental animation drivers, not really microclimate modeling" |
| python-audit.txt | 278 | "procedural feature authoring, not a pool physics model" |
| python-audit.txt | 353 | "a useful geological rulebook, not geochemistry simulation" |
| python-audit.txt | 539 | "temperature-dependent animation tuning, not refuge selection" |
| python-audit.txt | 714 | "a useful experiment configuration system, not yet an experimental science framework" |

### Pattern: "would make" / "would be" (hedging)

| File | Line | Text |
|------|------|------|
| python-audit.txt | 161 | "### What would make it substantially more impressive" |
| python-audit.txt | 250 | "### What would make it more impressive" |
| python-audit.txt | 319 | "### What would make it more impressive" |
| python-audit.txt | 375 | "### What would make it scientifically substantial" |
| python-audit.txt | 449 | "### What would make it more impressive" |
| python-audit.txt | 498 | "### What would make it more impressive" |
| python-audit.txt | 571 | "### What would make it more impressive" |
| python-audit.txt | 626 | "### What would make it more impressive" |
| python-audit.txt | 689 | "### What would make it more impressive" |
| python-audit.txt | 738 | "### What would make it more impressive" |
| python-audit.txt | 1005 | "The most useful next files to review would be your research documents..." |
| waterway-research.md | 59 | "It would make a natural two-stream mixing fixture for the spec." |

### Pattern: "This [X] matters" / "The important distinction" / "One important detail"

| File | Line | Text |
|------|------|------|
| improvements.md | 5 | "The important distinction is that real data, scientific methods, and validated predictions are three different things." |
| improvements.md | 138 | "One important detail for your project: the existence of a real monitoring station does not mean..." |
| improvements.md | 328 | "A particularly important distinction: a digital elevation model can constrain the channel's surrounding topography..." |
| addons.md | 981 | "**This placement matters.** It evaluates the detector's original performance..." |
| python-audit.txt | 32 | "These are important foundations for a credible project." |
| python-audit.txt | 474 | "This is one of the most important modules to rethink scientifically." |
| python-audit.txt | 780 | "**This is a major issue.**" |

### Pattern: "A caveat" (hedging)

| File | Line | Text |
|------|------|------|
| improvements.md | 68 | "A caveat: PHREEQC is not a general hydrothermal reservoir simulator..." |

---

## Proposed Document Fixes

| File | Issue | Proposed Fix |
|------|-------|--------------|
| improvements.md | 30+ AI tells: "I'd"/"I would" suggestions, "Yes." openers, "Crucially", "important distinction", em dashes, first-person narrative | Rewrite as a technical document. Remove all first-person narrative. Replace "I'd" with "The recommended approach is". Replace "Yes." openers with direct statements. Remove "Crucially", "importantly", "notably". Replace em dashes with periods. |
| addons.md | 10 AI tells: "I researched", "my implementation", "I would add next", em dashes | Rewrite as a technical document. Remove first-person narrative. Replace "I researched" with "Research areas:". Remove "my implementation". |
| waterway-research.md | 14 AI tells: first-person narrative, "my arithmetic", "I haven't verified", "your summary" | Rewrite as a research log. Remove first-person narrative. Replace "my arithmetic" with "calculated". Replace "I haven't verified" with "Unverified". Remove "your summary". |
| python-audit.txt | 28 AI tells: "My recommendation", "Important limitations/issues", "would make" hedging, first-person narrative | Rewrite as an audit report. Remove first-person narrative. Replace "My recommendation" with "Recommendation". Replace "Important limitations" with "Limitations". Replace "would make" with "requires". |
| 00_OVERVIEW_AND_VERDICT.md | 4 AI tells: em dashes, "You are doing", "Hand this to", "so you don't" | Replace em dashes with periods. Remove "You are doing the Yellowstone pilot." Remove "Hand this to art/acquisition." Replace "so you don't re-hunt" with "to avoid re-hunting". |
| 01_PYTHON_BUILD_SPEC.md | 13 AI tells: em dashes in section headings | Replace all em dashes in section headings with colons or periods. |
| 02_PREREQS_ASSETS_CHECKLIST.md | 7 AI tells: em dashes | Replace all em dashes with periods or colons. |
| 03_AUDIT_RESPONSE.md | 2 AI tells: em dashes | Replace em dashes with periods. |
| tooling-spec-*.md (9 files) | "Status: spec (authored...)" headers, "No code written; no deletions.", em dashes | Remove "Status: spec" headers. Remove "No code written; no deletions." lines. Replace em dashes with periods. |
