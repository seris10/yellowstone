import assert from "node:assert/strict";
import test from "node:test";
import {readFileSync} from "node:fs";
import vm from "node:vm";

const source = readFileSync(new URL("./src/analysis.js",import.meta.url),"utf8");
const snapshot = {snapshot:"fixture",nodes:[{id:"heat"}],domains:[{id:"thermal"},{id:"land"}],datasets:{river:{url:"/river.json"},systems:[
  {id:"thermal",title:"Geothermal systems",color:"#efa774"},{id:"land",title:"Terrestrial ecology",color:"#8ed5aa"}]}};
const flush = async () => { await Promise.resolve(); await Promise.resolve(); };
function element(tag = "div") {
  return {tag,hidden:false,textContent:"",className:"",href:"",children:[],dataset:{},attributes:{},
    style:{values:{},setProperty(name,value){this.values[name]=value;}},
    replaceChildren(...children){this.children=children;},append(...children){this.children.push(...children);},
    setAttribute(name,value){this.attributes[name]=value;}};
}
function setup({embedded = true,hash = "#view=systems",data = structuredClone(snapshot),initSystem,initRiver} = {}) {
  const ids = ["analysis-view","analysis-system-rail","workbench-view","systems-workbench-view","system-view","overview-view","view-description"];
  const elements = Object.fromEntries(ids.map(id=>[id,element()])), listeners = [], calls = [], errors = [];
  const document = {body:{dataset:{}},title:"Yellowstone",getElementById:id=>elements[id],createElement:element};
  const location = {origin:"https://example.test",pathname:embedded?"/dashboard/":"/dashboard/analyze/",hash};
  const window = {addEventListener(name,handler){listeners.push({name,handler});},YSSystems:{
    destroy(){calls.push({action:"destroy",kind:"system"});},
    init(s,options){calls.push({action:"init",kind:"system",options});return initSystem?.(s,options);}},YSWorkbench:{
    destroy(){calls.push({action:"destroy",kind:"river"});},
    init(s){calls.push({action:"init",kind:"river"});return initRiver?.(s);}}};
  vm.runInNewContext(source,{window,document,location,URL,URLSearchParams,console:{error:(...args)=>errors.push(args)}});
  window.YSAnalysis.init(data,{embedded});
  return {window,document,location,elements,calls,errors,listeners,
    async navigate(next){const oldURL=location.origin+location.pathname+location.hash;location.hash=next;await Promise.all(listeners.filter(l=>l.name==="hashchange").map(l=>l.handler({oldURL})));},
    fire(next){location.hash=next;return listeners.filter(l=>l.name==="hashchange").map(l=>l.handler());},
    rail:()=>elements["analysis-system-rail"].children,
    inits:()=>calls.filter(c=>c.action==="init")};
}

test("embedded explorer enters analysis in place and preserves the return context", async () => {
  const h = setup({hash:"#view=systems&process=heat"}); await flush();
  assert.equal(h.elements["analysis-view"].hidden,true);
  assert.equal(h.document.body.dataset.analysisActive,"false");
  assert.equal(h.inits().length,0);
  await h.navigate("#view=analysis&system=thermal");
  assert.equal(h.elements["analysis-view"].hidden,false);
  assert.equal(h.elements["system-view"].hidden,true);
  assert.equal(h.elements["overview-view"].hidden,true);
  assert.equal(h.document.body.dataset.analysisActive,"true");
  assert.equal(h.rail()[0].href,"/dashboard/#view=systems&process=heat");
  assert.equal(h.inits()[0].options.id,"thermal");
  await h.navigate("#view=systems&process=heat");
  assert.equal(h.elements["analysis-view"].hidden,true);
  assert.equal(h.elements["workbench-view"].hidden,true);
  assert.equal(h.elements["systems-workbench-view"].hidden,true);
});

test("standalone analysis chooses the available thermal workbench and honors legacy river selections", async () => {
  const h = setup({embedded:false,hash:""}); await flush();
  assert.equal(h.inits()[0].options.id,"thermal");
  assert.equal(h.document.title,"Geothermal systems | Yellowstone");
  assert.equal(h.rail().some(a=>a.className==="analysis-return"),false);
  assert.equal(h.rail().find(a=>a.dataset.system==="land").href,"/dashboard/analyze/#system=land");
  const river = setup({embedded:false,hash:"#t=600&cell=3"}); await flush();
  assert.equal(river.inits()[0].kind,"river");
});

test("catalog absence or unknown system routes never substitute unrelated system data", async () => {
  const empty = {...structuredClone(snapshot),datasets:{}};
  const h = setup({embedded:false,hash:"#system=not-published",data:empty}); await flush();
  assert.equal(h.inits().length,1);assert.equal(h.inits()[0].options.id,"unavailable");
  assert.equal(h.elements["systems-workbench-view"].hidden,false);
  assert.equal(h.elements["workbench-view"].hidden,true);
  assert.equal(h.document.title,"System analysis | Yellowstone");
  const fallback = setup({embedded:false,hash:"",data:empty}); await flush();
  assert.equal(fallback.inits()[0].kind,"river");
});

