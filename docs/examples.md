# Small Yellowstone examples

These scripts use the Yellowstone Python environment and synthetic inputs. They do not download observations or start Godot. From `yellowstone_python/`:

```sh
.venv/bin/python examples/portfolio/river_checks.py --out ../work/river-example
.venv/bin/python examples/portfolio/analysis_store.py --out ../work/query-example
.venv/bin/python examples/portfolio/evidence_checks.py --out ../work/source-example
```

Use a new or empty directory for each output. Matplotlib is needed for the river plot.

The river example writes numerical errors, conservation checks and a refinement plot. Momentum-only cases are marked inapplicable because this solver prescribes flow. The data example builds a small SQLite store and compares four queries with independently calculated JSON results. The source example changes its own temporary files and shows when a saved result becomes stale.

## Record a run

```sh
.venv/bin/python -m tools.run_evidence --name river-example --scope python --strict -- .venv/bin/python examples/portfolio/river_checks.py --out ../work/recorded-river
```

A record contains the command result and hashes of the selected sources and inputs. Available scopes are `python`, `godot`, `dashboard` and `combined`. Generated website files and dependency directories are excluded; add an individual generated input with `--fixture PATH` when it matters to the run.

With `--strict`, a successful command returns status 2 if its source files change while it runs. Earlier records retain their original file lists. Matching hashes show that the inputs have not changed; they do not prove that a calculation is correct.
