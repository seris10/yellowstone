"use strict";

((root) => {
  const D = typeof module !== "undefined" ? require("./data-model.js") : root.YSData;
  const finite = D.finite, finiteExtent = D.extent, nearestIndex = D.nearestIndex;
  const assert = (ok, message) => { if (!ok) throw Error(message); };
  const object = value => value !== null && typeof value === "object" && !Array.isArray(value);
  const text = value => typeof value === "string" && value.length > 0;
  const array = (value, label) => assert(Array.isArray(value), `${label} must be an array.`);
  const hash = value => typeof value === "string" && /^[a-f0-9]{64}$/.test(value);
  const roles = new Set(["direct_output", "driver", "context", "diagnostic", "authored_parameter"]);
  function unique(items, label) {
    const ids = new Set();
    for (const item of items) {
      assert(object(item) && text(item.id) && !ids.has(item.id), `${label} identities must be unique.`);
      ids.add(item.id);
    }
    return ids;
  }
  function support(value, label) {
    assert(object(value) && text(value.space) && text(value.time) && value.uncertainty === "unknown", `${label} support is incomplete.`);
    if (value.time_kind !== undefined) assert(["static", "instantaneous", "interval", "trajectory"].includes(value.time_kind), `${label} time support is invalid.`);
    if (value.interval_s !== undefined) assert(Array.isArray(value.interval_s) && value.interval_s.length === 2 && value.interval_s.every(finite) && value.interval_s[0] <= value.interval_s[1], `${label} interval is invalid.`);
  }
  function numeric(values, label) {
    array(values, label);
    for (const value of values) assert(value === null || finite(value), `${label} requires finite numbers or null.`);
  }
  function ordered(values, label) {
    array(values, label);
    for (let i = 0; i < values.length; i++) assert(finite(values[i]) && (!i || values[i] > values[i - 1]), `${label} must increase strictly.`);
  }
  function gridExtent(layer) {
    const g = layer.grid;
    return {x0:g.origin_xz_m[0], x1:g.origin_xz_m[0] + g.nx * g.cell_m,
      z0:g.origin_xz_m[1], z1:g.origin_xz_m[1] + g.nz * g.cell_m,
      width:g.nx * g.cell_m, height:g.nz * g.cell_m};
  }
  function validate(data, options = {}) {
    assert(data?.schema === "yellowstone.system.v1" && text(data.id) && text(data.snapshot), "System dataset identity is invalid.");
    assert(text(data.title) && text(data.summary) && /^#[a-f0-9]{6}$/i.test(data.color), "System presentation metadata is invalid.");
    assert(text(data.epoch) && /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})$/.test(data.epoch) && finite(Date.parse(data.epoch)) && ["illustrative", "scenario", "hindcast", "observed_replay"].includes(data.run_mode), "System scenario metadata is invalid.");
    if (options.snapshot !== undefined) assert(data.snapshot === options.snapshot, "Dataset snapshot differs from the catalog.");
    if (options.descriptor?.id !== undefined) assert(data.id === options.descriptor.id, "Dataset system differs from the catalog.");
    for (const key of ["sources", "entities", "variables", "grids", "series", "notes"]) array(data[key], key);
    if (data.profiles !== undefined) array(data.profiles, "Profiles");
    const sourceIds = unique(data.sources, "Source"), entityIds = unique(data.entities, "Entity");
    const quantityIds = unique([...data.variables, ...data.grids, ...data.series, ...(data.profiles || [])], "Quantity");
    const variableIds = new Set(data.variables.map(v => v.id));
    for (const source of data.sources) assert(text(source.label) && hash(source.sha256) && text(source.origin), "Source provenance is incomplete.");
    const quantity = item => {
      assert(text(item.label) && typeof item.unit === "string" && text(item.description) && roles.has(item.role), "Quantity metadata is invalid.");
      assert(sourceIds.has(item.source_id), "Quantity provenance source is unavailable.");
      support(item.support, item.id);
    };
    for (const item of data.variables) quantity(item);
    for (const entity of data.entities) {
      assert(text(entity.label) && text(entity.kind) && object(entity.values), "Entity metadata is invalid.");
      assert((finite(entity.x) && finite(entity.z)) || (entity.x === null && entity.z === null), "Entity coordinates must both be finite or null.");
      for (const [id, value] of Object.entries(entity.values)) assert(variableIds.has(id) && (value === null || finite(value)), "Entity quantity or numeric value is invalid.");
      if (entity.path_xz !== undefined) {
        array(entity.path_xz, "Entity path");
        for (const p of entity.path_xz) assert(Array.isArray(p) && p.length === 2 && p.every(finite), "Entity path coordinates are invalid.");
      }
      if (entity.bounds_m !== undefined) assert(Array.isArray(entity.bounds_m) && entity.bounds_m.every(finite), "Entity bounds are invalid.");
    }
    for (const layer of data.grids) {
      quantity(layer); const g = layer.grid;
      assert(object(g) && Number.isSafeInteger(g.nx) && g.nx > 0 && Number.isSafeInteger(g.nz) && g.nz > 0 && Number.isSafeInteger(g.nx * g.nz), "Grid dimensions are invalid.");
      assert(finite(g.cell_m) && g.cell_m > 0 && Array.isArray(g.origin_xz_m) && g.origin_xz_m.length === 2 && g.origin_xz_m.every(finite), "Grid spacing or origin is invalid.");
      assert(["z_increasing", "z_decreasing"].includes(g.row_order), "Grid row direction is unavailable.");
      numeric(layer.values, layer.id); assert(layer.values.length === g.nx * g.nz, "Grid value dimensions differ.");
      assert(Object.values(gridExtent(layer)).every(finite), "Grid extent exceeds finite coordinates.");
    }
    const sampled = (item, axis, label) => {
      quantity(item); ordered(item[axis], label); numeric(item.values, item.id);
      assert(item[axis].length === item.values.length && item.values.length > 0, `${label} dimensions differ.`);
      if (item.entity_id !== undefined) assert(entityIds.has(item.entity_id), "Sampled entity identity is unavailable.");
    };
    const linkedPairs = new Set();
    for (const item of data.series) {
      sampled(item, "times", "Series times");
      if (item.variable_id !== undefined) assert(variableIds.has(item.variable_id) && data.variables.find(v => v.id === item.variable_id).unit === item.unit, "Series variable identity or units differ.");
      if (item.variable_id && item.entity_id) {
        const pair = JSON.stringify([item.variable_id, item.entity_id]);
        assert(!linkedPairs.has(pair), "Entity variable has multiple unqualified time series."); linkedPairs.add(pair);
      }
      assert(!item.support.time_kind || item.support.time_kind === "trajectory", "Series requires trajectory time support.");
      if (item.support.interval_s) assert(item.times[0] >= item.support.interval_s[0] && item.times.at(-1) <= item.support.interval_s[1], "Series times exceed declared support.");
    }
    if (data.profiles !== undefined) {
      array(data.profiles, "Profiles");
      for (const item of data.profiles) {
        sampled(item, "positions", "Profile positions");
        assert(object(item.axis) && text(item.axis.id) && text(item.axis.label) && text(item.axis.unit), "Profile axis metadata is invalid.");
      }
    }
    if (data.tables !== undefined) {
      array(data.tables, "Tables"); unique(data.tables, "Table");
      for (const table of data.tables) {
        assert(text(table.label), "Table label is unavailable."); array(table.columns, "Table columns"); array(table.rows, "Table rows");
        unique(table.columns, "Table column");
        for (const col of table.columns) assert(text(col.label) && typeof col.unit === "string", "Table column metadata is invalid.");
        for (const row of table.rows) {
          assert(object(row), "Table row must be an object.");
          for (const col of table.columns) {
            const value = row[col.id];
            assert(value === null || typeof value === "string" || typeof value === "boolean" || finite(value), "Table cell is invalid.");
          }
        }
      }
    }
    for (const note of data.notes) assert(text(note), "Public note must be text.");
    assert(quantityIds.size || data.tables?.length, "System contains no scientific quantities.");
    return data;
  }
  function stats(values) {
    let count = 0, present = 0, missing = 0, minimum = Infinity, maximum = -Infinity, mean = 0;
    for (const value of values) {
      count++;
      if (!finite(value)) { missing++; continue; }
      present++; minimum = Math.min(minimum, value); maximum = Math.max(maximum, value);
      mean = mean * ((present - 1) / present) + value / present;
    }
    return {count, finite:present, missing, min:present ? minimum : null, max:present ? maximum : null, mean:present ? mean : null};
  }
  function capabilities(data) {
    const kinds = [...new Set(data.entities.map(e => e.kind))];
    return {entities:data.entities.length, spatial:data.entities.filter(e => finite(e.x) && finite(e.z)).length,
      variables:data.variables.map(v => v.id), grids:data.grids.map(g => g.id), series:data.series.map(s => s.id),
      profiles:(data.profiles || []).map(p => p.id), tables:(data.tables || []).map(t => t.id), kinds,
      missing:data.entities.reduce((n, e) => n + data.variables.reduce((m, v) => m + (!finite(e.values[v.id]) ? 1 : 0), 0), 0)};
  }
  function inRange(value, range) { return !range || finite(value) && value >= range[0] && value <= range[1]; }
  function entityRows(data, variableId, filters = {}) {
    assert(data.variables.some(v => v.id === variableId), "Entity variable is unavailable.");
    return data.entities.filter(e => (!filters.kind || filters.kind === "all" || e.kind === filters.kind) &&
      (!filters.ids || filters.ids.includes(e.id)) && inRange(e.values[variableId], filters.range))
      .map(entity => ({id:entity.id, label:entity.label, value:entity.values[variableId] ?? null, entity}));
  }
  function scatter(data, xId, yId, filters = {}) {
    const x = data.variables.find(v => v.id === xId), y = data.variables.find(v => v.id === yId);
    assert(x && y, "Scatter axes require entity variables.");
    const rows = entityRows(data, filters.variable || yId, filters), points = [];
    for (const row of rows) {
      const a = row.entity.values[xId], b = row.entity.values[yId];
      if (finite(a) && finite(b)) points.push({id:row.id, label:row.label, x:a, y:b, entity:row.entity});
    }
    return {points, missing:rows.length - points.length, total:rows.length, x, y};
  }
  function histogram(values, options = {}) {
    const valuesArray = Array.isArray(values) ? values : Array.from(values), all = stats(valuesArray);
    const extent = options.range || (all.finite ? [all.min, all.max] : null);
    assert(!extent || Array.isArray(extent) && extent.length === 2 && extent.every(finite) && extent[0] <= extent[1], "Histogram range is invalid.");
    const count = options.bins ?? 16;
    assert(Number.isInteger(count) && count > 0 && count <= 512, "Histogram bin count is invalid.");
    if (!extent) return {bins:[], extent:null, finite:0, missing:all.missing, outside:0, constant:false};
    const constant = extent[0] === extent[1], span = extent[1] - extent[0];
    const n = constant || span / count === 0 ? 1 : count;
    const bound = t => extent[0] * (1 - t) + extent[1] * t;
    const bins = Array.from({length:n}, (_, i) => ({lo:i ? bound(i / n) : extent[0], hi:i === n - 1 ? extent[1] : bound((i + 1) / n), count:0, last:i === n - 1}));
    let outside = 0, included = 0;
    for (const value of valuesArray) {
      if (!finite(value)) continue;
      if (value < extent[0] || value > extent[1]) { outside++; continue; }
      const fraction = finite(span) ? (value - extent[0]) / span : (value / 2 - extent[0] / 2) / (extent[1] / 2 - extent[0] / 2);
      bins[constant ? 0 : Math.min(n - 1, Math.floor(fraction * n))].count++; included++;
    }
    return {bins, extent:extent.slice(), finite:included, missing:all.missing, outside, constant};
  }
  function gridPoint(layer, index) {
    const g = layer.grid;
    if (!Number.isInteger(index) || index < 0 || index >= layer.values.length) return null;
    const row = Math.floor(index / g.nx), column = index % g.nx;
    return {index, row, column, x:g.origin_xz_m[0] + (column + .5) * g.cell_m,
      z:g.origin_xz_m[1] + (g.row_order === "z_increasing" ? row + .5 : g.nz - row - .5) * g.cell_m, value:layer.values[index]};
  }
  function sampleGrid(layer, x, z) {
    if (!finite(x) || !finite(z)) return null;
    const e = gridExtent(layer), g = layer.grid;
    if (x < e.x0 || x >= e.x1 || z < e.z0 || z >= e.z1) return null;
    const column = Math.floor((x - e.x0) / g.cell_m), increasingRow = Math.floor((z - e.z0) / g.cell_m);
    const row = g.row_order === "z_increasing" ? increasingRow : g.nz - increasingRow - 1;
    return gridPoint(layer, row * g.nx + column);
  }
  function mapTransform(extent, width, height, padding = 0) {
    assert(extent && [extent.x0, extent.x1, extent.z0, extent.z1, extent.x1 - extent.x0, extent.z1 - extent.z0, width, height, padding].every(finite) && extent.x1 >= extent.x0 && extent.z1 >= extent.z0 && width > 2 * padding && height > 2 * padding && padding >= 0, "Map display extent is invalid.");
    const k = Math.min((width - 2 * padding) / (extent.x1 - extent.x0 || 1), (height - 2 * padding) / (extent.z1 - extent.z0 || 1));
    const cx = extent.x0 / 2 + extent.x1 / 2, cz = extent.z0 / 2 + extent.z1 / 2;
    return {k, project:(x, z) => ({x:width / 2 + (x - cx) * k, y:height / 2 + (z - cz) * k}),
      invert:(x, y) => ({x:cx + (x - width / 2) / k, z:cz + (y - height / 2) / k})};
  }
  function segments(points, x = p => p.x, y = p => p.y) {
    let drawing = false; const tokens = [];
    for (const point of points) {
      if (!finite(point.x) || !finite(point.y)) { drawing = false; continue; }
      const px = x(point), py = y(point);
      if (!finite(px) || !finite(py)) { drawing = false; continue; }
      tokens.push(`${drawing ? "L" : "M"}${px},${py}`); drawing = true;
    }
    return tokens.join(" ");
  }
  function compatible(a, b) { return !!a && !!b && object(a.support) && object(b.support) && a.unit === b.unit && a.support.space === b.support.space && a.support.time === b.support.time; }
  function compare(a, b, values, reference) {
    assert(compatible(a, b), "Comparison units or physical support differ.");
    assert(values.length === reference.length, "Comparison sample dimensions differ.");
    return values.map((value, i) => finite(value) && finite(reference[i]) ? value - reference[i] : null);
  }
  const csvRows = rows => rows.map(row => row.map(D.csvCell).join(",")).join("\r\n") + "\r\n";
  function sampleAt(series, elapsed) {
    if (!finite(elapsed) || !series.times.length || elapsed < series.times[0] || elapsed > series.times.at(-1)) return null;
    const index = D.frameAtElapsed(series.times, elapsed);
    return {index, time:series.times[index], value:series.values[index]};
  }
  function temporalValues(data, variableId, elapsed) {
    const series = new Map(data.series.filter(s => s.variable_id === variableId && s.entity_id).map(s => [s.entity_id, s]));
    return data.entities.map(entity => ({id:entity.id, label:entity.label, entity,
      value:series.has(entity.id) ? sampleAt(series.get(entity.id), elapsed)?.value ?? null : null}));
  }
  function quantity(data, id) { return [...data.variables, ...data.grids, ...data.series, ...(data.profiles || [])].find(v => v.id === id); }
  function valuesFor(data, item) { return data.variables.includes(item) ? data.entities.map(e => e.values[item.id] ?? null) : item.values; }
  function quantityExtent(data, item) {
    return finiteExtent((function* () {
      yield* valuesFor(data, item);
      if (data.variables.includes(item)) for (const s of data.series) if (s.variable_id === item.id) yield* s.values;
    })());
  }
  function normalizeState(data, state) {
    assert(object(state), "Recipe view state is invalid.");
    const allowed = new Set(["variable", "x", "y", "kind", "range", "pins", "reference", "scale", "series", "timeRange", "map", "selected", "pinned", "gridIndex", "difference", "referenceGrid", "time", "temporal", "referenceTime", "query", "sort", "descending", "page"]);
    assert(Object.keys(state).every(k => allowed.has(k)), "Recipe contains unsupported view settings.");
    const variable = quantity(data, state.variable);
    assert(variable, "Recipe variable is unavailable.");
    const result = {variable:state.variable, x:state.x ?? null, y:state.y ?? null, kind:state.kind ?? "all", range:state.range ?? null,
      pins:state.pins ?? [], reference:state.reference ?? null, scale:state.scale ?? "run", series:state.series ?? null,
      timeRange:state.timeRange ?? null, map:state.map ?? {x:0, y:0, k:1}, selected:state.selected ?? null,
      pinned:state.pinned ?? false, gridIndex:state.gridIndex ?? null, difference:state.difference ?? false,
      referenceGrid:state.referenceGrid ?? null, time:state.time ?? null, temporal:state.temporal ?? false,
      referenceTime:state.referenceTime ?? null, query:state.query ?? "", sort:state.sort ?? "label",
      descending:state.descending ?? false, page:state.page ?? 0};
    for (const id of [result.x, result.y]) assert(id === null || data.variables.some(v => v.id === id), "Recipe scatter axis is unavailable.");
    assert(result.kind === "all" || data.entities.some(e => e.kind === result.kind), "Recipe entity filter is unavailable.");
    const domain = quantityExtent(data, variable);
    if (result.range !== null) assert(domain && Array.isArray(result.range) && result.range.length === 2 && result.range.every(finite) && result.range[0] <= result.range[1] && result.range[0] >= domain[0] && result.range[1] <= domain[1], "Recipe value range exceeds source support.");
    assert(Array.isArray(result.pins) && result.pins.every(id => data.entities.some(e => e.id === id)) && new Set(result.pins).size === result.pins.length, "Recipe pinned identities are invalid.");
    for (const id of [result.reference, result.selected]) assert(id === null || data.entities.some(e => e.id === id), "Recipe entity identity is unavailable.");
    if (result.reference !== null) assert(data.variables.includes(variable) && finite(data.entities.find(e => e.id === result.reference).values[variable.id]), "Recipe reference has no value for this variable.");
    assert(["run", "local"].includes(result.scale) && typeof result.pinned === "boolean" && typeof result.difference === "boolean" && typeof result.temporal === "boolean", "Recipe scale or selection mode is invalid.");
    const selectedSeries = result.series === null ? null : data.series.find(s => s.id === result.series);
    assert(result.series === null || selectedSeries, "Recipe time series is unavailable.");
    assert(!selectedSeries || selectedSeries.id === variable.id || selectedSeries.variable_id === variable.id, "Recipe time series belongs to a different quantity.");
    if (result.timeRange !== null) assert(selectedSeries && Array.isArray(result.timeRange) && result.timeRange.length === 2 && result.timeRange.every(finite) && result.timeRange[0] <= result.timeRange[1] && result.timeRange[0] >= selectedSeries.times[0] && result.timeRange[1] <= selectedSeries.times.at(-1), "Recipe elapsed range exceeds this series support.");
    assert(object(result.map) && Object.keys(result.map).length === 3 && [result.map.x, result.map.y, result.map.k].every(finite) && result.map.k > 0 && result.map.k <= 1e9 && Math.abs(result.map.x) <= 1e12 && Math.abs(result.map.y) <= 1e12, "Recipe map transform is invalid.");
    const grid = data.grids.find(g => g.id === variable.id);
    assert(result.gridIndex === null || grid && Number.isInteger(result.gridIndex) && result.gridIndex >= 0 && result.gridIndex < grid.values.length, "Recipe grid selection is invalid.");
    assert(result.referenceGrid === null || grid && Number.isInteger(result.referenceGrid) && result.referenceGrid >= 0 && result.referenceGrid < grid.values.length && finite(grid.values[result.referenceGrid]), "Recipe grid reference is invalid.");
    const linked = data.series.filter(s => s.variable_id === variable.id), currentSeries = data.series.includes(variable) ? variable : selectedSeries;
    const times = finiteExtent((function* () { for (const s of currentSeries ? [currentSeries] : linked) yield* s.times; })());
    for (const t of [result.time, result.referenceTime]) assert(t === null || times && finite(t) && t >= times[0] && t <= times[1], "Recipe selected time exceeds source support.");
    assert(!result.temporal || linked.length > 0 && result.time !== null, "Recipe temporal map requires linked saved samples.");
    assert(!result.difference || result.reference !== null || result.referenceGrid !== null || result.referenceTime !== null, "Difference mode requires a finite reference.");
    const tableSize = Math.max(data.entities.length, grid?.values.length || 0, selectedSeries?.values.length || 0, variable.values?.length || 0);
    assert(typeof result.query === "string" && result.query.length <= 200 && ["label", "value", "id"].includes(result.sort) && typeof result.descending === "boolean" && Number.isInteger(result.page) && result.page >= 0 && result.page <= Math.max(0, Math.ceil(tableSize / 100) - 1), "Recipe table settings are invalid.");
    return structuredClone(result);
  }
  function recipe(data, state, sha256) {
    assert(hash(sha256), "Dataset byte hash is unavailable.");
    return {schema:"yellowstone.system-view.v1", snapshot:data.snapshot, system:data.id, dataset_sha256:sha256,
      sources:data.sources.map(s => ({id:s.id, sha256:s.sha256})), units:quantity(data, state.variable)?.unit,
      uncertainty:"unknown", selection:normalizeState(data, state)};
  }
  function restoreRecipe(data, value, sha256) {
    assert(value?.schema === "yellowstone.system-view.v1" && hash(sha256) && value.dataset_sha256 === sha256 && value.snapshot === data.snapshot && value.system === data.id, "Recipe belongs to different dataset bytes.");
    assert(Array.isArray(value.sources) && value.sources.length === data.sources.length && value.sources.every((s, i) => s.id === data.sources[i].id && s.sha256 === data.sources[i].sha256), "Recipe source identity differs.");
    assert(value.uncertainty === "unknown" && quantity(data, value.selection?.variable)?.unit === value.units, "Recipe quantity metadata differs.");
    return normalizeState(data, value.selection);
  }
  const api = {finite, finiteExtent, extent:finiteExtent, nearestIndex, frameAtElapsed:D.frameAtElapsed, validate, normalize:validate, capabilities, stats, histogram,
    inRange, entityRows, scatter, gridExtent, gridPoint, sampleGrid, mapTransform, segments, compatible, compare, csvRows, sampleAt, temporalValues,
    recipe, restoreRecipe, validateRecipe:restoreRecipe, quantity, valuesFor, quantityExtent};
  if (typeof module !== "undefined") module.exports = api; else root.YSSystemsModel = api;
})(typeof window === "undefined" ? {} : window);
