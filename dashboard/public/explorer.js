"use strict";

(() => {
  const $ = id => document.getElementById(id);
  const NS = "http://www.w3.org/2000/svg";
  const reducedMotion = matchMedia("(prefers-reduced-motion: reduce)").matches;
  const svgElement = (tag, attributes = {}, text = "") => {
    const element = document.createElementNS(NS, tag);
    Object.entries(attributes).forEach(([key, value]) => element.setAttribute(key, value));
    if (text) element.textContent = text;
    return element;
  };
  const element = (tag, className, text) => {
    const result = document.createElement(tag);
    if (className) result.className = className;
    if (text) result.textContent = text;
    return result;
  };
  const clamp = (n, min, max) => Math.max(min, Math.min(max, n));
  let data, domainById, nodeById;
  let camera = { x: 0, y: 0, k: 1 }, target = { ...camera }, baseScale = 1;
  let focusedDomain = null, selectedNode = null, hoveredNode = null;
  let detail = 0, isRiver = false, moved = false, skipClick = false;
  let showResearch = false;
  const currentPage = document.body.dataset.page || "overview";
  let lastRender = 0, frameIndex = 0, playing = false, playTime = 0, lastPlayback = 0, selectedCell = null;
  const pointers = new Map();
  const particles = [], edgeElements = [], nodeElements = [], clusterElements = [];
  const map = $("network");
  let bounds = { width: 1200, height: 800 };

  function announce(text) { $("announcer").textContent = text; }
  function tooltip(event, title, subtitle = "") {
    const box = $("tooltip");
    box.replaceChildren(element("div", "", title));
    if (subtitle) box.append(element("small", "", subtitle));
    const rect = map.getBoundingClientRect();
    box.style.left = `${clamp(event.clientX - rect.left + 14, 8, bounds.width - 265)}px`;
    box.style.top = `${clamp(event.clientY - rect.top + 15, 8, bounds.height - 90)}px`;
    box.hidden = false;
  }

  function positionNodes(domain) {
    const nodes = data.nodes.filter(node => node.domain === domain.id && (showResearch || node.implementation !== "research"));
    const columns = nodes.length > 6 ? 3 : 2;
    const rows = Math.ceil(nodes.length / columns);
    const spacingX = domain.radius * (columns === 3 ? .52 : .79);
    const spacingY = domain.radius * (rows > 2 ? .48 : .65);
    nodes.forEach((node, index) => {
      const row = Math.floor(index / columns), col = index % columns;
      const rowCount = Math.min(columns, nodes.length - row * columns);
      node.x = domain.x + (col - (rowCount - 1) / 2) * spacingX;
      node.y = domain.y + (row - (rows - 1) / 2) * spacingY + 13;
    });
    return nodes;
  }

  function curve(a, b, bend = 0) {
    const dx = b.x - a.x, dy = b.y - a.y;
    const length = Math.hypot(dx, dy) || 1;
    return { a, b, c: { x: (a.x + b.x) / 2 - dy / length * bend, y: (a.y + b.y) / 2 + dx / length * bend } };
  }
  function pathFor(c) { return `M${c.a.x},${c.a.y} Q${c.c.x},${c.c.y} ${c.b.x},${c.b.y}`; }
  function pointAt(c, t) {
    return { x: (1 - t) ** 2 * c.a.x + 2 * (1 - t) * t * c.c.x + t * t * c.b.x,
      y: (1 - t) ** 2 * c.a.y + 2 * (1 - t) * t * c.c.y + t * t * c.b.y };
  }

  function createMap() {
    const narrow = innerWidth < 721;
    const layout = narrow ? [[-220, -430], [220, -430], [220, 0], [-220, 0], [-220, 430], [220, 430]] :
      [[0, -230], [-680, -230], [680, -230], [0, 245], [-680, 245], [680, 245]];
    data.domains.forEach((domain, index) => { [domain.x, domain.y] = layout[index]; });
    data.domains.forEach((domain, index) => {
      const nodes = positionNodes(domain);
      const group = svgElement("g", { class: "cluster", role: "button", tabindex: "0",
        "aria-label": `Explore ${domain.label}`, "data-domain": domain.id, style: `--domain:${domain.color}` });
      group.append(svgElement("circle", { cx: domain.x, cy: domain.y, r: domain.radius + 15, class: "outer-ring" }));
      group.append(svgElement("circle", { cx: domain.x, cy: domain.y, r: domain.radius, class: "domain-fill" }));
      const overview = svgElement("g", { class: "overview" });
      overview.append(svgElement("circle", { cx: domain.x, cy: domain.y, r: domain.radius, fill: "transparent" }));
      overview.append(svgElement("circle", { cx: domain.x, cy: domain.y, r: domain.radius * .75, class: "inner-ring" }));
      nodes.forEach((node, i) => {
        const angle = i * 2.39996 + index;
        overview.append(svgElement("circle", { cx: domain.x + Math.cos(angle) * domain.radius * .75,
          cy: domain.y + Math.sin(angle) * domain.radius * .75, r: 3.8 + (i % 3), class: `overview-mark${node.implementation === "research" ? " is-research" : node.display === "python" ? " is-python" : ""}` }));
      });
      overview.append(svgElement("text", { x: domain.x, y: domain.y - 55, class: "domain-number", "text-anchor": "middle" }, `0${index + 1}`));
      const domainTitle = svgElement("text", { x: domain.x, y: domain.y - 8, class: "domain-label" });
      if (domain.label.includes("biosphere")) {
        domainTitle.append(svgElement("tspan", { x: domain.x, dy: "-8" }, domain.label.split(" ")[0]), svgElement("tspan", { x: domain.x, dy: "1.15em" }, "biosphere"));
      } else domainTitle.textContent = domain.label;
      overview.append(domainTitle);
      overview.append(svgElement("text", { x: domain.x, y: domain.y + (domain.label.includes("biosphere") ? 60 : 20), class: "domain-sub" }, `${String(nodes.length).padStart(2, "0")} COMPONENTS`));
      overview.append(svgElement("text", { x: domain.x, y: domain.y + (domain.label.includes("biosphere") ? 95 : 59), class: "domain-sub", opacity: ".55" }, "+ EXPLORE"));
      group.append(overview);
      const expandedLabel = svgElement("text", { x: domain.x, y: domain.y - domain.radius + 37,
        class: "domain-label", "font-size": "15" }, domain.label);
      group.append(expandedLabel);
      const processes = svgElement("g", { class: "processes" });
      nodes.forEach(node => {
        const process = svgElement("g", { class: `process-node${node.implementation === "research" ? " research-node" : node.display === "python" ? " python-node" : ""}`, role: "button", tabindex: "-1",
          "aria-label": `Inspect ${node.label}`, "data-node": node.id, transform: `translate(${node.x},${node.y})` });
        process.append(svgElement("circle", { r: 20, class: "node-halo" }));
        process.append(node.kind === "prescribed" ? svgElement("path", { d: "M0 -7L7 0L0 7L-7 0Z", class: "prescribed-dot" }) :
          svgElement("circle", { r: 7, class: "node-dot" }));
        const words = node.label.split(" ");
        const split = node.label.length > 14 ? Math.ceil(words.length / 2) : words.length;
        process.append(svgElement("text", { y: 36, class: "node-label" }, words.slice(0, split).join(" ")));
        if (split < words.length) process.append(svgElement("text", { y: 49, class: "node-label" }, words.slice(split).join(" ")));
        const deeper = svgElement("text", { y: split < words.length ? 62 : 50, class: "detail-line" },
          node.kind === "prescribed" ? "PRESCRIBED INPUT" : node.units.split(";")[0].slice(0, 30));
        process.append(deeper);
        process.addEventListener("click", event => { event.stopPropagation(); if (!skipClick) inspectNode(node.id); });
        process.addEventListener("keydown", event => { if (["Enter", " "].includes(event.key)) { event.preventDefault(); event.stopPropagation(); inspectNode(node.id); } });
        process.addEventListener("pointerenter", event => { hoveredNode = node.id; highlight(); tooltip(event, node.label, `${node.summary} ${node.implementation === "research" ? "Research extension." : node.display === "rendered" ? "Runtime binding available." : "Python model."}`); });
        process.addEventListener("pointerleave", () => { hoveredNode = null; highlight(); $("tooltip").hidden = true; });
        processes.append(process); nodeElements.push({ node, process, deeper });
      });
      group.append(processes); $("clusters").append(group);
      group.addEventListener("click", () => { if (!skipClick) focusDomain(domain.id); });
      group.addEventListener("keydown", event => { if (["Enter", " "].includes(event.key) && event.target === group) { event.preventDefault(); focusDomain(domain.id); } });
      clusterElements.push({ domain, group, overview, processes, expandedLabel });
      const button = element("button", "", "");
      button.style.setProperty("--domain", domain.color); button.setAttribute("aria-pressed", "false");
      button.setAttribute("aria-label", `Explore ${domain.label}`); button.dataset.domain = domain.id;
      button.append(element("span", "domain-dot", ""), document.createTextNode(domain.label));
      button.addEventListener("click", () => focusedDomain === domain.id ? resetMap() : focusDomain(domain.id));
      $("domain-bar").append(button);
    });
    const pairs = new Map();
    data.edges.forEach((edge, index) => {
      if (edge.research && !showResearch) return;
      const a = nodeById.get(edge.from), b = nodeById.get(edge.to), color = domainById.get(a.domain).color;
      const c = curve(a, b, a.domain === b.domain ? (index % 2 ? -28 : 28) : (index % 3 - 1) * 30);
      const group = svgElement("g", { class: `edge-group${edge.condition ? " conditional-edge" : ""}`,
        role: "button", tabindex: "-1", "aria-label": `Inspect exchange: ${edge.label}`, "data-exchange": edge.id });
      const path = svgElement("path", { d: pathFor(c), stroke: color, class: "edge" });
      const hit = svgElement("path", { d: pathFor(c), class: "edge-hit" });
      group.append(path, hit);
      const end = pointAt(c, .86), before = pointAt(c, .84), angle = Math.atan2(end.y - before.y, end.x - before.x) * 180 / Math.PI;
      group.append(svgElement("path", { d: "M-5,-2L0,0L-5,2", transform: `translate(${end.x},${end.y}) rotate(${angle})`, stroke: color, fill: "none", opacity: ".5" }));
      if (edge.bidirectional) {
        const p = pointAt(c,.14), q = pointAt(c,.16), reverse = Math.atan2(p.y-q.y,p.x-q.x)*180/Math.PI;
        group.append(svgElement("path", { d: "M-5,-2L0,0L-5,2", transform: `translate(${p.x},${p.y}) rotate(${reverse})`, stroke: color, fill: "none", opacity: ".5" }));
      }
      group.addEventListener("click", event => { event.stopPropagation(); if (!skipClick) inspectEdge(edge); });
      group.addEventListener("keydown", event => { if (["Enter", " "].includes(event.key)) { event.preventDefault(); event.stopPropagation(); inspectEdge(edge); } });
      group.addEventListener("pointerenter", event => tooltip(event, edge.label, edge.summary));
      group.addEventListener("pointerleave", () => { $("tooltip").hidden = true; });
      $("process-links").append(group); edgeElements.push({ edge, group });
      if (a.domain !== b.domain && (!edge.condition || (showResearch && edge.research))) {
        const key = [a.domain, b.domain].sort().join(":");
        if (!pairs.has(key)) pairs.set(key, { a: domainById.get(a.domain), b: domainById.get(b.domain), count: 0, edges: [] });
        pairs.get(key).count++; pairs.get(key).edges.push(edge);
      }
    });
    pairs.forEach(({ a, b, count, edges }, index) => {
      const dx = b.x - a.x, dy = b.y - a.y, len = Math.hypot(dx, dy);
      const c = curve({ x: a.x + dx / len * a.radius, y: a.y + dy / len * a.radius },
        { x: b.x - dx / len * b.radius, y: b.y - dy / len * b.radius }, Math.abs(dx) > 1000 && Math.abs(dy) < 100 ? -Math.sign(dx) * 470 : (index % 2 ? 1 : -1) * 24);
      const both = edges.some(edge => nodeById.get(edge.from).domain === b.id || edge.bidirectional);
      const group = svgElement("g", { class: "aggregate-group", role: "button", tabindex: "0", "aria-label": `Explore interactions between ${a.label} and ${b.label}` });
      group.append(svgElement("path", { d: pathFor(c), stroke: a.color, class: "aggregate-glow" }));
      group.append(svgElement("path", { d: pathFor(c), stroke: a.color, class: "aggregate-edge" }));
      group.append(svgElement("path", { d: pathFor(c), class: "aggregate-hit" }));
      [.82, ...(both ? [.18] : [])].forEach(t => {
        const p = pointAt(c,t), q = pointAt(c,t + (t < .5 ? .01 : -.01));
        const angle = Math.atan2(p.y-q.y,p.x-q.x) * 180 / Math.PI;
        group.append(svgElement("path", { d: "M-8 -4L0 0L-8 4", transform: `translate(${p.x},${p.y}) rotate(${angle})`, stroke: a.color, class: "aggregate-arrow" }));
      });
      group.addEventListener("pointerenter", event => tooltip(event, `${a.label} ${both ? "⇄" : "→"} ${b.label}`, edges.slice(0,2).map(edge => edge.summary).join(" ")));
      group.addEventListener("pointerleave", () => { $("tooltip").hidden = true; });
      group.addEventListener("click", () => { if (!skipClick) inspectPair(a,b,edges); });
      group.addEventListener("keydown", event => { if (["Enter"," "].includes(event.key)) { event.preventDefault(); inspectPair(a,b,edges); } });
      const dot = svgElement("circle", { r: 2.4, fill: a.color, class: "aggregate-particle" });
      if (reducedMotion) dot.setAttribute("visibility", "hidden");
      group.append(dot); $("aggregate-links").append(group); particles.push({ dot, c, phase: index * .19 });
    });
    $("map-count").textContent = `${data.nodes.filter(n => n.implementation !== "research").length} components / ${data.edges.filter(e => !e.research).length} exchanges / 6 systems`;
  }

  function rebuildMap() {
    ["clusters", "process-links", "aggregate-links", "domain-bar"].forEach(id => $(id).replaceChildren());
    particles.length = 0; edgeElements.length = 0; nodeElements.length = 0; clusterElements.length = 0;
    createMap(); updateDomainButtons(); fit(true);
    if (focusedDomain) frameDomain(domainById.get(focusedDomain),true);
    highlight();
  }

  function availableArea() {
    const mobile = bounds.width < 721;
    return { left: mobile ? 20 : 35, top: mobile ? 125 : 85,
      right: bounds.width - (!$("inspector").hidden && !mobile ? 390 : mobile ? 25 : 55),
      bottom: bounds.height - (!$("inspector").hidden && mobile ? bounds.height * .43 + 20 : 110) };
  }
  function frameDomain(domain, instant = false) {
    const area = availableArea(), width = area.right - area.left, height = Math.max(130, area.bottom - area.top);
    const scale = Math.min(width, height) / (domain.radius * 2.1);
    target = { k: Math.max(baseScale * 1.8, scale), x: 0, y: 0 };
    target.x = (area.left + area.right) / 2 - domain.x * target.k;
    target.y = (area.top + area.bottom) / 2 - domain.y * target.k;
    if (instant || reducedMotion) camera = { ...target };
  }
  function fit(instant = false) {
    const mobile = bounds.width < 721;
    const left = mobile ? 15 : bounds.width > 1100 ? 310 : 230, right = bounds.width - (mobile ? 20 : 85);
    const top = mobile ? 140 : 90, bottom = bounds.height - (mobile ? 120 : 110);
    const xMin = Math.min(...data.domains.map(d => d.x - d.radius - 15));
    const xMax = Math.max(...data.domains.map(d => d.x + d.radius + 15));
    const yMin = Math.min(...data.domains.map(d => d.y - d.radius - 15));
    const yMax = Math.max(...data.domains.map(d => d.y + d.radius + 15));
    baseScale = Math.min((right - left) / (xMax - xMin), Math.max(120, bottom - top) / (yMax - yMin));
    target = { k: baseScale, x: (left + right) / 2 - (xMin + xMax) / 2 * baseScale,
      y: (top + bottom) / 2 - (yMin + yMax) / 2 * baseScale };
    clusterElements.forEach(({ overview }) => {
      overview.querySelector(".domain-label").style.fontSize = `${(mobile ? 12 : 16) / baseScale}px`;
      overview.querySelectorAll(".domain-sub").forEach(label => { label.style.fontSize = `${(mobile ? 7 : 9) / baseScale}px`; });
      overview.querySelector(".domain-number").style.fontSize = `${8 / baseScale}px`;
    });
    if (instant || reducedMotion) camera = { ...target };
  }
  function resetMap() {
    focusedDomain = null; selectedNode = null; hoveredNode = null;
    closeInspector(); $("back-button").hidden = true; $("map-intro").hidden = false;
    document.body.classList.remove("has-selection");
    $("map-hint").textContent = "Select a system to explore · Scroll to zoom · Drag to pan";
    updateDomainButtons(); fit(); highlight(); announce("All systems");
  }
  function updateDomainButtons() {
    $("domain-bar").querySelectorAll("button").forEach(button => button.setAttribute("aria-pressed", String(button.dataset.domain === focusedDomain)));
  }
  function showInspector(domain) {
    $("inspector").hidden = false;
    document.body.classList.add("has-selection");
    $("inspector-content").replaceChildren();
    $("inspector").style.setProperty("--domain", domain.color);
    $("inspector").scrollTop = 0;
    $("inspector-content").append(element("div", "inspector-domain", domain.label.toUpperCase()));
  }
  function section(title, text, className = "") {
    $("inspector-content").append(element("h3", "", title), element("p", className, text));
  }
  function processButton(node, subtitle) {
    const button = element("button", "", node.label);
    if (subtitle) button.append(element("small", "", subtitle));
    button.addEventListener("click", () => inspectNode(node.id));
    return button;
  }
  function focusDomain(id) {
    const domain = domainById.get(id);
    focusedDomain = id; selectedNode = null;
    showInspector(domain);
    $("inspector-content").append(element("h2", "", domain.label), element("p", "domain-description", domain.description));
    const list = element("div", "process-list", "");
    data.nodes.filter(node => node.domain === id && (showResearch || node.implementation !== "research")).forEach(node => list.append(processButton(node, node.kind === "prescribed" ? "PRESCRIBED INPUT" : node.kind === "boundary" ? "BOUNDARY OUTPUT" : node.implementation === "research" ? "RESEARCH EXTENSION" : node.display === "rendered" ? "RUNTIME BINDING" : "PYTHON MODEL")));
    $("inspector-content").append(list);
    section("Reading this system", "Select a process for its equations, assumptions, units, and exchanges. Lines indicate modeled dependencies; dashed lines require another scenario configuration.");
    $("back-button").hidden = false; $("map-intro").hidden = true;
    $("map-hint").textContent = "Select a process or an exchange · Scroll to zoom · Drag to pan";
    updateDomainButtons(); frameDomain(domain); highlight(); announce(`${domain.label}: ${list.children.length} components`);
  }
  function inspectNode(id) {
    const node = nodeById.get(id), domain = domainById.get(node.domain);
    if (node.implementation === "research" && !showResearch) { showResearch = true; $("show-research").checked = true; rebuildMap(); }
    const changingDomain = focusedDomain !== domain.id;
    focusedDomain = domain.id; selectedNode = id;
    showInspector(domain);
    $("inspector-content").append(element("h2", "", node.label), element("span", "badge", node.implementation === "research" ? "RESEARCH EXTENSION" : node.kind === "prescribed" ? "PRESCRIBED INPUT" : node.kind === "boundary" ? "BOUNDARY OUTPUT" : "MODEL PROCESS"));
    $("inspector-content").append(element("p", "interaction-science", node.summary),element("span", "formulation-badge", node.formulation));
    if (node.kind === "process") section("Implementation", node.display === "rendered" ? "Implemented in Python with a declared runtime display binding." : "Implemented in Python; no dedicated rendered layer is identified in this public selection.");
    section("Formulation", node.model_level);
    if (node.equations) section("Equation", node.equations, "equation");
    section("Units", node.units, "unit-text"); section("Assumptions", node.assumptions); section("Limits", node.limits);
    const exchanges = data.edges.filter(edge => (showResearch || !edge.research) && (edge.from === id || edge.to === id));
    if (exchanges.length) {
      $("inspector-content").append(element("h3", "", "Exchanges"));
      const list = element("div", "process-list", "");
      exchanges.forEach(edge => {
        const button = element("button", "", edge.label);
        button.append(element("small", "", `${edge.from === id ? "TO" : "FROM"} ${nodeById.get(edge.from === id ? edge.to : edge.from).label} · ${edge.units}`));
        button.addEventListener("click", () => inspectEdge(edge)); list.append(button);
      });
      $("inspector-content").append(list);
    }
    $("back-button").hidden = false; $("map-intro").hidden = true;
    if (changingDomain || camera.k / baseScale < 1.8) frameDomain(domain);
    updateDomainButtons(); highlight(); announce(`Selected ${node.label}`);
  }
  function inspectEdge(edge) {
    selectedNode = null;
    const source = nodeById.get(edge.from), destination = nodeById.get(edge.to), domain = domainById.get(source.domain);
    showInspector(domain);
    $("inspector-content").append(element("h2", "", "Process exchange"), element("div", "exchange-direction", `${source.label} → ${destination.label}`), element("p", "domain-description", edge.label));
    $("inspector-content").append(element("p", "interaction-science", edge.summary));
    section("Units", edge.units, "unit-text"); section("Method", edge.method);
    section("Spatial support", edge.spatial_support); section("Time support", edge.temporal_support);
    section("Relationship", `${edge.kind.replaceAll("_", " ")} · ${edge.conservation.replaceAll("_", " ")}`);
    if (edge.condition) section("Scenario condition", edge.condition);
    const links = element("div", "process-list", "");
    links.append(processButton(source, "SOURCE"), processButton(destination, "DESTINATION"));
    $("inspector-content").append(element("h3", "", "Connected processes"), links);
    edgeElements.forEach(({ edge: item, group }) => group.classList.toggle("active", item.id === edge.id));
    announce(`${source.label} to ${destination.label}: ${edge.label}`);
  }
  function inspectPair(a,b,edges) {
    showInspector(a);
    $("inspector-content").append(element("h2", "", `${a.label} / ${b.label}`),element("p", "domain-description", "Directed interactions between the two systems."));
    const list = element("div", "process-list", "");
    edges.forEach(edge => {
      const button = element("button", "", edge.summary);
      button.append(element("small", "", `${nodeById.get(edge.from).label} → ${nodeById.get(edge.to).label} · ${edge.units}`));
      button.addEventListener("click", () => inspectEdge(edge)); list.append(button);
    }); $("inspector-content").append(list);
    section("Direction", "Arrowheads show the direction of defined model exchanges. Two arrowheads indicate that separate exchanges operate in both directions. Line width does not represent flux magnitude.");
    $("map-intro").hidden = true; $("back-button").hidden = false;
    announce(`Interactions between ${a.label} and ${b.label}`);
  }
  function closeInspector() {
    $("inspector").hidden = true; selectedNode = null; highlight();
  }
  function highlight() {
    if (!data) return;
    const identity = hoveredNode || selectedNode;
    const connected = new Set(identity ? [identity] : []);
    data.edges.forEach(edge => { if (edge.from === identity || edge.to === identity) { connected.add(edge.from); connected.add(edge.to); } });
    nodeElements.forEach(({ node, process }) => {
      process.classList.toggle("dimmed", !!identity && !connected.has(node.id));
      process.classList.toggle("selected", node.id === selectedNode);
    });
    edgeElements.forEach(({ edge, group }) => {
      group.classList.toggle("dimmed", !!identity && edge.from !== identity && edge.to !== identity);
      group.classList.toggle("active", !!identity && (edge.from === identity || edge.to === identity));
    });
    clusterElements.forEach(({ domain, group }) => group.classList.toggle("domain-dimmed", !!focusedDomain && focusedDomain !== domain.id));
  }

  function zoom(factor, x = bounds.width / 2, y = bounds.height / 2) {
    const k = clamp(target.k * factor, baseScale * .65, baseScale * 12);
    const ratio = k / target.k;
    target = { k, x: x - (x - target.x) * ratio, y: y - (y - target.y) * ratio };
    if (reducedMotion) camera = { ...target };
  }
  function bindMapControls() {
    $("zoom-in").addEventListener("click", () => zoom(1.4));
    $("zoom-out").addEventListener("click", () => zoom(1 / 1.4));
    $("fit-map").addEventListener("click", resetMap); $("back-button").addEventListener("click", resetMap);
    $("fullscreen").addEventListener("click", async () => {
      try {
        if (document.fullscreenElement) await document.exitFullscreen(); else await $("explorer").requestFullscreen();
      } catch { announce("Full screen is unavailable in this browser."); }
    });
    if (!document.fullscreenEnabled) $("fullscreen").hidden = true;
    document.addEventListener("fullscreenchange", () => $("fullscreen").setAttribute("aria-label", document.fullscreenElement ? "Exit full screen" : "Enter full screen"));
    map.addEventListener("wheel", event => {
      event.preventDefault(); $("tooltip").hidden = true;
      const rect = map.getBoundingClientRect(); zoom(Math.exp(-event.deltaY * .002), event.clientX - rect.left, event.clientY - rect.top);
    }, { passive: false });
    map.addEventListener("pointerdown", event => {
      if (event.button !== 0 && event.pointerType === "mouse") return;
      pointers.set(event.pointerId, { x: event.clientX, y: event.clientY });
      moved = false; skipClick = false; map.classList.add("dragging");
    });
    map.addEventListener("pointermove", event => {
      if (!pointers.has(event.pointerId)) return;
      const previous = pointers.get(event.pointerId), current = { x: event.clientX, y: event.clientY };
      const dx = current.x - previous.x, dy = current.y - previous.y;
      if (Math.abs(dx) + Math.abs(dy) > 2) { moved = true; map.setPointerCapture(event.pointerId); }
      if (pointers.size === 2) {
        const other = [...pointers.entries()].find(([id]) => id !== event.pointerId)[1];
        const oldDistance = Math.hypot(previous.x - other.x, previous.y - other.y);
        const newDistance = Math.hypot(current.x - other.x, current.y - other.y);
        const rect = map.getBoundingClientRect();
        if (oldDistance > 5) zoom(newDistance / oldDistance, (previous.x + other.x) / 2 - rect.left, (previous.y + other.y) / 2 - rect.top);
        target.x += dx / 2; target.y += dy / 2;
      } else { target.x += dx; target.y += dy; }
      pointers.set(event.pointerId, current); camera = { ...target }; $("tooltip").hidden = true;
    });
    const end = event => { pointers.delete(event.pointerId); skipClick = moved; if (!pointers.size) map.classList.remove("dragging"); };
    map.addEventListener("pointerup", end); map.addEventListener("pointercancel", end);
    map.addEventListener("dblclick", event => { if (event.target === map || event.target.tagName === "rect") zoom(1.7, event.offsetX, event.offsetY); });
    map.addEventListener("keydown", event => {
      const keys = ["+", "=", "-", "0", "ArrowUp", "ArrowDown", "ArrowLeft", "ArrowRight"];
      if (!keys.includes(event.key)) return;
      event.preventDefault();
      if (["+", "="].includes(event.key)) zoom(1.3);
      if (event.key === "-") zoom(1 / 1.3);
      if (event.key === "0") resetMap();
      if (event.key === "ArrowUp") target.y += 65;
      if (event.key === "ArrowDown") target.y -= 65;
      if (event.key === "ArrowLeft") target.x += 65;
      if (event.key === "ArrowRight") target.x -= 65;
    });
    new ResizeObserver(entries => {
      const { width, height } = entries[0].contentRect;
      if (width <= 0 || height <= 0) return;
      const changedLayout = (bounds.width < 721) !== (width < 721);
      bounds = { width, height }; fit(true);
      if (changedLayout) {
        rebuildMap();
      }
      if (focusedDomain) frameDomain(domainById.get(focusedDomain), true);
    }).observe(map);
    $("process-search").addEventListener("input", event => {
      const query = event.target.value.trim().toLowerCase(), results = $("search-results"); results.replaceChildren();
      results.hidden = !query;
      if (!query) return;
      const matches = data.nodes.filter(node => `${node.label} ${domainById.get(node.domain).label}`.toLowerCase().includes(query));
      matches.forEach(node => {
        const button = processButton(node, domainById.get(node.domain).label);
        button.addEventListener("click", () => { results.hidden = true; $("process-search").value = ""; }); results.append(button);
      });
      if (!matches.length) results.append(element("p", "", "No matching process."));
    });
    $("process-search").parentElement.addEventListener("click", event => {
      if (event.target.classList.contains("search-wrap") || event.target.tagName === "SPAN") $("process-search").focus();
    });
  }

  const palette = [[121, 186, 206], [167, 202, 157], [211, 189, 117], [236, 151, 101], [199, 101, 87]];
  let tempMin = 0, tempMax = 30;
  const riverSegments = [], cellPoints = [];
  let profileLine, profilePoint, riverPoint;
  function temperatureColor(value) {
    const position = clamp((value - tempMin) / (tempMax - tempMin), 0, 1) * 4;
    const index = Math.min(3, Math.floor(position)), fraction = position - index;
    return `rgb(${palette[index].map((n, i) => Math.round(n + (palette[index + 1][i] - n) * fraction)).join(",")})`;
  }
  function timeLabel(seconds) {
    const hours = Math.floor(seconds / 3600), minutes = Math.floor(seconds % 3600 / 60), secs = Math.floor(seconds % 60);
    return `${hours ? `${String(hours).padStart(2, "0")}:` : ""}${String(minutes).padStart(2, "0")}:${String(secs).padStart(2, "0")}`;
  }
  function createRiver() {
    const river = data.river, cells = river.cells, svg = $("river-map"), profile = $("profile");
    const temperatures = river.frames.flatMap(frame => frame.temperature);
    tempMin = Math.floor(Math.min(...temperatures)); tempMax = Math.ceil(Math.max(...temperatures));
    if (tempMax === tempMin) tempMax = tempMin + 1;
    $("temp-min").textContent = `${tempMin} °C`; $("temp-max").textContent = `${tempMax} °C`;
    const minX = Math.min(...cells.map(c => c.x)), maxX = Math.max(...cells.map(c => c.x));
    const minZ = Math.min(...cells.map(c => c.z)), maxZ = Math.max(...cells.map(c => c.z));
    const scale = Math.min(510 / (maxX - minX), 545 / (maxZ - minZ));
    const x0 = 310 - (maxX + minX) / 2 * scale, y0 = 322 - (maxZ + minZ) / 2 * scale;
    const defs = svgElement("defs"), pattern = svgElement("pattern", { id: "river-grid", width: "30", height: "30", patternUnits: "userSpaceOnUse" });
    pattern.append(svgElement("circle", { cx: 1, cy: 1, r: .7, fill: "#9ea0a5", opacity: .15 })); defs.append(pattern); svg.append(defs);
    svg.append(svgElement("rect", { width: 620, height: 660, fill: "url(#river-grid)", "pointer-events": "none" }));
    cells.forEach(cell => cellPoints.push({ x: cell.x * scale + x0, y: cell.z * scale + y0 }));
    const riverPath = cellPoints.map((p, i) => `${i ? "L" : "M"}${p.x},${p.y}`).join(" ");
    svg.append(svgElement("path", { d: riverPath, stroke: "#a3a5aa", "stroke-width": 24, opacity: .07, fill: "none" }));
    cells.forEach((cell, index) => {
      const a = cellPoints[index], b = cellPoints[Math.min(index + 1, cells.length - 1)];
      const path = svgElement("path", { d: `M${a.x},${a.y}L${b.x},${b.y}`, "stroke-width": 6, class: "river-cell",
        tabindex: index % 20 === 0 ? 0 : -1, role: "button", "aria-label": `Inspect river cell at ${(cell.s / 1000).toFixed(2)} km` });
      path.addEventListener("pointerenter", () => probeCell(index)); path.addEventListener("click", () => probeCell(index));
      path.addEventListener("keydown", event => { if (["Enter", " "].includes(event.key)) { event.preventDefault(); probeCell(index); } });
      svg.append(path); riverSegments.push(path);
    });
    const start = cellPoints[0], end = cellPoints[cellPoints.length - 1];
    [[start, "UPSTREAM", 23], [end, "DOWNSTREAM", -18]].forEach(([p, label, offset]) => {
      svg.append(svgElement("circle", { cx: p.x, cy: p.y, r: 4, fill: "#cbcdd2" }));
      svg.append(svgElement("text", { x: p.x, y: p.y + offset, fill: "#aeb0b5", "text-anchor": "middle", "font-size": 10, "font-family": "monospace" }, label));
    });
    riverPoint = svgElement("circle", { r: 9, fill: "none", stroke: "#e4e6eb", "stroke-width": 1.5, visibility: "hidden", "pointer-events": "none" }); svg.append(riverPoint);
    const scaleLength = 500 * scale;
    svg.append(svgElement("path", { d: `M45 605v5h${scaleLength}v-5`, stroke: "#a5a7ac", fill: "none", "stroke-width": 1 }));
    svg.append(svgElement("text", { x: 45, y: 626, fill: "#93959a", "font-size": 9, "font-family": "monospace" }, "500 m"));
    profile.setAttribute("viewBox", "0 0 600 210");
    for (let i = 0; i <= 4; i++) {
      const y = 18 + i * 39;
      profile.append(svgElement("path", { d: `M42 ${y}H583`, stroke: "#3e4045", "stroke-width": .6 }));
      profile.append(svgElement("text", { x: 30, y: y + 4, "text-anchor": "end", fill: "#909297", "font-size": 10, "font-family": "monospace" }, (tempMax - i * (tempMax - tempMin) / 4).toFixed(1)));
    }
    for (let km = 0; km <= river.length_m / 1000; km++) {
      const x = 42 + km * 1000 / river.length_m * 541;
      profile.append(svgElement("text", { x, y: 195, "text-anchor": "middle", fill: "#909297", "font-size": 10, "font-family": "monospace" }, `${km} km`));
    }
    profileLine = svgElement("path", { fill: "none", stroke: "#b3b5ba", "stroke-width": 2, "stroke-linejoin": "round" });
    profile.append(profileLine);
    profilePoint = svgElement("circle", { r: 4, fill: "#dcdee3", visibility: "hidden" }); profile.append(profilePoint);
    $("river-time").max = String(river.frames.length - 1);
    $("river-facts").replaceChildren();
    [["MODELED CHANNEL", `${(river.length_m / 1000).toFixed(2)} km`], ["RIVER CELLS", String(cells.length)], ["UPSTREAM FLOW", `${river.boundary_flow} m3/s`]].forEach(([label, value]) => {
      const box = element("div", "", ""); box.append(element("span", "", label), element("strong", "", value)); $("river-facts").append(box);
    });
    $("river-time").addEventListener("input", event => { frameIndex = Number(event.target.value); playTime = river.frames[frameIndex].t; drawRiver(); });
    $("play-river").addEventListener("click", () => {
      playing = !playing; lastPlayback = 0;
      if (playing && frameIndex === river.frames.length - 1) { frameIndex = 0; playTime = 0; drawRiver(); }
      $("play-river").textContent = playing ? "Ⅱ" : "▶";
      $("play-river").setAttribute("aria-label", playing ? "Pause saved temperature frames" : "Play saved temperature frames");
    });
    drawRiver();
  }
  function drawRiver() {
    const frame = data.river.frames[frameIndex];
    riverSegments.forEach((segment, i) => segment.setAttribute("stroke", temperatureColor(frame.temperature[i])));
    profileLine.setAttribute("d", data.river.cells.map((cell, i) => `${i ? "L" : "M"}${42 + cell.s / data.river.length_m * 541},${18 + (tempMax - frame.temperature[i]) / (tempMax - tempMin) * 156}`).join(" "));
    $("river-time").value = String(frameIndex); $("river-time-label").textContent = timeLabel(frame.t);
    $("profile").setAttribute("aria-label", `Modeled temperature versus downstream distance at ${timeLabel(frame.t)} elapsed model time`);
    if (selectedCell !== null) probeCell(selectedCell);
  }
  function probeCell(index) {
    selectedCell = index;
    const cell = data.river.cells[index], value = data.river.frames[frameIndex].temperature[index], probe = $("river-probe");
    const values = element("strong", "", `${value.toFixed(2)} `); values.append(element("span", "", "°C"), document.createTextNode(`${(cell.s / 1000).toFixed(3)} `), element("span", "", "km downstream"));
    probe.replaceChildren(element("p", "eyebrow", `RIVER CELL ${index + 1} / ${data.river.cells.length}`), values);
    riverPoint.setAttribute("cx", cellPoints[index].x); riverPoint.setAttribute("cy", cellPoints[index].y); riverPoint.setAttribute("visibility", "visible");
    profilePoint.setAttribute("cx", 42 + cell.s / data.river.length_m * 541); profilePoint.setAttribute("cy", 18 + (tempMax - value) / (tempMax - tempMin) * 156); profilePoint.setAttribute("visibility", "visible");
  }

  function setView(river) {
    isRiver = river; $("system-view").hidden = river; $("river-view").hidden = !river; closeInspector();
    $("system-tab").setAttribute("aria-pressed", String(!river)); $("river-tab").setAttribute("aria-pressed", String(river));
    $("view-description").textContent = river ? "MODEL OUTPUTS / SAVED SCENARIO" : "SYSTEM RELATIONSHIPS / SCHEMATIC LAYOUT";
    if (!river) { playing = false; $("play-river").textContent = "▶"; $("play-river").setAttribute("aria-label", "Play saved temperature frames"); }
    announce(river ? "River transect" : "System map");
  }

  function animate(now) {
    requestAnimationFrame(animate);
    if (!data || document.hidden || now - lastRender < 30) return;
    lastRender = now;
    if (currentPage === "systems") {
      const mix = reducedMotion ? 1 : .18;
      ["x", "y", "k"].forEach(key => { camera[key] += (target[key] - camera[key]) * mix; });
      $("world").setAttribute("transform", `translate(${camera.x},${camera.y}) scale(${camera.k})`);
      const ratio = camera.k / baseScale;
      detail = clamp((ratio - 1.15) / .55, 0, 1);
      clusterElements.forEach(({ domain, group, overview, processes, expandedLabel }) => {
        overview.style.opacity = String(1 - detail); overview.style.pointerEvents = detail > .8 ? "none" : "auto";
        processes.style.opacity = String(detail * (focusedDomain && focusedDomain !== domain.id ? .28 : 1)); processes.style.pointerEvents = detail < .8 ? "none" : "auto";
        expandedLabel.style.opacity = String(detail); group.setAttribute("tabindex", detail > .8 ? "-1" : "0");
        group.setAttribute("role", detail > .8 ? "group" : "button");
        overview.setAttribute("aria-hidden", String(detail > .8));
        processes.setAttribute("aria-hidden", String(detail <= .8));
        expandedLabel.setAttribute("aria-hidden", String(detail <= .8));
      });
      nodeElements.forEach(({ process, deeper }) => { process.setAttribute("tabindex", detail > .8 ? "0" : "-1"); deeper.style.opacity = String(clamp((ratio - 2.4) / .8, 0, 1)); });
      edgeElements.forEach(({ group }) => group.setAttribute("tabindex", detail > .8 ? "0" : "-1"));
      $("process-links").style.opacity = String(detail); $("process-links").style.pointerEvents = detail > .8 ? "auto" : "none";
      $("process-links").setAttribute("aria-hidden", String(detail <= .8));
      $("aggregate-links").style.opacity = String(1 - detail);
      $("aggregate-links").style.pointerEvents = detail > .8 ? "none" : "auto";
      $("aggregate-links").setAttribute("aria-hidden",String(detail > .8));
      $("aggregate-links").querySelectorAll(".aggregate-group").forEach(group => group.setAttribute("tabindex",detail > .8 ? "-1" : "0"));
      $("zoom-level").value = `${Math.round(ratio * 100)}%`;
      if (!reducedMotion) particles.forEach(({ dot, c, phase }) => { const p = pointAt(c, (now / 15000 + phase) % 1); dot.setAttribute("cx", p.x); dot.setAttribute("cy", p.y); });
    }
    if (isRiver && playing) {
      if (lastPlayback) playTime += Math.min(now - lastPlayback, 100) / 1000 * 180 * Number($("playback-speed").value);
      lastPlayback = now;
      const frames = data.river.frames;
      while (frameIndex < frames.length - 1 && frames[frameIndex + 1].t <= playTime) frameIndex++;
      drawRiver();
      if (frameIndex === frames.length - 1) { playing = false; $("play-river").textContent = "▶"; $("play-river").setAttribute("aria-label", "Play saved temperature frames"); }
    }
  }

  async function start() {
    try {
      const response = await fetch("/dashboard/snapshot.json", { cache: "no-cache" });
      if (!response.ok) throw Error("Snapshot response failed");
      data = await response.json();
      if (data.schema !== "yellowstone.public.v1") throw Error("Snapshot schema differs");
      domainById = new Map(data.domains.map(domain => [domain.id, domain])); nodeById = new Map(data.nodes.map(node => [node.id, node]));
      const sections = { overview: "overview-view", systems: "system-view", results: "river-view", methods: "methods-view" };
      Object.entries(sections).forEach(([page,id]) => { $(id).hidden = page !== currentPage; });
      document.querySelectorAll(".site-nav a").forEach(link => { if (link.dataset.page === currentPage) link.setAttribute("aria-current","page"); });
      isRiver = currentPage === "results";
      $("view-description").textContent = {overview:"GEOGRAPHIC COVERAGE / SAVED MODEL DATA",systems:"EARTH SYSTEMS / SCHEMATIC RELATIONSHIPS",results:"MODEL OUTPUTS / SAVED SCENARIO",methods:"FORMULATIONS / SCIENTIFIC SCOPE"}[currentPage];
      createMap(); createRiver(); bindMapControls();
      window.YSScience.init(data);
      if (currentPage === "overview") window.YSCoverage.init(data);
      const date = new Date(data.epoch).toLocaleString("en-GB", { day: "2-digit", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit", timeZone: "UTC", hour12: false });
      $("run-description").textContent = `${data.run_mode === "scenario" ? "Illustrative scenario" : data.run_mode.replaceAll("_", " ")} · ${date} UTC`;
      $("about-snapshot").textContent = `Run mode: ${data.run_mode.replaceAll("_", " ")}\nInitial model time: ${date} UTC`;
      $("about-snapshot").style.whiteSpace = "pre-line";
      $("show-research").addEventListener("change", event => { showResearch = event.target.checked; rebuildMap(); });
      $("show-status").addEventListener("change", event => document.body.classList.toggle("status-off",!event.target.checked));
      $("close-inspector").addEventListener("click", () => { closeInspector(); if (focusedDomain) frameDomain(domainById.get(focusedDomain)); });
      ["about-button", "scope-button"].forEach(id => $(id).addEventListener("click", () => $("about-dialog").showModal()));
      $("close-about").addEventListener("click", () => $("about-dialog").close());
      $("about-dialog").addEventListener("click", event => { if (event.target === $("about-dialog")) { const rect = event.target.getBoundingClientRect(); if (event.clientX < rect.left || event.clientX > rect.right || event.clientY < rect.top || event.clientY > rect.bottom) event.target.close(); } });
      document.addEventListener("keydown", event => {
        if (event.key !== "Escape") return;
        $("search-results").hidden = true; $("tooltip").hidden = true;
        if (!$("about-dialog").open && !isRiver) resetMap();
      });
      document.addEventListener("pointerdown", event => { if (!event.target.closest(".search-wrap")) $("search-results").hidden = true; });
      fit(true); requestAnimationFrame(animate);
      const selected = decodeURIComponent(location.hash.slice(1));
      if (currentPage === "systems" && nodeById.has(selected)) {
        if (nodeById.get(selected).implementation === "research") { showResearch = true; $("show-research").checked = true; rebuildMap(); }
        inspectNode(selected);
      }
    } catch (error) { $("load-error").hidden = false; console.error("Model snapshot unavailable", error); }
  }
  $("retry-load").addEventListener("click", () => location.reload());
  start();
})();
