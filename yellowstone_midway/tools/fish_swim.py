"""Author illustrative traveling-wave trout spine animations in a GLB."""
from __future__ import annotations
import argparse
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import struct
from typing import Iterable
import numpy as np
GLB_MAGIC = 1179937895
JSON_CHUNK = 1313821514
BIN_CHUNK = 5130562
FLOAT = 5126
UNSIGNED_BYTE = 5121
ARRAY_BUFFER = 34962

@dataclass(frozen=True)
class SwimPreset:
    name: str
    frequency_hz: float
    tail_amplitude_bl: float
    wavelength_bl: float
PRESETS = (SwimPreset('Hold_1Hz', 1.0, 0.025, 1.15), SwimPreset('Cruise_2Hz', 2.0, 0.055, 1.1), SwimPreset('Burst_3Hz', 3.0, 0.075, 1.05))

@dataclass
class Rig:
    joint_z: np.ndarray
    bind_xyz: np.ndarray
    joints: np.ndarray
    weights: np.ndarray
    length: float
    head_z: float
    tail_z: float
    onset: float
    exponent: float

def read_glb(path: Path) -> tuple[dict, bytes]:
    raw = path.read_bytes()
    if len(raw) < 20:
        raise ValueError('Too short to be a GLB file')
    magic, version, declared_length = struct.unpack_from('<III', raw, 0)
    if magic != GLB_MAGIC or version != 2 or declared_length != len(raw):
        raise ValueError('Expected valid glTF 2.0 GLB container')
    chunks = []
    offset = 12
    while offset + 8 <= len(raw):
        length, kind = struct.unpack_from('<II', raw, offset)
        offset += 8
        if offset + length > len(raw):
            raise ValueError('Truncated GLB chunk')
        chunks.append((kind, raw[offset:offset + length]))
        offset += length
    if offset != len(raw) or len(chunks) != 2 or chunks[0][0] != JSON_CHUNK or (chunks[1][0] != BIN_CHUNK):
        raise ValueError('Currently supports GLBs containing one JSON and one BIN chunk')
    return (json.loads(chunks[0][1].decode('utf-8').rstrip(' \x00')), chunks[1][1])

def accessor_array(doc: dict, blob: bytes, accessor_id: int) -> np.ndarray:
    """Read a standard, non-sparse glTF accessor from a single BIN buffer."""
    a = doc['accessors'][accessor_id]
    if 'sparse' in a:
        raise ValueError('Sparse accessors are not supported for rig generation')
    view = doc['bufferViews'][a['bufferView']]
    if view.get('buffer', 0) != 0:
        raise ValueError('Only the primary GLB binary buffer is supported')
    types = {5120: 'i1', 5121: 'u1', 5122: '<i2', 5123: '<u2', 5125: '<u4', 5126: '<f4'}
    ncomps = {'SCALAR': 1, 'VEC2': 2, 'VEC3': 3, 'VEC4': 4, 'MAT4': 16}
    dtype = np.dtype(types[a['componentType']])
    count = a['count']
    cols = ncomps[a['type']]
    stride = view.get('byteStride', cols * dtype.itemsize)
    start = view.get('byteOffset', 0) + a.get('byteOffset', 0)
    result = np.ndarray((count, cols), dtype=dtype, buffer=blob, offset=start, strides=(stride, dtype.itemsize))
    return np.array(result)

def make_rig(vertices: np.ndarray, num_joints: int=15, onset: float=0.23, exponent: float=2.0) -> Rig:
    """Rig for the uploaded mesh: nose at +Z, tail at -Z, dorsal axis +Y."""
    if not 6 <= num_joints <= 200:
        raise ValueError('num_joints must be between 6 and 200')
    if not 0 <= onset < 0.6:
        raise ValueError('onset should lie in [0, .6) body lengths from the snout')
    if not 1.0 <= exponent <= 4.0:
        raise ValueError('envelope exponent must be between 1 and 4')
    lo, hi = (np.min(vertices, axis=0), np.max(vertices, axis=0))
    ext = hi - lo
    if ext[2] < 2.0 * max(ext[0], ext[1]):
        raise ValueError('Source mesh must have its long axis along Z; reorient it first')
    length = float(ext[2])
    head_z, tail_z = (float(hi[2]), float(lo[2]))
    z0 = head_z - 0.18 * length
    z1 = tail_z + 0.025 * length
    joint_z = np.linspace(z0, z1, num_joints, dtype=np.float64)
    x_c = float(np.median(vertices[:, 0]))
    y_c = float(np.median(vertices[np.abs(vertices[:, 2] - 0.3 * length) < 0.02 * length, 1])) if np.any(np.abs(vertices[:, 2] - 0.3 * length) < 0.02 * length) else 0.0
    y_c = float(np.clip(y_c, -0.05 * length, 0.05 * length))
    bind_xyz = np.column_stack((np.full(num_joints, x_c), np.full(num_joints, y_c), joint_z))
    z = vertices[:, 2].astype('float64')
    j0 = np.searchsorted(-joint_z, -z, side='right') - 1
    j0 = np.clip(j0, 0, num_joints - 2)
    j1 = j0 + 1
    a = np.clip((joint_z[j0] - z) / (joint_z[j0] - joint_z[j1]), 0, 1)
    blend = a * a * (3 - 2 * a)
    joints = np.zeros((len(z), 4), dtype=np.uint8)
    weights = np.zeros((len(z), 4), dtype=np.float32)
    joints[:, 0] = j0
    joints[:, 1] = j1
    weights[:, 0] = (1 - blend).astype(np.float32)
    weights[:, 1] = blend.astype(np.float32)
    if not np.allclose(weights.sum(axis=1), 1.0, atol=2e-07):
        raise ValueError('Skin weights must sum to one')
    return Rig(joint_z, bind_xyz, joints, weights, length, head_z, tail_z, onset, exponent)

