"use strict";

window.YSWorkbench = {
  destroy() {
    this.generation=(this.generation||0)+1;
    this.cleanup?.();this.cleanup=null;
  },
  async init(snapshot) {
    this.destroy();const generation=this.generation;
    const D = window.YSData, $ = id => document.getElementById(id), host = $("workbench-view");
    host.hidden = false;
    const descriptor = snapshot.datasets?.river;
    if (!descriptor) { host.textContent = "Native river samples are unavailable for this snapshot. Explore the system formulations or geographic coverage."; return; }
    host.innerHTML = `
      <div class="wb-heading"><div><p class="eyebrow">FIREHOLE RIVER / SAVED SCENARIO</p><h1>Follow heat through the river.</h1><p>Track a thermal signal downstream. Select a location and time to link all four views.</p></div><div class="wb-actions"><button id="wb-info" aria-expanded="false">Science & data</button><details><summary>Export view ↗</summary><div><button id="wb-csv">Source values · CSV</button><button id="wb-svg">Figure · SVG</button><button id="wb-recipe">View recipe · JSON</button><label class="wb-import">Load view recipe<input id="wb-import" type="file" accept=".json,application/json"></label></div></details></div></div>
      <div id="wb-loading" role="status">Loading native saved samples…</div>
      <div id="wb-controls" class="wb-controls" hidden>
        <button id="wb-play" aria-label="Play saved river run">▶</button>
        <label class="wb-time">Elapsed time <output id="wb-time-label"></output><input id="wb-time" type="range" min="0" step="1" aria-label="River elapsed time"></label>
        <label>Rate<select id="wb-speed" aria-label="Playback rate"><option value="60">60 s / s</option><option value="180" selected>180 s / s</option><option value="600">600 s / s</option></select></label>
        <label class="wb-location">Location <output id="wb-location-label"></output><input id="wb-location" type="range" min="0" step="1" aria-label="River cell"></label>
        <button id="wb-pin" aria-pressed="false">Pin selection</button><button id="wb-reset">Reset view</button>
      </div>
      <div id="wb-readout" class="wb-readout" role="status" aria-live="off"></div>
      <div id="wb-grid" class="wb-grid" hidden>
        <article class="wb-card wb-map-card"><div class="wb-card-title"><span>01 / CHANNEL</span><span>LOCAL GEOMETRY</span></div><div class="wb-map-container"><svg id="wb-map" viewBox="0 0 350 620" aria-label="River channel colored by temperature. Hover to probe; click to pin." role="img"></svg><div class="wb-map-buttons"><button id="wb-map-in" aria-label="Zoom river map in">+</button><button id="wb-map-out" aria-label="Zoom river map out">−</button><button id="wb-map-fit" aria-label="Fit river map">⌖</button></div></div><p class="wb-caption">Mapped centerline · N ↑<br>Local meters: x east, z south. Drag to pan; scroll to zoom.</p></article>
        <article class="wb-card wb-field-card"><div class="wb-card-title"><span>02 / HEAT THROUGH SPACE & TIME</span><span id="wb-field-kind">TEMPERATURE / °C</span></div><svg id="wb-field" viewBox="0 0 900 275" role="img" aria-label="Temperature field by downstream distance and elapsed minutes"></svg><div class="wb-legend"><span id="wb-low"></span><div id="wb-ramp"></div><span id="wb-high"></span><span class="wb-missing">▧ Missing</span><span>Fixed across saved run</span></div></article>
        <article class="wb-card wb-profile-card"><div class="wb-card-title"><span>03 / PROFILE AT SELECTED TIME</span><span>DOWNSTREAM DISTANCE / km</span></div><svg id="wb-profile" viewBox="0 0 500 250" role="img" aria-label="Longitudinal temperature profile"></svg><p class="wb-caption" id="wb-profile-note"></p></article>
        <article class="wb-card wb-history-card"><div class="wb-card-title"><span>04 / HISTORY AT SELECTED CELL</span><span>ELAPSED TIME / min</span></div><svg id="wb-history" viewBox="0 0 500 250" role="img" aria-label="Temperature history at selected river cell"></svg><p class="wb-caption" id="wb-history-note"></p></article>
      </div>
      <div id="wb-options" class="wb-options" hidden>
        <label><input id="wb-compare" type="checkbox" checked> Reference profile</label><button id="wb-reference">Use selected time as reference</button><span id="wb-reference-label"></span>
        <label><input id="wb-difference" type="checkbox"> Difference from reference</label><label>Vertical axes<select id="wb-scale"><option value="run">Fixed all-run range</option><option value="local">Local selected range</option></select></label>
        <details><summary>Range selection</summary><div class="wb-ranges"><label>From km<input id="wb-space-first" type="number" step="0.01" min="0"></label><label>To km<input id="wb-space-last" type="number" step="0.01" min="0"></label><label>From min<input id="wb-time-first" type="number" step="0.1"></label><label>To min<input id="wb-time-last" type="number" step="0.1"></label><button id="wb-range-apply">Apply range</button><button id="wb-range-reset">Full range</button></div></details>
      </div>
      <p id="wb-feedback" class="wb-feedback" role="status" aria-live="polite"></p>
      <section id="wb-details" class="wb-details" hidden aria-label="River science and data support">
        <article><p class="eyebrow">SCIENCE</p><h2>Water carries heat downstream.</h2><p>Advection transports heat with flowing water. Dispersion spreads temperature differences along the channel. Lateral inflows mix water and thermal energy; surface exchange and channel storage modify the temperature response.</p><p>This saved run uses prescribed upstream flow and temperature, authored meteorology, and a thermal inflow near Excelsior. Channel widths and submerged depths are estimates.</p><a id="wb-process-link" href="/dashboard/#view=systems&process=transport">Explore equations and exchanges ↗</a></article>
        <article><p class="eyebrow">DATA SUPPORT</p><h2>Saved model output</h2><dl id="wb-support"></dl><p>Numerical checks address the recorded model formulation. Field validation remains incomplete. Parameter uncertainty is unknown.</p></article>
        <article><p class="eyebrow">READING THE VIEWS</p><h2>One location, one time.</h2><p>Hover to preview. Click to pin; use the sliders for keyboard or touch selection. Drag across a profile or history to narrow its range. Numeric range controls provide the same selection.</p><p>Colors use one fixed range across the run. Difference mode uses a separate scale centered on zero. Gray marks identify missing values. Saved states are displayed without numerical interpolation.</p><p id="wb-availability"></p></article>
      </section>
      <details id="wb-table-wrap" class="wb-table-wrap" hidden><summary>Selected frame · source value table</summary><p id="wb-table-summary"></p><div class="wb-table-scroll"><table><thead><tr><th>Cell ID</th><th>Bounds / m</th><th>Distance / km</th><th>Temperature / °C</th><th>Difference / °C</th></tr></thead><tbody id="wb-table"></tbody></table></div></details>`;
    try {
      this.cache ||= new Map();
      let data=this.cache.get(descriptor.sha256);
      if(!data){
      const response = await fetch(descriptor.url, {cache:"no-cache"});
      if (!response.ok) throw Error("Native river dataset could not be loaded.");
      const bytes = await response.arrayBuffer();
      if (await D.hashBytes(bytes) !== descriptor.sha256) throw Error("Dataset byte identity differs from the catalog.");
      data = D.normalizeDataset(JSON.parse(new TextDecoder().decode(bytes)));
      if (data.snapshot !== snapshot.snapshot || data.source_sha256 !== descriptor.source_sha256) throw Error("Dataset source identity differs from the snapshot.");
      this.cache.set(descriptor.sha256,data);
      }
      if(generation!==this.generation)return;
      $("wb-loading").hidden = true;
      ["wb-controls","wb-grid","wb-options","wb-table-wrap"].forEach(id=>$(id).hidden=false);
      this.cleanup=this.mount(data, descriptor, snapshot);
    } catch (error) { if(generation===this.generation)$("wb-loading").textContent = error.message + " The system explorer remains available."; }
  },
  mount(data, descriptor, snapshot) {
    const lifecycle=new AbortController();
    const D=window.YSData, $=id=>document.getElementById(id), NS="http://www.w3.org/2000/svg";
    const svg=(tag,attrs={},text="")=>{const el=document.createElementNS(NS,tag);Object.entries(attrs).forEach(([k,v])=>el.setAttribute(k,v));el.textContent=text;return el;};
    const fmt=(value,digits=3)=>D.finite(value)?value.toLocaleString("en-US",{maximumFractionDigits:digits}):"Missing";
    const clock=t=>`${Math.floor(t/3600).toString().padStart(2,"0")}:${Math.floor(t%3600/60).toString().padStart(2,"0")}:${Math.floor(t%60).toString().padStart(2,"0")}`;
    const defaults={frame:D.nearestIndex(data.times,3600),cell:data.sources.length?D.nearestIndex(data.distances,data.sources[0].s_m+500):Math.floor(data.cells.length*.6),
      pinned:false,first:0,last:data.cells.length-1,timeFirst:0,timeLast:data.frames.length-1,reference:0,difference:false,compare:true,scale:"run"};
    let initial={...defaults};
    try {const stored=JSON.parse(sessionStorage.getItem(`ys-river-${data.snapshot}`));if(stored)initial={...initial,...D.restoreRecipe(stored,data,descriptor.sha256)};} catch {}
    const params=new URLSearchParams(location.hash.slice(1));
    if(params.has("t"))initial.frame=D.nearestIndex(data.times,D.clamp(Number(params.get("t")),data.times[0],data.times.at(-1)));
    if(params.has("cell"))initial.cell=D.clamp(Math.round(Number(params.get("cell")))||0,0,data.cells.length-1);
    const store=D.createStore(initial); let hover=null,queued=0,playing=false,lastTick=0,elapsed=data.times[initial.frame],playHandle=0;
    let lastRasterKey="",rasterUrl="",deltaDomain=null,deltaReference=-1,renderKey="",tableKey="",mapCamera={x:0,y:0,k:1},drag=null;
    let fieldKey="",fieldAxes=null,mapColorKey="";const lineCache=new WeakMap(),sizes=new WeakMap();
    const mapsvg=$("wb-map"),field=$("wb-field"),profile=$("wb-profile"),history=$("wb-history");
    [field,profile,history].forEach(chart=>{const r=chart.getBoundingClientRect();sizes.set(chart,{w:Math.max(200,r.width),h:Math.max(100,r.height)});chart.setAttribute("viewBox",`0 0 ${Math.max(200,r.width)} ${Math.max(100,r.height)}`);});
    const xe=D.extent(data.cells.map(c=>c.x)),ze=D.extent(data.cells.map(c=>c.z));
    const mk=Math.min(270/(xe[1]-xe[0]||1),500/(ze[1]-ze[0]||1));
    const mapPoint=c=>({x:175+(c.x-(xe[0]+xe[1])/2)*mk,y:300+(c.z-(ze[0]+ze[1])/2)*mk});
    const mapLayer=svg("g"),mapLines=[],mapMarker=svg("circle",{r:8,fill:"none",stroke:"#ffffff","stroke-width":2,"vector-effect":"non-scaling-stroke","pointer-events":"none"});
    mapsvg.append(mapLayer);
    data.cells.forEach((cell,i)=>{
      const p=mapPoint(cell),a=mapPoint(data.cells[Math.max(0,i-1)]),b=mapPoint(data.cells[Math.min(data.cells.length-1,i+1)]);
      const line=svg("path",{d:`M${(a.x+p.x)/2} ${(a.y+p.y)/2}L${p.x} ${p.y}L${(b.x+p.x)/2} ${(b.y+p.y)/2}`,fill:"none","stroke-width":5,"stroke-linecap":"round","vector-effect":"non-scaling-stroke"});
      line.append(svg("title",{},cell.id));mapLayer.append(line);mapLines.push(line);
    });
    data.sources.forEach(source=>{const p=mapPoint(data.cells[D.nearestIndex(data.distances,source.s_m)]);mapLayer.append(svg("path",{d:`M${p.x+15} ${p.y-10}L${p.x+5} ${p.y}`,stroke:"#efa774","stroke-width":1.5}),svg("text",{x:p.x+18,y:p.y-12,fill:"#efa774","font-size":10,"font-family":"monospace"},"THERMAL INPUT"));});
    mapLayer.append(mapMarker);
    mapsvg.append(svg("path",{d:`M25 580v6h${500*mk}v-6`,stroke:"#a2a4a9",fill:"none"}),svg("text",{x:25,y:605,fill:"#a2a4a9","font-size":11,"font-family":"monospace"},"500 m"));
    function mapTransform(){mapLayer.setAttribute("transform",`translate(${mapCamera.x},${mapCamera.y}) scale(${mapCamera.k})`);}
    function effective(){return {...store.get(),...hover};}
    function domain(s){if(!s.difference)return data.extent;if(deltaReference!==s.reference){deltaReference=s.reference;deltaDomain=D.differenceExtent(data,s.reference);}return deltaDomain;}
    function value(f,c,s){const v=data.frames[f].temperature[c];return s.difference?D.delta(v,data.frames[s.reference].temperature[c]):v;}
    function limits(s){return {x0:data.cells[s.first].bounds_m[0],x1:data.cells[s.last].bounds_m[1],t0:data.times[s.timeFirst],t1:data.times[s.timeLast]};}
    function update(patch,persist=true){hover=null;store.update(patch);if(persist){try{sessionStorage.setItem(`ys-river-${data.snapshot}`,JSON.stringify(D.recipe(data,descriptor.sha256,store.get())));}catch{}}}
    function schedule(){if(!queued)queued=requestAnimationFrame(()=>{queued=0;render();});}
    store.subscribe(schedule);
    function preview(patch){if(store.get().pinned||drag?.moved)return;hover=patch;schedule();}
    function pin(patch){pause();update({...patch,pinned:true});$("wb-feedback").textContent="Selection pinned. Sliders continue to change time and location.";}
    function raster(s){
      const key=[s.first,s.last,s.timeFirst,s.timeLast,s.difference,s.reference].join(":");
      if(key===lastRasterKey)return rasterUrl;lastRasterKey=key;
      const canvas=document.createElement("canvas");canvas.width=1000;canvas.height=360;const ctx=canvas.getContext("2d"),l=limits(s),colors=domain(s);
      const cols=Array.from({length:canvas.width},(_,i)=>{const distance=l.x0+(i+.5)/canvas.width*(l.x1-l.x0);let lo=s.first,hi=s.last;while(lo<hi){const mid=(lo+hi)>>>1;if(data.cells[mid].bounds_m[1]<distance)lo=mid+1;else hi=mid;}return lo;});
      const rows=Array.from({length:canvas.height},(_,i)=>D.nearestIndex(data.times,l.t1-(i+.5)/canvas.height*(l.t1-l.t0)));
      const image=ctx.createImageData(canvas.width,canvas.height);
      rows.forEach((f,y)=>cols.forEach((c,x)=>{const v=value(f,c,s),rgb=D.color(v,colors,s.difference).match(/\d+/g)?.map(Number)||[38,43,52],offset=(y*canvas.width+x)*4;
        if(D.finite(v)){image.data[offset]=rgb[0];image.data[offset+1]=rgb[1];image.data[offset+2]=rgb[2];}else{const shade=(x+y)%10<5?38:55;image.data[offset]=shade;image.data[offset+1]=shade;image.data[offset+2]=shade;}image.data[offset+3]=255;}));
      ctx.putImageData(image,0,0);rasterUrl=canvas.toDataURL("image/png");return rasterUrl;
    }
    function axis(chart,w,h,x0,x1,y0,y1,xformat,yformat){
      const left=58,top=18,right=w-18,bottom=h-42;
      for(let i=0;i<=4;i++){
        const x=left+(right-left)*i/4,y=top+(bottom-top)*i/4;
        chart.append(svg("path",{d:`M${left} ${y}H${right}`,stroke:"#2a2c31","stroke-width":.6}),
          svg("text",{x:left-9,y:y+4,fill:"#a2a4a9","font-size":11,"font-family":"monospace","text-anchor":"end"},yformat(y1-i/4*(y1-y0))),
          svg("text",{x,y:h-19,fill:"#a2a4a9","font-size":11,"font-family":"monospace","text-anchor":"middle"},xformat(x0+i/4*(x1-x0))));
      }
      return {x:v=>left+(v-x0)/(x1-x0||1)*(right-left),y:v=>bottom-(v-y0)/(y1-y0||1)*(bottom-top),left,right,top,bottom};
    }
    function fieldRender(s){
      const l=limits(s),{w,h}=sizes.get(field),key=[s.first,s.last,s.timeFirst,s.timeLast,s.difference,s.reference,w,h].join(":");
      if(key!==fieldKey){fieldKey=key;
      field.replaceChildren();fieldAxes=axis(field,w,h,l.x0,l.x1,l.t0,l.t1,v=>fmt(v/1000,2),v=>fmt(v/60,1));const a=fieldAxes;
      field.insertBefore(svg("image",{href:raster(s),x:a.left,y:a.top,width:a.right-a.left,height:a.bottom-a.top,preserveAspectRatio:"none"}),field.firstChild);
      field.append(svg("text",{x:15,y:13,fill:"#a2a4a9","font-size":10,"font-family":"monospace"},"min"),svg("text",{x:w-30,y:h-3,fill:"#a2a4a9","font-size":10,"font-family":"monospace"},"km"));
      }
      const a=fieldAxes;field.querySelectorAll(".wb-cursor").forEach(el=>el.remove());
      const fx=a.x(data.cells[s.cell].s),fy=a.y(data.times[s.frame]);
      if(fx>=a.left&&fx<=a.right)field.append(svg("path",{class:"wb-cursor",d:`M${fx} ${a.top}V${a.bottom}`,stroke:"white","stroke-opacity":.8,"pointer-events":"none"}));
      if(fy>=a.top&&fy<=a.bottom)field.append(svg("path",{class:"wb-cursor",d:`M${a.left} ${fy}H${a.right}`,stroke:"white","stroke-opacity":.8,"pointer-events":"none"}));
      return a;
    }
    function lineRender(chart,points,s,temporal){
      const {w,h}=sizes.get(chart),key=[temporal?s.cell:s.frame,s.first,s.last,s.timeFirst,s.timeLast,s.reference,s.difference,s.compare,s.scale,w,h].join(":");
      let a=lineCache.get(chart)?.axes;
      if(lineCache.get(chart)?.key!==key){
      chart.replaceChildren();let e=domain(s)||[0,1];
      if(s.scale==="local"){const ys=points.map(p=>p.y);if(!temporal&&s.compare&&!s.difference)points.forEach(p=>ys.push(data.frames[s.reference].temperature[p.index]));e=D.extent(ys)||e;}
      const pad=Math.max((e[1]-e[0])*.08,.00001),min=e[0]-pad,max=e[1]+pad,l=limits(s);
      a=axis(chart,w,h,temporal?l.t0:l.x0,temporal?l.t1:l.x1,min,max,v=>fmt(v/(temporal?60:1000),2),v=>fmt(v,3));
      chart.append(svg("text",{x:12,y:12,fill:"#a2a4a9","font-size":10,"font-family":"monospace"},s.difference?"Δ°C":"°C"));
      if(!temporal&&s.compare&&!s.difference){const reference=points.map(p=>({...p,y:data.frames[s.reference].temperature[p.index]}));chart.append(svg("path",{d:D.segments(reference,p=>a.x(p.x),p=>a.y(p.y)),fill:"none",stroke:"#b8b4e9","stroke-width":1.5,"stroke-dasharray":"5 4"}));}
      chart.append(svg("path",{d:D.segments(points,p=>a.x(p.x),p=>a.y(p.y)),fill:"none",stroke:temporal?"#efa774":"#8dcaca","stroke-width":2}));
      points.forEach((p,i)=>{if(D.finite(p.y)&&(!D.finite(points[i-1]?.y)||!D.finite(points[i+1]?.y)))chart.append(svg("circle",{cx:a.x(p.x),cy:a.y(p.y),r:2,fill:temporal?"#efa774":"#8dcaca"}));});
      chart.setAttribute("aria-label",`${temporal?"Time history":"Longitudinal profile"}. ${s.difference?"Difference":"Temperature"} in Celsius. ${s.scale==="local"?"Local":"Fixed all-run"} vertical range ${fmt(min,6)} to ${fmt(max,6)}. ${points.filter(p=>D.finite(p.y)).length} finite samples of ${points.length}.`);
      $(temporal?"wb-history-note":"wb-profile-note").textContent=`${s.scale==="local"?"Local selected range":"Fixed all-run range"} · ${s.difference?"Difference / °C":"Temperature / °C"}${!temporal&&s.compare&&!s.difference?" · Dashed: reference":""}`;
      lineCache.set(chart,{key,axes:a});
      }
      chart.querySelectorAll(".wb-cursor").forEach(el=>el.remove());const l=limits(s),x=temporal?data.times[s.frame]:data.cells[s.cell].s,y=value(s.frame,s.cell,s);
      if(x>=(temporal?l.t0:l.x0)&&x<=(temporal?l.t1:l.x1)){chart.append(svg("path",{class:"wb-cursor",d:`M${a.x(x)} ${a.top}V${a.bottom}`,stroke:"#d3d8e2","stroke-width":1,"stroke-dasharray":"3 3"}));if(D.finite(y))chart.append(svg("circle",{class:"wb-cursor",cx:a.x(x),cy:a.y(y),r:4,fill:"#ffffff"}));}
    }
    function render(){
      const s=effective(),persistent=store.get(),cell=data.cells[s.cell],frame=data.frames[s.frame],colors=domain(s),v=frame.temperature[s.cell],d=D.delta(v,data.frames[s.reference].temperature[s.cell]);
      const key=[s.frame,s.cell,s.first,s.last,s.timeFirst,s.timeLast,s.reference,s.difference,s.compare,s.scale].join(":");
      if(key!==renderKey){
        renderKey=key;fieldRender(s);
        lineRender(profile,data.cells.slice(s.first,s.last+1).map((c,i)=>({x:c.s,y:value(s.frame,s.first+i,s),index:s.first+i})),s,false);
        lineRender(history,data.frames.slice(s.timeFirst,s.timeLast+1).map((f,i)=>({x:f.t,y:value(s.timeFirst+i,s.cell,s),index:s.timeFirst+i})),s,true);
        const colorKey=[s.frame,s.first,s.last,s.reference,s.difference].join(":");if(colorKey!==mapColorKey){mapColorKey=colorKey;mapLines.forEach((line,i)=>{line.setAttribute("stroke",D.color(value(s.frame,i,s),colors,s.difference));line.setAttribute("opacity",i>=s.first&&i<=s.last?1:.2);});}
        const p=mapPoint(cell);mapMarker.setAttribute("cx",p.x);mapMarker.setAttribute("cy",p.y);
      }
      $("wb-readout").replaceChildren();
      [[`${fmt(v,5)} °C`,s.difference?`Δ ${fmt(d,5)} °C from reference`:"MODELED TEMPERATURE"],[`${fmt(cell.s/1000,3)} km`,cell.id],[clock(frame.t),new Date(Date.parse(data.epoch)+frame.t*1000).toISOString().replace("T"," ")],[hover?"Preview":persistent.pinned?"Pinned":"Interactive","HOVER TO PROBE · CLICK TO PIN"]].forEach(([a,b])=>{const el=document.createElement("div"),strong=document.createElement("strong"),small=document.createElement("small");strong.textContent=a;small.textContent=b;el.append(strong,small);$("wb-readout").append(el);});
      $("wb-time").value=s.frame;$("wb-location").value=s.cell;$("wb-time-label").textContent=clock(frame.t);$("wb-location-label").textContent=`${fmt(cell.s/1000,3)} km`;
      $("wb-pin").setAttribute("aria-pressed",String(persistent.pinned));$("wb-pin").textContent=persistent.pinned?"Unpin selection":"Pin selection";
      $("wb-compare").checked=s.compare;$("wb-difference").checked=s.difference;$("wb-scale").value=s.scale;$("wb-reference-label").textContent=`Reference ${clock(data.times[s.reference])}`;
      $("wb-low").textContent=colors?fmt(colors[0],4):"No finite values";$("wb-high").textContent=colors?`${fmt(colors[1],4)} ${s.difference?"Δ°C":"°C"}`:"";
      $("wb-ramp").style.background=`linear-gradient(90deg,${Array.from({length:9},(_,i)=>D.color(colors?colors[0]+i/8*(colors[1]-colors[0]):null,colors,s.difference)).join(",")})`;
      $("wb-field-kind").textContent=s.difference?"DIFFERENCE / Δ°C":"TEMPERATURE / °C";
      $("wb-process-link").href=`/dashboard/#view=systems&process=transport&t=${frame.t}&cell=${s.cell}`;
      if($("wb-table-wrap").open)renderTable();
    }
    function renderTable(){const s=store.get(),key=[s.frame,s.first,s.last,s.reference].join(":");if(key===tableKey)return;tableKey=key;const body=$("wb-table");body.replaceChildren();
      for(let i=s.first;i<=s.last;i++){const c=data.cells[i],v=data.frames[s.frame].temperature[i],tr=document.createElement("tr");
        [c.id,c.bounds_m.map(v=>fmt(v,4)).join(" – "),fmt(c.s/1000,6),D.finite(v)?String(v):"Missing",D.finite(D.delta(v,data.frames[s.reference].temperature[i]))?String(D.delta(v,data.frames[s.reference].temperature[i])):"Missing"].forEach(text=>{const td=document.createElement("td");td.textContent=text;tr.append(td);});body.append(tr);}
      $("wb-table-summary").textContent=`${s.last-s.first+1} cells at ${clock(data.times[s.frame])}. Numeric source precision retained. CSV includes all saved times within the selected range.`;
    }
    function ranges(){const s=store.get();$("wb-space-first").value=(data.cells[s.first].bounds_m[0]/1000).toFixed(6);$("wb-space-last").value=(data.cells[s.last].bounds_m[1]/1000).toFixed(6);$("wb-time-first").value=data.times[s.timeFirst]/60;$("wb-time-last").value=data.times[s.timeLast]/60;}
    function chartSelection(chart,event,kind){const p=D.eventToSvg(chart,event);if(!p)return null;const s=store.get(),l=limits(s),{w,h}=sizes.get(chart);
      if(p.x<58||p.x>w-18||p.y<18||p.y>h-42)return null;
      const distance=l.x0+(p.x-58)/(w-76)*(l.x1-l.x0),t=kind==="field"?l.t1-(p.y-18)/(h-60)*(l.t1-l.t0):l.t0+(p.x-58)/(w-76)*(l.t1-l.t0);
      return kind==="history"?{frame:D.nearestIndex(data.times,t)}:kind==="field"?{cell:D.nearestIndex(data.distances,distance),frame:D.nearestIndex(data.times,t)}:{cell:D.nearestIndex(data.distances,distance)};
    }
    [[field,"field"],[profile,"profile"],[history,"history"]].forEach(([chart,kind])=>{
      let brush=null;
      chart.addEventListener("pointermove",event=>{if(brush)return;const patch=chartSelection(chart,event,kind);if(patch)preview(patch);});
      chart.addEventListener("pointerleave",()=>{hover=null;schedule();});
      chart.addEventListener("pointerdown",event=>{const point=chartSelection(chart,event,kind);if(!point)return;brush={x:event.clientX,patch:point};chart.setPointerCapture(event.pointerId);});
      chart.addEventListener("pointerup",event=>{if(!brush)return;const end=chartSelection(chart,event,kind),start=brush;brush=null;if(!end)return;
        if(kind!=="field"&&Math.abs(event.clientX-start.x)>12){pause();const key=kind==="history"?"frame":"cell",bounds=[start.patch[key],end[key]].sort((a,b)=>a-b);update(kind==="history"?{timeFirst:bounds[0],timeLast:bounds[1]}:{first:bounds[0],last:bounds[1]});ranges();}else pin(end);});
      chart.addEventListener("pointercancel",()=>{brush=null;});
    });
    function mapSelect(event){const p=D.eventToSvg(mapsvg,event);if(!p)return null;let best=0,distance=Infinity;data.cells.forEach((c,i)=>{const q=mapPoint(c),d=Math.hypot(q.x*mapCamera.k+mapCamera.x-p.x,q.y*mapCamera.k+mapCamera.y-p.y);if(d<distance){distance=d;best=i;}});return {cell:best};}
    mapsvg.addEventListener("pointermove",event=>{if(drag){const p=D.eventToSvg(mapsvg,event);if(!p)return;if(Math.hypot(p.x-drag.start.x,p.y-drag.start.y)>3)drag.moved=true;if(drag.moved){mapCamera.x+=p.x-drag.previous.x;mapCamera.y+=p.y-drag.previous.y;mapTransform();}drag.previous=p;}else preview(mapSelect(event));});
    mapsvg.addEventListener("pointerleave",()=>{if(!drag){hover=null;schedule();}});
    mapsvg.addEventListener("pointerdown",event=>{const p=D.eventToSvg(mapsvg,event);if(!p)return;drag={start:p,previous:p,moved:false};mapsvg.setPointerCapture(event.pointerId);});
    mapsvg.addEventListener("pointerup",event=>{if(drag&&!drag.moved)pin(mapSelect(event));drag=null;});mapsvg.addEventListener("pointercancel",()=>{drag=null;});
    function zoom(factor,p={x:175,y:310}){const k=D.clamp(mapCamera.k*factor,.7,8),ratio=k/mapCamera.k;mapCamera={x:p.x-(p.x-mapCamera.x)*ratio,y:p.y-(p.y-mapCamera.y)*ratio,k};mapTransform();}
    mapsvg.addEventListener("wheel",event=>{if(innerWidth<721)return;event.preventDefault();zoom(Math.exp(-event.deltaY*.002),D.eventToSvg(mapsvg,event)||undefined);},{passive:false});
    $("wb-map-in").onclick=()=>zoom(1.4);$("wb-map-out").onclick=()=>zoom(1/1.4);$("wb-map-fit").onclick=()=>{mapCamera={x:0,y:0,k:1};mapTransform();};
    function pause(){playing=false;cancelAnimationFrame(playHandle);playHandle=0;lastTick=0;$("wb-play").textContent="▶";$("wb-play").setAttribute("aria-label","Play saved river run");}
    function tick(now){if(!playing)return;if(document.hidden){pause();return;}if(lastTick)elapsed+=(now-lastTick)/1000*Number($("wb-speed").value);lastTick=now;const s=store.get(),end=data.times[s.timeLast];
      const next=D.clamp(D.frameAtElapsed(data.times,Math.min(end,elapsed)),s.timeFirst,s.timeLast);if(next!==s.frame)update({frame:next},false);
      if(elapsed>=end){pause();update({});}else playHandle=requestAnimationFrame(tick);}
    $("wb-play").onclick=()=>{if(playing){pause();update({});return;}const s=store.get();elapsed=data.times[s.frame>=s.timeLast?s.timeFirst:Math.max(s.frame,s.timeFirst)];playing=true;hover=null;lastTick=0;$("wb-play").textContent="Ⅱ";$("wb-play").setAttribute("aria-label","Pause saved river run");playHandle=requestAnimationFrame(tick);};
    document.addEventListener("visibilitychange",()=>{if(document.hidden)pause();},{signal:lifecycle.signal});window.addEventListener("pagehide",pause,{signal:lifecycle.signal});
    $("wb-time").max=data.frames.length-1;$("wb-location").max=data.cells.length-1;
    $("wb-time").oninput=e=>{pause();update({frame:Number(e.target.value)});};$("wb-location").oninput=e=>update({cell:Number(e.target.value)});
    $("wb-pin").onclick=()=>update({pinned:!store.get().pinned});
    $("wb-reset").onclick=()=>{pause();update({...defaults});ranges();mapCamera={x:0,y:0,k:1};mapTransform();};
    $("wb-compare").onchange=e=>update({compare:e.target.checked});$("wb-difference").onchange=e=>update({difference:e.target.checked});$("wb-scale").onchange=e=>update({scale:e.target.value});
    $("wb-reference").onclick=()=>update({reference:effective().frame});
    $("wb-range-apply").onclick=()=>{const values=["wb-space-first","wb-space-last","wb-time-first","wb-time-last"].map(id=>$(id).valueAsNumber);
      if(values.some(v=>!D.finite(v))||values[0]>values[1]||values[2]>values[3]||values[0]<0||values[1]>data.length_m/1000+.000001||values[2]<data.times[0]/60||values[3]>data.times.at(-1)/60){$("wb-feedback").textContent="Enter ordered bounds within the saved distance and time support.";return;}
      pause();update({first:D.nearestIndex(data.distances,values[0]*1000),last:D.nearestIndex(data.distances,values[1]*1000),timeFirst:D.nearestIndex(data.times,values[2]*60),timeLast:D.nearestIndex(data.times,values[3]*60)});ranges();$("wb-feedback").textContent="Range snapped to saved cells and times.";};
    $("wb-range-reset").onclick=()=>{update({first:0,last:data.cells.length-1,timeFirst:0,timeLast:data.frames.length-1});ranges();};
    $("wb-info").onclick=()=>{const open=$("wb-details").hidden;$("wb-details").hidden=!open;$("wb-info").setAttribute("aria-expanded",String(open));if(open)$("wb-details").scrollIntoView({behavior:"smooth",block:"nearest"});};
    $("wb-table-wrap").addEventListener("toggle",renderTable);
    const support=$("wb-support");[["Scenario",`${data.run_mode} · ${data.snapshot}`],["Samples",`${data.frames.length} times × ${data.cells.length} cells`],["Time support",`${clock(data.times[0])}–${clock(data.times.at(-1))} elapsed · ${data.epoch}`],["Spatial support",data.support.space],["Saved states",data.support.time],["Display",data.support.display],["Geometry",data.support.geometry],["Dataset SHA-256",descriptor.sha256]].forEach(([label,text])=>{const dt=document.createElement("dt"),dd=document.createElement("dd");dt.textContent=label;dd.textContent=text;support.append(dt,dd);});
    $("wb-availability").textContent=`${(data.frames.length*data.cells.length-data.missing).toLocaleString()} finite temperature values; ${data.missing.toLocaleString()} missing. No field-observation series or uncertainty bounds are supplied in this workspace.`;
    function download(text,type,name){const blob=new Blob([text],{type}),url=URL.createObjectURL(blob),a=document.createElement("a");a.href=url;a.download=name;document.body.append(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(url),10000);}
    $("wb-csv").onclick=()=>{const s=store.get();download(D.csv(data,s,descriptor.sha256),"text/csv","yellowstone-river-values.csv");$("wb-feedback").textContent="Native values exported. Export a view recipe to retain the complete analysis settings.";};
    $("wb-recipe").onclick=()=>{download(JSON.stringify(D.recipe(data,descriptor.sha256,store.get()),null,2),"application/json","yellowstone-river-view.json");$("wb-feedback").textContent="View recipe exported with the selected dataset hash.";};
    $("wb-import").onchange=async event=>{try{const file=event.target.files[0];if(!file)return;if(file.size>1024*1024)throw Error("Recipe exceeds 1 MB.");const restored=D.restoreRecipe(JSON.parse(await file.text()),data,descriptor.sha256);pause();update(restored);ranges();$("wb-feedback").textContent="View restored from the matching dataset recipe.";}catch(error){$("wb-feedback").textContent=error.message;}finally{event.target.value="";}};
    $("wb-svg").onclick=()=>{
      hover=null;renderKey="";render();const s=store.get(),figure=svg("svg",{xmlns:NS,viewBox:"0 0 1500 1000",width:1500,height:1000});figure.append(svg("rect",{width:1500,height:1000,fill:"#07080b"}),svg("text",{x:30,y:35,fill:"#e8eaef","font-size":24,"font-family":"sans-serif"},"Firehole River · saved model temperature"),svg("text",{x:30,y:65,fill:"#a2a4a9","font-size":13,"font-family":"monospace"},`${data.snapshot} · ${clock(data.times[s.frame])} elapsed · cell ${data.cells[s.cell].id} · uncertainty unknown`));
      [[mapsvg,20,100,360,650],[field,400,100,1080,330],[profile,400,470,530,300],[history,950,470,530,300]].forEach(([source,x,y,width,height])=>{const clone=source.cloneNode(true);clone.setAttribute("x",x);clone.setAttribute("y",y);clone.setAttribute("width",width);clone.setAttribute("height",height);figure.append(clone);});
      const colorDomain=domain(s);for(let i=0;i<100;i++)figure.append(svg("rect",{x:800+i*3,y:62,width:3.1,height:9,fill:D.color(colorDomain?colorDomain[0]+i/99*(colorDomain[1]-colorDomain[0]):null,colorDomain,s.difference)}));
      figure.append(svg("text",{x:790,y:71,fill:"#a2a4a9","font-size":12,"font-family":"monospace","text-anchor":"end"},colorDomain?fmt(colorDomain[0],5):"Missing"),svg("text",{x:1110,y:71,fill:"#a2a4a9","font-size":12,"font-family":"monospace"},`${colorDomain?fmt(colorDomain[1],5):""} ${s.difference?"delta C":"C"}`));
      ["Channel: local meters, x east / z south; north up.","Field: distance downstream / km; elapsed time / min. Profile: distance / km. History: elapsed time / min.",`${s.difference?"Difference":"Temperature"} / C. Fixed color domain: ${(domain(s)||[]).join(" to ")}. ${s.scale==="local"?"Local selected":"Fixed all-run"} line axes.`,`${data.support.display} Raster resolution 1000 x 360. Missing: gray hatching.`,`${data.support.geometry} Prescribed forcing; field validation incomplete.`,`Dataset SHA-256: ${descriptor.sha256}`].forEach((text,i)=>figure.append(svg("text",{x:30,y:820+i*25,fill:"#a2a4a9","font-size":13,"font-family":"monospace"},text)));
      figure.append(svg("metadata",{},JSON.stringify(D.recipe(data,descriptor.sha256,s))));download(new XMLSerializer().serializeToString(figure),"image/svg+xml","yellowstone-river-figure.svg");$("wb-feedback").textContent="Figure exported with support, axes, source identity, and view recipe.";};
    const observer=new ResizeObserver(entries=>{entries.forEach(({target,contentRect:r})=>{if(r.width<1||r.height<1)return;const size={w:Math.max(200,r.width),h:Math.max(100,r.height)};sizes.set(target,size);target.setAttribute("viewBox",`0 0 ${size.w} ${size.h}`);});renderKey="";schedule();});
    [field,profile,history].forEach(chart=>observer.observe(chart));
    ranges();render();
    return ()=>{pause();observer.disconnect();cancelAnimationFrame(queued);lifecycle.abort();};
  }
};
