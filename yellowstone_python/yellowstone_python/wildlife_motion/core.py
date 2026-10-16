"""Skeleton, pose, and coordinate contracts."""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any
import numpy as np
from scipy.spatial.transform import Rotation


class AssetError(ValueError):
    """Actionable unsupported-asset or invalid-input error."""


def unit(v: np.ndarray, fallback: np.ndarray | None = None) -> np.ndarray:
    v = np.asarray(v, dtype=float)
    if v.shape != (3,) or not np.isfinite(v).all():
        raise ValueError("Direction requires three finite coordinates")
    n = np.linalg.norm(v)
    if n < 1e-12:
        if fallback is None:
            raise ValueError("Cannot normalize a zero vector")
        return unit(fallback)
    return v / n


def smoothstep(x: np.ndarray | float) -> np.ndarray:
    x = np.clip(x, 0., 1.)
    return x*x*(3.-2.*x)


def smootherstep(x: np.ndarray | float) -> np.ndarray:
    x = np.clip(x, 0., 1.)
    return x**3*(10.+x*(-15.+6.*x))


def axis_rotation(axis: str, angle: float) -> np.ndarray:
    return Rotation.from_euler(axis, angle).as_matrix()


def align_vectors(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    """Shortest proper rotation from a to b, including antiparallel vectors."""
    a, b = unit(a), unit(b)
    c = float(np.clip(a @ b, -1, 1))
    v = np.cross(a, b)
    s = np.linalg.norm(v)
    if s < 1e-10:
        if c > 0:
            return np.eye(3)
        seed = np.eye(3)[np.argmin(np.abs(a))]
        return Rotation.from_rotvec(np.pi*unit(np.cross(a, seed))).as_matrix()
    return Rotation.from_rotvec(unit(v)*np.arctan2(s, c)).as_matrix()


@dataclass
class Skeleton:
    names: list[str]
    parents: np.ndarray
    rest: np.ndarray
    groups: dict[str, list[int]] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.parents = np.asarray(self.parents, dtype=int)
        self.rest = np.asarray(self.rest, dtype=float)
        n = len(self.names)
        if self.rest.shape != (n, 3) or len(self.parents) != n:
            raise ValueError("Invalid skeleton dimensions")
        if (not np.isfinite(self.rest).all() or len(set(self.names)) != n
                or any(not isinstance(name,str) or not name for name in self.names)):
            raise ValueError("Skeleton coordinates must be finite and names unique")
        for i, p in enumerate(self.parents):
            if p >= i or p < -1 or (p == -1 and i != 0):
                raise ValueError("Skeleton must have one root and topological parent order")
        if not n or self.parents[0] != -1:
            raise ValueError("Skeleton requires a root")
        for indices in self.groups.values():
            if (not isinstance(indices, list) or not indices
                    or any(not isinstance(i, int) or i < 0 or i >= n for i in indices)
                    or len(set(indices)) != len(indices)):
                raise ValueError("Skeleton group indices must be unique and in range")

    def index(self, name: str) -> int:
        return self.names.index(name)

    @property
    def offsets(self) -> np.ndarray:
        out = self.rest.copy()
        out[1:] -= self.rest[self.parents[1:]]
        return out

    def to_dict(self) -> dict:
        return {"schema": "wildlife-motion.rig/1", "names": self.names,
                "parents": self.parents.tolist(), "rest": self.rest.tolist(),
                "groups": self.groups, "metadata": self.metadata}

    @classmethod
    def from_dict(cls, obj: dict) -> "Skeleton":
        if obj.get("schema") != "wildlife-motion.rig/1":
            raise ValueError("Unknown rig schema")
        return cls(obj["names"], obj["parents"], obj["rest"],
                   obj.get("groups", {}), obj.get("metadata", {}))


@dataclass
class Pose:
    positions: np.ndarray
    rotations: np.ndarray
    diagnostics: dict[str, Any] = field(default_factory=dict)

    def local(self, skeleton: Skeleton) -> tuple[np.ndarray, np.ndarray]:
        p, r = self.positions, self.rotations
        t, q = np.empty_like(p), np.empty((len(p), 4))
        for j, parent in enumerate(skeleton.parents):
            if parent < 0:
                t[j], lr = p[j], r[j]
            else:
                inv = r[parent].T
                t[j], lr = inv @ (p[j]-p[parent]), inv @ r[j]
            q[j] = Rotation.from_matrix(lr).as_quat()
        return t, q


def fk(skeleton: Skeleton, local_rotations: np.ndarray | None = None,
       root_translation: np.ndarray | None = None,
       local_offsets: np.ndarray | None = None) -> Pose:
    n = len(skeleton.names)
    lr = np.tile(np.eye(3), (n,1,1)) if local_rotations is None else local_rotations
    offsets = skeleton.offsets if local_offsets is None else np.asarray(local_offsets)
    p, r = np.empty((n,3)), np.empty((n,3,3))
    for i, parent in enumerate(skeleton.parents):
        if parent < 0:
            p[i], r[i] = offsets[i], lr[i]
            if root_translation is not None:
                p[i] += root_translation
        else:
            p[i] = p[parent]+r[parent] @ offsets[i]
            r[i] = r[parent] @ lr[i]
    return Pose(p, r)


def two_bone_ik(root: np.ndarray, target: np.ndarray, length_a: float,
                length_b: float, pole: np.ndarray) -> tuple[np.ndarray, np.ndarray, float]:
    """Return fixed-length link positions and unreachable distance."""
    if not np.isfinite([length_a, length_b]).all() or min(length_a, length_b) <= 0:
        raise ValueError("IK link lengths must be positive")
    root, target = np.asarray(root, float), np.asarray(target, float)
    if (root.shape != (3,) or target.shape != (3,)
            or not np.isfinite(root).all() or not np.isfinite(target).all()):
        raise ValueError("IK positions require three finite coordinates")
    delta = target-root
    direction = unit(delta, np.array([0.,-1.,0.]))
    distance = float(np.linalg.norm(delta))
    epsilon = min(length_a, length_b) * 1e-9
    lo = abs(length_a-length_b)+epsilon
    hi = length_a+length_b-epsilon
    d = float(np.clip(distance, lo, hi))
    endpoint = root+d*direction
    along = (length_a**2-length_b**2+d*d)/(2*d)
    height = np.sqrt(max(0., length_a**2-along**2))
    pole = np.asarray(pole)-direction*np.dot(pole,direction)
    if np.linalg.norm(pole) < 1e-9:
        basis = np.eye(3)[np.argmin(abs(direction))]
        pole = basis-direction*np.dot(basis,direction)
    middle = root+along*direction+height*unit(pole)
    return middle, endpoint, abs(distance-d)


def pose_limb(skeleton: Skeleton, pose: Pose, indices: list[int],
              target: np.ndarray, foot_rotation: np.ndarray | None = None) -> float:
    """Place hip/shoulder -> knee/elbow -> ankle/hock -> foot with level sole."""
    a,b,c,d = indices
    rest = skeleton.rest
    rf = np.eye(3) if foot_rotation is None else foot_rotation
    offset = rf @ (rest[d]-rest[c])
    ankle_target = np.asarray(target)-offset
    ab,bc = rest[b]-rest[a], rest[c]-rest[b]
    axis = unit(rest[c]-rest[a])
    pole = rest[b]-rest[a]-axis*np.dot(rest[b]-rest[a],axis)
    parent = skeleton.parents[a]
    # Preserve the rest bend plane under torso yaw/pitch/roll.
    pole = pose.rotations[parent] @ pole if parent >= 0 else pole
    middle, end, error = two_bone_ik(pose.positions[a], ankle_target,
                                    np.linalg.norm(ab), np.linalg.norm(bc), pole)
    pose.positions[b],pose.positions[c],pose.positions[d] = middle,end,end+offset
    pose.rotations[a] = align_vectors(ab, middle-pose.positions[a])
    pose.rotations[b] = align_vectors(bc, end-middle)
    pose.rotations[c],pose.rotations[d] = rf,rf
    return error


def skin(vertices: np.ndarray, skeleton: Skeleton, joints: np.ndarray,
         weights: np.ndarray, pose: Pose) -> np.ndarray:
    """Exact CPU reference for the rigid-joint glTF linear blend skinning used here."""
    out = np.zeros_like(vertices, dtype=float)
    for slot in range(joints.shape[1]):
        idx = joints[:,slot]
        x = np.einsum("nij,nj->ni", pose.rotations[idx],
                      vertices-skeleton.rest[idx], optimize=True)
        out += weights[:,slot,None]*(x+pose.positions[idx])
    return out


def vertex_normals(vertices: np.ndarray, faces: np.ndarray) -> np.ndarray:
    n = np.zeros_like(vertices, dtype=float)
    f = np.cross(vertices[faces[:,1]]-vertices[faces[:,0]],
                 vertices[faces[:,2]]-vertices[faces[:,0]])
    for corner in range(3):
        np.add.at(n,faces[:,corner],f)
    lengths = np.linalg.norm(n,axis=1)
    valid = lengths > 1e-12
    n[valid] /= lengths[valid,None]
    n[~valid] = [0,1,0]
    return n


@dataclass
class Clip:
    name: str
    times: np.ndarray
    translations: np.ndarray
    rotations: np.ndarray
    loop: bool = True
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if len(self.times) < 2 or np.any(np.diff(self.times) <= 0):
            raise ValueError("Animation times must increase strictly")
        if not all(np.isfinite(a).all() for a in (self.times,self.translations,self.rotations)):
            raise ValueError("Animation contains nonfinite values")
        if self.translations.shape != (len(self.times),self.rotations.shape[1],3):
            raise ValueError("Invalid clip translation shape")
        if self.rotations.shape != (len(self.times),self.translations.shape[1],4):
            raise ValueError("Invalid clip quaternion shape")
        norms = np.linalg.norm(self.rotations,axis=-1)
        if np.max(abs(norms-1.)) > 1e-6:
            raise ValueError("Animation quaternions are not normalized")
        # Consecutive quaternion signs must agree for stable interpolation.
        for i in range(1,len(self.times)):
            flip = np.sum(self.rotations[i-1]*self.rotations[i],axis=1)<0
            self.rotations[i,flip] *= -1


def sample_clip(skeleton: Skeleton, pose_function, duration: float, fps: int,
                name: str, loop: bool = True, metadata: dict | None = None) -> Clip:
    if not 0 < duration <= 120 or not 1 <= fps <= 240:
        raise ValueError("Duration must be in (0,120] and fps in [1,240]")
    times = np.linspace(0,duration,max(2,round(duration*fps)+1))
    t,q,errors = [],[],[]
    for time in times:
        pose = pose_function(float(time))
        ti,qi = pose.local(skeleton)
        t.append(ti);q.append(qi)
        errors.append(float(pose.diagnostics.get("max_reach_error",0.)))
    info = dict(metadata or {})
    info["max_ik_reach_error_asset_units"] = max(errors)
    return Clip(name,times,np.asarray(t),np.asarray(q),loop,info)
