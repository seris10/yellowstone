# fixes-49: comment and docstring house style beyond the current checker

Scope: comments, docstrings, test names, emitted provenance strings and Markdown across `yellowstone_python/` (package, `tools/`, `tests/`). `tools/check_comment_style.py` reports 0 findings over the 208 Python files, because it checks the rules it was written for (dashes, first person, reader address, X-not-Y, a temporal word list, "Every", capitals, British spelling, docstring length for module-level docstrings, comment blocks). The inconsistency and the remaining AI tells sit outside those rules. Audit 2026-10-13 at the request of KJR; complements fixes-32.
Method: `ai-tells/` catalog and `AGENTS.md` section 2 read; the checker read in full; module docstrings of every package module and tool read; `rg` sweeps with each hit opened. Counts are for comments and docstrings unless marked as strings.

## Findings

### 1. Process references a public reader cannot decode
- `fixes-N`, `item N`, `finding N`, `section N` of a fixes doc: 46 occurrences in 12 files. Concentrated in test docstrings (`tests/test_fetch_yellowstone_tributaries.py` cites `fixes-19 item N` in 15 docstrings and its module docstring; `tests/test_scenario_runners.py` cites `fixes-30 finding N` in 9), `tools/calibrate_river_transport.py` (module docstring "fixes-15 stages A..D" and every stage docstring), `exporters/godot_sidecars.py:434` and `:742`, `publish.py:37`, `tests/test_outflow_forcing.py:1`, `tests/test_gen_flora_sampling.py:1`, and the test file name `tests/test_integration_fixes_40_41.py`.
- The same references inside strings that reach JSON or the console: `replay/calibrate.py:522`, `:533`, `:964`, `:1327`; `publish.py:92` (an error message); `tools/calibrate_river_transport.py:328`.
- Milestone tags `M00` to `M12`: 15 module docstrings open with one (`common/provenance.py:1` "M00 provenance: ... (SHARED_WORLD_CONTRACT 8.1)", `common/units.py:1`, `publish.py:1`, `validation/checks.py:1`, `exporters/to_ecosystem.py:1`, `pool_crust.py:1`, `geochemistry.py:1` and others), 7 section banners in `build.py` (`# --- M03 shells ---`), and three emitted strings: `vegetation.py:482` (`"author_note": f"M04 reviewed proposal; ..."`), `grazers.py:22` (`"status": "partial_via_M08"`), `equations.py:12` (`"component": "M01 six-reach mixing chain"`, asserted by `tests/test_equations.py`).
- Other labels: `B1` (`replay/obs_frame.py:1`), `Phase 1b`, `Phase 2` (`publish.py:44`, `:49`), `item-9 swallow` (`outflow_foodweb.py:198`), `audit Phase 2 core` (`replay/README.md:3`), `WP-C2` in provenance strings (`aquatic_foodweb.py:356`, `:358`).

### 2. Session narration inside citations
Provenance and source strings describe the session that wrote them: "existence verified via WebSearch", "not retrieved in-session", "original paper not opened in-session" (`aquatic_foodweb.py:36-143`, 10 lines; `fish.py`, 6; `param_registry.py`, 4; `build.py`, 1). These strings are published in sidecars. What a reader needs is the citation and what the value is: taken from the paper, or authored within a cited range.

### 3. Comments that narrate history
`fish.py:258` and `:270` ("kept for ecosystem.gd parity"), `vegetation.py:294` ("retained for backward call-site compatibility"), `replay/hydraulics.py:111` ("kept for bias reporting"), `replay/river_transport.py:194` and `:664` ("replaces Newton exchange"), `aquatic_foodweb.py:765` ("retained for the final output"), and in strings: `outflow_thermal.py:819` (an exception message: "verify_flow_fraction now takes the whole network dict"), `build.py:1590` ("vcfg.grazers no longer feeds patch_step"), `replay/river_world.py:100-101` ("cannot be scheduled yet"), `replay/river_transport.py:1578` ("No world-coordinate mapping or Godot playback yet", which is also false: `river_world.py` maps it and Godot plays it).