def centerline_x(s: np.ndarray, t: float, rig: Rig, preset: SwimPreset, amplitude_multiplier: float=1.0) -> np.ndarray:
    """Subcarangiform-style traveling wave: x(s,t)=A(s)sin(2pi(ft-s/lambda))."""
    u = np.clip((np.asarray(s) - rig.onset) / (1 - rig.onset), 0.0, None)
    a = amplitude_multiplier * preset.tail_amplitude_bl * rig.length * u ** rig.exponent
    return a * np.sin(2 * np.pi * (preset.frequency_hz * t - np.asarray(s) / preset.wavelength_bl))

def global_spine_angles(t: float, rig: Rig, preset: SwimPreset, amplitude_multiplier: float=1.0) -> np.ndarray:
    """Bone headings derived from centerline chord tangents."""
    s = (rig.head_z - rig.joint_z) / rig.length
    x = centerline_x(s, t, rig, preset, amplitude_multiplier)
    dz = rig.joint_z[:-1] - rig.joint_z[1:]
    dx = x[1:] - x[:-1]
    theta = -np.arctan2(dx, dz)
    eps = 0.0001
    deriv = (centerline_x(s[-1] + eps, t, rig, preset, amplitude_multiplier) - centerline_x(s[-1] - eps, t, rig, preset, amplitude_multiplier)) / (2 * eps * rig.length)
    return np.r_[theta, -np.arctan(deriv)]

def local_spine_angles(t: float, rig: Rig, preset: SwimPreset, amplitude_multiplier: float=1.0) -> np.ndarray:
    heading = global_spine_angles(t, rig, preset, amplitude_multiplier)
    return np.r_[heading[0], np.diff(heading)]

def quaternions_y(angles: np.ndarray) -> np.ndarray:
    """glTF quaternion order is [x, y, z, w]."""
    q = np.zeros((len(angles), 4), dtype=np.float32)
    q[:, 1] = np.sin(angles / 2)
    q[:, 3] = np.cos(angles / 2)
    return q

def joint_world_matrices(rig: Rig, local_angles: np.ndarray) -> np.ndarray:
    """Rest-to-posed node matrices, for software preview and test validation."""
    n = len(rig.joint_z)
    out = np.empty((n, 4, 4), dtype=np.float64)
    for i, angle in enumerate(local_angles):
        co, si = (np.cos(angle), np.sin(angle))
        rot = np.eye(4)
        rot[0, 0] = co
        rot[0, 2] = si
        rot[2, 0] = -si
        rot[2, 2] = co
        local = np.eye(4)
        local[:3, 3] = rig.bind_xyz[i] if i == 0 else rig.bind_xyz[i] - rig.bind_xyz[i - 1]
        local = local @ rot
        out[i] = local if i == 0 else out[i - 1] @ local
    return out

def skin_vertices(vertices: np.ndarray, rig: Rig, t: float, preset: SwimPreset, amplitude_multiplier: float=1.0) -> np.ndarray:
    """CPU reference implementation of the glTF linear-blend skinning math."""
    joint_world = joint_world_matrices(rig, local_spine_angles(t, rig, preset, amplitude_multiplier))
    result = np.zeros_like(vertices, dtype=np.float64)
    for slot in (0, 1):
        idx = rig.joints[:, slot].astype('int64')
        rotated = np.einsum('nij,nj->ni', joint_world[idx, :3, :3], vertices - rig.bind_xyz[idx], optimize=True)
        result += (rotated + joint_world[idx, :3, 3]) * rig.weights[:, slot, None]
    return result.astype(np.float32)

