# Park runtime service termination save

## Scope

The reference park runtime service in `yellowstone_python/park_runtime/__main__.py`.
The runtime, the state store format and the HTTP contract do not change, and
no scientific claim changes state.

## Findings and implementation

- Termination skips the committed save. `main()` saves the committed
  checkpoint in a `finally` block reached only through `KeyboardInterrupt`.
  SIGTERM, the default signal of `kill`, `launchctl` and process supervisors,
  ends the process without running that block, so the service loses all
  progress since its last Ctrl+C stop. The `fixes-63` regression matrix
  records this on the service restart row. Implementation: a SIGTERM handler
  installed before `serve_forever()` raises `KeyboardInterrupt`, so both
  signals reach the same shutdown and save path; SIGTERM is ignored while the
  save runs, so a repeated signal cannot interrupt the store write. The
  startup line names both stop signals.

## Acceptance

1. A service started on an empty state file and stopped with SIGTERM exits
   with status 0, prints the saved checkpoint time and writes a committed
   checkpoint to the state file.
2. A second service on the same state file resumes from that checkpoint, and
   its own SIGTERM save is at or after the first saved time.
3. Ctrl+C behavior is unchanged.

## Verification

- `tests/park_runtime/test_park_service_process.py` runs the module as a
  subprocess for acceptance items 1 and 2.
- `pytest tests/park_runtime`; `check_comment_style.py` and the prose pattern
  checker clean on touched files.

## Sources

- `yellowstone_python/park_runtime/__main__.py`, `runtime.py`
  (`save_committed`, `load_committed`), `state_store.py`.
- `fixes/ledger/fixes-63.md`, service restart row.
