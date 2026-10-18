"use strict";

((root) => {
  const finite = Number.isFinite;
  const clamp = (value, lo, hi) => Math.max(lo, Math.min(hi, value));
  function extent(values) {
    let lo = Infinity, hi = -Infinity, count = 0;
    for (const value of values) if (finite(value)) { lo = Math.min(lo, value); hi = Math.max(hi, value); count++; }
    return count ? [lo, hi] : null;
  }
  function nearest(values, target) {
    let index = 0, distance = Infinity;
    values.forEach((value, i) => { if (finite(value) && Math.abs(value - target) < distance) { index = i; distance = Math.abs(value - target); } });
    return index;
  }
  function gridPoint(layer, index) {
    const g = layer.grid;
    if (!Number.isInteger(index) || index < 0 || index >= layer.values.length) return null;
    const row = Math.floor(index / g.nx), column = index % g.nx;
    return {index, row, column, x:g.origin_xz_m[0] + (column + .5) * g.cell_m,
      z:g.origin_xz_m[1] + (g.row_order === "z_increasing" ? row + .5 : g.nz - row - .5) * g.cell_m, value:layer.values[index]};
  }
  function sampleGrid(layer, x, z) {
    const g = layer.grid, column = Math.floor((x - g.origin_xz_m[0]) / g.cell_m), increasingRow = Math.floor((z - g.origin_xz_m[1]) / g.cell_m);
    if (!finite(x) || !finite(z) || column < 0 || column >= g.nx || increasingRow < 0 || increasingRow >= g.nz) return null;
    return gridPoint(layer, (g.row_order === "z_increasing" ? increasingRow : g.nz - increasingRow - 1) * g.nx + column);
  }
  function transect(layer, startIndex, endIndex) {
    const start = gridPoint(layer, startIndex), end = gridPoint(layer, endIndex);
    if (!start || !end) return [];
    const dx = end.x - start.x, dz = end.z - start.z, length = Math.hypot(dx, dz), crossings = [0, 1], g = layer.grid;
    if (!length) return [{...start, distance:0}];
    for (const [origin, delta, base, count] of [[start.x, dx, g.origin_xz_m[0], g.nx], [start.z, dz, g.origin_xz_m[1], g.nz]]) {
      if (!delta) continue;
      for (let edge = 1; edge < count; edge++) { const t = (base + edge * g.cell_m - origin) / delta; if (t > 0 && t < 1) crossings.push(t); }
    }
    crossings.sort((a, b) => a - b);
    const unique = crossings.filter((value, i) => !i || value - crossings[i - 1] > 1e-12), samples = [{...start, distance:0}];
    for (let i = 1; i < unique.length; i++) {
      const t = (unique[i - 1] + unique[i]) / 2, point = sampleGrid(layer, start.x + t * dx, start.z + t * dz);
      if (point && point.index !== samples.at(-1).index) samples.push({...point, distance:t * length});
    }
    if (samples.at(-1).index === end.index) samples[samples.length - 1].distance = length;
    else samples.push({...end, distance:length});
    return samples;
  }
  function classCounts(values) {
    const counts = new Map();
    for (const value of values) if (Number.isInteger(value)) counts.set(value, (counts.get(value) || 0) + 1);
    return counts;
  }
  function defaultTransect(layer) {
    const {nx, nz} = layer.grid; let best = null;
    function scan(start, step, count) {
      let run = null;
      function finish() {
        if (!run) return;
        const range = run.maximum - run.minimum, length = range > 0 ? Math.abs(run.maximumOffset - run.minimumOffset) + 1 : run.length;
        const candidate = {startIndex:range > 0 ? run.maximumIndex : run.first, endIndex:range > 0 ? run.minimumIndex : run.last, length, range, score:range * Math.sqrt(length)};
        if (!best || candidate.score > best.score || candidate.score === best.score && candidate.length > best.length) best = candidate;
        run = null;
      }
      for (let offset = 0; offset < count; offset++) {
        const index = start + offset * step, value = layer.values[index];
        if (!finite(value)) { finish(); continue; }
        if (!run) run = {first:index,last:index,length:0,minimum:value,maximum:value,minimumIndex:index,maximumIndex:index,minimumOffset:offset,maximumOffset:offset};
        run.last = index; run.length++;
        if (value < run.minimum) { run.minimum = value; run.minimumIndex = index; run.minimumOffset = offset; }
        if (value > run.maximum) { run.maximum = value; run.maximumIndex = index; run.maximumOffset = offset; }
      }
      finish();
    }
    for (let row = 0; row < nz; row++) scan(row * nx, 1, nx);
    for (let column = 0; column < nx; column++) scan(column, nx, nz);
    return best;
  }
  const fmt = (value, digits = 2) => finite(value) ? value.toLocaleString("en-US", {maximumFractionDigits:digits}) : "Missing";
  const html = (tag, cls = "", text = "") => { const node = document.createElement(tag); node.className = cls; node.textContent = text; return node; };
  const svg = (tag, attributes = {}, text = "") => { const node = document.createElementNS("http://www.w3.org/2000/svg", tag); for (const [key, value] of Object.entries(attributes)) node.setAttribute(key, value); node.textContent = text; return node; };
  function label(text, control) { const node = html("label", "thermal-control", text); if (!control.hasAttribute("aria-label")) control.setAttribute("aria-label", text); node.append(control); return node; }
  function range(text, maximum, onInput) {
    const control = html("input"); control.type = "range"; control.min = 0; control.max = maximum; control.step = 1; control.value = 0; control.setAttribute("aria-label", text); control.oninput = () => onInput(Number(control.value));
    return {label:label(text, control), control};
  }
  function responsive(host, draw) {
    let lastWidth = 0, destroyed = false;
    const update = () => { if (!host.isConnected) { destroyed = true; observer.disconnect(); return; } const width = Math.floor(host.clientWidth); if (!destroyed && width > 0 && width !== lastWidth) { lastWidth = width; draw(width); } };
    const observer = new ResizeObserver(update); observer.observe(host); update();
    return {destroy() { destroyed = true; observer.disconnect(); }};
  }
  function linePlot(target, width, positions, values, xLabel, unit, selected, onSelect) {
    target.replaceChildren(); const height = 205, plot = svg("svg", {viewBox:`0 0 ${width} ${height}`, role:"img", "aria-label":`${unit} against ${xLabel}. Missing samples remain gaps.`, tabindex:0}); target.append(plot);
    const xr = extent(positions), yr = extent(values); if (!xr || !yr) { target.append(html("p", "thermal-note", "No temperature values on this selection.")); return {update() {}}; }
    const margin = 48, right = width - 14, top = 30, bottom = 159, pad = Math.max((yr[1] - yr[0]) * .08, Math.abs(yr[0]) * .001, .001), lo = yr[0] - pad, hi = yr[1] + pad, digits = Math.max(1, Math.min(6, 1 - Math.floor(Math.log10(hi - lo))));
    const x = value => margin + (value - xr[0]) / (xr[1] - xr[0] || 1) * (right - margin), y = value => bottom - (value - lo) / (hi - lo) * (bottom - top);
    for (let i = 0; i <= 2; i++) { const px = margin + i / 2 * (right - margin), py = top + i / 2 * (bottom - top); plot.append(svg("path", {d:`M${margin} ${py}H${right}`, stroke:"#2a2c31"}), svg("text", {x:margin - 7, y:py + 4, "text-anchor":"end"}, fmt(hi - i / 2 * (hi - lo), digits)), svg("text", {x:px, y:181, "text-anchor":i === 0 ? "start" : i === 2 ? "end" : "middle"}, fmt(xr[0] + i / 2 * (xr[1] - xr[0]), 1))); }
    plot.append(svg("text", {x:margin, y:17}, unit), svg("text", {x:right, y:200, "text-anchor":"end"}, xLabel));
    let path = "", drawing = false;
    values.forEach((value, i) => { if (!finite(value) || !finite(positions[i])) { drawing = false; return; } path += `${drawing ? "L" : "M"}${x(positions[i])},${y(value)} `; drawing = true; });
    plot.append(svg("path", {d:path, fill:"none", stroke:"var(--domain,#8dcaca)", "stroke-width":2}));
    const cursor = svg("path", {stroke:"#a2a4a9", "stroke-dasharray":"3 3"}), point = svg("circle", {r:4, fill:"#e8eaef"}); plot.append(cursor, point);
    let index = selected;
    function update(next) { index = clamp(next, 0, values.length - 1); cursor.setAttribute("d", `M${x(positions[index])} ${top}V${bottom}`); point.setAttribute("cx", x(positions[index])); if (finite(values[index])) point.setAttribute("cy", y(values[index])); point.setAttribute("visibility", finite(values[index]) ? "visible" : "hidden"); }
    plot.onpointermove = event => { const rect = plot.getBoundingClientRect(); if (rect.width) onSelect(nearest(positions, xr[0] + (((event.clientX - rect.left) / rect.width * width - margin) / (right - margin)) * (xr[1] - xr[0]))); };
    plot.onkeydown = event => { if (["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key)) { event.preventDefault(); onSelect(event.key === "Home" ? 0 : event.key === "End" ? values.length - 1 : clamp(index + (event.key === "ArrowRight" ? 1 : -1), 0, values.length - 1)); } };
    update(selected); return {update};
  }
  function raster(layer, colorFor) {
    const g = layer.grid, canvas = document.createElement("canvas"); canvas.width = g.nx; canvas.height = g.nz;
    const context = canvas.getContext("2d"), pixels = context.createImageData(g.nx, g.nz), colors = new Map();
    for (let index = 0; index < layer.values.length; index++) {
      const value = layer.values[index]; if (!finite(value)) continue;
      const color = colorFor(value); if (!color) continue;
      if (!colors.has(color)) colors.set(color, color.startsWith("#") ? [1, 3, 5].map(i => parseInt(color.slice(i, i + 2), 16)) : color.match(/[\d.]+/g).slice(0, 3).map(Number));
      const row = Math.floor(index / g.nx), displayRow = g.row_order === "z_increasing" ? row : g.nz - row - 1, offset = (displayRow * g.nx + index % g.nx) * 4;
      pixels.data.set([...colors.get(color), 255], offset);
    }
    context.putImageData(pixels, 0, 0); return canvas.toDataURL("image/png");
  }
  function mapView(target, width, layer, image, description) {
    const M = root.YSSystemsModel, e = M.gridExtent(layer), height = clamp(width * e.height / e.width, 205, 350), transform = M.mapTransform(e, width, height, 12), a = transform.project(e.x0, e.z0), b = transform.project(e.x1, e.z1);
    target.replaceChildren(); const plot = svg("svg", {viewBox:`0 0 ${width} ${height}`, role:"img", "aria-label":description, tabindex:0});
    plot.append(svg("image", {href:image, x:a.x, y:a.y, width:b.x - a.x, height:b.y - a.y, "image-rendering":"pixelated"}), svg("text", {x:width - 12, y:17, "text-anchor":"end"}, "N ↑")); target.append(plot);
    function atEvent(event) { const rect = plot.getBoundingClientRect(); return rect.width && rect.height ? transform.invert((event.clientX - rect.left) / rect.width * width, (event.clientY - rect.top) / rect.height * height) : null; }
    return {plot, transform, atEvent};
  }
  function pool(host, context) {
    const field = context.field, radii = field.positions, values = field.values, domain = extent(values), radius = extent(radii)?.[1];
    if (!radii?.length || !domain || !finite(radius) || radius <= 0) return null;
    const section = html("section", "thermal-visual thermal-pool"), note = html("p", "thermal-note", "Color follows the saved radial temperature profile. The circular shape is a schematic; it does not show measured pool depth or shoreline."), ringWrap = html("div", "thermal-map"), chart = html("div", "thermal-plot"), readout = html("output", "thermal-readout"); readout.setAttribute("aria-live", "off");
    section.append(note, ringWrap, readout, chart); host.append(section); let index = 0, ring, marker, plotControl;
    const slider = range("Radius sample", values.length - 1, update); section.append(slider.label);
    function update(next) { index = clamp(next, 0, values.length - 1); slider.control.value = index; readout.textContent = `Radius ${fmt(radii[index])} ${field.axis?.unit || "m"} · ${fmt(values[index])} ${field.unit}`; slider.control.setAttribute("aria-valuetext", readout.textContent); plotControl?.update(index); if (ring) ring.setAttribute("r", radii[index] / radius * Number(ring.dataset.maximum)); if (marker) marker.setAttribute("cx", Number(marker.dataset.center) + radii[index] / radius * Number(ring.dataset.maximum)); }
    const observer = responsive(section, width => {
      ringWrap.replaceChildren(); const ringWidth = Math.max(230, ringWrap.clientWidth - 2), chartWidth = Math.max(230, chart.clientWidth - 2), height = 230, cx = ringWidth / 2, cy = 111, maximum = 92, plot = svg("svg", {viewBox:`0 0 ${ringWidth} ${height}`, role:"img", "aria-label":"Authored radial temperature profile shown as concentric rings. Probe with the radius control below.", tabindex:0});
      for (let i = values.length - 1; i >= 0; i--) { const edge = i === values.length - 1 ? radius : (radii[i] + radii[i + 1]) / 2; plot.append(svg("circle", {cx, cy, r:Math.max(0, edge / radius * maximum), fill:finite(values[i]) ? root.YSData.color(values[i], domain) : "#0b0e14"})); }
      ring = svg("circle", {cx, cy, r:0, fill:"none", stroke:"#e8eaef", "stroke-width":1.5}); ring.dataset.maximum = maximum;
      marker = svg("circle", {cx, cy, r:4, fill:"#e8eaef", stroke:"#07080b"}); marker.dataset.center = cx;
      plot.append(svg("path", {d:`M${cx} ${cy}H${cx + maximum}`, stroke:"#07080b", "stroke-width":1}), ring, marker, svg("text", {x:12, y:222}, `${fmt(domain[0])}–${fmt(domain[1])} ${field.unit}`), svg("text", {x:ringWidth - 12, y:222, "text-anchor":"end"}, `0–${fmt(radius)} m radius`)); ringWrap.append(plot);
      plot.onpointermove = event => { const rect = plot.getBoundingClientRect(), x = (event.clientX - rect.left) / rect.width * ringWidth, y = (event.clientY - rect.top) / rect.height * height; update(nearest(radii, clamp(Math.hypot(x - cx, y - cy) / maximum, 0, 1) * radius)); };
      plot.onkeydown = event => { if (["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key)) { event.preventDefault(); update(event.key === "Home" ? 0 : event.key === "End" ? values.length - 1 : index + (event.key === "ArrowRight" ? 1 : -1)); } };
      plotControl = linePlot(chart, chartWidth, radii, values, "radius (m)", field.unit, index, update); update(index);
    });
    return observer;
  }
  function outflow(host, context) {
    const layer = context.field, domain = extent(layer.values); if (!domain) return null;
    const section = html("section", "thermal-visual thermal-outflow"), map = html("div", "thermal-map"), chart = html("div", "thermal-plot"), controls = html("div", "thermal-endpoints"), readout = html("output", "thermal-readout"), cellReadout = html("output", "thermal-cell-readout"), note = html("p", "thermal-note", "Choose two cells to cut a straight transect through the saved temperature map. Distance is along this line, rather than the routed flow path. Dark cells have no saved temperature.");
    section.append(note, map, cellReadout, controls, readout, chart); host.append(section);
    const initial = defaultTransect(layer);
    let a = initial.startIndex, b = initial.endIndex, active = "B", samples = [], index = 0, width = 0, mapControl, path, startMarker, endMarker, cursor, plotControl;
    const palette = Array.from({length:256}, (_, i) => root.YSData.color(domain[0] + i / 255 * (domain[1] - domain[0]), domain)), image = raster(layer, value => palette[clamp(Math.round((value - domain[0]) / (domain[1] - domain[0] || 1) * 255), 0, 255)]), edit = html("select"); for (const id of ["A", "B"]) { const option = html("option", "", `Endpoint ${id}`); option.value = id; edit.append(option); } edit.value = active; edit.onchange = () => { active = edit.value; }; controls.append(label("Map click moves", edit));
    const inputs = {};
    for (const id of ["A", "B"]) {
      const group = html("fieldset", "thermal-endpoint"), legend = html("legend", "", `Endpoint ${id}`); group.append(legend); inputs[id] = {};
      for (const [axis, maximum] of [["column", layer.grid.nx], ["row", layer.grid.nz]]) { const control = html("input"); control.type = "number"; control.min = 1; control.max = maximum; control.step = 1; control.setAttribute("aria-label", `Endpoint ${id} ${axis}`); inputs[id][axis] = control; control.onchange = () => { const current = root.YSSystemsModel.gridPoint(layer, id === "A" ? a : b), value = Number(control.value); if (!Number.isInteger(value) || value < 1 || value > maximum) { updateEndpoints(); return; } const next = axis === "column" ? current.row * layer.grid.nx + value - 1 : (value - 1) * layer.grid.nx + current.column; if (id === "A") a = next; else b = next; redraw(); }; group.append(label(axis === "column" ? "Column" : "Native row", control)); }
      controls.append(group);
    }
    const slider = range("Probe transect sample", 0, update); section.append(slider.label, html("p", "thermal-note", `Saved range ${fmt(domain[0])}–${fmt(domain[1])} ${layer.unit}. Local coordinates: x east, z south. Each sample uses the native cell value; missing cells break the profile.`));
    function updateEndpoints() { for (const id of ["A", "B"]) { const point = root.YSSystemsModel.gridPoint(layer, id === "A" ? a : b); inputs[id].column.value = point.column + 1; inputs[id].row.value = point.row + 1; } }
    function update(next) { index = clamp(next, 0, samples.length - 1); const point = samples[index]; if (!point) return; slider.control.value = index; readout.textContent = `${fmt(point.distance)} m from A · ${fmt(point.value)} ${layer.unit} · cell ${point.column + 1}, ${point.row + 1}`; slider.control.setAttribute("aria-valuetext", readout.textContent); plotControl?.update(index); if (cursor && mapControl) { const p = mapControl.transform.project(point.x, point.z); cursor.setAttribute("cx", p.x); cursor.setAttribute("cy", p.y); } }
    function redraw() {
      if (!width) return; updateEndpoints(); samples = transect(layer, a, b); index = Math.min(index, samples.length - 1); slider.control.max = samples.length - 1;
      mapControl = mapView(map, width, layer, image, "Native steady outflow temperature map. Use endpoint controls or click to select a straight transect."); const p = mapControl.transform.project(root.YSSystemsModel.gridPoint(layer, a).x, root.YSSystemsModel.gridPoint(layer, a).z), q = mapControl.transform.project(root.YSSystemsModel.gridPoint(layer, b).x, root.YSSystemsModel.gridPoint(layer, b).z);
      path = svg("path", {d:`M${p.x} ${p.y}L${q.x} ${q.y}`, stroke:"#e8eaef", "stroke-width":1.5, "stroke-dasharray":"4 3"}); startMarker = svg("circle", {cx:p.x, cy:p.y, r:5, fill:"#07080b", stroke:"#e8eaef"}); endMarker = svg("circle", {cx:q.x, cy:q.y, r:5, fill:"#e8eaef", stroke:"#07080b"}); cursor = svg("circle", {r:4, fill:"var(--domain,#8dcaca)", stroke:"#07080b"});
      const markerLabel = (point, text) => svg("text", {x:clamp(point.x + 8, 12, width - 12), y:Math.max(30, point.y - 8), "text-anchor":point.x > width - 28 ? "end" : "start", class:"thermal-map-letter"}, text);
      mapControl.plot.append(path, startMarker, endMarker, markerLabel(p, "A"), markerLabel(q, "B"), cursor);
      mapControl.plot.onclick = event => { const world = mapControl.atEvent(event), point = world && root.YSSystemsModel.sampleGrid(layer, world.x, world.z); if (!point) return; if (active === "A") a = point.index; else b = point.index; redraw(); };
      mapControl.plot.onpointermove = event => { const world = mapControl.atEvent(event), point = world && root.YSSystemsModel.sampleGrid(layer, world.x, world.z); cellReadout.textContent = point ? `Map: x ${fmt(point.x)}, z ${fmt(point.z)} m · ${fmt(point.value)} ${layer.unit}` : "Move over the map to inspect a cell."; };
      plotControl = linePlot(chart, width, samples.map(point => point.distance), samples.map(point => point.value), "straight-line distance (m)", layer.unit, index, update); update(index);
    }
    const observer = responsive(section, next => { width = next; redraw(); }); cellReadout.textContent = "Move over the map to inspect a cell."; return observer;
  }
  function mat(host, context) {
    const layer = context.visual; if (!layer?.grid || !Array.isArray(layer.values) || !layer.legend?.length) return null;
    const section = html("section", "thermal-visual thermal-mat"), map = html("div", "thermal-map"), controls = html("select"), readout = html("output", "thermal-readout"), cellReadout = html("output", "thermal-cell-readout"), legend = html("div", "thermal-class-legend"), counts = classCounts(layer.values), labels = new Map(layer.legend.map(item => [item.class_id, item])), colors = new Map(layer.legend.map((item, i) => [item.class_id, item.rgb ? `rgb(${item.rgb.join(",")})` : root.YSData.color(i, [0, Math.max(1, layer.legend.length - 1)])]));
    const all = html("option", "", "All saved surface classes"); all.value = "all"; controls.append(all); for (const item of layer.legend) { const option = html("option", "", item.label); option.value = item.class_id; controls.append(option); }
    section.append(html("p", "thermal-note", "Select a modeled surface class to highlight where it occurs. Colors come from the model legend; they are not an aerial photograph."), label("Highlight surface class", controls), map, readout, cellReadout, legend); host.append(section);
    let selected = null, index = layer.values.findIndex(Number.isInteger), width = 0, mapControl, cursor;
    const slider = range("Probe native classified cell", layer.values.length - 1, update); section.append(slider.label, html("p", "thermal-note", `Native grid: ${layer.grid.nx} × ${layer.grid.nz} cells, ${fmt(layer.grid.cell_m)} m spacing. Dark cells have no saved class. Local coordinates: x east, z south. This is one saved surface classification.`));
    function update(next) { index = clamp(next, 0, layer.values.length - 1); const point = root.YSSystemsModel.gridPoint(layer, index), item = labels.get(point.value); slider.control.value = index; cellReadout.textContent = `Cell ${point.column + 1}, ${point.row + 1} · x ${fmt(point.x)}, z ${fmt(point.z)} m · ${item?.label || "No saved class"}`; slider.control.setAttribute("aria-valuetext", cellReadout.textContent); if (cursor && mapControl) { const p = mapControl.transform.project(point.x, point.z); cursor.setAttribute("cx", p.x); cursor.setAttribute("cy", p.y); } }
    function draw() {
      if (!width) return; const image = raster(layer, value => selected === null || value === selected ? colors.get(value) : "#262b34"); mapControl = mapView(map, width, layer, image, "Native modeled surface classification. A selected class stays colored while other classes are muted."); cursor = svg("circle", {r:4, fill:"none", stroke:"#e8eaef", "stroke-width":1.5}); mapControl.plot.append(cursor);
      mapControl.plot.onpointermove = event => { const world = mapControl.atEvent(event), point = world && root.YSSystemsModel.sampleGrid(layer, world.x, world.z); if (point) update(point.index); };
      mapControl.plot.onclick = event => { const world = mapControl.atEvent(event), point = world && root.YSSystemsModel.sampleGrid(layer, world.x, world.z); if (!point || !Number.isInteger(point.value)) return; selected = point.value; controls.value = selected; draw(); };
      mapControl.plot.onkeydown = event => { if (["ArrowLeft", "ArrowRight", "ArrowUp", "ArrowDown", "Home", "End"].includes(event.key)) { event.preventDefault(); update(event.key === "Home" ? 0 : event.key === "End" ? layer.values.length - 1 : index + (event.key === "ArrowUp" ? -layer.grid.nx : event.key === "ArrowDown" ? layer.grid.nx : event.key === "ArrowLeft" ? -1 : 1)); } };
      const count = selected === null ? [...counts.values()].reduce((sum, value) => sum + value, 0) : counts.get(selected) || 0, area = count * layer.grid.cell_m ** 2;
      readout.textContent = `${selected === null ? "All saved classes" : labels.get(selected)?.label} · ${fmt(count, 0)} cells · ${fmt(area)} m²`;
      legend.replaceChildren(); for (const item of layer.legend) { const row = html("div", "thermal-class-row"), chip = html("span", "thermal-chip"), text = html("span", "", item.label); chip.style.background = colors.get(item.class_id); row.append(chip, text, html("span", "", `${fmt((counts.get(item.class_id) || 0) * layer.grid.cell_m ** 2)} m²`)); if (selected !== null && selected !== item.class_id) row.classList.add("is-muted"); legend.append(row); } update(Math.max(0, index));
    }
    controls.onchange = () => { selected = controls.value === "all" ? null : Number(controls.value); draw(); }; const observer = responsive(section, next => { width = next; draw(); }); return observer;
  }
  function render(host, context) {
    if (context.process === "pool" && context.view.collection === "profiles") return pool(host, context);
    if (context.process === "outflow_cooling" && context.field.kind === "grid") return outflow(host, context);
    if (context.process === "mat" && context.view.id === "community_area") return mat(host, context);
    return null;
  }
  const api = {render, extent, nearest, gridPoint, sampleGrid, transect, classCounts, defaultTransect};
  if (typeof module !== "undefined") module.exports = api; else root.YSThermalCharts = api;
})(typeof window === "undefined" ? {} : window);
