"""Atomic checksummed checkpoints and append-only intervention records.

Saves hold one JSON checkpoint per world; to_portable() objects encode themselves."""
from __future__ import annotations
from collections.abc import Sequence
from contextlib import contextmanager
from pathlib import Path
import hashlib
import json
import sqlite3
import threading
import zlib
from .contracts import identifier, finite

MAX_RAW_BYTES = 64 * 1024 * 1024

def canonical(value) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()

def _portable(value):
    to_portable = getattr(value, "to_portable", None)
    if not callable(to_portable):
        raise TypeError(f"{type(value).__name__} has no portable encoding")
    return to_portable()

def canonical_checkpoint(value) -> bytes:
    """Encode a checkpoint, expanding objects that provide to_portable()."""
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False, default=_portable).encode()

class StateStore:
    def __init__(self, path: str | Path):
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self.db = sqlite3.connect(path, check_same_thread=False, isolation_level=None)
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("PRAGMA synchronous=FULL")
        self.db.executescript("""
          CREATE TABLE IF NOT EXISTS checkpoints(
            world_id TEXT PRIMARY KEY, model_id TEXT NOT NULL, time_s REAL NOT NULL,
            revision INTEGER NOT NULL, raw_bytes INTEGER NOT NULL,
            sha256 TEXT NOT NULL, payload BLOB NOT NULL);
          CREATE TABLE IF NOT EXISTS events(
            world_id TEXT NOT NULL, event_id TEXT NOT NULL, time_s REAL NOT NULL,
            revision INTEGER NOT NULL, payload TEXT NOT NULL,
            PRIMARY KEY(world_id,event_id));
        """)

    @contextmanager
    def transaction(self):
        with self._lock:
            self.db.execute("BEGIN IMMEDIATE")
            try:
                yield
                self.db.execute("COMMIT")
            except BaseException:
                self.db.execute("ROLLBACK")
                raise

    def save(self, world_id: str, model_id: str, time_s: float, revision: int,
             checkpoint: dict, events: Sequence[dict] = ()) -> None:
        identifier(world_id)
        identifier(model_id)
        finite(time_s, "time_s")
        raw = canonical_checkpoint(checkpoint)
        if len(raw) > MAX_RAW_BYTES:
            raise ValueError("checkpoint exceeds 64 MiB; split the model into bounded regions")
        row = (world_id, model_id, time_s, revision, len(raw),
               hashlib.sha256(raw).hexdigest(), zlib.compress(raw, 3))
        with self.transaction():
            self.db.execute("INSERT OR REPLACE INTO checkpoints VALUES (?,?,?,?,?,?,?)", row)
            for event in events:
                encoded = canonical(event).decode()
                previous = self.db.execute("SELECT payload FROM events WHERE world_id=? AND event_id=?",
                                           (world_id, event["event_id"])).fetchone()
                if previous and previous[0] != encoded:
                    raise ValueError("event id reused with different contents")
                self.db.execute("INSERT OR IGNORE INTO events VALUES (?,?,?,?,?)",
                                (world_id, event["event_id"], event["at_s"], event["revision"], encoded))

    def load(self, world_id: str, model_id: str) -> dict | None:
        with self._lock:
            row = self.db.execute("SELECT model_id,time_s,revision,raw_bytes,sha256,payload "
                                  "FROM checkpoints WHERE world_id=?", (world_id,)).fetchone()
        if row is None:
            return None
        model, time_s, revision, size, digest, data = row
        if model != model_id:
            raise ValueError("model version mismatch: explicit save migration required")
        if not 0 <= size <= MAX_RAW_BYTES:
            raise ValueError("invalid checkpoint size")
        decoder = zlib.decompressobj()
        raw = decoder.decompress(data, size + 1)
        if len(raw) != size or not decoder.eof or decoder.unused_data:
            raise ValueError("invalid or oversized compressed checkpoint")
        if hashlib.sha256(raw).hexdigest() != digest:
            raise ValueError("checkpoint checksum mismatch")
        return {"time_s": time_s, "revision": revision, "checkpoint": json.loads(raw)}

    def events(self, world_id: str) -> list[dict]:
        with self._lock:
            rows = self.db.execute("SELECT payload FROM events WHERE world_id=? ORDER BY revision,event_id",
                                   (world_id,)).fetchall()
        return [json.loads(row[0]) for row in rows]

    def close(self):
        with self._lock:
            self.db.close()
