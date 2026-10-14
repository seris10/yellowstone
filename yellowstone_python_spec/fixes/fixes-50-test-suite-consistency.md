# fixes-50: test suite consistency

Scope: `yellowstone_python/tests/` and `yellowstone_python/yellowstone_python/replay/tests/` as code a public reader will open to judge the science. Audit 2026-10-13 at the request of KJR.
Method: `rg` over both test trees, with the files cited below read in full.

## Items

### 1. Test names and docstrings describe audit bookkeeping
Docstrings such as "fixes-19 item 10: a site with no registry entry is unverified" (`tests/test_fetch_yellowstone_tributaries.py`, 15 docstrings) and "fixes-30 finding 1: ... deleted" (`tests/test_scenario_runners.py`, 9) tell a reader which ticket a test closed, not what the model must do. One file is named for tickets (`tests/test_integration_fixes_40_41.py`).
### Fix
Docstrings state the behavior ("A site with no registry entry is unverified."); rename the file by subject. Covered mechanically by fixes-49 item 5 (`process_tag` over test names and docstrings).
### Test
`process_tag` reports zero in both test trees.
### Cost
Cheap.

### 2. Tests that read source text instead of running code
`tests/test_scenario_runners.py` checks that strings such as `'hot["run_mode"] = "scenario"'`, `"--sub-uilt"` and `"VELOCITY_DEPTH_SWEEP"` appear in tool source (`:35-71`), parses a constant with `ast` (`:74-91`), and asserts that a deleted file stays deleted (`:12-15`). These pass when the code is broken and fail when it is refactored correctly.
### Fix
Replace with behavior tests on a small synthetic replay: run each scenario subcommand (after fixes-47 item 6) and assert `run_mode == "scenario"` in the output, the presence and values of the citation fields, the sweep values, and that no runner appends cells to the solver cell list (check the output replay's cell ids equal the input's). Delete the file-absence test.
### Test
The new tests fail when the scenario run mode is removed from the output, and pass after a rename of internal constants.
### Cost
Cheap to medium.

### 3. Two test styles
14 files use `unittest.TestCase` (most in `replay/tests/`), the rest pytest functions with fixtures.
### Fix
Convert the 14 files to pytest functions (`self.assertEqual(a, b)` to `assert a == b`, `assertAlmostEqual` to `pytest.approx`, `setUp` to fixtures). One commit per file, no assertion changes.
### Test
Same test count and same pass set before and after; `rg -l 'unittest.TestCase' tests yellowstone_python` returns nothing.
### Cost
Cheap.

### 4. Shared module state mutated without restoration
`tests/test_fetch_yellowstone_tributaries.py` calls `FYT.VERIFIED_TRIBUTARY_REGISTRY.clear()` 11 times and fills it in place; a failing assertion between fill and clear leaves the registry populated for later tests. The tool is loaded with `importlib.util.spec_from_file_location` and inserted into `sys.modules` (`:18-29`).
### Fix
A fixture that `monkeypatch.setattr`s the registry to a fresh dict per test. After fixes-47 items 1 and 4 the tool imports normally and the `importlib` block goes.
### Test
Run the file with `-p no:randomly` and with random order (`pytest-randomly`); both pass.
### Cost
Cheap.

### 5. Two ways to import the test path helper, no conftest
13 test files use `from paths import MIDWAY`, 2 use `from tests.paths import REPO`; neither tree has a `conftest.py`. Which form works depends on the working directory.
### Fix
After fixes-47 item 1, a `tests/conftest.py` provides `repo_root`, `world_root` and `world_ready` fixtures (`world_ready` skips with the missing path named); `tests/paths.py` keeps the resolution logic and the two import forms collapse to fixtures.
### Test
The suite passes from the repository root, from `tests/` and from outside the repository with `--rootdir`.
### Cost
Cheap.

### 6. Test location does not follow package layout
`replay/tests/test_thermal_curves.py` tests `yellowstone_python/thermal_curves.py`, which is not in `replay/`. Package-local tests live only under `replay/`; every other package's tests live in `tests/`.
### Fix
One tree: move `replay/tests/` into `tests/river/` (matching the fixes-47 item 3 subpackages, `tests/<subpackage>/`), so `pytest` needs no second path and the AGENTS.md verify command shortens to `pytest`.
### Test
`pytest` with no arguments collects the same number of tests as the two-path command today.
### Cost
Cheap.

### 7. Skipped tests are invisible
Fifteen `skipif` or `importorskip` sites skip when world files, pvlib, fipy or other optional inputs are absent; the last full run reported 15 skipped. A public reader cannot tell which science is untested on their machine.
### Fix
Mark each skip with a registered marker (`needs_world`, `needs_pvlib`, `needs_fipy`, `needs_network_inputs`) in `pyproject.toml`; the README lists the markers and what each requires; CI (when added) runs a declared subset and reports skipped markers.
### Test
`pytest --markers` lists them; `pytest -m "not needs_world"` runs on a checkout without the Godot world.
### Cost
Cheap.

## Order
Items 1 and 4 (small, independent), then 3, 2 after fixes-47 item 6, and 5, 6, 7 after fixes-47 item 1.
