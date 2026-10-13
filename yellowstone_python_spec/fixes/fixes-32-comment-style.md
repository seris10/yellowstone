# fixes-32: comment style across Python, GDScript and shaders

Scope: every `*.py`, `*.gd` and `*.gdshader` under `yellowstone_python/`, `yellowstone_midway/scripts`, `yellowstone_midway/shaders`, `yellowstone_midway/tools`, `yellowstone_atmosphere/` and `hydrology/` (186 files at sweep time).
Instrument: `yellowstone_python/tools/check_comment_style.py` (sha256 6c8ea7f4c7c4), tests in `yellowstone_python/tests/test_check_comment_style.py` (7 passing). It reads comments and docstrings only, never string literals, and reports against `yellowstone_python/AGENTS.md` section 2.

The rules in AGENTS.md section 2 were applied by hand in earlier passes, and the earlier audit prompt (`fixes/audit-prompt.md`) covered nine files. A sweep of the whole tree found 720 findings in 186 files. The counts below are a snapshot taken while other fixes were landing; rerun the tool for the current list.

```bash
cd yellowstone_python
fd -e py -e gd -e gdshader . yellowstone_python tools tests ../yellowstone_midway/scripts \
  ../yellowstone_midway/shaders ../yellowstone_midway/tools ../yellowstone_atmosphere ../hydrology > /tmp/style-files.txt
python3 tools/check_comment_style.py --list /tmp/style-files.txt --root .. --summary --report-only
python3 tools/check_comment_style.py --list /tmp/style-files.txt --root ..        # one line per finding
```

## Main problems

### 1. AI-tell phrasing survives in comments and docstrings

Snapshot counts: X-not-Y contrasts 103, ALL-CAPS emphasis 72, em or en dashes 37, British spellings 21, temporal references 17, "Every" claims 15, hypothetical-failure narratives 10, first person 6, reader address 1. Examples with file:line: `yellowstone_midway/scripts/python_river_replay.gd:6` "Replay interpolation is presentation, not a second solver."; `yellowstone_python/tests/test_microclimate.py:235` "We test the helper behavior..."; `yellowstone_python/tests/test_llm_backend.py:130` "must not silently disable..."; `yellowstone_atmosphere/scripts/weather_http_consumer.gd:19` "Legacy flat format".
### Fix
Comment-only edits, one finding at a time, stating what the thing is (AGENTS.md section 2 examples). No code changes in the same edit. A finding that is a true positive for a different reason (an acronym the allowlist lacks, a quoted source title) is resolved by adding the acronym to `ACRONYMS` in the tool or leaving the quote with a short source citation, never by rewording a quotation.
### Test
The tool exits 0 on the edited file for the rules above.

### 2. Docstrings and comment blocks exceed the length rule

Snapshot counts: 193 docstrings longer than two lines, 245 full-line comment blocks of two or more lines. Many carry real content: equations, sign conventions, source citations, units.
### Fix
Keep the content, move it to where the project keeps it: governing equations and sign conventions to the `equations.py` registry entry for the component (its docstring then names the registry id); parameter sources to `param_registry.py`; long rationale to the matching spec document under `yellowstone_python_spec/`. Then shorten the docstring to one or two lines. Do this file by file, owner by owner, after that file's other fixes have landed, so comment edits never collide with logic edits. Godot `##` doc comments follow the same rule.
### Test
The tool reports no `docstring_length` or `comment_block` finding for the file, and the moved content is findable by the registry id named in the docstring.

### 3. The rules are not enforced anywhere

Nothing in the verify commands runs a comment check, so the rules regress with each pass.
### Fix
Add the tool to `AGENTS.md` section 7 as a verification step and to `ystone` orientation, scoped to files changed in the session (`git diff --name-only | rg '\.(py|gd|gdshader)$'`), failing on any finding in a changed file.
### Test
A deliberately planted first-person comment in a scratch copy fails the documented command; removing it passes.

# Wiring and rendering

Not applicable.

# Comment-style violations

The tool's line output is the authoritative list; this document does not duplicate it.

# Priority order

1. Item 3 (enforce on changed files): cheap. Stops regression while items 1 and 2 land.
2. Item 1: cheap per finding, about 280 findings.
3. Item 2: medium to refactor; schedule per file after its logic fixes.
