"use strict";

window.YSCoverage = {
  init(data) {
    const geo = data.coverage;
    if (!geo) throw Error("Geographic snapshot unavailable");
    const $ = id => document.getElementById(id), NS = "http://www.w3.org/2000/svg";
    const make = (tag, attrs = {}, text = "") => {
      const node = document.createElementNS(NS, tag);
      Object.entries(attrs).forEach(([key, value]) => node.setAttribute(key, value));
      node.textContent = text; return node;
    };
    const html = (tag, className, text = "") => { const el = document.createElement(tag); el.className = className; el.textContent = text; return el; };
    const svg = $("coverage-map"), world = $("coverage-world");
    let width = 1200, height = 700, camera = { x: 0, y: 0, k: .3 }, target = { ...camera }, dragging = null, moved = false, full = false;
    const reduced = matchMedia("(prefers-reduced-motion: reduce)").matches;
    const layers = new Map(), labels = [], pointers = new Map();
    const extent = geo.extent, half = extent / 2;
    const line = points => points.map((p, i) => `${i ? "L" : "M"}${p[0]},${p[1]}`).join(" ");
    const layer = name => { const group = make("g", { "data-geo-layer": name }); world.append(group); layers.set(name, group); return group; };
    const terrain = layer("terrain");
    terrain.append(make("image", { href: "/dashboard/terrain.png", x: -half, y: -half, width: extent, height: extent, opacity: .7 }));
    const heat = layer("heat"), heatGrid = geo.heat.grid;
    heat.append(make("image", { href: "/dashboard/ground-heat.png", x: heatGrid.origin_xz_m[0], y: heatGrid.origin_xz_m[1], width: heatGrid.nx*heatGrid.cell_m, height:heatGrid.nz*heatGrid.cell_m, class:"ground-heat-image", "pointer-events":"none" }));
    heat.style.display = "none";
    const footprint = layer("coverage");
    footprint.append(make("rect", { x: -half, y: -half, width: extent, height: extent, class: "coverage-footprint" }));
    const core = geo.thermal_extent;
    footprint.append(make("rect", { x: core.origin_xz_m[0], y: core.origin_xz_m[1], width: core.nx * core.cell_size_m, height: core.nz * core.cell_size_m, class: "coverage-footprint thermal-footprint" }));
    footprint.append(make("rect", { x: -half, y: -half, width: extent, height: extent, fill: "url(#coverage-grid)", "pointer-events": "none" }));
    const coreLabel = make("text", { x: core.origin_xz_m[0] + 15, y: core.origin_xz_m[1] + 30, class: "geo-boundary-label" }, "THERMAL FIELD · 1.28 km GRID"); footprint.append(coreLabel); labels.push({ node: coreLabel, size: 8 });
    const paths = layer("paths"), water = layer("waterways"), pools = layer("pools"), habitats = layer("habitats");
    function describe(event, info, permanent = false) {
      if (moved && permanent) return;
      if (!permanent) {
        const tip = $("coverage-tooltip"); tip.replaceChildren(html("div", "", info.label), html("small", "", info.type));
        const rect = svg.getBoundingClientRect();
        tip.style.left = `${Math.max(10, Math.min(width - 270, event.clientX - rect.left + 15))}px`;
        tip.style.top = `${Math.max(10, Math.min(height - 80, event.clientY - rect.top + 16))}px`;
        tip.hidden = false; return;
      }
      const box = $("coverage-detail-content"); box.replaceChildren(html("p", "eyebrow", info.type.toUpperCase()), html("h2", "", info.label));
      if (info.value) box.append(html("div", "value", info.value));
      box.append(html("p", "", info.description));
      if (info.limit) box.append(html("p", "", info.limit));
      if (info.process) { const link = html("a", "", "Analyze this process →"); link.href = `/dashboard/systems/#${info.process}`; link.addEventListener("click",event=>{if(window.YSExplore){event.preventDefault();window.YSExplore.openProcess(info.process);}}); box.append(link); }
      $("coverage-detail").hidden = false; $("coverage-tooltip").hidden = true;
    }
    function interactive(node, info) {
      node.classList.add("coverage-feature"); node.setAttribute("role", "button"); node.setAttribute("tabindex", "0"); node.setAttribute("aria-label", `Inspect ${info.label}`);
      node.addEventListener("pointerenter", e => describe(e, info)); node.addEventListener("pointerleave", () => { $("coverage-tooltip").hidden = true; });
      node.addEventListener("click", e => { e.stopPropagation(); describe(e, info, true); });
      node.addEventListener("keydown", e => { if (["Enter", " "].includes(e.key)) { e.preventDefault(); describe(e, info, true); } });
    }
    geo.routes.forEach(route => {
      const node = make("path", { d: line(route.points), class: `coverage-route${route.kind === "road" ? "" : " coverage-trail"}` });
      interactive(node, { label: route.name || "Mapped path", type: "Mapped geographic feature", description: "The project places this route within the georeferenced terrain. Local elevation profiles and bridge approaches include authored geometry.", process: "grazers" }); paths.append(node);
    });
    geo.rivers.forEach(river => {
      const node = make("path", { d: line(river.points), class: "coverage-river" });
      interactive(node, { label: river.name || "Mapped waterway", type: "Mapped waterway", description: "This centerline is part of the geographic model. The bright river-cell overlay identifies the channel used by the saved transport simulation.", limit: "Mapped centerlines do not establish measured channel widths or submerged depths.", process: "transport" }); water.append(node);
    });
    const cells = data.river.cells;
    water.append(make("path", { d: line(cells.map(c => [c.x, c.z])), fill: "none", stroke: "#a3dcff", "stroke-width": 3, "vector-effect": "non-scaling-stroke", "pointer-events": "none", opacity: .8 }));
    geo.pools.forEach(pool => {
      const node = make("path", { d: line(pool.ring) + "Z", class: `coverage-pool${pool.thermal ? " is-thermal" : ""}` });
      interactive(node, { label: pool.name, type: pool.thermal ? "Mapped thermal feature" : "Mapped water body", description: "Outline and area come from mapped geography. Temperatures and the depth profile are authored values, not measurements. Bathymetry and reservoir heat balance are not modeled.", value: `${Math.round(pool.area_m2).toLocaleString("en-US")} m² mapped area`, process: "pool" }); pools.append(node);
      if (pool.thermal) {
        const offset = /prismatic/i.test(pool.name) ? [-60, 25] : /excelsior/i.test(pool.name) ? [85,-20] : /turquoise/i.test(pool.name) ? [35,-75] : [30,35];
        const label = make("text", { "text-anchor": offset[0] < 0 ? "end" : "start", class: "geo-feature-label" }, pool.name);
        const leader = make("path", { fill: "none", stroke: "#bd9b78", "stroke-width": .5, "stroke-opacity": .65, "vector-effect": "non-scaling-stroke", "pointer-events": "none" });
        pools.append(leader,label); labels.push({ node: label, size: 11, anchor: pool.center, offset, leader });
      }
    });
    geo.patches.forEach(patch => {
      const node = make("circle", { cx: patch.center[0], cy: patch.center[1], r: patch.radius, class: "coverage-patch" });
      interactive(node, { label: patch.label, type: "Authored habitat patch", description: "This patch supplies a simplified spatial unit for vegetation, soil water, and ecological responses.", value: `${patch.radius} m patch radius`, limit: "Patch boundaries, carrying capacities, and local ecological rates are authored. They are not surveyed habitat boundaries.", process: "vegetation" }); habitats.append(node);
    });
    const anchorLayer = layer("anchors");
    geo.anchors.forEach(anchor => {
      const marker = make("circle", { cx: anchor.position[0], cy: anchor.position[1], r: 8, fill: "#e4e9f3", stroke: "#11141b", "stroke-width": 2, "vector-effect": "non-scaling-stroke" });
      interactive(marker, { label: anchor.label, type: "Environment viewpoint", description: "A starting location in the rendered Yellowstone environment, placed on the geographic model.", limit: "The browser presents geographic and scientific layers independently of the game." }); anchorLayer.append(marker);
    });
    const inset = $("coverage-inset"), insetScale = 100 / extent;
    inset.append(make("rect", { x: 10, y: 10, width: 100, height: 100, fill: "#111823", stroke: "#5c7394", "stroke-width": .6 }));
    geo.rivers.forEach(r => inset.append(make("path", { d: line(r.points.map(p => [60 + p[0] * insetScale, 60 + p[1] * insetScale])), stroke: "#5698c9", fill: "none", "stroke-width": .8 })));
    const insetView = make("rect", { fill: "#a4c7ff", "fill-opacity": .08, stroke: "#c7d9f5", "stroke-width": .8 }); inset.append(insetView);
    const fact = (label, value) => { const el = html("div", ""); el.append(html("strong", "", value), html("span", "", label)); $("coverage-facts").append(el); };
    fact("GEOGRAPHIC EXTENT", `${(extent * extent / 1e6).toFixed(2)} km²`); fact("MODELED RIVER", `${(data.river.length_m / 1000).toFixed(2)} km`);
    fact("TERRAIN GRID", `${geo.grid_step_m} m`); fact("TRANSPORT CELLS", String(cells.length));
    function fit(fullExtent = false, instant = false) {
      full = fullExtent;
      const mobile = width < 721;
      const span = fullExtent ? extent * 1.12 : mobile ? 1900 : 1750;
      const k = Math.min((width - (mobile ? 0 : 280)) / span, (height - (mobile ? 100 : 70)) / span);
      target = { k, x: fullExtent && mobile ? width / 2 : width * (mobile ? .56 : .57) + 60 * k, y: height * (mobile ? .61 : .53) };
      if (instant || reduced) camera = { ...target };
      $("basin-view").setAttribute("aria-pressed", String(!full)); $("coverage-fit").setAttribute("aria-pressed", String(full));
    }
    function zoom(factor, x = width * .57, y = height * .53) {
      const k = Math.max(.04, Math.min(3, target.k * factor)), ratio = k / target.k;
      target = { k, x: x - (x - target.x) * ratio, y: y - (y - target.y) * ratio };
      if (reduced) camera = { ...target };
    }
    $("coverage-fit").addEventListener("click", () => fit(true)); $("basin-view").addEventListener("click", () => fit(false));
    $("coverage-plus").addEventListener("click", () => zoom(1.5)); $("coverage-minus").addEventListener("click", () => zoom(1 / 1.5));
    $("close-coverage-detail").addEventListener("click", () => { $("coverage-detail").hidden = true; });
    document.querySelectorAll("[data-layer]").forEach(input => input.addEventListener("change", () => {
      layers.get(input.dataset.layer).style.display = input.checked ? "" : "none";
      if (input.dataset.layer === "heat") { $("heat-legend").hidden = !input.checked; $("heat-probe").hidden = !input.checked; }
    }));
    const parameters = geo.heat.parameters;
    $("heat-legend").textContent = `Authored heat flux · W/m²\nBackground ${parameters.background_w_m2} · Apron ${parameters.apron_w_m2} · Pool ${parameters.pool_w_m2}`;
    svg.addEventListener("pointermove",event => {
      if (!document.querySelector('[data-layer="heat"]').checked || dragging) return;
      const rect = svg.getBoundingClientRect(), x = (event.clientX-rect.left-camera.x)/camera.k, z = (event.clientY-rect.top-camera.y)/camera.k;
      const column = Math.floor((x-heatGrid.origin_xz_m[0])/heatGrid.cell_m), row = Math.floor((z-heatGrid.origin_xz_m[1])/heatGrid.cell_m);
      if (column<0 || row<0 || column>=heatGrid.nx || row>=heatGrid.nz) { $("heat-probe").textContent="Outside ground-heat field"; return; }
      const values = geo.heat.values, value = Array.isArray(values[0]) ? values[row][column] : values[row*heatGrid.nx+column];
      $("heat-probe").textContent=`Authored ground heat: ${value} W/m² · ${heatGrid.cell_m} m cell`;
    });
    if (innerWidth < 721) document.querySelector(".map-layers").open = false;
    $("show-landscape").addEventListener("click", () => $("landscape-dialog").showModal()); $("close-landscape").addEventListener("click", () => $("landscape-dialog").close());
    document.querySelectorAll('.exploration-links a').forEach(link=>link.addEventListener("click",event=>{if(link.getAttribute("href")==="/dashboard/systems/"&&window.YSExplore){event.preventDefault();window.YSExplore.setMode("systems");}}));
    svg.addEventListener("wheel", event => { event.preventDefault(); const r = svg.getBoundingClientRect(); zoom(Math.exp(-event.deltaY * .002), event.clientX - r.left, event.clientY - r.top); }, { passive: false });
    svg.addEventListener("pointerdown", e => { pointers.set(e.pointerId,{ x: e.clientX, y: e.clientY }); dragging = true; moved = false; });
    svg.addEventListener("pointermove", e => {
      if (!dragging || !pointers.has(e.pointerId)) return;
      const previous = pointers.get(e.pointerId), dx = e.clientX - previous.x, dy = e.clientY - previous.y;
      if (Math.abs(dx) + Math.abs(dy) > 2) { moved = true; svg.setPointerCapture(e.pointerId); svg.classList.add("dragging"); }
      if (pointers.size === 2) {
        const other = [...pointers.entries()].find(([id]) => id !== e.pointerId)[1];
        const before = Math.hypot(previous.x-other.x,previous.y-other.y), after = Math.hypot(e.clientX-other.x,e.clientY-other.y);
        const rect = svg.getBoundingClientRect();
        if (before > 5) zoom(after/before,(previous.x+other.x)/2-rect.left,(previous.y+other.y)/2-rect.top);
        target.x += dx/2; target.y += dy/2;
      } else { target.x += dx; target.y += dy; }
      pointers.set(e.pointerId,{ x:e.clientX,y:e.clientY }); camera = { ...target }; $("coverage-tooltip").hidden = true;
    });
    ["pointerup", "pointercancel"].forEach(name => svg.addEventListener(name, event => { pointers.delete(event.pointerId); if (!pointers.size) { dragging = null; svg.classList.remove("dragging"); } }));
    svg.addEventListener("keydown", e => {
      if (!["+", "=", "-", "0", "ArrowUp", "ArrowDown", "ArrowLeft", "ArrowRight"].includes(e.key)) return;
      e.preventDefault(); if (["+", "="].includes(e.key)) zoom(1.4); if (e.key === "-") zoom(1 / 1.4); if (e.key === "0") fit(true);
      if (e.key === "ArrowUp") target.y += 60; if (e.key === "ArrowDown") target.y -= 60; if (e.key === "ArrowLeft") target.x += 60; if (e.key === "ArrowRight") target.x -= 60;
    });
    new ResizeObserver(entries => { width = entries[0].contentRect.width; height = entries[0].contentRect.height; if (width && height) fit(full, true); }).observe(svg);
    let last = 0;
    function draw(now) {
      requestAnimationFrame(draw); if (document.hidden || now - last < 30) return; last = now;
      ["x", "y", "k"].forEach(key => { camera[key] += (target[key] - camera[key]) * (reduced ? 1 : .2); });
      world.setAttribute("transform", `translate(${camera.x},${camera.y}) scale(${camera.k})`);
      labels.forEach(({ node, size, anchor, offset, leader }) => {
        node.style.fontSize = `${size / camera.k}px`; node.style.strokeWidth = `${3 / camera.k}px`;
        if (anchor) {
          const x = anchor[0] + offset[0] / camera.k, y = anchor[1] + offset[1] / camera.k;
          node.setAttribute("x",x); node.setAttribute("y",y);
          leader.setAttribute("d",`M${anchor[0]},${anchor[1]}L${x},${y-4/camera.k}`);
        }
      });
      anchorLayer.querySelectorAll("circle").forEach(node => node.setAttribute("r", 3 / camera.k));
      const x = Math.max(-half, -camera.x / camera.k), y = Math.max(-half, -camera.y / camera.k);
      const maxX = Math.min(half, (width - camera.x) / camera.k), maxY = Math.min(half, (height - camera.y) / camera.k);
      insetView.setAttribute("x", 60 + x * insetScale); insetView.setAttribute("y", 60 + y * insetScale);
      insetView.setAttribute("width", Math.max(0, (maxX - x) * insetScale)); insetView.setAttribute("height", Math.max(0, (maxY - y) * insetScale));
      const meters = camera.k > .4 ? 100 : camera.k > .18 ? 250 : 500;
      $("coverage-scale-line").style.width = `${meters * camera.k}px`; $("coverage-scale-label").textContent = `${meters} m`;
    }
    fit(false, true); requestAnimationFrame(draw);
  }
};
