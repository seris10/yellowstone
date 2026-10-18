"use strict";

((root) => {
  const M = typeof module !== "undefined" ? require("./systems-model.js") : root.YSSystemsModel;
  const D = typeof module !== "undefined" ? require("./data-model.js") : root.YSData;
  const finite = Number.isFinite;
  function channelData(dataset, variable = "feeding_brown_trout") {
    const series = new Map(dataset.series.filter(s => s.variable_id === variable && s.entity_id).map(s => [s.entity_id, s]));
    const cells = dataset.entities.filter(e => finite(e.metadata?.chainage_m)).slice().sort((a,b) => a.metadata.chainage_m-b.metadata.chainage_m);
    const times = [...new Set([...series.values()].flatMap(s => s.times))].sort((a,b) => a-b);
    const extent = M.stats((function*(){for(const s of series.values()) yield* s.values;})());
    return {cells, series, times, extent};
  }
  function savedProfile(channel, elapsed) {
    return channel.cells.map(entity => {
      const series = channel.series.get(entity.id), i = series ? D.nearestIndex(series.times, elapsed) : -1;
      const exact = i >= 0 && series.times[i] === elapsed;
      return {entity, x:entity.metadata.chainage_m, y:exact && finite(series.values[i]) ? series.values[i] : null};
    });
  }
  function crownRange(entities, variable, range) {
    const values = entities.map(e => e.values[variable]), selected = values.filter(v => finite(v) && v >= range[0] && v <= range[1]);
    const all = M.histogram(values, {bins:16});
    const filtered = M.histogram(selected, {bins:16, range:all.extent});
    return {all, filtered, selected:selected.length, missing:all.missing};
  }
  function nearestSpatial(entities, point) {
    let selected = null, distance = Infinity;
    for (const entity of entities) {
      if (!finite(entity.x) || !finite(entity.z)) continue;
      const d = (entity.x-point.x)**2+(entity.z-point.z)**2;
      if (d < distance) { selected=entity; distance=d; }
    }
    return selected;
  }
  function spatialExtent(entities) {
    const x=M.stats(entities.map(e=>e.x)),z=M.stats(entities.map(e=>e.z));
    return x.finite && z.finite ? {x0:x.min,x1:x.max,z0:z.min,z1:z.max} : null;
  }
  function render(host, context) {
    const {process, view, field, dataset, selectEntity = () => {}} = context;
    const quantity = view?.quantity || view?.id || field?.variable_id || field?.id;
    if (!dataset || !(process === "fish" && ["feeding_brown_trout","stressor_factors"].includes(quantity) || process === "canopy" && ["height","core_area"].includes(quantity))) return null;
    const el=(tag,cls="",text="")=>{const node=document.createElement(tag);node.className=cls;node.textContent=text;return node;};
    const svg=(tag,attrs={},text="")=>{const node=document.createElementNS("http://www.w3.org/2000/svg",tag);for(const [k,v]of Object.entries(attrs))node.setAttribute(k,v);node.textContent=text;return node;};
    const fmt=(v,digits=3)=>finite(v)?v.toLocaleString("en-US",{maximumFractionDigits:digits}):"Missing";
    const section=el("section","pe-chart"),description=el("p","pe-note"),readout=el("output","pe-readout");
    readout.setAttribute("aria-live","polite");section.append(description);host.append(section);
    let destroyed=false, redraw=()=>{}, resize=null;
    const cleanups=[];
    const listen=(node,event,fn)=>{node.addEventListener(event,fn);cleanups.push(()=>node.removeEventListener(event,fn));};
    const control=(title,input)=>{const label=el("label","pe-control",title);label.append(input);return label;};
    const range=(label,max,value=0)=>{const node=el("input");node.type="range";node.min=0;node.max=max;node.step=1;node.value=value;node.setAttribute("aria-label",label);return node;};
    const figure=(title,kind)=>{const figure=el("figure","pe-figure"),caption=el("figcaption","pe-caption",title),node=kind==="canvas"?el("canvas","pe-map"):svg("svg",{class:"pe-plot",role:"img"});node.setAttribute("role","img");node.setAttribute("tabindex","0");node.setAttribute("aria-label",title);figure.append(caption,node);section.append(figure);return node;};
    const width=()=>Math.max(180,section.querySelector(".pe-map")?.getBoundingClientRect().width||section.clientWidth-2||278),canvasBounds=new WeakMap();
    const canvasSetup=(canvas,w,h)=>{const dpr=Math.min(2,root.devicePixelRatio||1);canvas.width=Math.round(w*dpr);canvas.height=Math.round(h*dpr);canvas.style.height=`${h}px`;canvasBounds.set(canvas,{w,h});const ctx=canvas.getContext("2d");ctx.setTransform(dpr,0,0,dpr,0,0);ctx.fillStyle="#0b0e14";ctx.fillRect(0,0,w,h);return ctx;};
    const pointAt=(canvas,event)=>{const rect=canvas.getBoundingClientRect(),bounds=canvasBounds.get(canvas);return{x:(event.clientX-rect.left)*bounds.w/rect.width,y:(event.clientY-rect.top)*bounds.h/rect.height};};
    function mapLabels(ctx,w,h,extent,transform){ctx.font="11px monospace";ctx.fillStyle="#a2a4a9";ctx.textAlign="left";ctx.fillText("N ↑",9,17);const metres=Math.max(1,10**Math.floor(Math.log10(Math.max(1,(w-40)/transform.k/3))));const pixels=metres*transform.k;ctx.strokeStyle="#a2a4a9";ctx.beginPath();ctx.moveTo(12,h-22);ctx.lineTo(12+pixels,h-22);ctx.stroke();ctx.fillText(`${fmt(metres,0)} m`,12,h-7);ctx.textAlign="right";ctx.fillText("local coordinates",w-9,h-7);}
    function linePlot(plot,rows,w,domain,label,selected){
      const h=210,right=w-12,top=25,bottom=168,xs=M.stats(rows.map(p=>p.x)),lo=domain[0],hi=domain[1],span=hi-lo||Math.max(Math.abs(lo)*.01,.01),digits=Math.max(0,Math.min(8,2-Math.floor(Math.log10(span)))),left=Math.max(50,18+Math.max(fmt(lo,digits).length,fmt(lo+span,digits).length)*7);
      plot.replaceChildren();plot.setAttribute("viewBox",`0 0 ${w} ${h}`);
      const x=v=>left+(v-xs.min)/(xs.max-xs.min||1)*(right-left),y=v=>bottom-(v-lo)/span*(bottom-top);
      for(let i=0;i<3;i++){const v=lo+span*i/2,py=y(v);plot.append(svg("path",{d:`M${left} ${py}H${right}`,stroke:"#2a2c31"}),svg("text",{x:left-7,y:py+4,"text-anchor":"end",class:"pe-axis"},fmt(v,digits)));}
      for(let i=0;i<3;i++){const v=xs.min+(xs.max-xs.min)*i/2;plot.append(svg("text",{x:x(v),y:188,"text-anchor":i===0?"start":i===2?"end":"middle",class:"pe-axis"},fmt(v,0)));}
      plot.append(svg("text",{x:left,y:14,class:"pe-axis"},label),svg("text",{x:right,y:206,"text-anchor":"end",class:"pe-axis"},"distance downstream (m)"),svg("path",{d:D.segments(rows,p=>x(p.x),p=>y(p.y)),fill:"none",stroke:"var(--domain,#8dcaca)","stroke-width":2}));
      const row=rows.find(p=>p.entity.id===selected);if(row){plot.append(svg("path",{d:`M${x(row.x)} ${top}V${bottom}`,stroke:"#e8eaef","stroke-dasharray":"3 4"}));if(finite(row.y))plot.append(svg("circle",{cx:x(row.x),cy:y(row.y),r:4,fill:"#e8eaef"}));}
      return {x, left, right, min:xs.min,max:xs.max};
    }
    if(process==="fish") {
      const channel=channelData(dataset),cells=channel.cells,extent=spatialExtent(cells);
      if(!cells.length||!extent){section.remove();return null;}
      let selected=field.entity?.id||field.entity_id||cells[0].id,frame=0,transform=null,profileScale=null,rows=[];
      const factors=quantity==="stressor_factors",table=dataset.tables?.find(t=>t.id==="stressor_factors");
      if(factors&&!table?.rows?.length){section.remove();return null;}
      const factorById=new Map((table?.rows||[]).map(row=>[row.cell_id,row]));
      description.textContent=factors?"Select a channel cell to inspect its saved suitability factors. These diagnostic factors are separate from the feeding trajectory.":"Brown trout feeding response along the saved channel. Scrub the saved times, then select a cell on either view. This relative model index is not a fish count or observed feeding.";
      let timeSlider=null,timeOutput=null;
      if(!factors){
        if(!channel.times.length){section.remove();return null;}
        timeSlider=range("Saved feeding time",channel.times.length-1);timeOutput=el("output");const label=control("Saved simulation time",timeSlider);label.append(timeOutput);section.append(label);listen(timeSlider,"input",()=>{frame=Number(timeSlider.value);redraw();});
      }
      const map=figure("Channel map — select a saved cell","canvas"),profile=figure(factors?"Combined suitability factor along the channel":"Feeding response along the channel","svg");
      const cellSlider=range("Channel cell",cells.length-1,Math.max(0,cells.findIndex(e=>e.id===selected)));section.append(control("Channel cell",cellSlider),readout);
      const factorBox=factors?el("div","pe-factor-list"):null;if(factorBox)section.append(factorBox);
      const note=el("p","pe-note",factors?"A factor of 1 leaves the thermal utility unchanged. The component factors are multiplicative; bars are not parts of a total.":`${channel.times.length} saved times. Colors and the profile use one range across the full saved interval. Missing values remain gaps; values between saved times are not interpolated.`);section.append(note);
      const choose=(id)=>{selected=id;cellSlider.value=cells.findIndex(e=>e.id===id);redraw();selectEntity(id);};
      listen(cellSlider,"input",()=>choose(cells[Number(cellSlider.value)].id));
      const keyboard=event=>{if(!["ArrowLeft","ArrowRight","Home","End"].includes(event.key))return;event.preventDefault();const i=cells.findIndex(e=>e.id===selected);choose(cells[event.key==="Home"?0:event.key==="End"?cells.length-1:Math.max(0,Math.min(cells.length-1,i+(event.key==="ArrowRight"?1:-1)))].id);};
      listen(map,"keydown",keyboard);listen(profile,"keydown",keyboard);
      listen(map,"click",event=>{if(!transform)return;const p=pointAt(map,event),nearest=nearestSpatial(cells,transform.invert(p.x,p.y));if(nearest)choose(nearest.id);});
      listen(profile,"click",event=>{const p=D.eventToSvg(profile,event);if(!p||!profileScale)return;const chainage=profileScale.min+(p.x-profileScale.left)/(profileScale.right-profileScale.left)*(profileScale.max-profileScale.min);const i=D.nearestIndex(cells.map(e=>e.metadata.chainage_m),chainage);if(i>=0)choose(cells[i].id);});
      redraw=()=>{
        if(destroyed)return;const w=width(),h=230,ctx=canvasSetup(map,w,h);transform=M.mapTransform(extent,w,h,28);
        rows=factors?cells.map(entity=>({entity,x:entity.metadata.chainage_m,y:factorById.get(entity.id)?.combined_stressor_factor??null})):savedProfile(channel,channel.times[frame]);
        const stats=factors?M.stats(table.rows.map(r=>r.combined_stressor_factor)):channel.extent,domain=[stats.min??0,stats.max??1];
        ctx.strokeStyle="#3d4657";ctx.lineWidth=3;ctx.beginPath();cells.forEach((cell,i)=>{const p=transform.project(cell.x,cell.z);i?ctx.lineTo(p.x,p.y):ctx.moveTo(p.x,p.y);});ctx.stroke();
        for(const row of rows){const p=transform.project(row.entity.x,row.entity.z);ctx.fillStyle=D.color(row.y,domain);ctx.beginPath();ctx.arc(p.x,p.y,2.5,0,Math.PI*2);ctx.fill();}
        const chosen=rows.find(r=>r.entity.id===selected)||rows[0],p=transform.project(chosen.entity.x,chosen.entity.z);ctx.strokeStyle="#e8eaef";ctx.lineWidth=2;ctx.beginPath();ctx.arc(p.x,p.y,6,0,Math.PI*2);ctx.stroke();mapLabels(ctx,w,h,extent,transform);
        profileScale=linePlot(profile,rows,w,domain,factors?"combined factor":"feeding index",selected);
        const missing=rows.filter(r=>!finite(r.y)).length;
        readout.textContent=`${chosen.entity.label} · ${fmt(chosen.x,1)} m downstream · ${factors?"combined factor":"feeding index"} ${fmt(chosen.y,6)}${missing?` · ${missing} cells missing at this time`:""}`;
        map.setAttribute("aria-label",`Saved channel cells. Selected ${readout.textContent}. Arrow keys select adjacent cells.`);profile.setAttribute("aria-label",`${factors?"Combined factor":"Feeding response"} by downstream distance. ${readout.textContent}. Arrow keys select adjacent cells.`);
        if(timeOutput){const t=channel.times[frame];timeOutput.textContent=`${fmt(t/60,2)} min elapsed · ${frame+1} / ${channel.times.length}`;timeSlider.setAttribute("aria-valuetext",`${fmt(t/60,2)} minutes elapsed`);}
        if(factorBox){factorBox.replaceChildren();const r=factorById.get(chosen.entity.id)||{};for(const [id,label]of[["do_factor","Oxygen"],["solute_factor","Solutes"],["predation_factor","Predation"],["combined_stressor_factor","Combined"]]){const row=el("div","pe-factor"),bar=el("span","pe-factor-bar");bar.style.width=`${finite(r[id])?Math.max(0,Math.min(1,r[id]))*100:0}%`;row.append(el("span","",label),el("output","",fmt(r[id],6)),bar);factorBox.append(row);}factorBox.append(el("p","pe-note",`Thermal utility: ${fmt(r.thermal_only_U,6)} relative index. This signed utility is not a probability.`));}
      };
    } else {
      const entities=dataset.entities.filter(e=>finite(e.x)&&finite(e.z)),extent=spatialExtent(entities),valueStats=M.stats(entities.map(e=>e.values[quantity]));
      if(!entities.length||!extent||!valueStats.finite){section.remove();return null;}
      const unit=dataset.variables.find(v=>v.id===quantity)?.unit||"",title=quantity==="height"?"Crown height":"Crown core area",rangeValues=[valueStats.min,valueStats.max],colorDomain=[valueStats.min,valueStats.max],palette=Array.from({length:256},(_,i)=>D.color(valueStats.min+i/255*(valueStats.max-valueStats.min),colorDomain));
      let selected=field.entity?.id||entities[0].id,transform=null,histogramScale=null;
      description.remove();
      const map=figure("LiDAR dominant crown detections — select a crown","canvas"),histogram=figure(`${title} distribution — select a bin`,"svg");
      const colorLegend=el("div","pe-color-legend"),colorBar=el("div","pe-color-bar"),colorLimits=el("div","pe-color-limits");
      colorBar.style.background=`linear-gradient(to right,${palette.map((color,i)=>`${color} ${i/255*100}%`).join(",")})`;colorBar.setAttribute("aria-hidden","true");colorLimits.append(el("span","",`${fmt(valueStats.min,3)} ${unit}`),el("span","",`${fmt(valueStats.max,3)} ${unit}`));colorLegend.append(el("span","",`${title} · full dataset range`),colorBar,colorLimits);
      const controls=el("div","pe-range-controls"),lo=el("input"),hi=el("input");
      for(const [node,index,label]of[[lo,0,"Minimum"],[hi,1,"Maximum"]]){node.type="number";node.min=valueStats.min;node.max=valueStats.max;node.step="any";node.value=rangeValues[index];node.setAttribute("aria-label",`${label} ${title.toLowerCase()}`);controls.append(control(`${label} (${unit})`,node));}
      const loRange=range(`Minimum ${title.toLowerCase()} range`,1000),hiRange=range(`Maximum ${title.toLowerCase()} range`,1000,1000),reset=el("button","pe-reset","Show all crowns");reset.type="button";
      const advanced=el("details","pe-advanced");advanced.append(el("summary","","Range sliders"),control("Lower range limit",loRange),control("Upper range limit",hiRange));
      const count=el("p","pe-note"),legend=el("p","pe-note","Bright points match the range; faint points retain all locations. Select a histogram bin or edit the limits to filter. Map arrow keys select adjacent records. Crown detections do not identify species or count stems.");
      section.replaceChildren(map.parentElement,colorLegend,readout,controls,histogram.parentElement,advanced,reset,count,legend);
      const sync=()=>{lo.value=rangeValues[0];hi.value=rangeValues[1];loRange.value=(rangeValues[0]-valueStats.min)/(valueStats.max-valueStats.min||1)*1000;hiRange.value=(rangeValues[1]-valueStats.min)/(valueStats.max-valueStats.min||1)*1000;};
      const setRange=(index,value)=>{if(!finite(value))return;const v=Math.max(valueStats.min,Math.min(valueStats.max,value));rangeValues[index]=index===0?Math.min(v,rangeValues[1]):Math.max(v,rangeValues[0]);sync();redraw();};
      listen(lo,"change",()=>setRange(0,lo.valueAsNumber));listen(hi,"change",()=>setRange(1,hi.valueAsNumber));
      listen(loRange,"input",()=>setRange(0,valueStats.min+Number(loRange.value)/1000*(valueStats.max-valueStats.min)));listen(hiRange,"input",()=>setRange(1,valueStats.min+Number(hiRange.value)/1000*(valueStats.max-valueStats.min)));
      listen(reset,"click",()=>{rangeValues[0]=valueStats.min;rangeValues[1]=valueStats.max;sync();redraw();});
      const choose=id=>{selected=id;redraw();selectEntity(id);};
      listen(map,"click",event=>{if(!transform)return;const p=pointAt(map,event),nearest=nearestSpatial(entities,transform.invert(p.x,p.y));if(nearest)choose(nearest.id);});
      listen(map,"keydown",event=>{if(!["ArrowLeft","ArrowRight","Home","End"].includes(event.key))return;event.preventDefault();const i=entities.findIndex(e=>e.id===selected);choose(entities[event.key==="Home"?0:event.key==="End"?entities.length-1:Math.max(0,Math.min(entities.length-1,i+(event.key==="ArrowRight"?1:-1)))].id);});
      listen(histogram,"click",event=>{const p=D.eventToSvg(histogram,event);if(!p||!histogramScale||p.x<histogramScale.left||p.x>histogramScale.right)return;const i=Math.min(histogramScale.bins.length-1,Math.floor((p.x-histogramScale.left)/(histogramScale.right-histogramScale.left)*histogramScale.bins.length)),bin=histogramScale.bins[i];rangeValues[0]=bin.lo;rangeValues[1]=bin.hi;sync();redraw();});
      redraw=()=>{
        if(destroyed)return;const w=width(),h=250,ctx=canvasSetup(map,w,h),result=crownRange(entities,quantity,rangeValues);transform=M.mapTransform(extent,w,h,28);
        ctx.fillStyle="#3d4657";ctx.globalAlpha=.3;for(const entity of entities){const p=transform.project(entity.x,entity.z);ctx.fillRect(p.x,p.y,1,1);}ctx.globalAlpha=1;
        for(const entity of entities)if(finite(entity.values[quantity])&&entity.values[quantity]>=rangeValues[0]&&entity.values[quantity]<=rangeValues[1]){const p=transform.project(entity.x,entity.z),index=Math.max(0,Math.min(255,Math.round((entity.values[quantity]-valueStats.min)/(valueStats.max-valueStats.min||1)*255)));ctx.fillStyle=palette[index];ctx.fillRect(p.x-.5,p.y-.5,1,1);}
        const chosen=entities.find(e=>e.id===selected)||entities[0],point=transform.project(chosen.x,chosen.z);ctx.strokeStyle="#e8eaef";ctx.lineWidth=2;ctx.beginPath();ctx.arc(point.x,point.y,6,0,Math.PI*2);ctx.stroke();mapLabels(ctx,w,h,extent,transform);
        readout.textContent=`${chosen.label} · ${chosen.id} · ${title.toLowerCase()} ${fmt(chosen.values[quantity],3)} ${unit} · x ${fmt(chosen.x,2)}, z ${fmt(chosen.z,2)} m${!M.inRange(chosen.values[quantity],rangeValues)?" · outside filter":""}`;
        count.textContent=`${fmt(result.selected,0)} of ${fmt(entities.length,0)} detections in ${fmt(rangeValues[0],3)}–${fmt(rangeValues[1],3)} ${unit}.${result.missing?` ${result.missing} detections have no saved value.`:""} Local meters; x east and z south. Each histogram bar counts detections.`;
        const right=w-12,top=24,bottom=160,max=Math.max(1,...result.all.bins.map(b=>b.count)),left=Math.max(42,12+fmt(max,0).length*7),barWidth=(right-left)/result.all.bins.length;
        histogram.replaceChildren();histogram.setAttribute("viewBox",`0 0 ${w} 205`);
        for(let i=0;i<3;i++){const n=max*i/2,py=bottom-n/max*(bottom-top);histogram.append(svg("path",{d:`M${left} ${py}H${right}`,stroke:"#2a2c31"}),svg("text",{x:left-6,y:py+4,"text-anchor":"end",class:"pe-axis"},fmt(n,0)));}
        result.all.bins.forEach((bin,i)=>{const x=left+i*barWidth,y=bottom-bin.count/max*(bottom-top),filtered=result.filtered.bins[i].count;histogram.append(svg("rect",{x,y,width:Math.max(1,barWidth-1),height:bottom-y,fill:"#3d4657"}),svg("rect",{x,y:bottom-filtered/max*(bottom-top),width:Math.max(1,barWidth-1),height:filtered/max*(bottom-top),fill:"var(--domain,#9ad58c)"}));});
        for(let i=0;i<3;i++){const value=valueStats.min+(valueStats.max-valueStats.min)*i/2;histogram.append(svg("text",{x:left+(right-left)*i/2,y:181,"text-anchor":i===0?"start":i===2?"end":"middle",class:"pe-axis"},fmt(value,2)));}
        histogram.append(svg("text",{x:left,y:14,class:"pe-axis"},"detections"),svg("text",{x:right,y:202,"text-anchor":"end",class:"pe-axis"},`${title.toLowerCase()} (${unit})`));
        histogramScale={left,right,bins:result.all.bins};histogram.setAttribute("aria-label",`${title} distribution. ${result.selected} detections in the selected range. Use the numeric or range controls to filter.`);map.setAttribute("aria-label",`LiDAR dominant crown detections. ${readout.textContent}. Arrow keys select adjacent records.`);
      };
    }
    resize=new ResizeObserver(()=>{if(destroyed||!section.isConnected){resize.disconnect();return;}redraw();});resize.observe(section);redraw();
    return {destroy(){destroyed=true;resize?.disconnect();cleanups.forEach(fn=>fn());section.remove();}};
  }
  const api={channelData,savedProfile,crownRange,nearestSpatial,spatialExtent,render};
  if(typeof module!=="undefined")module.exports=api;else root.YSEcologyCharts=api;
})(typeof window==="undefined"?{}:window);
