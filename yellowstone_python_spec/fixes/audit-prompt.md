# Read-only AI-tells audit prompt (second pass)

Purpose: Audit edited Python / GDScript / shader files in the repository for comment convention violations per the ai-tells rules in `ai-tells/edits-2.md`. Report per-item verdicts only. Do NOT edit any source file.

Reference docs (must read first):
- `../yellowstone_python/yellowstone_python/yellowstone_python/AGENTS.md` (lines on no AI tells, comment style, no rewrites, American spelling, no dating in filenames, no first-person / no reader-addressing, no X-not-Y contrasts, no temporal references, no "Every" claims, no ALL-CAPS emphasis, one-line comments)
- `ai-tells/edits-2.md` (good vs bad comment examples)
- `ai-tells/ai-tells-1.md`, `ai-tells-2.md` (full conventions)

Work directory: `/Users/kreed/!claude/roots-of-reason/5-original-games/yellowstone/yellowstone_python`
Scope: all `*.py` under `yellowstone_python/` that have been edited in this session; check `tests/` updates; verify no rewrites occurred (use `git diff --stat` to report line-change counts, not full rewrites).

Audit rules (per AGENTS.md / ai-tells):
- Only edit comments (lines starting with # or inside docstrings / triple-quoted docstrings / shader comments)
- No code logic changes
- No first person, no reader-addressing ("you", "your"), no em-dashes (use periods/colons), no "X, not Y" contrasts, no temporal references ("new work", "legacy", etc.), no hypothetical-failure narratives ("never silently"), no date-stamped filenames
- American spelling; one-line inline comments; two-line docstrings max
- Comments state what the thing IS, not what it could fail to be

Deliverable: For every edited Python file, a compact table: `line | original comment | verdict (implemented-correctly / implemented-incorrectly / missing) | note (one line) | cost [cheap/medium/refactor]`. Evidence MUST be real file:line references. No guessing. Report total line-change counts per file (from `git diff --stat`). Confirm surgical edits only (no rewrites). Note any comments that remain non-compliant.

Files edited in this session (confirmed by git status):
- `yellowstone_python/gen_trail_mask.py`
- `yellowstone_python/geochemistry.py`
- `yellowstone_python/grazers.py`
- `yellowstone_python/hydro_thermal.py`
- `yellowstone_python/insects_birds.py`
- `yellowstone_python/llm_backend.py`
- `yellowstone_python/replay/plume2d.py`
- `tests/test_gen_trail_mask.py`
- `tests/test_grazers.py`

Do NOT attempt fixes. Report only. No rewrites under any circumstances. If a fix requires >5 surgical edits for one file, note it as [refactor] rather than attempting it.