test("same system selection avoids duplicate mounts while a new variable or entity mounts once", async () => {
  const h = setup({hash:"#view=analysis&system=land&variable=biomass&entity=patch-a"}); await flush();
  await h.navigate("#view=analysis&system=land&variable=biomass&entity=patch-a");
  assert.equal(h.inits().length,1);
  await h.navigate("#view=analysis&system=land&variable=moisture&entity=patch-a");
  assert.equal(h.inits().length,2);
  await h.navigate("#view=analysis&system=land&variable=moisture&entity=patch-b");
  assert.equal(h.inits().length,3);
  assert.deepEqual({...h.inits()[2].options},{id:"land",variable:"moisture",entity:"patch-b"});
});

test("river deep-link time and cell changes apply instead of reusing stale selection", async () => {
  const h = setup({hash:"#view=analysis&system=river&t=600&cell=10"}); await flush();
  assert.equal(h.inits().length,1);
  await h.navigate("#view=analysis&system=river&t=1200&cell=20");
  assert.equal(h.inits().length,2,"A changed native river selection must reach its workbench.");
  await h.navigate("#view=analysis&system=river&t=1200&cell=20");
  assert.equal(h.inits().length,2,"The identical native selection must not duplicate the mount.");
  await h.navigate("#view=analysis&system=river&t=1200&cell=21");
  assert.equal(h.inits().length,3);
});

test("analysis return preserves a matching explorer's complete filters, ranges, and selection", async () => {
  const original = "view=systems&domain=land&process=heat&research=1&conditional=0&status=python&scale=local&first=4&last=55&timeFirst=2&timeLast=20&frame=8&cell=12&tab=science";
  const h = setup({hash:"#"+original}); await flush();
  await h.navigate("#view=analysis&system=thermal&from=heat");
  assert.equal(h.rail()[0].href,"/dashboard/#"+original,"The known explorer context must take precedence over a reduced from breadcrumb.");
  await h.navigate("#view=analysis&system=land");
  assert.equal(h.rail()[0].href,"/dashboard/#"+original,"Exploring another system must retain the same return context.");
});

test("analysis return retains explorer edits written without a hashchange event", async () => {
  const h = setup(); await flush();
  const current = "view=systems&domain=thermal&process=heat&tab=science&frame=120&cell=275&conditional=0";
  h.location.hash = "#" + current;
  await h.navigate("#view=analysis&system=thermal&from=heat");
  assert.equal(h.rail()[0].href,"/dashboard/#"+current);
  await h.navigate("#view=analysis&system=land");
  assert.equal(h.rail()[0].href,"/dashboard/#"+current);
});

test("process and domain origins become valid explorer breadcrumbs and rail links retain analysis mode", async () => {
  const h = setup({hash:"#view=analysis&system=thermal&from=heat"}); await flush();
  assert.equal(h.rail()[0].href,"/dashboard/#view=systems&process=heat");
  assert.equal(h.rail().find(a=>a.dataset.system==="land").href,"/dashboard/#view=analysis&system=land");
  assert.equal(h.rail().find(a=>a.dataset.system==="thermal").attributes["aria-current"],"location");
  assert.equal(h.rail().find(a=>a.dataset.system==="thermal").style.values["--system-color"],"#efa774");
  await h.navigate("#view=analysis&system=land&from=land");
  assert.equal(h.rail()[0].href,"/dashboard/#view=systems&domain=land");
  await h.navigate("#view=analysis&system=land&from=missing");
  assert.equal(h.rail()[0].href,"/dashboard/#view=systems");
});

test("stale asynchronous system completion cannot hide the newer system in its shared host", async () => {
  const pending = new Map();
  const h = setup({hash:"#view=analysis&system=thermal",initSystem:(_,options)=>new Promise(resolve=>pending.set(options.id,resolve))});
  await flush();
  const newer = h.fire("#view=analysis&system=land");await flush();
  assert.equal(h.elements["systems-workbench-view"].hidden,false);
  pending.get("thermal")();await flush();
  assert.equal(h.elements["systems-workbench-view"].hidden,false,"The stale thermal request must leave the current land host visible.");
  pending.get("land")();await Promise.all(newer);
});

test("stale river completion after returning to the explorer stays hidden", async () => {
  let resolveRiver;
  const h = setup({hash:"#view=analysis&system=river",initRiver:()=>new Promise(resolve=>{resolveRiver=resolve;})});await flush();
  await h.navigate("#view=systems&process=heat");
  resolveRiver();await flush();
  assert.equal(h.elements["analysis-view"].hidden,true);
  assert.equal(h.elements["workbench-view"].hidden,true);
});

test("failed current dataset reports a bounded unavailable state in the active host", async () => {
  const h = setup({hash:"#view=analysis&system=land",initSystem:()=>Promise.reject(Error("fixture failure"))});await flush();
  assert.equal(h.elements["systems-workbench-view"].children[0].textContent,"Analysis unavailable");
  assert.equal(h.elements["systems-workbench-view"].children[1].textContent.includes("fixture failure"),false);
  assert.equal(h.errors.length,1);
});