### 4. Inconsistent shapes and voice
- Module docstrings come in four shapes: one line without a tag (most modules); one line with a milestone tag; two lines (declarative plus scope note); and one line over 100 characters (`analysis_store.py:1`, `piscivores.py:1`, `steam_microclimate.py:1`).
- Function docstrings are mostly imperative ("Return", "Build", "Load"), with noun-phrase openings mixed into the same files (`insects_birds.py:14`). The checker enforces the two-line limit on module docstrings only in practice; 41 function and class docstrings exceed two lines (`outflow_thermal.py:75`, `build.py:768`, `replay/river_transport.py:947` and `:1478`, `microbial_mats.py:340`, `outflow_network.py:494`, `replay/surface_flux.py:171`, `replay/obs_frame.py:62`, `replay/calibrate.py:73`, `hydro_thermal.py:115`, `replay/obs_model.py:105`), and 31 single-line docstrings run past 100 characters, often as three to five clauses joined by semicolons (`fish.py:371` is 270 characters).
- Section banners: `# --- Label ---` (most), `# ---- Label ----` (`analysis_store.py:538`, `llm_backend.py:871`), and bare `# Section 1: ...` (`replay/calibrate.py:192`, `:315`, `:1027`).
- Citations: `Author YYYY` in most of the package (about 217), `Author (YYYY)` throughout `replay/` and in `river_oxygen.py`, `river_shading.py`, `periphyton.py`, `ssurgo_loader.py`, `outflow_network.py`, `evapotranspiration.py` (about 29), DOIs written as `doi:...`, `DOI:` or a bare `10.xxxx/...` (52 lines).
- Units in emitted unit strings: `m3/s` in code and comments, but `"m^3 s^-1"` and `"m^3"` in `exporters/godot_sidecars.py:347`, `:731-733`.
- Non-ASCII in docstrings and printed text: a degree sign and U+2265 (`fish.py:258`), U+0394 delta (`replay/calibrate.py:1264`), a U+2192 arrow (`publish.py:272`), and an em dash in an argparse help string (`replay/calibrate.py:1218`).

### 5. Vocabulary the catalog flags
"fail loudly" (`common/units.py:1`, `build.py:31`, test docstrings in `tests/test_groundwater_provider.py`, `tests/test_overland_provider.py`, the test name `test_rtree_absent_fails_loudly`), "single source of truth" (`census_validate.py:91`, `outflow_foodweb.py:198`), "comprehensive" (`tools/fetch_yellowstone_tributaries.py:17`, `:1248`), "authoritative" in emitted strings (`build.py:2282`, `:2346`), "(e.g. ...)" asides (`ground_heat.py:55`, `replay/obs_frame.py:193`), "This is not ..." (`replay/river_transport.py:1481`). Domain uses that stay: "guard" as a code concept, "explicit" for the explicit surface budget, "by construction" for a stated mathematical property (`replay/identifiability.py:56`), "leverage" in its statistical sense.

## Items

### 1. House style (add to `AGENTS.md` section 2)
- Module docstring: one line, a noun phrase naming what the module models or does; an optional second line for scope or status. No tags, no milestone codes, no contract section numbers.
- Function and class docstring: one imperative line under 100 characters; an optional second line for one return contract, unit convention or raise condition. Longer content (equations, sign conventions, sources) goes to the `equations.py` component or `param_registry` entry, which the docstring names (fixes-32 item 2).
- Inline comment: one line, present tense, what the code does.
- Banner: `# --- Label ---` only.
- Citation: `Author (YYYY)`, `First and Second (YYYY)`, `First et al. (YYYY)`, then `, doi:10.xxxx/...` when a DOI exists.
- Units: ASCII `m3/s`, `m2`, `W/m2`, `W/m2/K`, `mg/L`, `C`, in comments and in emitted unit strings.
- ASCII only in comments, docstrings, help text and console output; physics symbols spelled out (`delta`, `deg C`, `>=`).
- Provenance strings state the source and the value class (`measured`, `literature`, `authored_within_cited_range`, `fitted`), never how a session found it.
### Test
`AGENTS.md` section 2 lists each rule with one good and one bad example from this codebase.
### Cost
Cheap.

