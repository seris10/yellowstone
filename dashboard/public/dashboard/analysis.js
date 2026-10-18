"use strict";

window.YSAnalysis = {
  init(snapshot, {embedded = false} = {}) {
    const $ = id => document.getElementById(id), host = $("analysis-view"), rail = $("analysis-system-rail");
    const systems = snapshot.datasets?.systems || [], available = new Set(["river", ...systems.map(s=>s.id)]);
    let generation = 0, current = "", selection = "", returnHash = "view=systems";
    function address(id) {
      const p = new URLSearchParams();
      if (embedded) p.set("view","analysis");
      p.set("system",id);
      return `${location.pathname}#${p}`;
    }
    function buildRail(id) {
      rail.replaceChildren();
      if (embedded) {
        const back = document.createElement("a"); back.href = `${location.pathname}#${returnHash}`;
        back.textContent = "← Explorer"; back.className = "analysis-return"; rail.append(back);
      }
      const items = [{id:"river",title:"River heat",color:"#77b9e6"},...systems];
      items.forEach(item=>{
        const link=document.createElement("a");link.href=address(item.id);link.textContent=item.title;
        link.style.setProperty("--system-color",item.color||"#8dcaca");link.dataset.system=item.id;
        if(item.id===id)link.setAttribute("aria-current","location");rail.append(link);
      });
    }
    async function route(event) {
      const p = new URLSearchParams(location.hash.slice(1)), active = !embedded || p.get("view") === "analysis";
      if (embedded && active && event?.oldURL) {
        const previous = new URL(event.oldURL);
        if (previous.origin === location.origin && previous.pathname === location.pathname &&
            new URLSearchParams(previous.hash.slice(1)).get("view") !== "analysis") {
          returnHash = previous.hash.slice(1) || "view=systems";
        }
      }
      document.body.dataset.analysisActive = String(active);host.hidden = !active;
      if (!active) {
        returnHash = location.hash.slice(1) || "view=systems";
        generation++; current="";selection="";
        window.YSSystems?.destroy();window.YSWorkbench?.destroy();
        $("workbench-view").hidden=true;$("systems-workbench-view").hidden=true;
        return;
      }
      if (embedded) {
        $("system-view").hidden=true;$("overview-view").hidden=true;
        if(p.has("from")){
          const previous=new URLSearchParams(returnHash), from=p.get("from");
          if(previous.get("process")!==from && previous.get("domain")!==from){
            const fallback=new URLSearchParams({view:"systems"});
            if(snapshot.nodes.some(n=>n.id===from))fallback.set("process",from);
            else if(snapshot.domains.some(d=>d.id===from))fallback.set("domain",from);
            returnHash=fallback.toString();
          }
        }
      }
      const requested=p.get("system") || (p.has("t")||p.has("cell")?"river":systems.some(s=>s.id==="thermal")?"thermal":"river");
      const id=available.has(requested)?requested:"unavailable", nextSelection=[p.get("variable"),p.get("entity"),p.get("t"),p.get("cell")].join(":");
      buildRail(id);$("view-description").textContent="EARTH SYSTEMS / DATA ANALYSIS";
      document.title=`${id==="river"?"River heat":systems.find(s=>s.id===id)?.title||"System analysis"} | Yellowstone`;
      if(current===id && selection===nextSelection)return;
      generation++;const ticket=generation;current=id;selection=nextSelection;
      window.YSSystems?.destroy();window.YSWorkbench?.destroy();
      $("workbench-view").hidden=id!=="river";$("systems-workbench-view").hidden=id==="river";
      try {
        if(id==="river")await window.YSWorkbench.init(snapshot);
        else await window.YSSystems.init(snapshot,{id,variable:p.get("variable"),entity:p.get("entity")});
        if(ticket!==generation){
          $("workbench-view").hidden=current!=="river";
          $("systems-workbench-view").hidden=!current||current==="river";
        }
      } catch(error) {
        if(ticket!==generation)return;
        const target=$(id==="river"?"workbench-view":"systems-workbench-view");target.replaceChildren();
        const title=document.createElement("h1"),text=document.createElement("p");title.textContent="Analysis unavailable";
        text.textContent="This dataset could not be loaded. Select another system or return to the explorer.";target.append(title,text);
        console.error("Scientific analysis unavailable",error);
      }
    }
    window.addEventListener("hashchange",route);
    route();
  }
};