class Appender:

    def __init__(self, doc: dict, buffer_data: bytes):
        self.doc = doc
        self.blob = bytearray(buffer_data)

    def add(self, arr: np.ndarray, gltf_type: str, component_type: int, *, target: int | None=None, normalized: bool=False, with_minmax: bool=False) -> int:
        arr = np.ascontiguousarray(arr)
        if component_type == 5126 and arr.dtype != np.float32:
            arr = arr.astype('<f4')
        if component_type == 5121 and arr.dtype != np.uint8:
            arr = arr.astype('u1')
        while len(self.blob) % 4:
            self.blob.append(0)
        offset = len(self.blob)
        binary = arr.tobytes()
        self.blob.extend(binary)
        view = {'buffer': 0, 'byteOffset': offset, 'byteLength': len(binary)}
        if target is not None:
            view['target'] = target
        vi = len(self.doc['bufferViews'])
        self.doc['bufferViews'].append(view)
        ac = {'bufferView': vi, 'componentType': component_type, 'count': len(arr), 'type': gltf_type}
        if normalized:
            ac['normalized'] = True
        if with_minmax:
            ac['min'] = [float(np.min(arr))]
            ac['max'] = [float(np.max(arr))]
        ai = len(self.doc['accessors'])
        self.doc['accessors'].append(ac)
        return ai

def build_animated_glb(doc: dict, original_bin: bytes, rig: Rig, *, fps: int=30, duration: float=2.0, amp_multiplier: float=1.0, target_length_m: float | None=None, source_hash: str | None=None) -> tuple[dict, bytes]:
    if doc.get('skins') or doc.get('animations'):
        raise ValueError('Input already contains rig or animations; use the original unrigged mesh')
    if len(doc.get('meshes', [])) != 1 or len(doc['meshes'][0]['primitives']) != 1:
        raise ValueError('This implementation expects one mesh with one primitive')
    if doc['nodes'][0].get('mesh') != 0:
        raise ValueError('Expected the original mesh in node 0')
    if not (fps >= 12 and fps <= 120 and (duration >= 0.5) and (duration <= 15)):
        raise ValueError('fps/duration out of supported range')
    if not np.isclose(duration, round(duration), atol=1e-07):
        raise ValueError('Duration must be an integer number of seconds for preset loops')
    app = Appender(doc, original_bin)
    attrs = doc['meshes'][0]['primitives'][0]['attributes']
    attrs['JOINTS_0'] = app.add(rig.joints, 'VEC4', UNSIGNED_BYTE, target=ARRAY_BUFFER)
    attrs['WEIGHTS_0'] = app.add(rig.weights, 'VEC4', FLOAT, target=ARRAY_BUFFER)
    invbind = np.array([np.linalg.inv(joint_world_matrices(rig, np.zeros(len(rig.joint_z)))[i]) for i in range(len(rig.joint_z))], dtype=np.float32)
    invbind_accessor = app.add(invbind.transpose((0, 2, 1)).reshape(-1, 16), 'MAT4', FLOAT)
    joint_ids = []
    for i in range(len(rig.joint_z)):
        node = {'name': f'Spine_{i:02d}' + ('_Head' if i == 0 else '_Caudal' if i == len(rig.joint_z) - 1 else ''), 'translation': (rig.bind_xyz[i] if i == 0 else rig.bind_xyz[i] - rig.bind_xyz[i - 1]).tolist(), 'rotation': [0.0, 0.0, 0.0, 1.0]}
        node_id = len(doc['nodes'])
        doc['nodes'].append(node)
        joint_ids.append(node_id)
        if i > 0:
            doc['nodes'][joint_ids[i - 1]]['children'] = [node_id]
    old_matrix = doc['nodes'][0].pop('matrix', None)
    if old_matrix is not None and (not np.allclose(np.asarray(old_matrix).reshape(4, 4), np.eye(4), atol=1e-07)):
        raise ValueError('Source mesh has nonidentity matrix; apply its transform before rigging')
    doc['nodes'][0]['name'] = 'Fish_Original_Textured_Mesh'
    doc['nodes'][0]['skin'] = len(doc.setdefault('skins', []))
    doc['skins'].append({'name': 'FishSpineSkin', 'inverseBindMatrices': invbind_accessor, 'skeleton': joint_ids[0], 'joints': joint_ids})
    root = {'name': 'Fish_Root', 'children': [0, joint_ids[0]]}
    if target_length_m is not None:
        if not 0.03 <= target_length_m <= 4.0:
            raise ValueError('target length must lie between 0.03 and 4 meters')
        scale = target_length_m / rig.length
        root['scale'] = [scale, scale, scale]
    root_id = len(doc['nodes'])
    doc['nodes'].append(root)
    doc['scenes'][doc.get('scene', 0)]['nodes'] = [root_id]
    times = np.linspace(0.0, duration, round(fps * duration) + 1, dtype=np.float32)
    time_accessor = app.add(times.reshape(-1, 1), 'SCALAR', FLOAT, with_minmax=True)
    animation_docs = []
    for preset in PRESETS:
        channels = []
        samplers = []
        angles = np.stack([local_spine_angles(float(t), rig, preset, amp_multiplier) for t in times])
        for j, node_id in enumerate(joint_ids):
            q = quaternions_y(angles[:, j])
            for k in range(1, len(q)):
                if np.dot(q[k - 1], q[k]) < 0:
                    q[k] *= -1
            q_accessor = app.add(q, 'VEC4', FLOAT)
            sampler_id = len(samplers)
            samplers.append({'input': time_accessor, 'output': q_accessor, 'interpolation': 'LINEAR'})
            channels.append({'sampler': sampler_id, 'target': {'node': node_id, 'path': 'rotation'}})
        animation_docs.append({'name': preset.name, 'samplers': samplers, 'channels': channels, 'extras': {'frequency_hz': preset.frequency_hz, 'tail_amplitude_body_lengths': preset.tail_amplitude_bl * amp_multiplier, 'wavelength_body_lengths': preset.wavelength_bl, 'kinematic_model': 'quadratic-envelope traveling wave, not calibrated to specific specimen'}})
    doc['animations'] = animation_docs
    doc.setdefault('extras', {})['fish_swim'] = {'source_sha256': source_hash, 'source_dimensions': {'body_length_model_units': rig.length, 'forward_axis': '+Z', 'up_axis': '+Y'}, 'bone_count': len(rig.joint_z), 'onset_body_lengths': rig.onset, 'envelope_exponent': rig.exponent, 'reference_length_m': target_length_m, 'warning': 'Procedural illustrative trout swimming; no specimen-specific motion calibration'}
    doc['buffers'][0]['byteLength'] = len(app.blob)
    return (doc, bytes(app.blob))

