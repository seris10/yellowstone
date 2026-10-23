export function worldCoordinates(x, elevation, z, origin) {
  return {easting: origin[0] + x, northing: origin[1] - z, elevation};
}

export function terrainValue(grid, spec, x, z) {
  const col = (x - spec.start[0]) / spec.spacing_m;
  const row = (z - spec.start[1]) / spec.spacing_m;
  if (!Number.isFinite(col) || !Number.isFinite(row) || col < 0 || row < 0 || col > spec.n - 1 || row > spec.n - 1) return null;
  const i = Math.min(Math.floor(col), spec.n - 2), j = Math.min(Math.floor(row), spec.n - 2);
  const u = col - i, v = row - j;
  const a = grid[j * spec.n + i], b = grid[j * spec.n + i + 1];
  const c = grid[(j + 1) * spec.n + i], d = grid[(j + 1) * spec.n + i + 1];
  if (![a, b, c, d].every(Number.isFinite)) return null;
  // The mesh diagonal joins the northeast and southwest vertices.
  return u + v <= 1 ? a + u * (b - a) + v * (c - a) : d + (1 - u) * (c - d) + (1 - v) * (b - d);
}

export function sampleIndex(value, count) {
  const index = Number(value);
  if (!Number.isInteger(index) || index < 0 || index >= count) throw new RangeError('Sample outside saved time support');
  return index;
}

export function validateReplay(replay) {
  if (!replay.cells?.length || !replay.frames?.length) throw new Error('Replay support is empty');
  if (new Set(replay.cells.map(c => c.id)).size !== replay.cells.length) throw new Error('Duplicate cell identity');
  for (const [i, f] of replay.frames.entries()) {
    if (!Number.isFinite(f.t) || (i && f.t <= replay.frames[i - 1].t)) throw new Error('Invalid time support');
    if (f.values.length !== replay.cells.length || f.values.some(v => v !== null && (typeof v !== 'number' || !Number.isFinite(v)))) throw new Error('Invalid cell values');
  }
  return replay;
}

export async function verifiedBytes(url, expected) {
  const response = await fetch(url);
  if (!response.ok) throw new Error(`Data request failed (${response.status})`);
  const bytes = await response.arrayBuffer();
  const digest = await crypto.subtle.digest('SHA-256', bytes);
  const hash = [...new Uint8Array(digest)].map(v => v.toString(16).padStart(2, '0')).join('');
  if (hash !== expected.sha256 || bytes.byteLength !== expected.bytes) throw new Error(`Data integrity check failed: ${url}`);
  return bytes;
}
