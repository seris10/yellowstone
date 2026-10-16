"use strict";

window.YSScience = {
  init(data, page) {
    const $ = id => document.getElementById(id), NS = "http://www.w3.org/2000/svg";
    const element = (tag, cls, text = "") => { const node = document.createElement(tag); node.className = cls; node.textContent = text; return node; };
    const svg = (tag, attrs, text = "") => { const node = document.createElementNS(NS, tag); Object.entries(attrs).forEach(([k,v]) => node.setAttribute(k,v)); node.textContent = text; return node; };
    const domains = new Map(data.domains.map(d => [d.id,d]));
    const catalog = $("process-catalog");
    function catalogUpdate() {
      const query = $("catalog-filter").value.toLowerCase(), status = $("catalog-status").value;
      catalog.replaceChildren();
      data.nodes.filter(node => node.implementation !== "research" && node.kind === "process" && (status === "all" || node.display === status) && `${node.label} ${node.summary} ${node.equations || ""}`.toLowerCase().includes(query)).forEach(node => {
        const card = element("article", "process-card"); card.id = node.id; card.style.setProperty("--domain", domains.get(node.domain).color);
        card.append(element("p", "eyebrow", domains.get(node.domain).label.toUpperCase()), element("h3", "", node.label), element("p", "", node.summary));
        card.append(element("div", "science-state", `${node.display === "rendered" ? "● Runtime binding" : "○ Python model"} · ${node.formulation}`));
        const details = element("details", ""); details.append(element("summary", "", "Equations, assumptions, and limits"));
        [["Formulation", node.model_level], ["Equation", node.equations], ["Variables", node.variables], ["Units", node.units], ["Assumptions", node.assumptions], ["Limits", node.limits]].forEach(([label,text]) => {
          if (!text) return; details.append(element("h4", "", label.toUpperCase()), element(label === "Equation" ? "pre" : "p", "", text));
        }); card.append(details); catalog.append(card);
      });
      if (!catalog.children.length) catalog.append(element("p", "", "No matching process."));
    }
    if (page === "methods") {
    $("catalog-filter").addEventListener("input", catalogUpdate); $("catalog-status").addEventListener("change", catalogUpdate); catalogUpdate();
    data.nodes.filter(n => n.implementation === "research").forEach(node => {
      const card = element("article", ""); card.append(element("h3", "", node.label), element("p", "", node.summary)); $("research-catalog").append(card);
    });
    [["NPS · Midway Geyser Basin", "https://www.nps.gov/features/yell/ofvec/exhibits/treasures/midway/index.htm"],
      ["USGS · 3D Elevation Program", "https://www.usgs.gov/3d-elevation-program"],
      ["FAO · Reference evapotranspiration", "https://www.fao.org/4/x0490e/x0490e0a.htm"]].forEach(([label,url]) => {
      const link = element("a", "", label + " ↗"); link.href = url; link.target = "_blank"; link.rel = "noopener noreferrer"; $("reference-links").append(link);
    });
    }
    if (page !== "results" || !data.ecology || !data.river) return;
    function lineChart(container, values, unit, color) {
      const valid = values.filter(Number.isFinite), low = Math.min(...valid), high = Math.max(...valid);
      if (!valid.length) { $(container).append(element("p","","No values available for this diagnostic.")); return; }
      const chart = svg("svg", { viewBox: "0 0 600 230", role: "img", "aria-label": `${unit} versus distance downstream` });
      const tip = element("div", "chart-tooltip", "Hover the profile to inspect a river location.");
      const toggle = element("button", "chart-scale-button", "Expand local range");
      const axisNote = element("small", "", "Vertical scale begins at zero.");
      let local = false;
      const points = [], line = svg("path", { fill: "none", stroke: color, "stroke-width": 2 });
      const marker = svg("circle", { r: 4, fill: color, visibility: "hidden", "pointer-events": "none" });
      function render() {
        const pad = Math.max((high - low) * .12, .0001), min = local ? low - pad : 0, max = local ? high + pad : Math.ceil(high * 1.1);
        chart.replaceChildren(); points.length = 0;
        for (let i = 0; i <= 4; i++) {
          const y = 15 + i * 45;
          chart.append(svg("path", { d: `M57 ${y}H585`, stroke: "#2d3544", "stroke-width": .7 }));
          chart.append(svg("text", { x: 47, y: y + 4, fill: "#97a6be", "text-anchor": "end", "font-size": 10, "font-family": "monospace" }, (max - i * (max - min) / 4).toFixed(local ? 3 : 1)));
        }
        for (let km = 0; km < data.river.length_m / 1000; km++) chart.append(svg("text", { x: 57 + km * 1000 / data.river.length_m * 528, y: 222, fill: "#97a6be", "text-anchor": "middle", "font-size": 10, "font-family": "monospace" }, `${km} km`));
        values.forEach((v,i) => points.push(Number.isFinite(v) ? { x: 57 + data.river.cells[i].s / data.river.length_m * 528, y: 15 + (max - v) / (max - min) * 180 } : null));
        let segment = false;
        line.setAttribute("d", points.map(p => { if (!p) { segment = false; return ""; } const token = `${segment ? "L" : "M"}${p.x},${p.y}`; segment = true; return token; }).join(" "));
        chart.append(line, marker); marker.setAttribute("visibility", "hidden");
        axisNote.textContent = local ? `Local vertical range: ${min.toFixed(4)} to ${max.toFixed(4)} ${unit}.` : "Vertical scale begins at zero.";
        toggle.textContent = local ? "Use zero baseline" : "Expand local range";
        toggle.setAttribute("aria-pressed",String(local));
      }
      chart.addEventListener("pointermove", event => {
        const pointInChart = window.YSData.eventToSvg(chart,event); if (!pointInChart) return; const x = pointInChart.x;
        let nearest = 0, distance = Infinity;
        points.forEach((p,i) => { if (p && Math.abs(p.x - x) < distance) { nearest = i; distance = Math.abs(p.x - x); } });
        const point = points[nearest]; if (!point) return; marker.setAttribute("cx",point.x); marker.setAttribute("cy",point.y); marker.setAttribute("visibility","visible");
        tip.textContent = `${(data.river.cells[nearest].s / 1000).toFixed(3)} km downstream · ${values[nearest].toFixed(4)} ${unit}`;
      });
      toggle.addEventListener("click", () => { local = !local; render(); });
      $(container).append(chart,tip,toggle,axisNote); render();
    }
    function bars(container, rows, unit, maximum = null) {
      const max = maximum || Math.max(...rows.map(r => r.value)) * 1.08;
      const chart = svg("svg", { viewBox: `0 0 600 ${rows.length * 43 + 20}`, role: "img", "aria-label": rows.map(r => `${r.label}: ${r.value.toFixed(3)} ${unit}`).join("; ") });
      rows.forEach((r,i) => {
        const y = i * 43 + 15;
        chart.append(svg("text", { x: 0, y, fill: "#a9b9d1", "font-size": 10, "font-family": "monospace" }, r.label));
        chart.append(svg("rect", { x: 0, y: y + 7, width: 455, height: 9, rx: 2, fill: "#202a3a" }));
        chart.append(svg("rect", { x: 0, y: y + 7, width: Math.max(0,r.value / max * 455), height: 9, rx: 2, fill: r.color }));
        chart.append(svg("text", { x: 590, y: y + 15, fill: "#e0e8f5", "text-anchor": "end", "font-size": 11, "font-family": "monospace" }, `${r.value.toFixed(3)} ${unit}`));
      }); $(container).append(chart);
    }
    lineChart("oxygen-chart",data.ecology.oxygen || [],"mg/L","#79b9ff");
    lineChart("algae-chart",data.ecology.periphyton || [],"mg C/m²","#c5a0ee");
    $("oxygen-chart").append(element("small","",`Recorded integration increment: ${data.ecology.oxygen_dt_s} s.`));
    $("algae-chart").append(element("small","",`Recorded integration increment: ${data.ecology.periphyton_dt_s} s.`));
    const w = data.ecology.water;
    if (w) {
    bars("water-chart",[
      {label:"Initial storage",value:w.initial_mm,color:"#a8b4c9"}, {label:"Rain input",value:w.rain_mm,color:"#69b1f4"},
      {label:"Final storage",value:w.final_mm,color:"#bac9e2"}, {label:"Evapotranspiration",value:w.et_mm,color:"#d0b0e9"},
      {label:"Surface runoff",value:w.runoff_mm,color:"#70c9db"}, {label:"Subsurface drainage",value:w.drainage_mm,color:"#d6a369"}
    ],"mm");
    }
    bars("patch-chart",(data.ecology.patches || []).map((p,i) => ({label:p.label,value:p.biomass / p.capacity * 100,color:["#9ed57e","#7fbedb","#c6a2e6"][i%3]})),"%",100);
    function stat(container,label,value) { const box = element("div", ""); box.append(element("span", "", label),element("strong", "", value)); $(container).append(box); }
    if (data.ecology.trout) {
    stat("ecology-summary","SELECTED TROUT REFUGE",`${(data.ecology.trout.s_m / 1000).toFixed(3)} km`);
    stat("ecology-summary","REFUGE TEMPERATURE",`${data.ecology.trout.temperature_c.toFixed(2)} °C`);
    stat("ecology-summary","FOOD-WEB INTEGRATION",`${data.ecology.foodweb_days} days`);
    }
    if (w) {
    $("water-window").textContent = `${w.days}-day snow and soil integration before the river experiment. Values sum water-equivalent depths across ${w.modeled_patch_count} authored patches; they are not a basin-wide mean.`;
    stat("water-summary","WATER BALANCE RESIDUAL",`${w.water_residual_mm.toExponential(2)} mm`);
    stat("water-summary","SUMMED SNOW STORAGE",`${(data.ecology.snow || []).reduce((sum,p) => sum+p.snow_mm,0).toFixed(2)} mm`);
    stat("water-summary","RIVER RUNOFF CONNECTION","Inactive in this scenario");
    }
    document.querySelectorAll("[data-result]").forEach(button => button.addEventListener("click", () => {
      const result = button.dataset.result;
      ["river","ecology","water"].forEach(id => { $(`${id}-results`).hidden = result !== id; });
      document.querySelectorAll("[data-result]").forEach(item => item.setAttribute("aria-pressed",String(item === button)));
      document.querySelector(".playback").hidden = result !== "river";
      $("river-view").classList.toggle("result-data-view",result !== "river");
      if (result !== "river" && $("play-river").getAttribute("aria-label").startsWith("Pause")) $("play-river").click();
    }));
  }
};
