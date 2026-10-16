"""Numeric snapshot codec shared with Godot field_buffer.gd.

Layout is magic YSP1, uint32 header length, UTF-8 JSON header, f32 values [2, entity, field]."""
from __future__ import annotations
import json
import struct
import numpy as np
from .contracts import finite
from .state_store import canonical

MAX_HEADER = 64 * 1024
MAX_PAYLOAD = 16 * 1024 * 1024

def encode(values, *, session_id: str, revision: int, t0_s: float, t1_s: float,
           entity_ids: list[str], fields: list[str], units: list[str]) -> bytes:
    array = np.asarray(values, dtype="<f4", order="C")
    if array.shape != (2, len(entity_ids), len(fields)) or len(fields) != len(units):
        raise ValueError("field dimensions/units disagree")
    if not entity_ids or not fields or len(set(entity_ids)) != len(entity_ids) or len(set(fields)) != len(fields):
        raise ValueError("entity and field identifiers must be nonempty and unique")
    if not np.all(np.isfinite(array)):
        raise ValueError("nonfinite values require a separate explicit validity channel")
    if finite(t1_s, "t1_s") < finite(t0_s, "t0_s"):
        raise ValueError("time bracket reversed")
    if not isinstance(revision, int) or isinstance(revision, bool) or revision < 0:
        raise ValueError("invalid revision")
    metadata = {"schema":"yellowstone.field_pair.v1", "session_id": session_id,
        "revision":revision,"t0_s":t0_s,"t1_s":t1_s,"entity_ids":entity_ids,
        "fields":fields,"units":units,"shape":list(array.shape),"dtype":"<f4"}
    header = canonical(metadata)
    if len(header)>MAX_HEADER or array.nbytes>MAX_PAYLOAD:
        raise ValueError("packet exceeds configured limits")
    return b"YSP1"+struct.pack("<I",len(header))+header+array.tobytes()

def decode(payload: bytes):
    if len(payload)<8 or payload[:4]!=b"YSP1":
        raise ValueError("invalid field packet magic")
    size, = struct.unpack_from("<I",payload,4)
    if size>MAX_HEADER or len(payload)<8+size or len(payload)-8-size>MAX_PAYLOAD:
        raise ValueError("invalid packet length")
    header=json.loads(payload[8:8+size])
    if header.get("schema")!="yellowstone.field_pair.v1" or header.get("dtype")!="<f4":
        raise ValueError("unsupported field packet")
    entities, fields = header["entity_ids"], header["fields"]
    shape=(2,len(entities),len(fields))
    if header["shape"]!=list(shape) or len(header["units"])!=len(fields):
        raise ValueError("invalid shape/units")
    if len(payload)-8-size!=np.prod(shape)*4:
        raise ValueError("numeric byte count differs")
    values=np.frombuffer(payload, dtype="<f4",offset=8+size).reshape(shape)
    if not entities or not fields or len(set(entities)) != len(entities) or len(set(fields)) != len(fields):
        raise ValueError("nonempty unique entity/field IDs required")
    if not isinstance(header.get("session_id"), str):
        raise ValueError("session identifier required")
    revision = header.get("revision")
    if isinstance(revision, bool) or not isinstance(revision, int) or revision < 0:
        raise ValueError("invalid revision")
    if finite(header["t1_s"], "t1_s") < finite(header["t0_s"], "t0_s"):
        raise ValueError("reversed time bracket")
    if not np.all(np.isfinite(values)):
        raise ValueError("nonfinite numeric field")
    return header, values
