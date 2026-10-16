"use strict";

((root) => {
  const finite = x => typeof x === "number" && Number.isFinite(x);
  const clamp = (x, a, b) => Math.max(a, Math.min(b, x));
  const assert = (ok, message) => { if (!ok) throw Error(message); };
  function extent(values) {
    let low = Infinity, high = -Infinity;
    for (const value of values) if (finite(value)) { low = Math.min(low, value); high = Math.max(high, value); }
    return low === Infinity ? null : [low, high];
  }
  function nearestIndex(values, target) {
    if (!values.length || !finite(target)) return -1;
    let lo = 0, hi = values.length - 1;
    while (lo < hi) { const mid = (lo + hi) >>> 1; if (values[mid] < target) lo = mid + 1; else hi = mid; }
    return lo > 0 && Math.abs(values[lo - 1] - target) <= Math.abs(values[lo] - target) ? lo - 1 : lo;
  }
  function frameAtElapsed(times, elapsed) {
    if (!times.length || !finite(elapsed)) return -1;
    let lo = 0, hi = times.length;
    while (lo < hi) { const mid = (lo + hi) >>> 1; if (times[mid] <= elapsed) lo = mid + 1; else hi = mid; }
    return clamp(lo - 1, 0, times.length - 1);
  }
  function segments(points, x = p => p.x, y = p => p.y) {
    let drawing = false;
    return points.map(p => {
      if (!finite(p.x) || !finite(p.y)) { drawing = false; return ""; }
      const token = `${drawing ? "L" : "M"}${x(p)},${y(p)}`; drawing = true; return token;
    }).join(" ");
  }
  function eventToSvg(svg, event) {
    const matrix = svg.getScreenCTM();
    if (!matrix) return null;
    const point = svg.createSVGPoint(); point.x = event.clientX; point.y = event.clientY;
    return point.matrixTransform(matrix.inverse());
  }
  function csvCell(value) {
    if (finite(value)) return String(value);
    let text = String(value ?? "");
    if (/^[\s]*[=+@-]/.test(text)) text = "'" + text;
    return '"' + text.replace(/"/g, '""') + '"';
  }
  function validateRiver(river, native = false) {
    assert(river && finite(river.length_m) && river.length_m > 0, "River length is unavailable.");
    assert(Array.isArray(river.cells) && river.cells.length && Array.isArray(river.frames) && river.frames.length, "Saved river samples are unavailable.");
    const ids = new Set();
    river.cells.forEach((cell, i) => {
      assert(finite(cell.s) && cell.s >= 0 && cell.s <= river.length_m && (!i || cell.s > river.cells[i-1].s), "River chainage must increase.");
      assert(finite(cell.x) && finite(cell.z), "River coordinates are unavailable.");
      if (native) {
        assert(typeof cell.id === "string" && cell.id && !ids.has(cell.id), "Cell identities must be unique."); ids.add(cell.id);
        assert(Array.isArray(cell.bounds_m) && cell.bounds_m.length === 2 && cell.bounds_m.every(finite) &&
          cell.bounds_m[0] <= cell.s && cell.bounds_m[1] >= cell.s && cell.bounds_m[1] > cell.bounds_m[0] &&
          cell.bounds_m[0] >= 0 && cell.bounds_m[1] <= river.length_m + 1e-6, "Cell bounds are invalid.");
      }
    });
    river.frames.forEach((frame, i) => {
      assert(finite(frame.t) && (!i || frame.t > river.frames[i-1].t), "Saved times must increase.");
      assert(Array.isArray(frame.temperature) && frame.temperature.length === river.cells.length, "River frame dimensions differ.");
      assert(frame.temperature.every(v => v === null || finite(v)), "Temperature must be a finite number or null.");
    });
    return river;
  }
  function validateSnapshot(data) {
    assert(data?.schema === "yellowstone.public.v1" && typeof data.snapshot === "string", "Snapshot identity is invalid.");
    assert(Array.isArray(data.domains) && data.domains.length && Array.isArray(data.nodes) && Array.isArray(data.edges), "System structure is unavailable.");
    const domains = new Set(data.domains.map(d => d.id)), ids = new Set();
    data.nodes.forEach(n => { assert(!ids.has(n.id) && domains.has(n.domain), "Process identity is invalid."); ids.add(n.id); });
    data.edges.forEach(e => assert(ids.has(e.from) && ids.has(e.to), "Exchange endpoint is unavailable."));
    const availability = [];
    try { validateRiver(data.river); } catch (error) { data.river = null; availability.push(error.message); }
    for (const [container,key] of [[data.ecology,"oxygen"],[data.ecology,"periphyton"],[data.analytics,"shading"]]) {
      if (!container || container[key] === undefined) continue;
      if (!Array.isArray(container[key]) || !data.river || container[key].length !== data.river.cells.length ||
        !container[key].every(v=>v === null || finite(v))) { container[key]=null; availability.push(`${key} spatial support is invalid.`); }
    }
    data.availability = availability;
    return data;
  }
  function normalizeDataset(doc) {
    assert(doc?.schema === "yellowstone.river.v1" && typeof doc.snapshot === "string", "River dataset identity is invalid.");
    const river = validateRiver(doc.river, true), times = river.frames.map(f => f.t), distances = river.cells.map(c => c.s);
    let domain = null, missing = 0;
    river.frames.forEach(f => { const e = extent(f.temperature); missing += f.temperature.filter(v => !finite(v)).length;
      if (e) domain = domain ? [Math.min(domain[0], e[0]), Math.max(domain[1], e[1])] : e; });
    return {...doc, ...river, times, distances, extent: domain, missing};
  }
  const temperatureStops = [[77,148,244],[73,207,187],[245,211,99],[246,110,72]];
  const differenceStops = [[109,160,247],[223,226,235],[236,115,103]];
  function color(value, domain, difference = false) {
    if (!finite(value) || !domain) return "#262b34";
    const stops = difference ? differenceStops : temperatureStops;
    const q = clamp((value-domain[0])/(domain[1]-domain[0] || 1), 0, 1)*(stops.length-1);
    const i = Math.min(stops.length-2, Math.floor(q)), f = q-i;
    return `rgb(${stops[i].map((n,k) => Math.round(n+(stops[i+1][k]-n)*f)).join(",")})`;
  }
  function delta(value, reference) { return finite(value) && finite(reference) ? value-reference : null; }
  function differenceExtent(data, reference) {
    let maximum = 0;
    for (const frame of data.frames) for (let i=0; i<data.cells.length; i++) {
      const d = delta(frame.temperature[i], data.frames[reference].temperature[i]);
      if (finite(d)) maximum = Math.max(maximum, Math.abs(d));
    }
    return [-Math.max(maximum, 1e-9), Math.max(maximum, 1e-9)];
  }
  function createStore(initial) {
    let state = Object.freeze({...initial}); const listeners = new Set();
    return {get: () => state, update(patch) { state = Object.freeze({...state,...patch}); listeners.forEach(f => f(state)); },
      subscribe(f) { listeners.add(f); return () => listeners.delete(f); }};
  }
  function recipe(dataset, sha256, state) {
    return {schema:"yellowstone.view.v1", snapshot:dataset.snapshot, dataset_sha256:sha256, variable:"river_temperature",
      time_basis:"elapsed_seconds", units:"C", uncertainty:"unknown", selection:{cell:state.cell,frame:state.frame,pinned:state.pinned},
      range:{space:[state.first,state.last],time:[state.timeFirst,state.timeLast]},
      reference_frame:state.reference, transform:state.difference?"difference":"absolute", compare:state.compare,
      scale:state.scale, temperature_domain:dataset.extent, difference_domain:state.difference?differenceExtent(dataset,state.reference):null,
      status_filter:"all", support:dataset.support};
  }
  function restoreRecipe(value, dataset, sha256) {
    assert(value?.schema === "yellowstone.view.v1" && value.dataset_sha256 === sha256 && value.snapshot === dataset.snapshot, "Recipe belongs to different dataset bytes.");
    assert(value.variable === "river_temperature" && value.time_basis === "elapsed_seconds" && value.units === "C", "Recipe quantity or time basis differs.");
    const index = (v,n) => Number.isInteger(v) && v >= 0 && v < n;
    const s = value.selection, r = value.range;
    assert(s && index(s.cell,dataset.cells.length) && index(s.frame,dataset.frames.length) && typeof s.pinned === "boolean", "Recipe selection is invalid.");
    assert(r && [r.space,r.time].every(a=>Array.isArray(a)&&a.length===2) && r.space.every(v=>index(v,dataset.cells.length)) &&
      r.time.every(v=>index(v,dataset.frames.length)) && r.space[0]<=r.space[1] && r.time[0]<=r.time[1], "Recipe bounds are invalid.");
    assert(index(value.reference_frame,dataset.frames.length) && ["absolute","difference"].includes(value.transform) &&
      ["run","local"].includes(value.scale) && typeof value.compare === "boolean" && value.status_filter === "all", "Recipe settings are invalid.");
    return {cell:s.cell, frame:s.frame, pinned:s.pinned, first:r.space[0], last:r.space[1], timeFirst:r.time[0],timeLast:r.time[1],
      reference:value.reference_frame,difference:value.transform==="difference",compare:value.compare,scale:value.scale};
  }
  function csv(dataset, state, sha256) {
    const rows = [["snapshot","dataset_sha256","cell_id","cell_start_m","cell_end_m","chainage_m","x_m","z_m","elapsed_s","utc","temperature_c","reference_temperature_c","difference_c"]];
    for(let f=state.timeFirst;f<=state.timeLast;f++) for(let c=state.first;c<=state.last;c++) {
      const cell=dataset.cells[c],frame=dataset.frames[f],reference=dataset.frames[state.reference].temperature[c];
      rows.push([dataset.snapshot,sha256,cell.id,...cell.bounds_m,cell.s,cell.x,cell.z,frame.t,
        new Date(Date.parse(dataset.epoch)+frame.t*1000).toISOString(),frame.temperature[c],reference,delta(frame.temperature[c],reference)]);
    }
    return rows.map(row=>row.map(csvCell).join(",")).join("\r\n")+"\r\n";
  }
  async function hashBytes(bytes) { return [...new Uint8Array(await crypto.subtle.digest("SHA-256",bytes))].map(v=>v.toString(16).padStart(2,"0")).join(""); }
  const api = {finite,clamp,extent,nearestIndex,frameAtElapsed,segments,eventToSvg,csvCell,validateSnapshot,validateRiver,
    normalizeDataset,color,delta,differenceExtent,createStore,recipe,restoreRecipe,csv,hashBytes};
  if (typeof module !== "undefined") module.exports = api; else root.YSData = api;
})(typeof window === "undefined" ? {} : window);
