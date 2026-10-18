"use strict";

(() => {
  const $ = id => document.getElementById(id);
  const NS = "http://www.w3.org/2000/svg";
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
  let data, isRiver = false;
  const currentPage = document.body.dataset.page || "overview";
  let lastRender = 0, frameIndex = 0, playing = false, playTime = 0, lastPlayback = 0, selectedCell = null;

  const palette = [[121, 186, 206], [167, 202, 157], [211, 189, 117], [236, 151, 101], [199, 101, 87]];
  let tempMin = 0, tempMax = 30;
  const riverSegments = [], cellPoints = [];
  let profileLine, profilePoint, riverPoint;
  function temperatureColor(value) {
    return window.YSData.color(value,[tempMin,tempMax]);
  }
  function timeLabel(seconds) {
    const hours = Math.floor(seconds / 3600), minutes = Math.floor(seconds % 3600 / 60), secs = Math.floor(seconds % 60);
    return `${hours ? `${String(hours).padStart(2, "0")}:` : ""}${String(minutes).padStart(2, "0")}:${String(secs).padStart(2, "0")}`;
  }
  function createRiver() {
    const river = data.river, cells = river.cells, svg = $("river-map"), profile = $("profile");
    [tempMin,tempMax] = river.temperature_domain || window.YSData.extent((function*(){for(const frame of river.frames)yield* frame.temperature;})()) || [0,1];
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
      if (playing) requestAnimationFrame(animate);
      if (playing && frameIndex === river.frames.length - 1) { frameIndex = 0; playTime = 0; drawRiver(); }
      $("play-river").textContent = playing ? "Ⅱ" : "▶";
      $("play-river").setAttribute("aria-label", playing ? "Pause saved temperature frames" : "Play saved temperature frames");
    });
    drawRiver();
  }
  function drawRiver() {
    const frame = data.river.frames[frameIndex];
    riverSegments.forEach((segment, i) => segment.setAttribute("stroke", temperatureColor(frame.temperature[i])));
    profileLine.setAttribute("d", window.YSData.segments(data.river.cells.map((cell,i)=>({x:cell.s,y:frame.temperature[i]})),p=>42+p.x/data.river.length_m*541,p=>18+(tempMax-p.y)/(tempMax-tempMin)*156));
    $("river-time").value = String(frameIndex); $("river-time-label").textContent = timeLabel(frame.t);
    $("profile").setAttribute("aria-label", `Modeled temperature versus downstream distance at ${timeLabel(frame.t)} elapsed model time`);
    if (selectedCell !== null) probeCell(selectedCell);
  }
  function probeCell(index) {
    selectedCell = index;
    const cell = data.river.cells[index], value = data.river.frames[frameIndex].temperature[index], probe = $("river-probe");
    const values = element("strong", "", `${Number.isFinite(value)?value.toFixed(2):"Missing"} `); values.append(element("span", "", "°C"), document.createTextNode(`${(cell.s / 1000).toFixed(3)} `), element("span", "", "km downstream"));
    probe.replaceChildren(element("p", "eyebrow", `RIVER CELL ${index + 1} / ${data.river.cells.length}`), values);
    riverPoint.setAttribute("cx", cellPoints[index].x); riverPoint.setAttribute("cy", cellPoints[index].y); riverPoint.setAttribute("visibility", "visible");
    if (!Number.isFinite(value)) { profilePoint.setAttribute("visibility","hidden"); return; }
    profilePoint.setAttribute("cx", 42 + cell.s / data.river.length_m * 541); profilePoint.setAttribute("cy", 18 + (tempMax - value) / (tempMax - tempMin) * 156); profilePoint.setAttribute("visibility", "visible");
  }

  function animate(now) {
    if (playing) requestAnimationFrame(animate);
    if (!data || document.hidden || now - lastRender < 30) return;
    lastRender = now;
    if (isRiver && playing) {
      if (lastPlayback) playTime += (now - lastPlayback) / 1000 * 180 * Number($("playback-speed").value);
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
      data = window.YSData.validateSnapshot(await response.json());
      if (data.schema !== "yellowstone.public.v1") throw Error("Snapshot schema differs");
      const sections = { overview: "overview-view", systems: "system-view", results: "river-view", methods: "methods-view", analyze: "analysis-view" };
      Object.entries(sections).forEach(([page,id]) => { $(id).hidden = page !== currentPage; });
      document.querySelectorAll(".site-nav a").forEach(link => { if (link.dataset.page === (currentPage === "systems" ? "overview" : currentPage)) link.setAttribute("aria-current","page"); });
      isRiver = currentPage === "results";
      document.querySelector('[data-result="ecology"]').disabled = !data.ecology?.oxygen && !data.ecology?.periphyton;
      document.querySelector('[data-result="water"]').disabled = !data.ecology?.water;
      $("mode-landscape").disabled = !data.coverage;
      $("view-description").textContent = {overview:"GEOGRAPHIC COVERAGE / SAVED MODEL DATA",systems:"EARTH SYSTEMS / SCHEMATIC RELATIONSHIPS",results:"MODEL OUTPUTS / SAVED SCENARIO",analyze:"EARTH SYSTEMS / LINKED SCIENTIFIC ANALYSIS",methods:"FORMULATIONS / SCIENTIFIC SCOPE"}[currentPage];
      if (isRiver && data.river) createRiver();
      if (["overview", "systems"].includes(currentPage)) window.YSWorkspace.init(data, { page: currentPage, domain: document.body.dataset.domain });
      window.YSScience.init(data, currentPage);
      if (["overview", "systems"].includes(currentPage) && data.coverage) window.YSCoverage.init(data);
      if (["overview","systems","analyze"].includes(currentPage)) window.YSAnalysis.init(data,{embedded:currentPage!=="analyze"});
      const date = new Date(data.epoch).toLocaleString("en-GB", { day: "2-digit", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit", timeZone: "UTC", hour12: false });
      $("run-description").textContent = `${data.run_mode === "scenario" ? "Saved scenario" : data.run_mode.replaceAll("_", " ")} · ${date} UTC`;
      $("about-snapshot").textContent = `Run mode: ${data.run_mode.replaceAll("_", " ")}\nInitial model time: ${date} UTC`;
      $("about-snapshot").style.whiteSpace = "pre-line";
      ["about-button", "scope-button"].forEach(id => $(id).addEventListener("click", () => $("about-dialog").showModal()));
      $("close-about").addEventListener("click", () => $("about-dialog").close());
      $("about-dialog").addEventListener("click", event => { if (event.target === $("about-dialog")) { const rect = event.target.getBoundingClientRect(); if (event.clientX < rect.left || event.clientX > rect.right || event.clientY < rect.top || event.clientY > rect.bottom) event.target.close(); } });
      if (isRiver && data.river) requestAnimationFrame(animate);
    } catch (error) { $("load-error").hidden = false; console.error("Model snapshot unavailable", error); }
  }
  $("retry-load").addEventListener("click", () => location.reload());
  start();
})();
