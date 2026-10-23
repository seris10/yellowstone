"use strict";

((root) => {
  const clamp = (value, low, high) => Math.max(low, Math.min(high, value));
  function fade(value, start, end) {
    const t = clamp((value - start) / (end - start), 0, 1);
    return t * t * (3 - 2 * t);
  }
  function pack(count, radius = 94) {
    if (!count) return [];
    if (count === 1) return [{x:0,y:0,r:radius*.64}];
    const center = count > 6, ring = count - Number(center), sine = Math.sin(Math.PI / ring);
    const r = Math.min(radius*.38, radius*sine/(1+sine)*.87), orbit = radius-r;
    return Array.from({length:count},(_,i)=>{
      if (center && i === 0) return {x:0,y:0,r};
      const angle = (i-Number(center))*Math.PI*2/ring-Math.PI/2;
      return {x:Math.cos(angle)*orbit,y:Math.sin(angle)*orbit,r};
    });
  }
  function zoomAt(camera, factor, point, min, max) {
    const k=clamp(camera.k*factor,min,max),ratio=k/camera.k;
    return {k,x:point.x-(point.x-camera.x)*ratio,y:point.y-(point.y-camera.y)*ratio};
  }
  function frameCircle(circle, radius, center) {
    const k=radius/circle.r;
    return {k,x:center.x-circle.x*k,y:center.y-circle.y*k};
  }
  const processRoles = [
    {id:"heat",label:"Heat",color:"#f2a46e",nodes:["surface","plume","pool","ground","outflow_cooling","transport","hyporheic"]},
    {id:"water",label:"Water",color:"#77b9e6",nodes:["snow","et","snow_assimilation","mixing","boundary","tributaries","outlet","dynamic_flow","winter_ice","measured_bathymetry","canopy_interception"]},
    {id:"chemistry",label:"Chemistry",color:"#bd9bea",nodes:["solutes","oxygen","reactive_chemistry"]},
    {id:"light",label:"Light",color:"#e6cb78",nodes:["shading"]},
    {id:"producers",label:"Vegetation & microbes",color:"#8ed5aa",nodes:["vegetation","canopy","periphyton","mat"]},
    {id:"animals",label:"Animals",color:"#e5a6c8",nodes:["grazers","mammals","insects","fish","predation","aerial","outflow","taxa"]},
    {id:"weather",label:"Air & weather",color:"#8dcaca",nodes:["weather","steam"]}
  ];
  function processRole(id) {return processRoles.find(role=>role.nodes.includes(id));}
  function mixColor(first, second, fraction) {
    const amount=clamp(fraction,0,1);
    return "#"+[1,3,5].map(i=>{
      const a=parseInt(first.slice(i,i+2),16),b=parseInt(second.slice(i,i+2),16);
      return Math.round(a+(b-a)*amount).toString(16).padStart(2,"0");
    }).join("");
  }
  function visible(data, state) {
    const nodes = data.nodes.filter(node => (state.research || node.implementation !== "research") &&
      (state.status === "all" || node.display === state.status || node.id === state.process));
    const ids = new Set(nodes.map(node => node.id));
    const edges = data.edges.filter(edge => ids.has(edge.from) && ids.has(edge.to) &&
      (state.research || !edge.research) && (state.conditional || !edge.condition));
    return { nodes, edges };
  }
  function relationships(data, id, state) {
    const { edges } = visible(data, state);
    return edges.filter(edge => edge.from === id || edge.to === id);
  }
  function neighborhood(data, id, state) {
    const edges = relationships(data, id, state).filter(edge => state.direction === "all" ||
      edge.bidirectional || (state.direction === "in" ? edge.to === id : edge.from === id));
    const incoming = new Set(), outgoing = new Set();
    edges.forEach(edge => {
      if (edge.to === id) incoming.add(edge.from);
      if (edge.from === id) outgoing.add(edge.to);
      if (edge.bidirectional) { incoming.add(edge.from === id ? edge.to : edge.from); outgoing.add(edge.from === id ? edge.to : edge.from); }
    });
    return { edges, incoming: [...incoming], outgoing: [...outgoing] };
  }
  function range(first, last, count) {
    const a = clamp(Math.round(Number.isFinite(first) ? first : 0), 0, count - 1), b = clamp(Math.round(Number.isFinite(last) ? last : count - 1), 0, count - 1);
    return [Math.min(a, b), Math.max(a, b)];
  }
  function nearestIndex(values, value) {
    if (!values.length || !Number.isFinite(value)) return -1;
    let low = 0, high = values.length - 1;
    while (low < high) { const mid = Math.floor((low + high) / 2); if (values[mid] < value) low = mid + 1; else high = mid; }
    return low > 0 && Math.abs(values[low - 1] - value) <= Math.abs(values[low] - value) ? low - 1 : low;
  }
  function series(data, metric, frame, cell) {
    if (!available(data, metric)) return null;
    const ecology = data.ecology, analytics = data.analytics;
    const spatial = (values, unit, label) => ({ label, unit, xUnit: "km downstream", type: "line", spatial: true,
      points: values.map((y, index) => ({ x: data.river.cells[index].s / 1000, y, index })) });
    if (metric === "temperature") return spatial(data.river.frames[frame].temperature, "°C", "River temperature");
    if (metric === "history") return { label: "Temperature through time", unit: "°C", xUnit: "minutes elapsed", type: "line", temporal: true,
      points: data.river.frames.map((row, index) => ({ x: row.t / 60, y: row.temperature[cell], index })) };
    if (metric === "oxygen") return spatial(ecology.oxygen, "mg/L", "Dissolved oxygen");
    if (metric === "periphyton") return spatial(ecology.periphyton, "mg C/m²", "Periphyton biomass");
    if (metric === "shading") return spatial(analytics.shading, "fraction", "Shortwave transmission");
    if (["air", "wind"].includes(metric)) return { label: metric === "air" ? "Air temperature" : "Wind speed", unit: metric === "air" ? "°C" : "m/s",
      xUnit: "seconds elapsed", type: "line", points: analytics.weather.trace.map((row,index) => ({ x: row.t, y: row[metric], index })) };
    if (["biomass", "moisture", "snow"].includes(metric)) return { type: "bars", label: { biomass:"Relative vegetation biomass",moisture:"Patch soil moisture",snow:"Patch snow storage" }[metric],
      unit: metric === "snow" ? "mm water equivalent" : "%", points: (metric === "snow" ? ecology.snow : ecology.patches).map((p,index) => ({
        label: p.label, y: metric === "snow" ? p.snow_mm : metric === "biomass" ? p.biomass / p.capacity * 100 : p.moisture * 100, index })) };
    if (metric === "water") return {type:"bars",label:"Snow storage by patch",unit:"mm water equivalent",points:ecology.snow.map((p,index)=>({label:p.label,y:p.snow_mm,index}))};
    if (metric === "water-sum") {
      const w = ecology.water;
      return { type: "bars", label: "Summed patch depth accounting diagnostic", unit: "mm summed across patches", points: [
        ["Initial storage",w.initial_mm],["Rain",w.rain_mm],["Snow input",w.accum_mm],["Final storage",w.final_mm],
        ["Evapotranspiration",w.et_mm],["Surface runoff",w.runoff_mm],["Subsurface drainage",w.drainage_mm],["Solid snow export",w.snow_export_mm]
      ].map(([label,y],index) => ({ label,y,index })) };
    }
    if (metric === "pools") return { type: "bars", label: "Pool temperatures", unit: "°C", points: analytics.pools.flatMap((p,index) => [
      {label:p.label+" · center"+(p.center_basis==="measured_literature"?" (published sample)":" (authored)"),y:p.center,index:index*2},{label:p.label+" · edge (authored)",y:p.edge,index:index*2+1}]) };
    return null;
  }
  function available(data, metric) {
    const vector = values => Array.isArray(values) && data.river && values.length === data.river.cells.length;
    if (["temperature","history","field"].includes(metric)) return !!data.river?.frames.length && !!data.river?.cells.length;
    if (["oxygen","periphyton"].includes(metric)) return !!vector(data.ecology?.[metric]);
    if (metric === "shading") return !!vector(data.analytics?.shading);
    if (["air","wind"].includes(metric)) return !!data.analytics?.weather?.trace?.length;
    if (["biomass","moisture"].includes(metric)) return !!data.ecology?.patches?.length;
    if (["snow","water"].includes(metric)) return !!data.ecology?.snow?.length;
    if (metric === "water-sum") return !!data.ecology?.water;
    if (metric === "pools") return !!data.analytics?.pools?.length;
    if (metric === "heat") return !!data.coverage?.heat;
    return false;
  }
  const contextual = new Set(["grazers","mammals","taxa","hyporheic","mixing","canopy"]);
  function binding(process, metric) {
    if (!process) return {role:"Dataset",note:"Recorded support belongs to the selected dataset."};
    if (process === "fish") return {role:"Driver",note:"River temperature and oxygen support habitat calculations. These plots contain no fish abundance or survival measurements."};
    if (process === "steam") return {role:"Driver",note:"Authored ambient weather supplies the microclimate calculation. This trace contains no modeled plume temperature response."};
    if (["outflow_cooling","outflow","pool"].includes(process) && metric === "pools") return {role:"Authored parameter",note:"Pool edge temperatures are prescribed scenario values; center temperatures are published point samples where labeled and authored otherwise. No cooling or food-web trajectory is plotted."};
    if (process === "boundary" || process === "tributaries") return {role:"Context",note:"These are downstream river outputs. The selected boundary supplies prescribed forcing."};
    if (contextual.has(process)) return {role:"Context",note:"This diagnostic describes a connected process. It is not a direct output of the selected process."};
    if (["oxygen","periphyton","shading","heat","water-sum"].includes(metric)) return {role:metric === "heat"?"Authored spatial field":"Diagnostic",note:"Recorded spatial support and integration increments are separate from the river playback clock."};
    if (process === "et") return {role:"Context",note:"Snow and soil accounting records bucket evapotranspiration. Reference evapotranspiration is a separate diagnostic."};
    return {role:"Direct output",note:"Saved values for the represented model process; field validation remains incomplete."};
  }
  const api = { fade, pack, zoomAt, frameCircle, processRole, mixColor, visible, relationships, neighborhood, range, nearestIndex, series, available, binding };
  if (typeof module !== "undefined") module.exports = api;
  else root.YSModel = api;
})(typeof window === "undefined" ? {} : window);
