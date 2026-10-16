"""Golden field packet shared with the Godot decoder check."""
import numpy as np

from tests.paths import MIDWAY
from yellowstone_python.park_runtime.field_codec import decode, encode

FIXTURE = MIDWAY / "tests/park_runtime/fixtures/field_pair.bin"
VALUES = np.array([[[10.0, 2.0], [14.0, 4.0]], [[12.0, 3.0], [18.0, 8.0]]], dtype="<f4")


def test_encode_matches_golden_bytes():
    """Encode the fixed values to the stored packet bytes."""
    packet = encode(VALUES, session_id="golden-session", revision=3, t0_s=0.0, t1_s=10.0,
                    entity_ids=["a", "b"], fields=["temperature_c", "flow_m3s"], units=["C", "m3/s"])
    assert packet == FIXTURE.read_bytes()


def test_decode_golden_packet():
    """Decode the stored packet to the fixed values and metadata."""
    header, values = decode(FIXTURE.read_bytes())
    assert header["session_id"] == "golden-session"
    assert header["revision"] == 3
    assert np.array_equal(values, VALUES)
