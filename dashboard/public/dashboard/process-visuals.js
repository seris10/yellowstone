"use strict";

((root) => {
  const cache = new Map(), finite = Number.isFinite;
  const assert = (condition, message) => { if (!condition) throw Error(message); };
  const nullable = value => value === null || finite(value);
  function validate(data, snapshot, id) {
    assert(data?.schema === "yellowstone.process-visual.v1" && data.id === id && data.snapshot === snapshot, "The visual data belongs to a different catalog.");
    assert(Array.isArray(data.sources) && data.sources.length && data.sources.every(source => typeof source.label === "string" && /^[a-f0-9]{64}$/.test(source.sha256)), "The visual data has no valid source identity.");
    if (id === "steam") {
      assert(data.report && ["upwind_air_c", "downwind_air_c", "upwind_rh", "downwind_rh", "fetch_length_m", "internal_boundary_layer_m", "latent_flux_w_m2", "sensible_flux_w_m2"].every(key => finite(data.report[key])), "The steam estimate is incomplete.");
      assert(Array.isArray(data.components) && data.components.length === 2 && new Set(data.components.map(item => item.id)).size === 2 && data.components.every(item => ["pool", "outflow"].includes(item.id) && finite(item.area_m2) && item.area_m2 >= 0 && finite(item.latent_w_m2) && finite(item.sensible_w_m2)), "The steam source components are invalid.");
    } else if (id === "hyporheic") {
      assert(Array.isArray(data.times) && data.times.length && data.times.every((value, index) => finite(value) && (!index || value > data.times[index - 1])), "Saved channel times must increase.");
      assert(Array.isArray(data.cells) && data.cells.length && new Set(data.cells.map(cell => cell.id)).size === data.cells.length && data.cells.every((cell, index) => finite(cell.position_m) && (!index || cell.position_m > data.cells[index - 1].position_m)), "Saved channel cells must follow physical distance.");
      assert([data.water, data.bed].every(rows => Array.isArray(rows) && rows.length === data.times.length && rows.every(row => Array.isArray(row) && row.length === data.cells.length && row.every(nullable))), "Water and bed samples have different support.");
    } else if (id === "mat") {
      const grid = data.grid;
      assert(grid && Number.isInteger(grid.nx) && grid.nx > 0 && Number.isInteger(grid.nz) && grid.nz > 0 && finite(grid.cell_m) && grid.cell_m > 0 && Array.isArray(grid.origin_xz_m) && grid.origin_xz_m.length === 2 && grid.origin_xz_m.every(finite) && ["z_increasing", "z_decreasing"].includes(grid.row_order), "The classified map has invalid geometry.");
      assert(Array.isArray(data.legend) && data.legend.length && new Set(data.legend.map(item => item.class_id)).size === data.legend.length, "The classified map legend is invalid.");
      const ids = new Set(data.legend.map(item => item.class_id));
      assert(Array.isArray(data.values) && data.values.length === grid.nx * grid.nz && data.values.every(value => value === null || Number.isInteger(value) && ids.has(value)), "The classified map has an unknown class or different dimensions.");
    }
    return data;
  }
  async function load(snapshot, id, dependencies = {}) {
    const descriptor = snapshot.datasets?.process_visuals?.find(item => item.id === id);
    assert(descriptor, "The process visual is unavailable in this saved scenario.");
    const fetcher = dependencies.fetch || fetch, hash = dependencies.hashBytes || root.YSData.hashBytes;
    if (!cache.has(descriptor.sha256)) cache.set(descriptor.sha256, (async () => {
      const response = await fetcher(descriptor.url, {cache:"no-cache"});
      assert(response.ok, "The process visual could not be loaded.");
      const bytes = await response.arrayBuffer();
      assert(bytes.byteLength === descriptor.bytes && await hash(bytes) === descriptor.sha256, "The process visual failed its identity check.");
      return validate(JSON.parse(new TextDecoder().decode(bytes)), snapshot.snapshot, id);
    })());
    try { return validate(await cache.get(descriptor.sha256), snapshot.snapshot, id); }
    catch (error) { cache.delete(descriptor.sha256); throw error; }
  }
  function steamSummary(data, quantity, sourceId) {
    const report = data.report, humidity = quantity === "steam_humidity";
    const before = report[humidity ? "upwind_rh" : "upwind_air_c"] * (humidity ? 100 : 1);
    const after = report[humidity ? "downwind_rh" : "downwind_air_c"] * (humidity ? 100 : 1);
    const source = data.components.find(item => item.id === sourceId) || data.components[0];
    const flux = source[humidity ? "latent_w_m2" : "sensible_w_m2"];
    return {before, after, change:after-before, unit:humidity ? "%" : "°C", source, flux, powerMW:source.area_m2 * flux / 1e6,
      average:report[humidity ? "latent_flux_w_m2" : "sensible_flux_w_m2"], humidity};
  }
  function pairedSample(data, frame, cell) {
    const water = data.water[frame][cell], bed = data.bed[frame][cell];
    return {water, bed, difference:finite(water) && finite(bed) ? water-bed : null, time:data.times[frame], cell:data.cells[cell]};
  }
  const html = (tag, cls = "", text = "") => { const el = document.createElement(tag); el.className = cls; el.textContent = text; return el; };
  const svg = (tag, attrs = {}, text = "") => { const el = document.createElementNS("http://www.w3.org/2000/svg", tag); Object.entries(attrs).forEach(([key,value]) => el.setAttribute(key,value)); el.textContent = text; return el; };
  const fmt = (value, digits = 2) => finite(value) ? value.toLocaleString("en-US", {maximumFractionDigits:digits}) : "Missing";
  function steam(host, context) {
    const {visual, view} = context, section = html("section", "process-rich steam-visual"), figure = svg("svg", {role:"img", "aria-label":"Air exchange over warm water, shown schematically"});
    const caption = html("p", "analysis-note", "Bulk air exchange · schematic, not to scale"), controls = html("div", "rich-controls"), detail = html("output", "rich-readout");
    detail.setAttribute("aria-live", "polite");
    let selected = "pool";
    const buttons = visual.components.map(source => { const button = html("button", "", "Inspect " + source.label.toLowerCase()); button.type = "button"; button.onclick = () => {selected = source.id; draw();}; controls.append(button); return button; });
    section.append(caption, figure, controls, detail); host.append(section);
    function draw() {
      if (!section.isConnected) { observer.disconnect(); return; }
      const w = Math.max(240, section.clientWidth), h = 335, middle = w/2;
      figure.setAttribute("viewBox", `0 0 ${w} ${h}`); figure.setAttribute("height", h); figure.replaceChildren();
      const info = steamSummary(visual, view.id, selected), color = info.humidity ? "#8dcaca" : "#efa774";
      buttons.forEach((button, index) => button.setAttribute("aria-pressed", String(visual.components[index].id === selected)));
      figure.append(svg("text", {x:8,y:20}, "Upwind air"), svg("text", {x:w-8,y:20,"text-anchor":"end"}, "Downwind air"),
        svg("text", {x:8,y:44}, `${fmt(info.before)} ${info.unit}`), svg("text", {x:w-8,y:44,"text-anchor":"end"}, `${fmt(info.after)} ${info.unit}`),
        svg("text", {x:middle,y:77,"text-anchor":"middle"}, `${info.change >= 0 ? "+" : ""}${fmt(info.change)} ${info.humidity ? "percentage points" : "°C"}`));
      figure.append(svg("rect", {x:8,y:94,width:w-16,height:35,rx:17,fill:"#13151a"}), svg("path", {d:`M16 112H${w-16}m-9 -6l9 6l-9 6`,fill:"none",stroke:color,"stroke-width":2}),
        svg("text", {x:middle,y:153,"text-anchor":"middle",class:"rich-muted"}, info.humidity ? "Water vapor added to air" : "Heat added to air"));
      visual.components.forEach((source, index) => {
        const x = w*(index ? .71 : .29), active = source.id === selected;
        const path = svg("path", {d:`M${x} 223C${x-12} 191 ${x+12} 170 ${x} 120m-5 9l5 -9l6 8`,fill:"none",stroke:color,"stroke-width":active?2.5:1.5,opacity:active?1:.3});
        figure.append(path);
        if (!index) figure.append(svg("ellipse", {cx:x,cy:231,rx:Math.min(43,w*.14),ry:14,fill:color,opacity:active?.3:.1}));
        else figure.append(svg("path", {d:`M${x-w*.14} 233Q${x-w*.04} 220 ${x} 232T${x+w*.14} 232`,stroke:color,"stroke-width":13,fill:"none",opacity:active?.3:.1,"stroke-linecap":"round"}));
        figure.append(svg("text", {x,y:270,"text-anchor":"middle"}, source.label), svg("text", {x,y:290,"text-anchor":"middle",class:"rich-muted"}, `${fmt(source[info.humidity?"latent_w_m2":"sensible_w_m2"],1)} W/m²`));
      });
      figure.append(svg("text", {x:middle,y:326,"text-anchor":"middle",class:"rich-muted"}, `Effective fetch ${fmt(visual.report.fetch_length_m,1)} m`));
      detail.textContent = `${info.source.label}: ${fmt(info.source.area_m2,0)} m² · ${fmt(info.powerMW)} MW ${info.humidity ? "latent heat in evaporation" : "sensible heat"}. Area-weighted average: ${fmt(info.average,1)} W/m². Mixing depth: ${fmt(visual.report.internal_boundary_layer_m,1)} m.`;
    }
    const observer = new ResizeObserver(draw); observer.observe(section); draw();
    return {destroy:()=>observer.disconnect(), visual};
  }
  function bed(host, context) {
    const {visual} = context, section = html("section", "process-rich bed-visual"), controls = html("div", "rich-controls"), figure = svg("svg", {role:"img","aria-label":"Saved water and bed-water temperatures along the channel"}), stores = svg("svg",{role:"img","aria-label":"Temperature difference between selected water and bed stores"}), detail = html("output","rich-readout"), legend = html("div","rich-legend");
    detail.setAttribute("aria-live","polite");
    legend.append(html("span","rich-water","Channel water"),html("span","rich-bed","Bed-water store"));
    const timeLabel = html("label","analysis-control","Saved time"), time = html("input"), timeValue = html("output");
    time.type="range";time.min=0;time.max=visual.times.length-1;time.step=1;time.value=0;time.setAttribute("aria-label","Channel-bed saved time");timeLabel.append(timeValue,time);
    const cellLabel = html("label","analysis-control","Channel location"), cellInput = html("input");
    cellInput.type="range";cellInput.min=0;cellInput.max=visual.cells.length-1;cellInput.step=1;cellInput.value=0;cellInput.setAttribute("aria-label","Channel-bed cell");cellLabel.append(cellInput);
    controls.append(timeLabel,cellLabel);section.append(controls,legend,figure,stores,detail,html("p","analysis-note",`${visual.times.length} saved times across ${fmt((visual.times.at(-1)-visual.times[0])/3600)} hours. The lower store is modeled bed water; this is not a sediment-depth section.`));host.append(section);
    let frame=visual.times.length-1, cell=visual.cells.findIndex(item=>item.id===context.entity);
    if(cell<0){cell=0;let largest=-Infinity;visual.cells.forEach((_,index)=>{const sample=pairedSample(visual,frame,index);if(sample.difference!==null&&Math.abs(sample.difference)>largest){cell=index;largest=Math.abs(sample.difference);}});}
    time.value=frame;
    let lo=Infinity,hi=-Infinity;
    for(const frames of [visual.water,visual.bed])for(const row of frames)for(const value of row)if(finite(value)){lo=Math.min(lo,value);hi=Math.max(hi,value);}
    if(!finite(lo)){section.append(html("p","analysis-note","No paired temperatures were saved."));return {destroy(){},visual};}
    const pad=Math.max((hi-lo)*.06,.1);lo-=pad;hi+=pad;
    const positions=visual.cells.map(item=>item.position_m),start=positions[0],end=positions.at(-1);
    function draw() {
      if(!section.isConnected){observer.disconnect();return;}
      const w=Math.max(240,section.clientWidth),h=225,left=49,right=w-9,top=27,bottom=181;
      const x=value=>left+(value-start)/(end-start||1)*(right-left), y=value=>bottom-(value-lo)/(hi-lo)*(bottom-top);
      figure.setAttribute("viewBox",`0 0 ${w} ${h}`);figure.setAttribute("height",h);figure.replaceChildren();
      for(let tick=0;tick<3;tick++){
        const fraction=tick/2,py=top+fraction*(bottom-top),distance=start+fraction*(end-start),px=x(distance);
        figure.append(svg("path",{d:`M${left} ${py}H${right}`,stroke:"#2a2c31"}),svg("text",{x:left-7,y:py+4,"text-anchor":"end"},fmt(hi-fraction*(hi-lo),1)),svg("text",{x:px,y:202,"text-anchor":tick===0?"start":tick===2?"end":"middle"},fmt(distance,0)));
      }
      figure.append(svg("text",{x:8,y:15},"°C"),svg("text",{x:right,y:221,"text-anchor":"end",class:"rich-muted"},"Distance along channel · m"));
      for(const [values,color] of [[visual.water[frame],"#77b9e6"],[visual.bed[frame],"#efa774"]])figure.append(svg("path",{d:root.YSData.segments(values.map((value,index)=>({x:positions[index],y:value})),p=>x(p.x),p=>y(p.y)),fill:"none",stroke:color,"stroke-width":2}));
      figure.append(svg("path",{d:`M${x(positions[cell])} ${top}V${bottom}`,stroke:"#a2a4a9","stroke-width":1,"stroke-dasharray":"3 3"}));
      const sample=pairedSample(visual,frame,cell);
      for(const [value,color] of [[sample.water,"#77b9e6"],[sample.bed,"#efa774"]])if(finite(value))figure.append(svg("circle",{cx:x(positions[cell]),cy:y(value),r:3,fill:color}));
      timeValue.textContent=`${fmt(sample.time/60,1)} minutes`;cellInput.value=cell;
      stores.setAttribute("viewBox",`0 0 ${w} 147`);stores.setAttribute("height",147);stores.replaceChildren();
      stores.append(svg("rect",{x:8,y:12,width:w-16,height:43,fill:"#77b9e6",opacity:.12}),svg("rect",{x:8,y:88,width:w-16,height:43,fill:"#efa774",opacity:.12}),
        svg("text",{x:17,y:38},`Channel water ${fmt(sample.water)} °C`),svg("text",{x:17,y:114},`Bed-water store ${fmt(sample.bed)} °C`));
      const direction=sample.difference===null?"Missing paired sample":Math.abs(sample.difference)<1e-8?"Same temperature":sample.difference>0?"Water warmer":"Bed water warmer";
      stores.append(svg("text",{x:w/2,y:76,"text-anchor":"middle",class:"rich-muted"},`${direction}${sample.difference===null?"":` · Δ ${fmt(Math.abs(sample.difference))} °C`}`));
      detail.textContent=`${sample.cell.id} · ${fmt(sample.cell.position_m,1)} m along channel. Water ${fmt(sample.water)} °C; bed water ${fmt(sample.bed)} °C.`;
    }
    time.oninput=()=>{frame=Number(time.value);draw();};cellInput.oninput=()=>{cell=Number(cellInput.value);draw();};
    figure.onpointermove=event=>{const point=root.YSData.eventToSvg(figure,event);if(!point)return;const w=Math.max(240,section.clientWidth),distance=start+(point.x-49)/(w-58)*(end-start);cell=root.YSData.nearestIndex(positions,distance);draw();};
    const observer=new ResizeObserver(draw);observer.observe(section);draw();
    return {destroy:()=>observer.disconnect(),visual};
  }
  async function mount(host, context) {
    const {process,view,snapshot}=context;
    const custom=process==="steam"&&["steam_temperature","steam_humidity"].includes(view.id)||process==="mat"&&view.id==="community_area"||process==="hyporheic"&&view.id==="channel_bed";
    const visual=custom?await load(snapshot,process):null;
    if(!host.isConnected||context.isCurrent&&!context.isCurrent())return null;
    const next={...context,visual};
    if(process==="steam"&&visual)return steam(host,next);
    if(process==="hyporheic"&&visual)return bed(host,next);
    return root.YSThermalCharts?.render(host,next)||root.YSEcologyCharts?.render(host,next)||null;
  }
  const api={validate,load,steamSummary,pairedSample,mount};
  if(typeof module!=="undefined")module.exports=api;else root.YSProcessVisuals=api;
})(typeof window==="undefined"?{}:window);
