# Park runtime service termination save ledger

Specification: `fixes/fixes-68-park-runtime-service-termination-save.md`.

Baseline ledger written at document creation with every row `missing`;
rows updated with the implementation and its evidence.

| Item | Verdict | Implementation and evidence |
|---|---|---|
| Termination skips the committed save | implemented | Baseline: `park_runtime/__main__.py` saves only after `KeyboardInterrupt`; SIGTERM exits without the save. `_interrupt()` raises `KeyboardInterrupt` from a SIGTERM handler installed before `serve_forever()`; the `finally` block ignores SIGTERM during the save. `tests/park_runtime/test_park_service_process.py`: `test_sigterm_saves_and_restart_resumes` (exit 0, saved checkpoint at or after 1 s, state file written, second run resumes and saves at or after the first time) and `test_sigint_save_is_unchanged`. Against the baseline module the SIGTERM test fails with exit status -15 and no save. `pytest tests/park_runtime` 124 passed. |
