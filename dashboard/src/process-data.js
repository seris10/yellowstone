"use strict";

((root) => {
  const cache = new Map(), instances = new WeakMap(), finite = Number.isFinite;
  function dispose(container) { instances.get(container)?.(); instances.delete(container); }
  function expand(container) {const open=instances.get(container)?.expand;if(!open)return false;open();return true;}
  function summary(values) {
    let min = Infinity, max = -Infinity, count = 0;
    for (const value of values) if (finite(value)) { min = Math.min(min, value); max = Math.max(max, value); count++; }
    return {min:count ? min : null, max:count ? max : null, count, missing:values.length-count, constant:count > 0 && min === max};
  }
  function resolve(data, view, requested) {
    const groups = [data.variables, data.grids, data.profiles || [], data.tables || []];
    let field = groups.flat().find(item => item.id === view.quantity);
    if (!field) throw Error("The process quantity is absent from its dataset.");
    if (view.collection === "profiles") {
      const choices = data.profiles.filter(item => item.unit === field.unit);
      field = choices.find(item => item.entity_id === requested) || field;
      return {...field, kind:"profile", x_unit:field.axis.unit, choices:choices.map(item=>({id:item.entity_id,label:item.label}))};
    }
    if (data.grids.includes(field)) return {...field, kind:"grid"};
    if ((data.profiles || []).includes(field)) return {...field, kind:"profile", x_unit:field.axis.unit};
    if ((data.tables || []).includes(field)) return {...field, kind:"table", sources:data.sources.filter(s=>s.id===field.source_id)};
    const linked = data.series.filter(item => item.variable_id === field.id);
    const channelSupport=data.entities.length>0&&data.entities.every(item=>finite(item.metadata?.chainage_m))&&data.entities.some(item=>finite(item.values[field.id]));
    const entities = channelSupport?data.entities:data.entities.filter(entity => finite(entity.values[field.id]) || linked.some(item=>item.entity_id===entity.id));
    let entity = entities.find(item=>item.id===requested);
    if (!entity) {
      const ranked = linked.map(item=>({item,stats:summary(item.values)})).filter(row=>row.stats.count);
      ranked.sort((a,b)=>(b.stats.max-b.stats.min)-(a.stats.max-a.stats.min));
      entity = entities.find(item=>item.id===ranked[0]?.item.entity_id) || entities[0];
    }
    const series = linked.find(item=>item.entity_id===entity?.id), choices=entities.map(item=>({id:item.id,label:item.label}));
    if (series) return {...series, kind:"series", choices, entity, entities};
    if (entities.length > 1 && entities.every(item=>finite(item.metadata?.chainage_m))) return {...field, kind:"profile",
      positions:entities.map(item=>item.metadata.chainage_m), values:entities.map(item=>item.values[field.id]), x_unit:"m downstream", entities, choices, entity};
    if (entities.length > 25 && entities.some(item=>finite(item.x)&&finite(item.z))) return {...field, kind:"spatial", entities, entity, choices};
    return {...field, kind:"values", points:entities.map(item=>({label:item.label,y:item.values[field.id]})), choices, entity, entities};
  }
  async function load(snapshot, reference, dependencies={}) {
    const descriptor = (snapshot.datasets?.systems||[]).find(item=>item.id===reference.system);
    if (!descriptor) throw Error("This process dataset is unavailable.");
    const fetcher=dependencies.fetch||fetch,hashBytes=dependencies.hashBytes||root.YSData.hashBytes,validate=dependencies.validate||root.YSSystemsModel.validate;
    if (!cache.has(descriptor.sha256)) cache.set(descriptor.sha256, (async()=>{
      const response=await fetcher(descriptor.url,{cache:"no-cache"});
      if (!response.ok) throw Error("The process dataset could not be loaded.");
      const bytes=await response.arrayBuffer();
      if (await hashBytes(bytes)!==descriptor.sha256) throw Error("The process dataset failed its identity check.");
      return validate(JSON.parse(new TextDecoder().decode(bytes)),{snapshot:snapshot.snapshot,descriptor});
    })());
    try {const data=await cache.get(descriptor.sha256);if(data.id!==descriptor.id||data.snapshot!==snapshot.snapshot)throw Error("The process dataset belongs to a different catalog.");return data;} catch(error) { cache.delete(descriptor.sha256); throw error; }
  }
  async function mount(container, snapshot, process, selection={}, onChange=()=>{}) {
    dispose(container);
    const views=snapshot.process_views?.[process] || [];
    if (!views.length) return;
    const html=(tag,cls="",text="")=>{const el=document.createElement(tag);el.className=cls;el.textContent=text;return el;};
    const svg=(tag,attrs={},text="")=>{const el=document.createElementNS("http://www.w3.org/2000/svg",tag);for(const [key,value] of Object.entries(attrs))el.setAttribute(key,value);el.textContent=text;return el;};
    const fmt=(value,digits=4)=>finite(value)?value.toLocaleString("en-US",{maximumFractionDigits:digits}):"Missing";
    const host=html("section","process-data"),status=html("p","analysis-note","Loading process data…");
    host.setAttribute("aria-label","Process data");container.append(host);host.append(status);
    let view=views.find(item=>item.id===selection.view)||views[0],entity=selection.entity||null,ticket=0,resizeObserver=null,richCleanup=null,dialog=null,disposed=false;
    const cleanup=()=>{disposed=true;ticket++;resizeObserver?.disconnect();richCleanup?.();dialog?.close();dialog?.remove();dialog=null;host.remove();};
    instances.set(container,cleanup);
    async function render() {
      const current=++ticket;resizeObserver?.disconnect();richCleanup?.();richCleanup=null;host.replaceChildren();
      const choice=html("select");choice.setAttribute("aria-label","Process quantity");
      for(const item of views){const option=html("option","",item.label);option.value=item.id;choice.append(option);}choice.value=view.id;
      const label=html("label","analysis-control","Quantity");label.append(choice);host.append(label);
      choice.onchange=()=>{view=views.find(item=>item.id===choice.value);entity=null;render();};
      const waiting=html("p","analysis-note","Loading saved values…");host.append(waiting);
      let dataset=null,field;
      try { dataset=view.kind==="native"?await load(snapshot,view):null;
        if(current!==ticket||!host.isConnected)return;
        field=dataset?resolve(dataset,view,entity):view;
      } catch(error) {if(current===ticket&&host.isConnected){waiting.textContent=error.message;waiting.setAttribute("role","alert");}return;}
      if(field.kind==="routes")field={...field,entity:field.routes.find(route=>route.id===entity)||field.routes[0],choices:field.routes.map(route=>({id:route.id,label:route.label}))};
      waiting.remove();entity=field.entity?.id || field.entity_id || entity;onChange({view:view.id,entity,system:view.system,quantity:field.id});
      if(field.choices?.length>1){
        const select=html("select");select.setAttribute("aria-label","Process entity");
        const options=field.choices.slice(0,500);if(entity&&!options.some(item=>item.id===entity))options.unshift(field.choices.find(item=>item.id===entity));
        for(const item of options.filter(Boolean)){const option=html("option","",item.label);option.value=item.id;select.append(option);}select.value=entity;
        const wrap=html("label","analysis-control",view.collection==="profiles"?"Pool":"Location or entity");wrap.append(select);host.append(wrap);
        select.onchange=()=>{entity=select.value;render();};
        if(field.choices.length>500)host.append(html("p","analysis-note","Use the map or full dataset to inspect entities beyond this list."));
      }
      const description=field.description?html("p","analysis-note",field.description):null;if(description)host.append(description);
      let rich=null,richError=null;
      try {
        rich=await root.YSProcessVisuals?.mount(host,{snapshot,process,view,field,dataset,entity,isCurrent:()=>current===ticket,
          selectEntity:id=>{entity=id;const select=host.querySelector('[aria-label="Process entity"]');if(select){if(![...select.options].some(option=>option.value===id)){const row=field.choices?.find(item=>item.id===id);if(row){const option=html("option","",row.label);option.value=id;select.prepend(option);}}select.value=id;}onChange({view:view.id,entity,system:view.system,quantity:field.id});}});
      } catch(error) {richError=error;}
      if(current!==ticket||!host.isConnected){rich?.destroy?.();return;}
      richCleanup=rich?.destroy;
      cleanup.expand=null;
      if(rich){
        description?.remove();if(field.choices?.length>500)host.querySelector('.analysis-note')?.remove();
        const open=html("button","process-expand","Expand charts");open.type="button";open.hidden=Boolean(dialog);host.prepend(open);
        cleanup.expand=()=>{
          if(dialog)return;
          const modal=html("dialog","process-chart-dialog"),heading=html("header","process-chart-heading"),close=html("button","","Close charts"),body=html("div","process-chart-body");
          heading.append(html("h2","",snapshot.nodes?.find(node=>node.id===process)?.label||view.label),close);close.type="button";close.onclick=()=>modal.close();
          modal.setAttribute("aria-label","Expanded process charts");modal.append(heading,body);document.body.append(modal);body.append(host);open.hidden=true;dialog=modal;
          modal.addEventListener("keydown",event=>event.stopPropagation());
          modal.addEventListener("close",()=>{dialog=null;if(!disposed&&container.isConnected){container.prepend(host);const button=host.querySelector('.process-expand');if(button){button.hidden=false;button.focus();}}modal.remove();});
          modal.showModal();
        };
        open.onclick=cleanup.expand;
        document.getElementById?.("expand-analysis")?.setAttribute("aria-label","Expand charts");
      }
      if(richError){const error=html("p","analysis-note",richError.message);error.setAttribute("role","alert");const retry=html("button","","Retry visual");retry.type="button";retry.onclick=render;host.append(error,retry);}
      const plot=svg("svg",{viewBox:"0 0 600 300",role:"img",tabindex:0,"aria-label":field.label}),wrap=html("div","workspace-chart process-chart"),probe=html("output","analysis-probe");
      probe.setAttribute("aria-live","off");wrap.append(plot);host.append(wrap,probe);
      resizeObserver=new ResizeObserver(()=>{if(!host.isConnected){resizeObserver.disconnect();return;}plot.style.setProperty("--process-axis-size",`${Math.min(26,Math.max(12,7200/(wrap.clientWidth||600)))}px`);});resizeObserver.observe(wrap);
      const note=html("p","analysis-axis-note");host.append(note);
      function line(positions,values,xUnit) {
        const stats=summary(values),xs=summary(positions);
        if(!stats.count){wrap.hidden=true;probe.textContent="No finite values were saved for this quantity.";return;}
        const factor=xUnit==="seconds elapsed"&&xs.max>=3600?3600:xUnit==="seconds elapsed"&&xs.max>=60?60:1;
        const axisUnit=xUnit==="seconds elapsed"?(factor===3600?"hours elapsed":factor===60?"minutes elapsed":xUnit):xUnit;
        if(stats.constant){wrap.hidden=true;probe.textContent=`${fmt(stats.min,6)} ${field.unit} · unchanged in ${stats.count} saved samples over ${fmt(xs.min/factor)}–${fmt(xs.max/factor)} ${axisUnit}${stats.missing?`; ${stats.missing} samples missing`:""}.`;note.hidden=true;return;}
        const pad=Math.max((stats.max-stats.min)*.1,Math.abs(stats.min)*.001,1e-6),lo=stats.min-pad,hi=stats.max+pad;
        const digits=Math.max(0,Math.min(8,2-Math.floor(Math.log10(hi-lo)))),left=digits>3?130:90,span=575-left;
        const x=value=>left+(value-xs.min)/(xs.max-xs.min||1)*span,y=value=>245-(value-lo)/(hi-lo)*190;
        for(let i=0;i<=4;i++){const px=left+i*span/4,py=55+i*47.5;plot.append(svg("path",{d:`M${left} ${py}H575`,stroke:"#2c3545"}),svg("text",{x:left-10,y:py+4,class:"ws-axis","text-anchor":"end"},fmt(hi-i/4*(hi-lo),digits)),svg("text",{x:px,y:270,class:"ws-axis","text-anchor":"middle"},fmt((xs.min+i/4*(xs.max-xs.min))/factor,2)));}
        plot.append(svg("path",{d:root.YSData.segments(values.map((value,index)=>({x:positions[index],y:value})),p=>x(p.x),p=>y(p.y)),fill:"none",stroke:"var(--domain,#8dcaca)","stroke-width":2}),svg("text",{x:575,y:295,class:"ws-axis","text-anchor":"end"},axisUnit),svg("text",{x:8,y:22,class:"ws-axis"},field.unit));
        const cursor=svg("circle",{r:4,fill:"#fff0d1"});plot.append(cursor);
        let index=0;
        const update=next=>{index=Math.max(0,Math.min(values.length-1,next));cursor.setAttribute("cx",x(positions[index]));if(finite(values[index]))cursor.setAttribute("cy",y(values[index]));cursor.setAttribute("visibility",finite(values[index])?"visible":"hidden");probe.textContent=`${fmt(positions[index]/factor)} ${axisUnit} · ${fmt(values[index],6)} ${field.unit}`;if(field.kind==="profile"&&field.entities?.[index]){entity=field.entities[index].id;const choice=host.querySelector('[aria-label="Process entity"]');if(choice)choice.value=entity;onChange({view:view.id,entity,system:view.system,quantity:field.id});}};
        plot.onpointermove=event=>{const point=root.YSData.eventToSvg(plot,event);if(point)update(root.YSData.nearestIndex(positions,xs.min+(point.x-left)/span*(xs.max-xs.min)));};
        plot.onkeydown=event=>{if(["ArrowLeft","ArrowRight","Home","End"].includes(event.key)){event.preventDefault();update(event.key==="Home"?0:event.key==="End"?values.length-1:index+(event.key==="ArrowRight"?1:-1));}};
        const initial=field.kind==="profile"&&field.entities?Math.max(0,field.entities.findIndex(item=>item.id===entity)):0;
        const slider=html("input");slider.type="range";slider.min=0;slider.max=values.length-1;slider.step=1;slider.value=initial;slider.setAttribute("aria-label","Probe saved sample");slider.oninput=()=>update(Number(slider.value));host.append(slider);update(initial);
        const fullWindow=`${fmt(xs.min/factor)}–${fmt(xs.max/factor)} ${axisUnit}`;
        note.textContent=`${values.length} samples · ${fullWindow}. Range ${fmt(stats.min,6)}–${fmt(stats.max,6)} ${field.unit}. ${stats.missing?`${stats.missing} missing samples; gaps are preserved.`:""}`;
        plot.setAttribute("aria-label",`${field.label}. ${note.textContent}`);
      }
      if(rich||richError){wrap.hidden=true;probe.hidden=true;note.hidden=true;}
      else if(field.kind==="series")line(field.times,field.values,"seconds elapsed");
      else if(field.kind==="profile")line(field.positions,field.values,field.x_unit);
      else if(field.kind==="values"){
        const points=field.points,stats=summary(points.map(p=>p.y));
        if(points.length===1){wrap.hidden=true;probe.textContent=`${points[0].label}: ${fmt(points[0].y,6)} ${field.unit}`;}
        else {
          wrap.hidden=true;probe.hidden=true;const list=html("div","process-values");host.insertBefore(list,wrap);
          const extent=Math.max(Math.abs(stats.min||0),Math.abs(stats.max||0),1e-12);
          for(const point of points){const row=html("div","process-value"),bar=html("div","process-value-bar");bar.style.width=`${finite(point.y)?Math.abs(point.y)/extent*100:0}%`;row.append(html("span","",point.label),html("strong","",`${fmt(point.y,6)} ${field.unit}`),bar);list.append(row);}
          note.hidden=true;
        }
      } else if(field.kind==="grid"||field.kind==="spatial"||field.kind==="routes"){
        const M=root.YSSystemsModel,canvas=document.createElement("canvas");canvas.width=600;canvas.height=300;const ctx=canvas.getContext("2d");ctx.fillStyle="#0b0e14";ctx.fillRect(0,0,600,300);
        let extent,points=[];
        if(field.kind==="grid")extent=M.gridExtent(field);
        else {points=field.kind==="routes"?field.routes.flatMap(route=>route.points.map(([x,z])=>({x,z}))):field.entities.filter(e=>finite(e.x)&&finite(e.z));const xs=summary(points.map(p=>p.x)),zs=summary(points.map(p=>p.z));extent={x0:xs.min,x1:xs.max,z0:zs.min,z1:zs.max};}
        const transform=M.mapTransform(extent,600,300,20);const min=summary(field.kind==="grid"?field.values:field.kind==="spatial"?points.map(p=>p.values[field.id]):[0,1]);
        if(field.kind==="grid"){
          const raster=document.createElement("canvas");raster.width=field.grid.nx;raster.height=field.grid.nz;const native=raster.getContext("2d"),pixels=native.createImageData(raster.width,raster.height);
        const palette=Array.from({length:256},(_,i)=>root.YSData.color(min.min+i/255*(min.max-min.min),[min.min,min.max])).map(color=>color.startsWith("#")?[1,3,5].map(i=>parseInt(color.slice(i,i+2),16)):color.match(/\d+/g).map(Number));
          for(let i=0;i<field.values.length;i++){const value=field.values[i];if(!finite(value))continue;const row=Math.floor(i/field.grid.nx),displayRow=field.grid.row_order==="z_increasing"?row:field.grid.nz-row-1,j=(displayRow*field.grid.nx+i%field.grid.nx)*4,rgb=palette[Math.max(0,Math.min(255,Math.round((value-min.min)/(min.max-min.min||1)*255)))];pixels.data.set([...rgb,255],j);}
          native.putImageData(pixels,0,0);const a=transform.project(extent.x0,extent.z0),b=transform.project(extent.x1,extent.z1);ctx.imageSmoothingEnabled=false;ctx.drawImage(raster,a.x,a.y,b.x-a.x,b.y-a.y);
        }else if(field.kind==="spatial")for(const point of points){const p=transform.project(point.x,point.z);ctx.fillStyle=root.YSData.color(point.values[field.id],[min.min,min.max]);ctx.fillRect(p.x-1,p.y-1,2,2);}
        else for(const route of field.routes){ctx.strokeStyle=route.id===entity?"#fff0d1":"#8dcaca";ctx.lineWidth=route.id===entity?2.5:1;ctx.beginPath();route.points.forEach(([x,z],i)=>{const p=transform.project(x,z);i?ctx.lineTo(p.x,p.y):ctx.moveTo(p.x,p.y);});ctx.stroke();}
        plot.append(svg("image",{href:canvas.toDataURL("image/png"),width:600,height:300}),svg("text",{x:570,y:17,class:"ws-axis"},"N ↑"));
        note.textContent=field.kind==="routes"?`${field.routes.length} authored routes. Local meters; x east and z south.`:`Local meters; equal aspect. ${fmt(min.min)}–${fmt(min.max)} ${field.unit}. Dark cells have no saved value.`;
        const inspect=(point)=>{const world=transform.invert(point.x,point.y);if(field.kind==="grid"){const cell=M.sampleGrid(field,world.x,world.z);if(cell)probe.textContent=`x ${fmt(cell.x)} / z ${fmt(cell.z)} m · ${fmt(cell.value,6)} ${field.unit}`;}else if(field.kind==="spatial"){const selected=points.reduce((a,b)=>Math.hypot(a.x-world.x,a.z-world.z)<Math.hypot(b.x-world.x,b.z-world.z)?a:b);probe.textContent=`${selected.label}: ${fmt(selected.values[field.id])} ${field.unit}`;}};
        plot.onpointermove=event=>{const p=root.YSData.eventToSvg(plot,event);if(p)inspect(p);};
        if(field.kind==="spatial")plot.onclick=event=>{const p=root.YSData.eventToSvg(plot,event);if(!p)return;const world=transform.invert(p.x,p.y),selected=points.reduce((a,b)=>Math.hypot(a.x-world.x,a.z-world.z)<Math.hypot(b.x-world.x,b.z-world.z)?a:b);entity=selected.id;render();};
        if(field.kind==="grid"){const slider=html("input");slider.type="range";slider.min=0;slider.max=field.values.length-1;slider.step=1;slider.value=0;slider.setAttribute("aria-label","Probe native cell");slider.oninput=()=>{const cell=M.gridPoint(field,Number(slider.value));probe.textContent=`Cell ${cell.column+1}, ${cell.row+1}: ${fmt(cell.value,6)} ${field.unit}`;};host.append(slider);}
        if(field.kind==="routes"){const route=field.entity,length=route.points.slice(1).reduce((sum,p,i)=>sum+Math.hypot(p[0]-route.points[i][0],p[1]-route.points[i][1]),0);probe.textContent=`${route.label} · ${route.points.length} waypoints · ${fmt(length,2)} m of authored path. No animal playback.`;}else probe.textContent="Move over the map to inspect saved values.";
      } else if(field.kind==="table"){
        wrap.hidden=true;const table=html("table","process-table"),head=html("thead"),tr=html("tr"),tbody=html("tbody");field.columns.forEach(col=>tr.append(html("th","",col.label+(col.unit?` (${col.unit})`:""))));head.append(tr);table.append(head,tbody);const scroll=html("div","process-table-scroll");scroll.append(table);host.append(scroll);let page=0;
        const controls=html("div","chart-options"),previous=html("button","","Previous"),next=html("button","","Next"),count=html("span");controls.append(previous,count,next);host.append(controls);
        const draw=()=>{tbody.replaceChildren();field.rows.slice(page*25,page*25+25).forEach(row=>{const tr=html("tr");field.columns.forEach(col=>tr.append(html("td","",typeof row[col.id]==="number"?fmt(row[col.id],6):String(row[col.id]??"Missing"))));tbody.append(tr);});previous.disabled=page===0;next.disabled=(page+1)*25>=field.rows.length;count.textContent=`${field.rows.length} rows · page ${page+1}`;};previous.onclick=()=>{page--;draw();};next.onclick=()=>{page++;draw();};draw();
      }
      const support=rich?.visual?.support||field.support||view.support;
      if(support&&field.kind!=="series")host.append(html("p","analysis-note process-time",support.time));
      const sources=rich?.visual?.sources||field.sources||dataset?.sources.filter(item=>item.id===field.source_id)||view.sources||[];
      const provenance=html("details","analysis-provenance");provenance.append(html("summary","","Source and limits"));
      provenance.append(html("p","analysis-note",`${(field.role||"diagnostic").replaceAll("_"," ")} · ${support?.space||"Saved source table."} Uncertainty is not quantified.`));
      if(rich&&field.description)provenance.append(html("p","analysis-note",field.description));
      if(support&&field.kind==="series")provenance.append(html("p","analysis-note",support.time));
      for(const note of rich?.visual?.notes||[])provenance.append(html("p","analysis-note",note));
      for(const source of sources)provenance.append(html("p","analysis-note",`${source.label} · SHA-256 ${source.sha256}`));
      host.append(provenance);
    }
    await render();
  }
  const api={summary,resolve,load,mount,dispose,expand};
  if(typeof module!=="undefined")module.exports=api;else root.YSProcessData=api;
})(typeof window==="undefined"?{}:window);