def write_glb(path: Path, doc: dict, binary: bytes) -> None:
    j = json.dumps(doc, ensure_ascii=False, separators=(',', ':')).encode('utf-8')
    j += b' ' * (-len(j) % 4)
    b = binary + b'\x00' * (-len(binary) % 4)
    full_length = 12 + 8 + len(j) + 8 + len(b)
    with path.open('wb') as f:
        f.write(struct.pack('<III', GLB_MAGIC, 2, full_length))
        f.write(struct.pack('<II', len(j), JSON_CHUNK))
        f.write(j)
        f.write(struct.pack('<II', len(b), BIN_CHUNK))
        f.write(b)

def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('input', type=Path, help='Unrigged GLB, trout head oriented toward +Z')
    ap.add_argument('output', type=Path, help='Destination animated GLB (will not overwrite the original)')
    ap.add_argument('--bones', type=int, default=15, help='Spinal joint count [default: 15]')
    ap.add_argument('--fps', type=int, default=30, help='Animation keyframes per second [default: 30]')
    ap.add_argument('--duration', type=float, default=2.0, help='Integer cycle duration in seconds [default: 2]')
    ap.add_argument('--amplitude-scale', type=float, default=1.0, help='Multiply lateral excursion [default: 1]')
    ap.add_argument('--target-length-m', type=float, default=None, help='Optional overall mesh length in meters')
    ap.add_argument('--wave-onset', type=float, default=0.23, help='Onset as fraction of length from snout')
    ap.add_argument('--envelope-exponent', type=float, default=2.0, help='Exponent for posterior amplitude growth')
    args = ap.parse_args()
    if args.input.resolve() == args.output.resolve():
        ap.error('Input and output must be different files; original must remain unchanged')
    if not 0 < args.amplitude_scale <= 3:
        ap.error('Amplitude scale must be in (0,3]')
    doc, binary = read_glb(args.input)
    original_sha = hashlib.sha256(args.input.read_bytes()).hexdigest()
    attrs = doc['meshes'][0]['primitives'][0]['attributes']
    v = accessor_array(doc, binary, attrs['POSITION'])
    rig = make_rig(v, num_joints=args.bones, onset=args.wave_onset, exponent=args.envelope_exponent)
    doc, binary = build_animated_glb(doc, binary, rig, fps=args.fps, duration=args.duration, amp_multiplier=args.amplitude_scale, target_length_m=args.target_length_m, source_hash=original_sha)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    write_glb(args.output, doc, binary)
    print(f'Wrote {args.output}: {args.output.stat().st_size / 1048576:.1f} MB')
    print(f'Mesh vertices {len(v):,}; joints {len(rig.joint_z)}; animations: ' + ', '.join((p.name for p in PRESETS)))
    print('Original file preserved:', args.input)
if __name__ == '__main__':
    main()