### 2. Remove process references
Rewrite each finding in section 1 as the statement the reference pointed at (`"""Stage C: fit lateral discharge and temperature with the surface budget at identity defaults."""` in place of "Stage C per fixes-15 section 4C"). Rename `tests/test_integration_fixes_40_41.py` by subject (`test_stressor_integration.py`). Test docstrings say what behavior they check. Emitted strings drop the reference; `equations.py` component names become descriptive (`"six-reach mixing chain"`), updating `tests/test_equations.py`. Before renaming a status value such as `partial_via_M08`, search `yellowstone_midway/scripts` and `tools/audit_provenance.py` for consumers that match it and change them in the same commit.
### Test
Checker rule `process_tag` (item 5) reports zero.
### Cost
Cheap (about 75 lines).

### 3. Rewrite session narration in citations
For each source string in `aquatic_foodweb.INVERT_TAXA`, `fish.THERMAL_SPECIES` and `param_registry`: citation in the house format, then the value class. Example: `"Davis (1975), J. Fish. Res. Board Can. 32:2295-2312; DO ramp anchors authored within the range reported for aquatic insects"`. Where a value was not read from the source, the class says so (`authored_within_cited_range`); the verb "verified via WebSearch" goes.
### Test
`rg -n -i 'in-session|websearch' yellowstone_python` returns nothing; `audit_provenance` still passes.
### Cost
Cheap.

### 4. Fix history narration and stale statements
Rewrite the section 3 findings as present-tense statements; delete the false "Godot playback yet" limitation; change the `river_world.py:100-101` message once fixes-43 item 1 makes source flows schedulable; the `outflow_thermal.py:819` message states the expected argument shape only.
### Test
Checker rule `history` (item 5) reports zero.
### Cost
Cheap.

### 5. Extend the checker
Add rules to `tools/check_comment_style.py`, each with tests in `tests/test_check_comment_style.py` using a true positive from this audit and a known false positive:
- `process_tag`: `\bfixes-\d|\b(item|finding) \d+\b|\bM(0\d|1[0-2])\b|SHARED_WORLD_CONTRACT|\b[Pp]hase \d|\bWP-[A-Z]\d|\bB[1-4]\b`. Scope: comments, docstrings, test function names, and string literals that are dict values for keys `status`, `note`, `reason`, `source`, `sources`, `basis`, `author_note`, `component`, or argparse `help=`, or exception messages.
- `history`: `\b(kept for|retained for|replaces|no longer|now (takes|returns|carries|accepts|reports)|\byet\b|at their own pace)\b`, same scope; `now(` excluded.
- `session_narration`: `in-session|in session|WebSearch|verified via`, same scope.
- `docstring_shape`: function and class docstrings over two non-blank lines; any docstring line over 100 characters; three or more semicolon-separated clauses in one docstring line.
- `vocabulary`: `fail(s|ed)? loudly|single source of truth|comprehensive|honestly|stated plainly|\(not hidden\)|This (is not|module|function)`, warn-level, owner reviews.
- `non_ascii`: any non-ASCII character in comments, docstrings, help strings and print strings.
- `citation_format`: `\b[A-Z][a-z]+ (et al\.? )?(19|20)\d\d\b` not followed by `)` and not inside parentheses, warn-level.
Expected first run: about 280 findings, about 230 unique lines.
### Test
Each rule's tests pass; the full-tree run after items 2 to 4 reports zero for the hard rules.
### Cost
Medium.

### 6. Check Markdown and notebooks
The checker skips `.md` and `.ipynb`. README voice problems (fixes-48 item 5) are not caught.
### Fix
Add `.md` (prose outside code fences) and notebook markdown cells to the checker with the dash, `non_ascii` (arrows), `vocabulary`, `process_tag` and a dated-prose rule (`\b(verified|checked|frozen|refetched)( live)? 20\d\d-\d\d-\d\d\b`).
### Test
Planted findings in a scratch README fail; the three project READMEs pass after fixes-48 item 5.
### Cost
Cheap.

### 7. Run the checker on the whole tree in the verify step
`AGENTS.md` section 7 runs the checker only on files changed since `HEAD`; style drifts in files nobody touches.
### Fix
Add the whole-tree run (`--list` over all `.py`, `.gd`, `.gdshader`, `.md`, `.ipynb` in scope) as a test in the suite, so `pytest` fails on any hard-rule finding.
### Test
The suite fails when a planted finding is added to any file.
### Cost
Cheap.

## Order
Item 1, then 5 and 7 (so regressions stop), then 2, 3, 4 (the cleanup the checker now lists), then 6 with fixes-48 item 5. Comment edits never ride in the same commit as logic edits (fixes-32 item 2).
