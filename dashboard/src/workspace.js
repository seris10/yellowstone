"use strict";

window.YSWorkspace = {
  init(data, options) {
    data.river ||= {cells:[],frames:[]};
    const $ = id => document.getElementById(id), NS = "http://www.w3.org/2000/svg", model = window.YSModel;
    const html = (tag, cls = "", text = "") => { const el = document.createElement(tag); el.className = cls; el.textContent = text; return el; };
    const svg = (tag, attrs = {}, text = "") => { const el = document.createElementNS(NS, tag); Object.entries(attrs).forEach(([k,v]) => el.setAttribute(k,v)); el.textContent = text; return el; };
    const clamp = (x,a,b) => Math.max(a,Math.min(b,x));
    const domains = new Map(data.domains.map(d => [d.id,d])), nodes = new Map(data.nodes.map(n => [n.id,n]));
    const map = $("network"), world = $("workspace-world"), active = ["overview","systems"].includes(options.page);
    const reduced = matchMedia("(prefers-reduced-motion: reduce)").matches;
    const state = { domain: null, process: null, research: false, conditional: true, status: "all", direction: "all", tab: "data",
      metric: "temperature", frame: 0, cell: 0, first: 0, last: data.river.cells.length - 1, timeFirst: 0, timeLast: data.river.frames.length - 1,
      local: false, compare: false, mode: "systems", panel: false, expanded: false, traceFirst: 0, traceLast: Infinity, arrange: false, network: false };
    const temperatureExtent=data.river.temperature_domain||window.YSData.extent((function*(){for(const frame of data.river.frames)yield* frame.temperature;})())||[0,1], [temperatureMin,temperatureMax]=temperatureExtent;
    let width = 1200, height = 700, camera = {x:0,y:0,k:1}, target = {...camera}, base = 1, cards = [], sceneEdges = [];
    let playElapsed = 0;
    let hovered = null, skipClick = false, dragLength = 0, exchange = null, panelWidth = 400, playing = false, lastTick = 0, nodeDragging = null;
    const pointers = new Map();
    let plot = null, chartSeries = null, brush = null, miniMap = null, fieldImage = null, urlTimer = null, inlineCard = null;
    let overviewCamera = {...camera}, networkCamera = {...camera}, overviewEdges = [], detailEdges = [], sceneReady = false, restored = false, renderedFilters = "", semanticDirty = true, netMix = 0;
    const panel = $("analysis-panel"), panelHome = panel.parentElement;
    const colorLegend=html("div","workspace-color-legend");colorLegend.setAttribute("aria-label","Process colors");panelHome.append(colorLegend);
    const titles = {temperature:"River temperature · distance",history:"River temperature · time",field:"Temperature · distance × time",oxygen:"Dissolved oxygen",periphyton:"Periphyton biomass",shading:"Shortwave transmission",air:"Air temperature · 60 s",wind:"Wind speed · 60 s",pools:"Pool center and edge temperatures",heat:"Ground heat field",water:"Snow storage by patch", "water-sum":"Summed-depth accounting diagnostic",snow:"Patch snow storage",biomass:"Vegetation biomass",moisture:"Patch soil moisture"};
    const domainMetrics = {atmosphere:["air","wind"],snow:["snow","moisture","water-sum"],thermal:["heat","pools"],river:["temperature","field","history","shading"],land:["biomass","moisture"],aquatic:["oxygen","periphyton","temperature","field"]};
    const processMetrics = {transport:["temperature","field","history"],shading:["shading"]};
    function announce(text) { $("announcer").textContent = text; }
    function depth() { return state.process ? 2 : state.domain ? 1 : 0; }
    function metrics() { return state.process ? metricsFor(nodes.get(state.process)) : (domainMetrics[state.domain] || []).filter(metric=>model.available(data,metric)); }
    function fmt(value, digits = 2) { return Number.isFinite(value) ? value.toLocaleString("en-US",{maximumFractionDigits:digits}) : "Unavailable"; }
    function time(seconds) { return `${String(Math.floor(seconds/3600)).padStart(2,"0")}:${String(Math.floor(seconds%3600/60)).padStart(2,"0")}:${String(Math.floor(seconds%60)).padStart(2,"0")}`; }
    function marker(node) { return node.implementation === "research" ? "╌" : node.kind === "prescribed" ? "◇" : node.display === "rendered" ? "●" : "○"; }
    function type(node) { return node.implementation === "research" ? "Research extension" : node.kind === "prescribed" ? "Prescribed input" : node.display === "rendered" ? "Runtime binding" : "Python model"; }
    function wrapped(group, text, x, y, columns = 25, cls = "ws-card-label", lineHeight = 18, limit = 2) {
      const lines = [], words = text.split(" "); let line = "";
      words.forEach(word => { if (line.length + word.length > columns && line) { lines.push(line); line = word; } else line += (line ? " " : "") + word; }); if (line) lines.push(line);
      lines.slice(0,limit).forEach((text,index) => group.append(svg("text",{x,y:y+index*lineHeight,class:cls},text + (index === limit-1 && lines.length > limit ? "…" : ""))));
    }
    function tooltip(event, title, text) {
      const tip = $("tooltip"), r = map.getBoundingClientRect(); tip.replaceChildren(html("div","",title),html("small","",text));
      tip.style.left = `${clamp(event.clientX-r.left+12,8,width-265)}px`; tip.style.top = `${clamp(event.clientY-r.top+16,8,height-100)}px`; tip.hidden = false;
    }
    function workbenchTarget() {
      const views=data.process_views?.[state.process],native=views?.find(view=>view.id===state.processView&&view.kind==="native")||views?.find(view=>view.kind==="native");
      if(native)return native.system;
      return ["mammals","grazers"].includes(state.process)?"wildlife":state.process==="canopy"?"canopy":state.domain||"thermal";
    }
    function workbenchAddress() {
      const p=new URLSearchParams({view:"analysis",system:workbenchTarget()});
      if(state.process||state.domain)p.set("from",state.process||state.domain);
      const views=data.process_views?.[state.process],native=views?.find(view=>view.id===state.processView&&view.kind==="native")||views?.find(view=>view.kind==="native");
      if(native){const target=native.field_group==="tables"?views.find(view=>view.field_group==="variables"):native;p.set("variable",target?.collection==="profiles"?"pool_center":target?.quantity||native.quantity);if(state.processEntity)p.set("entity",state.processEntity);}
      if(workbenchTarget()==="river"&&data.river.frames.length){p.set("t",data.river.frames[state.frame].t);p.set("cell",state.cell);}
      return `${location.pathname}#${p}`;
    }
    function writeURL() {
      if (!active) return;
      clearTimeout(urlTimer);
      urlTimer = setTimeout(() => {
      if(document.body.dataset.analysisActive==="true")return;
      const p = new URLSearchParams(); p.set("view",state.mode); if (state.network) p.set("network","1");
      if (state.domain) p.set("domain",state.domain); if (state.process) p.set("process",state.process);
      if (state.research) p.set("research","1");
      if (state.local) p.set("scale","local");if(state.compare)p.set("compare","1");
      if (!state.conditional) p.set("conditional","0");if(state.status!=="all")p.set("status",state.status);if(state.direction!=="all")p.set("direction",state.direction);
      if(state.first||state.last!==data.river.cells.length-1){p.set("first",state.first);p.set("last",state.last);}
      if(state.timeFirst||state.timeLast!==data.river.frames.length-1){p.set("timeFirst",state.timeFirst);p.set("timeLast",state.timeLast);}
      if (state.domain) { p.set("tab",state.tab); p.set("metric",state.metric); p.set("frame",state.frame); p.set("cell",state.cell); }
      if(state.processView)p.set("quantity",state.processView);if(state.processEntity)p.set("entity",state.processEntity);
      history.replaceState(null,"",`#${p}`);
      },150);
    }
    function setMode(mode, save = true) {
      state.mode = mode; $("overview-view").hidden = mode !== "landscape"; $("system-view").hidden = mode !== "systems";
      $("mode-systems").setAttribute("aria-pressed",String(mode === "systems")); $("mode-landscape").setAttribute("aria-pressed",String(mode === "landscape"));
      document.body.classList.toggle("geographic-mode",mode === "landscape"); $("process-search").parentElement.hidden = mode === "landscape";
      $("workspace-breadcrumb").hidden = mode === "landscape"; $("open-analysis").hidden = mode === "landscape" || !state.domain || state.panel;
      $("view-description").textContent = mode === "systems" ? "ECOSYSTEM / DOMAIN / PROCESS" : "GEOGRAPHIC COVERAGE / SAVED MODEL DATA";
      document.title=mode==="landscape"?"Geographic coverage | Yellowstone":`${nodes.get(state.process)?.label||domains.get(state.domain)?.label||"Ecosystem explorer"} | Yellowstone`;
      if (save) writeURL();
    }
    function selectDomain(id, save = true, move = true) {
      if (!domains.has(id)) return;
      state.network = false; state.domain = id; state.process = null; state.panel = false; state.expanded = false; exchange = null; state.tab = "data"; playing = false;
      if (!domainMetrics[id].filter(metric=>model.available(data,metric)).includes(state.metric)) state.metric = domainMetrics[id].find(metric=>model.available(data,metric)) || "";
      setMode("systems",false); header(); if(move)fit(); if (save) writeURL(); announce(`${domains.get(id).label}. Processes inside the sphere.`);
    }
    function selectProcess(id, save = true, move = true) {
      const node = nodes.get(id); if (!node) return;
      const previous=state.process;
      if(previous!==id){state.processView=null;state.processEntity=null;}
      state.network = false; state.domain = node.domain; state.process = id; state.panel = true; state.expanded = false; exchange = null;
      if (node.implementation === "research") { state.research = true; $("show-research").checked = true; }
      if(sceneReady&&!cards.some(c=>c.kind==="process"&&c.item.id===id))renderScene(false);
      const choices = metrics(); if (!choices.includes(state.metric)) state.metric = choices[0] || "";
      if(previous!==id)state.tab = choices.length ? "data" : "science";
      setMode("systems",false); renderAnalysis(); if(move)fit(); if (save) writeURL(); announce(`${node.label}. Data, science, and exchanges inside the process.`);
    }
    function ecosystem(save = true, move = true) {
      state.domain = null; state.process = null; state.panel = false; state.expanded = false; exchange = null; playing = false;
      header(); if(move)fit(); if (save) writeURL(); announce("Ecosystem overview. Six connected Earth systems.");
    }
    function setNetwork(on, save = true) {
      if (on === state.network) return;
      state.network = on;
      if (on) ecosystem(false); else { header(); fit(); }
      if (save) writeURL(); announce(on ? "Full network. Every process and exchange in one view." : "Domain overview.");
    }
    function parent() { if (state.process) selectDomain(state.domain); else if (state.domain) ecosystem(); else fit(); }
    function addBreadcrumb(label, action, current) {
      const b = html("button","",label); if (current) b.setAttribute("aria-current","location"); b.addEventListener("click",action); $("workspace-breadcrumb").append(b);
    }
    function header() {
      semanticDirty=true;
      const d = domains.get(state.domain), n = nodes.get(state.process), selected = model.visible(data,state);
      $("workspace-breadcrumb").replaceChildren(); addBreadcrumb("Ecosystem",() => ecosystem(),!d);
      if (d) addBreadcrumb(d.label,() => selectDomain(d.id),!n); if (n) addBreadcrumb(n.label,() => selectProcess(n.id),true);
      $("workspace-level").textContent = "ECOSYSTEM / DOMAIN / PROCESS";
      $("workspace-title").textContent = "Earth systems";
      $("workspace-description").textContent = "Scroll into a sphere to see its processes and data.";
      $("workspace-count").textContent = `${selected.nodes.length} visible components · ${selected.edges.length} exchanges · 6 systems`;
      $("open-system-workbench").href=workbenchAddress();$("open-system-workbench").textContent="Analyze Earth systems ↗";
      $("domain-page-link").hidden = true;
      $("workspace-hint").textContent = n ? "Probe the chart · Scroll outside the data to zoom · Escape moves out" : d ? "Scroll into a process · Drag to pan · Escape moves out" : state.network ? "Hover a process to trace its exchanges · Scroll to zoom · Drag to pan" : "Scroll into a sphere · Hover a connection · Drag to pan";
      const networkToggle = $("network-toggle"); networkToggle.parentElement.hidden = depth() > 0; networkToggle.setAttribute("aria-pressed",String(state.network)); document.body.classList.toggle("network-view",state.network);
      document.body.dataset.depth = String(depth()); document.body.classList.remove("analysis-open","analysis-expanded");
      document.body.style.setProperty("--analysis-width",`${panelWidth}px`);
      $("analysis-resize").setAttribute("aria-valuemin","320");$("analysis-resize").setAttribute("aria-valuemax","650");$("analysis-resize").setAttribute("aria-valuenow",String(Math.round(panelWidth)));
      $("workspace-domains").querySelectorAll("button").forEach(b => b.setAttribute("aria-pressed",String(b.dataset.domain === state.domain)));
      colorLegend.replaceChildren();
      if(d){
        colorLegend.append(html("span","legend-label","PROCESS COLOR"));
        const roles=new Map(selected.nodes.filter(node=>node.domain===d.id).map(node=>{const role=model.processRole(node.id);return [role?.id,role];}));
        roles.forEach(role=>{if(!role)return;const item=html("span","",role.label);item.style.setProperty("--role-color",role.color);colorLegend.append(item);});
      }
      $("open-analysis").hidden = true;
      if (active) document.title = `${n ? n.label : d ? d.label : "Ecosystem explorer"} | Yellowstone`;
    }
    function viewport() {
      const mobile=width<721;
      return {left:mobile?20:45,right:width-(mobile?20:65),top:mobile?100:145,bottom:height-(mobile?120:100)};
    }
    function focusRadius(kind) {
      const v=viewport(),span=Math.max(140,Math.min(v.right-v.left,v.bottom-v.top));
      return span*(kind==="process"?.72:.48);
    }
    function fit(instant = false) {
      if (!sceneReady || !width || !height) return;
      const v=viewport(),subject=cards.find(c=>state.process?c.kind==="process"&&c.item.id===state.process:c.kind==="domain"&&c.item.id===state.domain);
      if(subject)target=model.frameCircle(subject,focusRadius(subject.kind),{x:(v.left+v.right)/2,y:(v.top+v.bottom)/2});
      else target={...(state.network?networkCamera:overviewCamera)};
      if (instant || reduced) {
        camera = {...target};
        world.setAttribute("transform",`translate(${camera.x},${camera.y}) scale(${camera.k})`);updateSemantic();
      }
      semanticDirty=true;
    }
    function setOpacity(element, value, interactive = false) {
      element.style.opacity=value.toFixed(3);
      if(interactive){
        const visible=value>.45;
        element.style.pointerEvents=visible?"auto":"none";
        element.querySelectorAll(".ws-edge-hit").forEach(hit=>hit.style.pointerEvents=visible?"stroke":"none");
        element.setAttribute("aria-hidden",String(!visible));
        element.setAttribute("tabindex",visible?"0":"-1");
      }
    }
    function card(key, item, x, y, kind = "process", parent = null, radius = 110) {
      const d=kind==="domain"?item:domains.get(item.domain),localX=parent?x-parent.x:x,localY=parent?y-parent.y:y;
      const group=svg("g",{class:`ws-card ws-${kind}`,"data-node":kind==="process"?item.id:"","data-domain":d.id,style:`--domain:${d.color}`,transform:`translate(${localX},${localY})`});
      const hit=svg("g",{class:"ws-circle-hit",role:"button",tabindex:0,"aria-label":`${kind==="domain"?"Explore":"Analyze"} ${item.label}`});
      const sphere=svg("circle",{r:radius,class:"ws-sphere"});
      hit.append(sphere);group.append(hit);
      const summary=svg("g",{class:"ws-circle-summary",transform:`scale(${radius/110})`,"pointer-events":"none"});
      let tag=null,names=null,netNames=null;
      if(kind==="domain"){
        group.append(svg("circle",{r:radius-5,class:"ws-orbit"}));
        tag=svg("g",{class:"ws-network-tag","pointer-events":"none"});tag.append(svg("text",{class:"ws-network-label","text-anchor":"end"},d.label));group.append(tag);
        wrapped(summary,d.label,0,-9,20,"ws-domain-title",21,2);
        summary.append(svg("text",{y:43,class:"ws-domain-count"},`${model.visible(data,state).nodes.filter(n=>n.domain===d.id).length} PROCESSES`),svg("text",{y:64,class:"ws-enter-label"},"SCROLL TO EXPLORE"));
      }else{
        summary.append(svg("text",{y:-47,class:"ws-node-type","text-anchor":"middle"},`${marker(item)} ${type(item).toUpperCase()}`));
        names=svg("g",{class:"ws-names"});wrapped(names,item.label,0,-20,17,"ws-domain-title ws-process-name",24,3);summary.append(names);
        netNames=svg("g",{class:"ws-net-names",opacity:0});wrapped(netNames,item.label,0,-20,11,"ws-domain-title ws-net-name",24,4);summary.append(netNames);
        const measure=(processMetrics[item.id]||[]).find(metric=>model.available(data,metric)),values=measure&&model.series(data,measure,state.frame,state.cell);
        if(values?.type==="line"){
          const ys=values.points.map(p=>p.y).filter(Number.isFinite),lo=Math.min(...ys),hi=Math.max(...ys),points=values.points.filter((_,i)=>i%Math.max(1,Math.floor(values.points.length/45))===0);
          summary.append(svg("path",{d:window.YSData.segments(points.map((p,i)=>({x:-59+i/(points.length-1||1)*118,y:Number.isFinite(p.y)?56-(p.y-lo)/(hi-lo||1)*19:null}))),class:"ws-spark"}));
        }else summary.append(svg("text",{y:62,class:"ws-enter-label"},metricsFor(item).length?"SAVED MODEL DATA":"SCIENCE & EXCHANGES"));
        if(item.implementation==="research")group.classList.add("ws-research");
      }
      group.append(summary);
      const c={key,item,x,y,localX,localY,r:radius,w:radius*2,h:radius*2,kind,parent,group,summary,hit,tag,names,netNames};cards.push(c);
      const open=()=>kind==="domain"?selectDomain(item.id):selectProcess(item.id);
      hit.addEventListener("click",event=>{event.stopPropagation();if(!skipClick)open();});
      hit.addEventListener("keydown",event=>{if(["Enter"," "].includes(event.key)){event.preventDefault();event.stopPropagation();open();}});
      hit.addEventListener("pointerenter",event=>{hovered=key;semanticDirty=true;tooltip(event,item.label,kind==="domain"?d.description:`${item.summary} ${type(item)}.`);});
      hit.addEventListener("pointerleave",()=>{hovered=null;semanticDirty=true;$("tooltip").hidden=true;});
      hit.addEventListener("pointerdown",event=>{
        if(!state.arrange&&(!event.shiftKey||event.pointerType==="touch"))return;
        event.stopPropagation();event.preventDefault();nodeDragging={card:c,x:event.clientX,y:event.clientY};skipClick=true;hit.setPointerCapture(event.pointerId);$("tooltip").hidden=true;
      });
      hit.addEventListener("pointermove",event=>{
        if(nodeDragging?.card!==c)return;event.stopPropagation();
        let dx=(event.clientX-nodeDragging.x)/camera.k,dy=(event.clientY-nodeDragging.y)/camera.k;
        if(c.parent){const limit=c.parent.r-c.r-8,nx=c.localX+dx,ny=c.localY+dy,length=Math.hypot(nx,ny),scale=Math.min(1,limit/(length||1));dx=nx*scale-c.localX;dy=ny*scale-c.localY;}
        c.x+=dx;c.y+=dy;c.localX+=dx;c.localY+=dy;nodeDragging.x=event.clientX;nodeDragging.y=event.clientY;
        c.group.setAttribute("transform",`translate(${c.localX},${c.localY})`);
        cards.filter(child=>child.parent===c).forEach(child=>{child.x+=dx;child.y+=dy;});
        sceneEdges.forEach(updateConnection);
        semanticDirty=true;
      });
      ["pointerup","pointercancel"].forEach(name=>hit.addEventListener(name,event=>{if(nodeDragging?.card!==c)return;event.stopPropagation();nodeDragging=null;announce(`${item.label} repositioned.`);}));
      return c;
    }
    function metricsFor(node) {return data.process_views?.[node?.id]?.map(view=>view.id) || (processMetrics[node?.id]||[]).filter(metric=>model.available(data,metric));}
    function updateConnection({a,b,group}) {
      const dx=b.x-a.x,dy=b.y-a.y,len=Math.hypot(dx,dy)||1,inset=c=>c.r;
      const ai=inset(a),bi=inset(b),start={x:a.x+dx/len*ai,y:a.y+dy/len*ai},end={x:b.x-dx/len*bi,y:b.y-dy/len*bi},bend=Math.abs(dx)>600&&Math.abs(dy)<30?80:Math.abs(dy)>300?35:0;
      const cx=(start.x+end.x)/2-dy/len*bend,cy=(start.y+end.y)/2+dx/len*bend,d=`M${start.x},${start.y}Q${cx},${cy} ${end.x},${end.y}`;
      group.querySelectorAll(".ws-edge,.ws-edge-hit").forEach(path=>path.setAttribute("d",d));
      const point=t=>({x:(1-t)**2*start.x+2*(1-t)*t*cx+t*t*end.x,y:(1-t)**2*start.y+2*(1-t)*t*cy+t*t*end.y});
      group.querySelectorAll(".ws-arrow").forEach(arrow=>{const t=Number(arrow.dataset.position),p=point(t),q=point(t+(t<.5?.01:-.01));arrow.setAttribute("transform",`translate(${p.x},${p.y}) rotate(${Math.atan2(p.y-q.y,p.x-q.x)*180/Math.PI}) scale(${3/camera.k})`);});
    }
    function connect(a,b,edges,layer) {
      if(!a||!b) return;
      const color=domains.get(nodes.get(edges[0].from).domain).color;
      const group=svg("g",{class:`ws-exchange${edges.every(e=>e.condition)?" conditional":""}`,role:"button",tabindex:0,"aria-label":`Inspect exchange: ${edges[0].label}${edges.length>1?` and ${edges.length-1} related exchanges`:""}`});
      group.append(svg("path",{stroke:color,class:"ws-edge"}),svg("path",{class:"ws-edge-hit"}));
      const arrow=t=>group.append(svg("path",{d:"M-2 -.9L0 0L-2 .9",stroke:color,class:"ws-arrow","data-position":t}));
      arrow(.82);if(edges.some(e=>e.bidirectional)||edges.some(e=>nodes.get(e.from).domain===(b.kind==="domain"?b.item.id:b.item.domain)&&nodes.get(e.to).domain===(a.kind==="domain"?a.item.id:a.item.domain)))arrow(.18);
      updateConnection({a,b,group});
      group.addEventListener("pointerenter",event=>{group.classList.add("is-hover");tooltip(event,edges[0].label,edges.slice(0,2).map(e=>e.summary).join(" "));});
      group.addEventListener("pointerleave",()=>{group.classList.remove("is-hover");$("tooltip").hidden=true;});
      const open=()=>{selectProcess(edges[0].from);exchange=edges;state.tab="exchanges";renderAnalysis();};
      group.addEventListener("click",event=>{event.stopPropagation();if(!skipClick)open();});group.addEventListener("keydown",event=>{if(["Enter"," "].includes(event.key)){event.preventDefault();open();}});
      layer.append(group);const connection={a,b,edges,group};sceneEdges.push(connection);return connection;
    }
    function renderScene(reframe = true) {
      $("tooltip").hidden=true;panelHome.append(panel);panel.hidden=true;inlineCard=null;
      world.replaceChildren();cards=[];sceneEdges=[];overviewEdges=[];detailEdges=[];
      const visible=model.visible(data,state),mobile=width<721;renderedFilters=[state.research,state.conditional,state.status].join(":");
      const layout=mobile?[[0,0],[290,0],[0,290],[290,290],[0,580],[290,580]]:[[320,0],[0,0],[640,0],[320,290],[0,290],[640,290]];
      const background=svg("g",{class:"ws-overview-exchanges"}),connections=svg("g",{class:"ws-detail-exchanges"});
      world.append(background,connections);
      data.domains.forEach((d,i)=>{
        const domain=card(d.id,d,...layout[i],"domain");world.append(domain.group);
        const clip=svg("clipPath",{id:`ws-clip-${d.id}`});clip.append(svg("circle",{r:domain.r-2}));domain.group.append(clip);
        domain.children=svg("g",{class:"ws-domain-contents","clip-path":`url(#ws-clip-${d.id})`});
        domain.group.insertBefore(domain.children,domain.summary);
        const members=visible.nodes.filter(n=>n.domain===d.id),packed=model.pack(members.length);
        members.forEach((n,j)=>{const p=packed[j],child=card(n.id,n,domain.x+p.x,domain.y+p.y,"process",domain,p.r);domain.children.append(child.group);});
      });
      const pairs=new Map();visible.edges.forEach(e=>{
        const a=nodes.get(e.from).domain,b=nodes.get(e.to).domain;
        if(a!==b){const key=[a,b].sort().join(":");if(!pairs.has(key))pairs.set(key,{a,b,edges:[]});pairs.get(key).edges.push(e);}
        const connection=connect(cards.find(c=>c.kind==="process"&&c.item.id===e.from),cards.find(c=>c.kind==="process"&&c.item.id===e.to),[e],connections);
        if(connection)detailEdges.push(connection);
      });
      pairs.forEach(p=>{const edge=connect(cards.find(c=>c.kind==="domain"&&c.key===p.a),cards.find(c=>c.kind==="domain"&&c.key===p.b),p.edges,background);if(edge)overviewEdges.push(edge);});
      const domainsOnly=cards.filter(c=>c.kind==="domain"),left=mobile?12:270,right=width-(mobile?12:65),top=mobile?132:90,bottom=height-(mobile?120:105);
      const minX=Math.min(...domainsOnly.map(c=>c.x-c.r-10)),maxX=Math.max(...domainsOnly.map(c=>c.x+c.r+10));
      const minY=Math.min(...domainsOnly.map(c=>c.y-c.r-10)),maxY=Math.max(...domainsOnly.map(c=>c.y+c.r+10));
      base=Math.max(.12,Math.min((right-left)/(maxX-minX),Math.max(100,bottom-top)/(maxY-minY),1.4));
      overviewCamera={k:base,x:(left+right)/2-(minX+maxX)/2*base,y:(top+bottom)/2-(minY+maxY)/2*base};
      const netTop=mobile?84:top,netScale=mobile?Math.max(.12,Math.min((right-left)/(maxX-minX),Math.max(100,bottom-netTop)/(maxY-minY),1.4)):base;
      networkCamera={k:netScale,x:(left+right)/2-(minX+maxX)/2*netScale,y:(netTop+bottom)/2-(minY+maxY)/2*netScale};
      sceneReady=true;header();if(reframe)fit();renderAnalysis();updateSemantic();
    }
    function attachPanel(c) {
      if(inlineCard===c)return;
      if(inlineCard?.detail){inlineCard.detail.remove();inlineCard.detail=null;}
      const detail=svg("foreignObject",{class:"ws-inline-analysis","data-process":c.item.id});
      c.group.append(detail);detail.append(panel);c.detail=detail;inlineCard=c;
      panel.classList.add("is-inline");panel.hidden=false;
    }
    function nameBox(c) {
      if(c.nameBox)return c.nameBox;
      let x0=Infinity,y0=Infinity,x1=-Infinity,y1=-Infinity;
      try{c.summary.querySelectorAll(".ws-net-name").forEach(text=>{const b=text.getBBox();x0=Math.min(x0,b.x);y0=Math.min(y0,b.y);x1=Math.max(x1,b.x+b.width);y1=Math.max(y1,b.y+b.height);});}catch{return null;}
      return x1>x0&&y1>y0?c.nameBox={x:x0,y:y0,width:x1-x0,height:y1-y0}:null;
    }
    function updateSemantic() {
      if(!sceneReady)return;
      const domainRadius=focusRadius("domain"),processRadius=focusRadius("process");
      cards.filter(c=>c.kind==="domain").forEach(c=>{
        const r=c.r*camera.k,detail=Math.max(model.fade(r,domainRadius*.67,domainRadius*.95),netMix),title=(1-model.fade(r,domainRadius*.48,domainRadius*.68))*(1-netMix);
        const compact=width<721;c.tag.firstChild.setAttribute("text-anchor",compact?"start":"end");
        c.tag.setAttribute("transform",`translate(${compact?-c.r*.95:-c.r*.74},${compact?-c.r-5:-c.r*.74-6}) scale(${(compact?.8:1)/camera.k})`);setOpacity(c.tag,netMix);
        c.reveal=detail;setOpacity(c.summary,title);setOpacity(c.children,.045+.955*detail);
        c.hit.style.pointerEvents=detail>.85?"none":"auto";
        c.hit.firstElementChild.setAttribute("fill-opacity",1-detail*.78);
        c.children.style.pointerEvents=detail>.4?"auto":"none";c.children.setAttribute("aria-hidden",String(detail<=.4));
        c.hit.setAttribute("tabindex",detail>.85?"-1":"0");
      });
      cards.filter(c=>c.kind==="process").forEach(c=>{
        const r=c.r*camera.k,detail=c===inlineCard?model.fade(r,processRadius*.55,processRadius*.86):0;
        const role=model.processRole(c.item.id),color=model.mixColor(c.parent.item.color,role?.color||c.parent.item.color,c.parent.reveal);
        c.group.style.setProperty("--domain",color);
        c.names.setAttribute("opacity",(1-netMix).toFixed(3));c.netNames.setAttribute("opacity",netMix.toFixed(3));
        const normalScale=Math.min(c.r/110,100/(110*camera.k)),box=netMix>0?nameBox(c):null;
        let summaryTransform=`scale(${normalScale})`;
        if(box){const fitScale=.96*c.r/Math.hypot(box.width/2,box.height/2),netScale=Math.min(12/(21*camera.k),fitScale),s=normalScale+(netScale-normalScale)*netMix;summaryTransform=`translate(0,${-s*(box.y+box.height/2)*netMix}) scale(${s})`;}
        c.summary.setAttribute("transform",summaryTransform);
        setOpacity(c.summary,c===inlineCard?1-model.fade(r,processRadius*.32,processRadius*.53):1);c.hit.setAttribute("tabindex",c.parent.reveal>.45&&detail<.55?"0":"-1");
        c.hit.style.pointerEvents=c.parent.reveal>.45&&detail<.55?"auto":"none";
        c.hit.setAttribute("aria-hidden",String(c.parent.reveal<=.45||detail>=.55));
        c.group.classList.toggle("is-focus",c.item.id===state.process);
        if(!c.detail)return;
        const v=viewport(),w=Math.max(180,Math.min(r*1.32,width-(width<721?110:180),710));
        const h=Math.max(180,Math.min(Math.sqrt(Math.max(0,r*r-w*w/4))*1.82,v.bottom-v.top,660));
        c.detail.setAttribute("x",-w/2);c.detail.setAttribute("y",-h/2);c.detail.setAttribute("width",w);c.detail.setAttribute("height",h);
        c.detail.setAttribute("transform",`scale(${1/camera.k})`);setOpacity(c.detail,detail);
        c.detail.style.pointerEvents=detail>.6?"auto":"none";c.detail.setAttribute("aria-hidden",String(detail<=.6));panel.inert=detail<=.6;
        c.detail.style.visibility=detail<.001?"hidden":"visible";
      });
      overviewEdges.forEach(edge=>{const opacity=1-Math.max(edge.a.reveal,edge.b.reveal);setOpacity(edge.group,opacity,true);});
      const hoverCard=netMix>.5&&hovered?cards.find(c=>c.kind==="process"&&c.key===hovered):null;
      const related=hoverCard?new Set(model.neighborhood(data,hoverCard.item.id,state).edges.map(e=>e.id)):state.process?new Set(model.neighborhood(data,state.process,state).edges.map(e=>e.id)):null;
      detailEdges.forEach(edge=>{
        const reveal=Math.max(edge.a.parent.reveal,edge.b.parent.reveal),focus=related&&!related.has(edge.edges[0].id)?.12:1;
        const source=nodes.get(edge.edges[0].from),domain=domains.get(source.domain),color=model.mixColor(domain.color,model.processRole(source.id)?.color||domain.color,reveal);
        edge.group.querySelectorAll(".ws-edge,.ws-arrow").forEach(path=>path.setAttribute("stroke",color));
        setOpacity(edge.group,reveal*focus,true);
      });
      sceneEdges.forEach(updateConnection);
      setOpacity(colorLegend,state.domain?cards.find(c=>c.kind==="domain"&&c.item.id===state.domain)?.reveal||0:0);
      const heading=document.querySelector(".workspace-heading"),home=state.network?networkCamera:overviewCamera,opacity=(1-model.fade(camera.k/base,1.1,1.8))*(width<721?(1-netMix)*(1-model.fade(Math.hypot(camera.x-home.x,camera.y-home.y)/width,.03,.18)):1);
      setOpacity(heading,opacity);heading.style.visibility=opacity<.01?"hidden":"visible";
      semanticDirty=false;
    }
    function syncFocus(point) {
      if(state.network)return;
      const candidates=cards.filter(c=>c.kind==="domain"),worldPoint={x:(point.x-target.x)/target.k,y:(point.y-target.y)/target.k};
      const contains=c=>Math.hypot(c.x-worldPoint.x,c.y-worldPoint.y)<=c.r;
      const domain=candidates.find(contains),existing=cards.find(c=>c.kind==="domain"&&c.item.id===state.domain);
      const d=domain||existing;
      if(!d||d.r*target.k<focusRadius("domain")*.61){if(state.domain)ecosystem(true,false);return;}
      const children=cards.filter(c=>c.parent===d),process=children.find(contains),current=children.find(c=>c.item.id===state.process);
      const p=process||current;
      if(p&&p.r*target.k>focusRadius("process")*.44){if(state.process!==p.item.id)selectProcess(p.item.id,true,false);}
      else if(state.domain!==d.item.id||state.process)selectDomain(d.item.id,true,false);
    }
    function paragraph(container,title,text,cls="") {
      if(!text)return;container.append(html("h3","analysis-subtitle",title),html("p",cls,text));
    }
    function processLink(node,subtitle="") {
      const button=html("button","analysis-process-link",node.label);button.style.setProperty("--domain",domains.get(node.domain).color);
      if(subtitle)button.append(html("small","",subtitle));button.addEventListener("click",()=>selectProcess(node.id));return button;
    }
    function renderExchanges(container) {
      const n=nodes.get(state.process),id=state.domain;
      const edges=exchange||model.visible(data,state).edges.filter(e=>n?(e.from===n.id||e.to===n.id):!id||nodes.get(e.from).domain===id||nodes.get(e.to).domain===id);
      if(n){
        const label=html("label","analysis-control","Direction"),select=html("select");select.setAttribute("aria-label","Exchange direction");
        [["all","Inputs and outputs"],["in","Inputs / drivers"],["out","Outputs / responses"]].forEach(([v,t])=>{const o=html("option","",t);o.value=v;select.append(o);});select.value=state.direction;
        select.addEventListener("change",()=>{state.direction=select.value;exchange=null;renderAnalysis();writeURL();});label.append(select);container.append(label);
      }
      edges.filter(e=>!n||state.direction==="all"||e.bidirectional||(state.direction==="in"?e.to===n.id:e.from===n.id)).forEach(e=>{
        const item=html("article","analysis-exchange");
        item.append(html("p","eyebrow",e.research?"RESEARCH EXTENSION":e.condition?"CONDITIONAL EXCHANGE":"DEFINED EXCHANGE"));
        item.append(html("h3","",e.label),html("p","exchange-science",e.summary));
        const a=nodes.get(e.from),b=nodes.get(e.to),direction=html("div","analysis-endpoints");direction.append(processLink(a,"SOURCE"),html("span","",e.bidirectional?"⇄":"→"),processLink(b,"DESTINATION"));item.append(direction);
        paragraph(item,"Units",e.units,"analysis-mono");
        const details=html("details","exchange-method"),summary=html("summary","","Method and support");details.append(summary);
        [["Method",e.method],["Space",e.spatial_support],["Time",e.temporal_support],["Relationship",`${e.kind.replaceAll("_"," ")} · ${e.conservation.replaceAll("_"," ")}`],["Scenario condition",e.condition]].forEach(([label,text])=>paragraph(details,label,text));item.append(details);container.append(item);
      });
      if(!edges.length)container.append(html("p","analysis-note","No defined exchanges match the selected layers."));
      container.append(html("p","analysis-note","Arrows show the direction of each exchange. Line width does not show its magnitude."));
    }
    function renderScience(container) {
      const n=nodes.get(state.process),d=domains.get(state.domain);
      if(n){
        container.append(html("p","analysis-lead",n.summary),html("div","analysis-state",`${marker(n)} ${type(n)} · ${n.formulation}`));
        [["Formulation",n.model_level],["Equation",n.equations],["Variables",n.variables],["Units",n.units],["Assumptions",n.assumptions],["Limits",n.limits]].forEach(([title,text])=>paragraph(container,title,text,title==="Equation"?"analysis-equation":""));
        if(n.implementation!=="research")paragraph(container,"Interpretation","A working implementation does not establish field accuracy. The model still needs evaluation against observations.");
      }else if(d){
        container.append(html("p","analysis-lead",d.description));paragraph(container,"Scientific scope",data.scientific_acceptance);
        const members=model.visible(data,state).nodes.filter(node=>node.domain===d.id);members.forEach(node=>container.append(processLink(node,`${type(node)} · ${node.formulation}`)));
      }
    }
    function basis(metric) {
      if(["temperature","history","field"].includes(metric))return "Saved river experiment. Prescribed upstream flow and temperature; authored meteorology and lateral sources. Playback and chart controls do not rerun the model. This preview uses selected saved times. The full river dataset includes every saved frame.";
      if(metric==="oxygen")return `Saved spatial diagnostic. Recorded integration increment: ${data.ecology.oxygen_dt_s} s. This is separate from the river playback window.`;
      if(metric==="periphyton")return `Saved spatial diagnostic. Recorded integration increment: ${data.ecology.periphyton_dt_s} s. Biomass and nutrient parameters are authored.`;
      if(["air","wind"].includes(metric))return data.analytics.weather.basis+" The saved trace spans 60 seconds.";
      if(metric==="water-sum")return `${data.ecology.water.days}-day preparation before the river experiment. Water depths sum across ${data.ecology.water.modeled_patch_count} authored patches; they are not a basin-wide mean. Surface and subsurface drainage are separate equal shares of bucket overflow.`;
      if(metric==="snow"||metric==="water")return "Per-patch snow water-equivalent depth. Physical contributing areas are unavailable; no basin volume or area-weighted depth is represented.";
      if(metric==="heat")return `Authored spatial heat flux on a ${data.coverage.heat.grid.cell_m} m grid. Background, apron, and pool categories are scenario values. They are not measured local heat fluxes.`;
      if(metric==="pools")return "Authored center and edge values for mapped thermal pools. These are steady scenario parameters; the snapshot contains no reservoir temperature trajectory.";
      if(metric==="shading")return `Saved single-sample shortwave diagnostic. ${data.analytics.shading_basis}. This field is not a diurnal trajectory.`;
      return "Saved authored patch state. Relative biomass and soil moisture do not establish measured vegetation mass, habitat boundaries, or field conditions.";
    }
    function control(label,el) {const wrap=html("label","analysis-control",label);wrap.append(el);return wrap;}
    function slider(id,label,min,max,value,onInput) {
      const input=html("input");input.type="range";input.id=id;input.min=min;input.max=max;input.step=1;input.value=value;input.setAttribute("aria-label",label);input.addEventListener("input",onInput);return input;
    }
    function renderData(container) {
      if(data.process_views?.[state.process]?.length){
        const process=state.process;
        window.YSProcessData.mount(container,data,process,{view:state.processView,entity:state.processEntity},selection=>{
          if(state.process!==process)return;state.processView=selection.view;state.processEntity=selection.entity;
          container.querySelector(".analysis-workbench-link")?.setAttribute("href",workbenchAddress());writeURL();
        });return;
      }
      const choices=metrics();
      if(state.status==="none"&&!state.process){container.append(html("p","analysis-lead","Research extensions have no numerical results in the selected model."),html("p","analysis-note","Select a research process for its scientific scope and proposed connections."));return;}
      if(!choices.length){container.append(html("p","analysis-lead",nodes.get(state.process)?.implementation==="research"?"This research extension contributes no numerical results to the selected model.":"The public snapshot has no plotted diagnostic for this process."));
        container.append(html("p","analysis-note","See the Science tab for the calculation and its limits."));return;}
      const select=html("select");select.id="workspace-metric";select.setAttribute("aria-label","Analysis variable");choices.forEach(key=>{const o=html("option","",titles[key]);o.value=key;select.append(o);});select.value=state.metric;
      select.addEventListener("change",()=>{state.metric=select.value;playing=false;renderAnalysis();writeURL();});container.append(control("Variable",select));
      const binding=model.binding(state.process,state.metric);container.append(html("p","analysis-note",`${binding.role} · ${binding.note}`));

      const provenance=html("details","analysis-provenance");provenance.append(html("summary","","Source and time window"),html("p","analysis-note analysis-basis",basis(state.metric)));
      const riverMetric=["temperature","history","field","oxygen","periphyton","shading"].includes(state.metric);
      if(riverMetric){
        const region=html("div","linked-map");miniMap=svg("svg",{viewBox:"0 0 600 100",role:"group","aria-label":"Linked river location. Select a channel location to update the analysis."});region.append(miniMap);container.append(region);
        container.append(control("River location",slider("workspace-cell","River location",0,data.river.cells.length-1,state.cell,e=>{state.cell=Number(e.target.value);updatePlot();writeURL();})));
      }
      if(["temperature","history","field"].includes(state.metric)){
        const wrap=html("div","workspace-playback"),button=html("button","",playing?"Ⅱ":"▶");button.id="workspace-play";button.setAttribute("aria-label",playing?"Pause saved model frames":"Play saved model frames");button.addEventListener("click",()=>{playing=!playing;lastTick=0;playElapsed=data.river.frames[state.frame].t;if(playing&&state.frame===data.river.frames.length-1){state.frame=0;playElapsed=data.river.frames[0].t;}button.textContent=playing?"Ⅱ":"▶";button.setAttribute("aria-label",playing?"Pause saved model frames":"Play saved model frames");});
        const label=control("Elapsed model time",slider("workspace-frame","Saved model time",0,data.river.frames.length-1,state.frame,e=>{state.frame=Number(e.target.value);playElapsed=data.river.frames[state.frame].t;lastTick=0;updatePlot();writeURL();}));
        const output=html("output","",time(data.river.frames[state.frame].t));output.id="workspace-frame-label";label.prepend(output);wrap.append(button,label);container.append(wrap);
      }
      const chart=html("div","workspace-chart");plot=svg("svg",{viewBox:"0 0 600 300",role:"img","aria-label":titles[state.metric]});chart.append(plot);container.append(chart);
      const probe=html("output","analysis-probe");probe.id="analysis-probe";probe.setAttribute("aria-live","off");container.append(probe);
      if(!["field","heat","water","water-sum","snow","pools","biomass","moisture"].includes(state.metric)){
        const controls=html("div","chart-options"),local=html("input");local.type="checkbox";local.checked=state.local;local.id="workspace-local";local.addEventListener("change",()=>{state.local=local.checked;updatePlot();writeURL();});controls.append(control("Local vertical range",local));
        if(state.metric==="temperature"){const compare=html("input");compare.type="checkbox";compare.checked=state.compare;compare.id="workspace-compare";compare.addEventListener("change",()=>{state.compare=compare.checked;updatePlot();writeURL();});controls.append(control("Compare initial frame",compare));}
        const reset=html("button","","Reset chart range");reset.id="workspace-reset-range";reset.addEventListener("click",()=>{state.first=0;state.last=data.river.cells.length-1;state.timeFirst=0;state.timeLast=data.river.frames.length-1;state.traceFirst=0;state.traceLast=Infinity;updatePlot();writeURL();});controls.append(reset);container.append(controls,html("p","analysis-note chart-gesture-note","Drag across the profile to select a horizontal range. Hover to probe; the river location and other spatial diagnostics retain the same cell selection."));
      }
      container.append(html("div","analysis-axis-note"));
      container.insertBefore(chart,container.children[1]||null);
      const playback=container.querySelector(".workspace-playback");if(playback)container.insertBefore(playback,chart);
      container.insertBefore(probe,chart.nextSibling);
      const linked=container.querySelector(".linked-map"),cellControl=container.querySelector("#workspace-cell")?.closest("label");
      if(linked)container.append(linked);if(cellControl)container.append(cellControl);container.append(provenance);
      plot.addEventListener("pointerdown",event=>{if(chartSeries?.type!=="line")return;brush=plotPosition(event).x;plot.setPointerCapture(event.pointerId);});
      plot.addEventListener("pointermove",event=>probePlot(event));
      plot.addEventListener("pointerup",event=>{
        if(brush===null)return;const end=plotPosition(event).x,start=brush;brush=null;
        if(Math.abs(end-start)>18&&chartSeries?.type==="line"){
          const [a,b]=[nearestPoint(start),nearestPoint(end)];const [first,last]=model.range(a.index,b.index,chartSeries.spatial?data.river.cells.length:chartSeries.temporal?data.river.frames.length:chartSeries.points.length);
          if(last>first){if(chartSeries.spatial){state.first=first;state.last=last;}else if(chartSeries.temporal){state.timeFirst=first;state.timeLast=last;}else{state.traceFirst=first;state.traceLast=last;}updatePlot();writeURL();}
        }
      });
      plot.addEventListener("pointercancel",()=>{brush=null;});updatePlot();
    }
    function renderAnalysis() {
      header();if(!state.panel)return;
      const subject=cards.find(c=>c.kind==="process"&&c.item.id===state.process);if(!subject)return;attachPanel(subject);
      const n=nodes.get(state.process),d=domains.get(state.domain);$("analysis-domain").textContent=d?d.label.toUpperCase():"SYSTEM INTERACTIONS";
      $("analysis-title").textContent=exchange?"Process exchanges":n?n.label:d?`${d.label} analysis`:"Directed exchanges";
      $("analysis-panel").style.setProperty("--domain",model.processRole(n?.id)?.color||d?.color||"#bac6df");
      document.querySelectorAll("[data-analysis-tab]").forEach(b=>b.setAttribute("aria-pressed",String(b.dataset.analysisTab===state.tab)));
      $("expand-analysis").setAttribute("aria-label","Zoom further into process data");
      $("close-analysis").setAttribute("aria-label","Zoom out to domain");
      const container=$("analysis-content");window.YSProcessData.dispose(container);container.dataset.tab=state.tab;container.replaceChildren();plot=null;miniMap=null;chartSeries=null;
      if(state.tab==="science")renderScience(container);else if(state.tab==="exchanges")renderExchanges(container);else renderData(container);
      if(n?.implementation!=="research"&&(!data.process_views?.[n?.id]||data.process_views[n.id].some(view=>view.kind==="native"))){const link=html("a","analysis-workbench-link","Open full system dataset ↗");link.href=workbenchAddress();container.append(link);}
    }
    function temperature(value) {return window.YSData.color(value,temperatureExtent);}
    function drawMiniMap() {
      if(!miniMap)return;miniMap.replaceChildren();const cells=data.river.cells,xs=cells.map(c=>c.x),zs=cells.map(c=>c.z),loX=Math.min(...xs),hiX=Math.max(...xs),loZ=Math.min(...zs),hiZ=Math.max(...zs);
      const k=Math.min(520/(hiX-loX),76/(hiZ-loZ)),px=c=>({x:300+(c.x-(loX+hiX)/2)*k,y:48+(c.z-(loZ+hiZ)/2)*k});
      const path=cells.map((c,i)=>`${i?"L":"M"}${px(c).x},${px(c).y}`).join(" ");miniMap.append(svg("path",{d:path,fill:"none",stroke:"#689ed2","stroke-width":3}));
      const point=px(cells[state.cell]);miniMap.append(svg("circle",{cx:point.x,cy:point.y,r:5,fill:"#f4e0b2",stroke:"#07080b","stroke-width":1.5}));
      miniMap.append(svg("text",{x:9,y:20,class:"analysis-map-label"},"LINKED RIVER CELL"),svg("text",{x:9,y:40,class:"analysis-map-value"},`${fmt(cells[state.cell].s/1000,3)} km`));
      miniMap.onclick=event=>{const point=window.YSData.eventToSvg(miniMap,event);if(!point)return;const {x,y}=point;let closest=0,dist=Infinity;cells.forEach((c,i)=>{const p=px(c),d=Math.hypot(p.x-x,p.y-y);if(d<dist){closest=i;dist=d;}});state.cell=closest;updatePlot();writeURL();};
    }
    function plotPosition(event) {return window.YSData.eventToSvg(plot,event)||{x:-1,y:-1};}
    function nearestPoint(x) {const points=chartSeries.visible;return points.reduce((a,b)=>Math.abs(a.px-x)<Math.abs(b.px-x)?a:b);}
    function probePlot(event) {
      if(!plot)return;const p=plotPosition(event);
      if(state.metric==="field"){
        state.cell=model.nearestIndex(data.river.cells.map(c=>c.s),clamp((p.x-57)/525,0,1)*data.river.length_m);state.frame=model.nearestIndex(data.river.frames.map(f=>f.t),clamp((p.y-20)/225,0,1)*data.river.frames.at(-1).t);updatePlot();writeURL();
      }else if(state.metric==="heat"){
        const grid=data.coverage.heat.grid,col=Math.floor((p.x-170)/240*grid.nx),row=Math.floor((p.y-20)/240*grid.nz),values=data.coverage.heat.values;
        if(col<0||row<0||col>=grid.nx||row>=grid.nz)return;const value=Array.isArray(values[0])?values[row][col]:values[row*grid.nx+col];$("analysis-probe").textContent=`${fmt(value)} W/m² · authored cell (${col+1}, ${row+1}) · ${grid.cell_m} m grid`;
      }else if(chartSeries?.type==="line"){
        const point=nearestPoint(p.x);if(brush!==null){const rect=svg("rect",{x:Math.min(brush,p.x),y:20,width:Math.abs(brush-p.x),height:225,fill:"#9ac4ff","fill-opacity":.16,"pointer-events":"none",id:"plot-brush"});plot.querySelector("#plot-brush")?.remove();plot.append(rect);return;}
        if(chartSeries.spatial)state.cell=point.index;else if(chartSeries.temporal)state.frame=point.index;
        else{$("analysis-probe").textContent=`${fmt(point.x,3)} ${chartSeries.xUnit} · ${fmt(point.y,5)} ${chartSeries.unit}`;return;}updatePlot();writeURL();
      }
    }
    function updatePlot() {
      if(!plot)return;plot.replaceChildren();chartSeries=model.series(data,state.metric,state.frame,state.cell);
      $("analysis-content").querySelector(".analysis-workbench-link")?.setAttribute("href",workbenchAddress());
      const color=model.processRole(state.process)?.color||domains.get(state.domain)?.color||"#80bdff",frame=data.river.frames[state.frame] || {t:0,temperature:[]};
      $("workspace-cell")&&($("workspace-cell").value=String(state.cell));$("workspace-frame")&&($("workspace-frame").value=String(state.frame));if($("workspace-frame-label"))$("workspace-frame-label").textContent=time(frame.t);
      const axis=$("analysis-content").querySelector(".analysis-axis-note"),probe=$("analysis-probe");drawMiniMap();
      if(state.metric==="field"){
        const n=data.river.cells.length,frames=data.river.frames;
        if(!fieldImage){const raster=document.createElement("canvas");raster.width=1024;raster.height=frames.length;const ctx=raster.getContext("2d"),distances=data.river.cells.map(c=>c.s),times=frames.map(f=>f.t),lookup=Array.from({length:1024},(_,i)=>model.nearestIndex(distances,(i+.5)/1024*data.river.length_m));
          for(let j=0;j<raster.height;j++){const row=frames[model.nearestIndex(times,(j+.5)/raster.height*frames.at(-1).t)];lookup.forEach((index,i)=>{ctx.fillStyle=temperature(row.temperature[index]);ctx.fillRect(i,j,1,1);});}fieldImage=raster.toDataURL("image/png");}
        plot.append(svg("image",{href:fieldImage,x:57,y:20,width:525,height:225,preserveAspectRatio:"none",class:"ground-heat-image","pointer-events":"none"}));
        plot.append(svg("path",{d:`M${57+data.river.cells[state.cell].s/data.river.length_m*525} 20V245M57 ${20+frame.t/frames.at(-1).t*225}H582`,stroke:"white","stroke-opacity":.8,"stroke-width":1,"pointer-events":"none"}));
        for(let i=0;i<=4;i++){plot.append(svg("text",{x:57+i/4*525,y:268,class:"ws-axis","text-anchor":"middle"},`${fmt(i/4*data.river.length_m/1000,1)} km`),svg("text",{x:48,y:25+i/4*220,class:"ws-axis","text-anchor":"end"},`${fmt(i/4*frames.at(-1).t/60,0)} min`));}
        for(let i=0;i<100;i++)plot.append(svg("rect",{x:220+i*1.6,y:285,width:1.7,height:5,fill:temperature(temperatureMin+i/99*(temperatureMax-temperatureMin)),"pointer-events":"none"}));
        plot.append(svg("text",{x:209,y:291,class:"ws-axis","text-anchor":"end"},`${fmt(temperatureMin,2)} °C`),svg("text",{x:390,y:291,class:"ws-axis"},`${fmt(temperatureMax,2)} °C`));
        axis.textContent=`Saved frames × river cells. Horizontal: distance downstream. Vertical: elapsed minutes. Nearest saved cell and frame; no numerical interpolation. Color range across all frames: ${fmt(temperatureMin,4)}–${fmt(temperatureMax,4)} °C (blue–orange). Select any position to link time and location.`;
      }else if(state.metric==="heat"){
        plot.append(svg("image",{href:"/dashboard/ground-heat.png",x:170,y:20,width:240,height:240,class:"ground-heat-image"}),svg("rect",{x:170,y:20,width:240,height:240,fill:"none",stroke:"#56647d"}));
        const p=data.coverage.heat.parameters;plot.append(svg("text",{x:290,y:284,class:"ws-axis","text-anchor":"middle"},`${fmt(data.coverage.heat.grid.nx*data.coverage.heat.grid.cell_m/1000,3)} × ${fmt(data.coverage.heat.grid.nz*data.coverage.heat.grid.cell_m/1000,3)} km · N ↑`));axis.textContent=`Authored flux: background ${p.background_w_m2}, apron ${p.apron_w_m2}, pool ${p.pool_w_m2} W/m². Hover to inspect the grid.`;probe.textContent="Hover the field to inspect authored heat flux.";
      }else if(chartSeries?.type==="bars"){
        const rows=chartSeries.points,max=Math.max(...rows.map(p=>p.y),1),rowHeight=Math.min(33,225/Math.max(rows.length,1));
        rows.forEach((p,i)=>{const y=20+i*rowHeight,label=svg("text",{x:4,y:y+11,class:"ws-axis"},p.label.length>29?p.label.slice(0,28)+"…":p.label);label.append(svg("title",{},`${p.label}: ${p.y} ${chartSeries.unit}`));plot.append(label,svg("rect",{x:215,y:y+1,width:265,height:13,rx:2,fill:"#1b2330"}),svg("rect",{x:215,y:y+1,width:p.y/max*265,height:13,rx:2,fill:i%2?"#9cacc5":color}),svg("text",{x:590,y:y+11,class:"ws-axis","text-anchor":"end"},fmt(p.y,3)));});
        axis.textContent=`${chartSeries.label} · ${chartSeries.unit}. Zero baseline.`;probe.textContent=state.metric==="water-sum"?`Summed-depth water balance residual: ${data.ecology.water.water_residual_mm.toExponential(2)} mm`:state.metric==="biomass"?"Biomass relative to each authored carrying capacity.":"Saved values from the selected model generation.";
      }else if(chartSeries?.type==="line"){
        const all=chartSeries.points,first=chartSeries.spatial?state.first:chartSeries.temporal?state.timeFirst:state.traceFirst,last=chartSeries.spatial?state.last:chartSeries.temporal?state.timeLast:state.traceLast;
        const points=all.filter(p=>p.index>=first&&p.index<=last),values=points.map(p=>p.y).filter(Number.isFinite);
        if(!values.length){axis.textContent="No finite values in the selected range.";probe.textContent="No plotted diagnostic available.";return;}
        if(state.compare&&state.metric==="temperature")points.forEach(p=>values.push(data.river.frames[0].temperature[p.index]));
        const lo=Math.min(...values),hi=Math.max(...values),pad=Math.max((hi-lo)*.12,.0001),min=state.local?lo-pad:["temperature","history"].includes(state.metric)?temperatureMin-Math.max((temperatureMax-temperatureMin)*.12,.0001):Math.min(0,lo),max=state.local?hi+pad:["temperature","history"].includes(state.metric)?temperatureMax+Math.max((temperatureMax-temperatureMin)*.12,.0001):Math.max(hi*1.08,min+1);
        const xMin=points[0]?.x||0,xMax=points.at(-1)?.x||1,x=p=>57+(p.x-xMin)/(xMax-xMin||1)*525,y=v=>20+(max-v)/(max-min)*225;
        for(let i=0;i<=4;i++){const py=20+i*225/4;plot.append(svg("path",{d:`M57 ${py}H582`,stroke:"#2c3545","stroke-width":.7}),svg("text",{x:48,y:py+4,class:"ws-axis","text-anchor":"end"},fmt(max-i*(max-min)/4,3)),svg("text",{x:57+i*525/4,y:268,class:"ws-axis","text-anchor":"middle"},fmt(xMin+i*(xMax-xMin)/4,2)));}
        if(state.compare&&state.metric==="temperature")plot.append(svg("path",{d:window.YSData.segments(points.map(p=>({...p,y:data.river.frames[0].temperature[p.index]})),x,p=>y(p.y)),fill:"none",stroke:"#c2c9d6","stroke-dasharray":"4 4","stroke-width":1.5}));
        plot.append(svg("path",{d:window.YSData.segments(points,x,p=>y(p.y)),fill:"none",stroke:color,"stroke-width":2,"pointer-events":"none"}));
        chartSeries.visible=points.map(p=>({...p,px:x(p)}));const selected=all[chartSeries.temporal?state.frame:chartSeries.spatial?state.cell:0];
        if(selected&&Number.isFinite(selected.y)&&selected.index>=first&&selected.index<=last){plot.append(svg("path",{d:`M${x(selected)} 20V245`,stroke:"#bbc9df","stroke-opacity":.5,"stroke-dasharray":"3 3","pointer-events":"none"}),svg("circle",{cx:x(selected),cy:y(selected.y),r:4,fill:"#fff0d1","pointer-events":"none"}));}
        axis.textContent=`${chartSeries.unit} · ${state.local?"Local vertical range":["temperature","history"].includes(state.metric)?"Fixed all-run range":"Zero baseline"}: ${fmt(min,5)}–${fmt(max,5)}. Horizontal: ${fmt(xMin,3)}–${fmt(xMax,3)} ${chartSeries.xUnit}.${state.compare&&state.metric==="temperature"?" Dashed: initial frame.":""}`;
        probe.textContent=selected?`${fmt(selected.x,3)} ${chartSeries.xUnit} · ${fmt(selected.y,5)} ${chartSeries.unit}`:"No selected value.";
      }
      if(["temperature","history","field"].includes(state.metric))probe.textContent=`Cell ${state.cell+1}/${data.river.cells.length} · ${fmt(data.river.cells[state.cell].s/1000,3)} km · ${time(frame.t)} · ${fmt(frame.temperature[state.cell],4)} °C`;
      plot.setAttribute("aria-label",`${titles[state.metric]}. ${axis.textContent} ${probe.textContent}`);
    }
    function zoom(factor,x=width/2,y=height/2) {
      target=model.zoomAt(target,factor,{x,y},base*.45,base*170);
      if(reduced)camera={...target};
      semanticDirty=true;
      syncFocus({x,y});
    }
    function restore() {
      const raw=location.hash.slice(1),p=new URLSearchParams(raw);
      if(p.get("view")==="analysis"){playing=false;lastTick=0;return;}
      state.research=p.get("research")==="1";$("show-research").checked=state.research;state.local=p.get("scale")==="local";state.compare=p.get("compare")==="1";
      state.conditional=p.get("conditional")!=="0";$("show-conditional").checked=state.conditional;
      state.status=["rendered","python","none"].includes(p.get("status"))?p.get("status"):"all";$("workspace-status").value=state.status;
      state.direction=["in","out"].includes(p.get("direction"))?p.get("direction"):"all";
      state.frame=clamp(Math.round(Number(p.get("frame")))||0,0,data.river.frames.length-1);state.cell=clamp(Math.round(Number(p.get("cell")))||0,0,data.river.cells.length-1);
      [state.first,state.last]=model.range(Number(p.get("first"))||0,p.has("last")?Number(p.get("last")):data.river.cells.length-1,data.river.cells.length);
      [state.timeFirst,state.timeLast]=model.range(Number(p.get("timeFirst"))||0,p.has("timeLast")?Number(p.get("timeLast")):data.river.frames.length-1,data.river.frames.length);
      if(p.has("t")&&data.river.frames.length)state.frame=model.nearestIndex(data.river.frames.map(f=>f.t),Number(p.get("t")));
      if(state.first===state.last){state.first=0;state.last=data.river.cells.length-1;}if(state.timeFirst===state.timeLast){state.timeFirst=0;state.timeLast=data.river.frames.length-1;}
      if(renderedFilters!==[state.research,state.conditional,state.status].join(":"))renderScene(false);
      if(nodes.has(raw))selectProcess(raw,false);
      else if(nodes.has(p.get("process")))selectProcess(p.get("process"),false);
      else if(domains.has(p.get("domain")||(!p.has("view")?options.domain:null)))selectDomain(p.get("domain")||options.domain,false);
      else ecosystem(false);
      state.network=!state.domain&&!state.process&&p.get("network")==="1";if(!restored)netMix=state.network?1:0;header();
      state.processView=p.get("quantity");state.processEntity=p.get("entity");
      if(metrics().includes(p.get("metric")))state.metric=p.get("metric");if(["data","science","exchanges"].includes(p.get("tab")))state.tab=p.get("tab");
      setMode(p.get("view")==="landscape"?"landscape":"systems",false);renderAnalysis();fit(!restored);restored=true;
    }
    function bind() {
      $("mode-systems").addEventListener("click",()=>{setMode("systems");});$("mode-landscape").addEventListener("click",()=>setMode("landscape"));
      $("network-toggle").addEventListener("click",()=>setNetwork(!state.network));
      $("zoom-in").addEventListener("click",()=>zoom(1.4));$("zoom-out").addEventListener("click",()=>zoom(1/1.4));$("fit-map").addEventListener("click",()=>fit());
      $("arrange-nodes").addEventListener("click",()=>{state.arrange=!state.arrange;$("arrange-nodes").setAttribute("aria-pressed",String(state.arrange));document.body.classList.toggle("workspace-arrange",state.arrange);announce(state.arrange?"Arrange nodes. Drag any sphere or process; connections follow.":"Pan mode. Drag the background to move the diagram.");});
      $("reset-layout").addEventListener("click",()=>{renderScene();announce("Default diagram layout restored.");});
      $("fullscreen").addEventListener("click",async()=>{try{if(document.fullscreenElement)await document.exitFullscreen();else await $("explorer").requestFullscreen();}catch{announce("Full screen is unavailable in this browser.");}});
      if(!document.fullscreenEnabled)$("fullscreen").hidden=true;
      $("open-analysis").addEventListener("click",()=>{state.panel=true;renderAnalysis();fit();});
      $("close-analysis").addEventListener("click",()=>selectDomain(state.domain));
      $("expand-analysis").addEventListener("click",()=>zoom(1.3));
      document.querySelectorAll("[data-analysis-tab]").forEach(b=>b.addEventListener("click",()=>{state.tab=b.dataset.analysisTab;renderAnalysis();writeURL();}));
      $("show-research").addEventListener("change",event=>{state.research=event.target.checked;if(state.process&&nodes.get(state.process).implementation==="research"&&!state.research)state.process=null;renderScene();renderAnalysis();writeURL();});
      $("show-conditional").addEventListener("change",event=>{state.conditional=event.target.checked;exchange=null;renderScene();renderAnalysis();writeURL();});
      $("show-status").addEventListener("change",event=>document.body.classList.toggle("workspace-status-off",!event.target.checked));
      $("workspace-status").addEventListener("change",event=>{state.status=event.target.value;if(state.status==="none"){state.research=true;$("show-research").checked=true;}renderScene();renderAnalysis();writeURL();});
      $("process-search").addEventListener("input",event=>{const query=event.target.value.trim().toLowerCase(),results=$("search-results");results.replaceChildren();results.hidden=!query;if(!query)return;
        const matches=data.nodes.filter(n=>`${n.label} ${n.summary} ${domains.get(n.domain).label}`.toLowerCase().includes(query));matches.forEach(n=>{const b=processLink(n,`${domains.get(n.domain).label} · ${type(n)}`);b.addEventListener("click",()=>{results.hidden=true;event.target.value="";});results.append(b);});if(!matches.length)results.append(html("p","","No matching process."));});
      const topline=$("workspace-topline"),searchToggle=$("search-toggle"),searchInput=$("process-search");
      const openSearch=open=>{topline.classList.toggle("search-open",open);searchToggle.setAttribute("aria-expanded",String(open));if(open)searchInput.focus();else{$("search-results").hidden=true;searchInput.value="";searchInput.blur();}};
      searchToggle.addEventListener("click",()=>openSearch(!topline.classList.contains("search-open")));
      searchInput.addEventListener("keydown",event=>{if(event.key==="Escape")openSearch(false);});
      $("search-results").addEventListener("click",()=>topline.classList.remove("search-open"));
      document.addEventListener("pointerdown",event=>{if(!event.target.closest(".workspace-search,#search-toggle")){$("search-results").hidden=true;if(topline.classList.contains("search-open"))openSearch(false);}});
      map.addEventListener("wheel",event=>{event.preventDefault();$("tooltip").hidden=true;const r=map.getBoundingClientRect();zoom(Math.exp(clamp(-event.deltaY*.002,-.5,.5)),event.clientX-r.left,event.clientY-r.top);},{passive:false});
      map.addEventListener("pointerdown",event=>{if(event.button!==0&&event.pointerType==="mouse")return;target={...camera};pointers.set(event.pointerId,{x:event.clientX,y:event.clientY});skipClick=false;dragLength=0;map.classList.add("dragging");});
      map.addEventListener("pointermove",event=>{if(!pointers.has(event.pointerId))return;const prev=pointers.get(event.pointerId),dx=event.clientX-prev.x,dy=event.clientY-prev.y;dragLength+=Math.hypot(dx,dy);if(dragLength>5){skipClick=true;map.setPointerCapture(event.pointerId);}
        if(pointers.size===2){const other=[...pointers.entries()].find(([id])=>id!==event.pointerId)[1],before=Math.hypot(prev.x-other.x,prev.y-other.y),after=Math.hypot(event.clientX-other.x,event.clientY-other.y),r=map.getBoundingClientRect();if(before>5)zoom(after/before,(prev.x+other.x)/2-r.left,(prev.y+other.y)/2-r.top);target.x+=dx/2;target.y+=dy/2;}else{target.x+=dx;target.y+=dy;}pointers.set(event.pointerId,{x:event.clientX,y:event.clientY});camera={...target};semanticDirty=true;$("tooltip").hidden=true;});
      ["pointerup","pointercancel"].forEach(name=>map.addEventListener(name,event=>{pointers.delete(event.pointerId);if(!pointers.size)map.classList.remove("dragging");}));
      map.addEventListener("dblclick",event=>{if(event.target===map||event.target.tagName==="rect"){const r=map.getBoundingClientRect();zoom(1.7,event.clientX-r.left,event.clientY-r.top);}});
      map.addEventListener("keydown",event=>{if(!["+","=","-","0","ArrowUp","ArrowDown","ArrowLeft","ArrowRight"].includes(event.key))return;event.preventDefault();if(["+","="].includes(event.key))zoom(1.4);if(event.key==="-")zoom(1/1.4);if(event.key==="0")fit();if(event.key==="ArrowUp")target.y+=60;if(event.key==="ArrowDown")target.y-=60;if(event.key==="ArrowLeft")target.x+=60;if(event.key==="ArrowRight")target.x-=60;});
      document.addEventListener("keydown",event=>{if(event.key!=="Escape"||!active||document.body.dataset.analysisActive==="true"||state.mode!=="systems"||event.target.matches("input,select")||document.querySelector("dialog[open]"))return;$("search-results").hidden=true;if(state.network){setNetwork(false);return;}if(state.expanded){state.expanded=false;renderAnalysis();}else parent();});
      const resize=$("analysis-resize"),resizeWidth=value=>{panelWidth=clamp(value,320,Math.min(650,width*.65));document.body.style.setProperty("--analysis-width",`${panelWidth}px`);resize.setAttribute("aria-valuenow",String(Math.round(panelWidth)));fit(true);};
      resize.addEventListener("pointerdown",event=>{resize.setPointerCapture(event.pointerId);resize.dataset.dragging="true";});resize.addEventListener("pointermove",event=>{if(resize.dataset.dragging!=="true")return;resizeWidth(width-event.clientX+map.getBoundingClientRect().left-20);});["pointerup","pointercancel"].forEach(name=>resize.addEventListener(name,()=>{resize.dataset.dragging="false";}));resize.addEventListener("keydown",event=>{if(!["ArrowLeft","ArrowRight"].includes(event.key))return;event.preventDefault();resizeWidth(panelWidth+(event.key==="ArrowLeft"?25:-25));});
      let sized=false;
      new ResizeObserver(entries=>{const r=entries[0].contentRect;if(r.width<=0||r.height<=0)return;if(Math.abs(width-r.width)<1&&Math.abs(height-r.height)<1)return;width=r.width;height=r.height;renderScene(false);fit(!sized);sized=true;}).observe(map);
      window.addEventListener("hashchange",restore);
    }
    data.domains.forEach(d=>{const b=html("button","",d.label);b.style.setProperty("--domain",d.color);b.dataset.domain=d.id;b.setAttribute("aria-pressed","false");b.addEventListener("click",()=>selectDomain(d.id));$("workspace-domains").append(b);});
    window.YSExplore={openProcess:selectProcess,openDomain:selectDomain,setMode};
    document.addEventListener("ys:inspect",event=>selectProcess(event.detail));
    $("workspace-topline").hidden=!active;
    if(!active)return;
    document.body.classList.add("continuous-explorer");
    panel.addEventListener("pointerdown",event=>{
      if(event.pointerType==="touch"){
        target={...camera};pointers.set(event.pointerId,{x:event.clientX,y:event.clientY,scroll:!event.target.closest("input,select,button,a,.workspace-chart")});
      }
      event.stopPropagation();
    });
    panel.addEventListener("pointermove",event=>{
      if(pointers.size>=2)return;
      const previous=pointers.get(event.pointerId);
      if(previous?.scroll)$("analysis-content").scrollTop-=event.clientY-previous.y;
      if(previous)pointers.set(event.pointerId,{...previous,x:event.clientX,y:event.clientY});
      event.stopPropagation();
    });
    panel.addEventListener("click",event=>event.stopPropagation());
    panel.addEventListener("wheel",event=>{if(!event.ctrlKey)event.stopPropagation();},{passive:true});
    panel.addEventListener("keydown",event=>{if(event.key!=="Escape")event.stopPropagation();});
    width=map.parentElement.clientWidth||innerWidth;height=map.parentElement.clientHeight||600;renderScene(false);bind();restore();
    document.fonts?.ready.then(()=>{cards.forEach(c=>{c.nameBox=null;});semanticDirty=true;});
    let last=0;
    function draw(now){requestAnimationFrame(draw);if(document.hidden||document.body.dataset.analysisActive==="true"||now-last<16||state.mode!=="systems")return;
      const elapsed=Math.min(64,now-last||16);last=now;
      const netGoal=state.network?1:0;if(netMix!==netGoal){netMix=reduced||Math.abs(netGoal-netMix)<.002?netGoal:netMix+(netGoal-netMix)*(1-Math.exp(-elapsed/160));semanticDirty=true;}
      const moving=Math.abs(camera.x-target.x)+Math.abs(camera.y-target.y)+Math.abs(camera.k-target.k)>1e-5;
      if(moving||semanticDirty){
        const mix=reduced?1:1-Math.exp(-elapsed/160);["x","y","k"].forEach(k=>camera[k]+=(target[k]-camera[k])*mix);
        world.setAttribute("transform",`translate(${camera.x},${camera.y}) scale(${camera.k})`);$("zoom-level").value=`${Math.round(camera.k/base*100)}%`;updateSemantic();
      }
      if(playing&&state.panel&&state.tab==="data"&&["temperature","history","field"].includes(state.metric)){if(!lastTick)lastTick=now;if(now-lastTick>30){playElapsed+=(now-lastTick)/1000*180;lastTick=now;state.frame=window.YSData.frameAtElapsed(data.river.frames.map(f=>f.t),playElapsed);updatePlot();if(state.frame===data.river.frames.length-1){playing=false;const b=$("workspace-play");if(b){b.textContent="▶";b.setAttribute("aria-label","Play saved model frames");}writeURL();}}}}
    requestAnimationFrame(draw);
  }
};
