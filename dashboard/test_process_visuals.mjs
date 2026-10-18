import {createRequire} from "node:module";
import assert from "node:assert/strict";
import test from "node:test";
import {createHash} from "node:crypto";
import {readFileSync} from "node:fs";
import vm from "node:vm";

const require=createRequire(import.meta.url),P=require("./src/process-visuals.js");
const hashBytes=bytes=>createHash("sha256").update(Buffer.from(bytes)).digest("hex");
const source={label:"Checked fixture output",sha256:"a".repeat(64)};
const base=(id,snapshot)=>({schema:"yellowstone.process-visual.v1",id,snapshot,sources:[source]});
function steam(snapshot="steam-fixture") {
  return {...base("steam",snapshot),report:{upwind_air_c:20,downwind_air_c:21,upwind_rh:.4,downwind_rh:.5,
    fetch_length_m:250,internal_boundary_layer_m:9,latent_flux_w_m2:110,sensible_flux_w_m2:38},
    components:[{id:"pool",label:"Pools",area_m2:100,latent_w_m2:200,sensible_w_m2:20},
      {id:"outflow",label:"Outflow",area_m2:900,latent_w_m2:100,sensible_w_m2:40}]};
}
function bed(snapshot="bed-fixture") {
  return {...base("hyporheic",snapshot),times:[0,600],
    cells:[{id:"upstream",position_m:10,x:1,z:3},{id:"downstream",position_m:50,x:4,z:6}],
    water:[[0,null],[22,18]],bed:[[0,19],[20,null]]};
}
function mat(snapshot="mat-fixture") {
  return {...base("mat",snapshot),grid:{nx:2,nz:2,cell_m:1,origin_xz_m:[-1,-1],row_order:"z_increasing"},
    values:[0,1,null,1],legend:[{class_id:0,label:"Dry sinter",rgb:[184,168,138],count:1,area_m2:1},
      {class_id:1,label:"Mat",rgb:[95,110,60],count:2,area_m2:2}]};
}
function packaged(data) {
  const bytes=Buffer.from(JSON.stringify(data)),descriptor={id:data.id,url:`/dashboard/data/${data.snapshot}.json`,sha256:hashBytes(bytes),bytes:bytes.byteLength};
  return {bytes,descriptor,snapshot:{snapshot:data.snapshot,datasets:{process_visuals:[descriptor]}}};
}
const response=bytes=>({ok:true,arrayBuffer:async()=>Uint8Array.from(bytes).buffer});

test("visual validation binds both scenario and process identity to checked source hashes",()=>{
  for(const data of [steam(),mat(),bed()]){
    assert.equal(P.validate(data,data.snapshot,data.id),data);
    assert.throws(()=>P.validate(data,"other-scenario",data.id),/different catalog/);
    assert.throws(()=>P.validate(data,data.snapshot,"other-process"),/different catalog/);
    assert.throws(()=>P.validate({...data,sources:[{...source,sha256:"not-a-source-hash"}]},data.snapshot,data.id),/source identity/);
  }
});

test("invalid native support cannot become a plausible but misaligned chart",()=>{
  for(const mutate of [
    data=>{data.times=[0,0];},
    data=>{data.cells[1].position_m=5;},
    data=>{data.cells[1].id="upstream";},
    data=>{data.water[1]=[22];},
    data=>{data.bed[0][1]=Number.NaN;},
    data=>{data.water[0][0]=false;},
  ]){const data=bed();mutate(data);assert.throws(()=>P.validate(data,data.snapshot,data.id));}
  for(const mutate of [
    data=>{data.grid.row_order="unknown";},
    data=>{data.grid.nx=3;},
    data=>{data.values[0]=99;},
    data=>{data.values[2]=undefined;},
    data=>{data.legend[1].class_id=0;},
  ]){const data=mat();mutate(data);assert.throws(()=>P.validate(data,data.snapshot,data.id));}
  const data=steam();data.components[1].id="pool";
  assert.throws(()=>P.validate(data,data.snapshot,data.id),/source components/);
});

test("lazy loading hashes the actual response bytes and retries after a same-length mutation",async()=>{
  const data=steam("tamper-retry"),bundle=packaged(data),altered=Buffer.from(bundle.bytes);altered[altered.length-1]=93;
  let requests=0;
  const dependencies={hashBytes,fetch:async(url,options)=>{
    assert.equal(url,bundle.descriptor.url);assert.equal(options.cache,"no-cache");
    return response(++requests===1?altered:bundle.bytes);
  }};
  await assert.rejects(P.load(bundle.snapshot,"steam",dependencies),/identity check/);
  assert.deepEqual(await P.load(bundle.snapshot,"steam",dependencies),data);
  assert.equal(requests,2);
  assert.deepEqual(await P.load(bundle.snapshot,"steam",dependencies),data);
  assert.equal(requests,2,"A verified response should be shared by later mounts");
});

test("an incorrect declared byte count is rejected even when the digest matches",async()=>{
  const bundle=packaged(steam("declared-length"));bundle.descriptor.bytes++;
  await assert.rejects(P.load(bundle.snapshot,"steam",{hashBytes,fetch:async()=>response(bundle.bytes)}),/identity check/);
});

test("cached data is revalidated for a new scenario and process, then can be reloaded correctly",async()=>{
  const data=steam("cached-identity"),bundle=packaged(data);let requests=0;
  const dependencies={hashBytes,fetch:async()=>{requests++;return response(bundle.bytes);}};
  await P.load(bundle.snapshot,"steam",dependencies);
  const stale={...bundle.snapshot,snapshot:"new-scenario"};
  await assert.rejects(P.load(stale,"steam",dependencies),/different catalog/);
  assert.equal(requests,1,"A cached hit still needs its scenario checked");
  await P.load(bundle.snapshot,"steam",dependencies);
  const wrongProcess={...bundle.snapshot,datasets:{process_visuals:[{...bundle.descriptor,id:"mat"}]}};
  await assert.rejects(P.load(wrongProcess,"mat",dependencies),/different catalog/);
  assert.equal(requests,2,"A cached hit still needs its process checked");
  assert.deepEqual(await P.load(bundle.snapshot,"steam",dependencies),data);
  assert.equal(requests,3);
});

test("HTTP failure and a hash-valid stale document leave no poisoned retry entry",async()=>{
  const current=steam("http-and-stale"),bundle=packaged(current);let requests=0;
  const dependencies={hashBytes,fetch:async()=>++requests===1?{ok:false}:response(bundle.bytes)};
  await assert.rejects(P.load(bundle.snapshot,"steam",dependencies),/could not be loaded/);
  assert.deepEqual(await P.load(bundle.snapshot,"steam",dependencies),current);
  const old=packaged(steam("old-catalog"));old.snapshot.snapshot="new-catalog";
  await assert.rejects(P.load(old.snapshot,"steam",{hashBytes,fetch:async()=>response(old.bytes)}),/different catalog/);
  await assert.rejects(P.load({snapshot:"missing",datasets:{process_visuals:[]}},"mat",dependencies),/unavailable/);
});

test("simultaneous consumers share one checked fetch",async()=>{
  const data=bed("concurrent-bed"),bundle=packaged(data);let requests=0;
  const dependencies={hashBytes,fetch:async()=>{requests++;return response(bundle.bytes);}};
  const results=await Promise.all([P.load(bundle.snapshot,"hyporheic",dependencies),P.load(bundle.snapshot,"hyporheic",dependencies)]);
  assert.deepEqual(results,[data,data]);assert.equal(requests,1);
});

test("steam source powers respect source area while the combined flux remains area weighted",()=>{
  const data=steam(),area=data.components.reduce((sum,item)=>sum+item.area_m2,0);
  const weighted=field=>data.components.reduce((sum,item)=>sum+item.area_m2*item[field],0)/area;
  const pool=P.steamSummary(data,"steam_temperature","pool"),outflow=P.steamSummary(data,"steam_temperature","outflow");
  assert.equal(pool.powerMW,.002);assert.equal(outflow.powerMW,.036);
  assert.equal(pool.average,weighted("sensible_w_m2"));assert.equal(outflow.average,pool.average);
  assert.notEqual(pool.average,(20+40)/2,"A source average must not give unequal areas equal weight");
  assert.equal(pool.before,20);assert.equal(pool.after,21);assert.equal(pool.change,1);assert.equal(pool.unit,"°C");
  const humid=P.steamSummary(data,"steam_humidity","outflow");
  assert.equal(humid.before,40);assert.equal(humid.after,50);assert.equal(humid.change,10);
  assert.equal(humid.unit,"%");assert.equal(humid.powerMW,.09);assert.equal(humid.average,weighted("latent_w_m2"));
  assert.equal(humid.source.id,"outflow");
});

test("paired samples retain a real zero and never turn a missing store into a heat difference",()=>{
  const data=bed(),zero=P.pairedSample(data,0,0),missingWater=P.pairedSample(data,0,1),missingBed=P.pairedSample(data,1,1);
  assert.deepEqual(zero,{water:0,bed:0,difference:0,time:0,cell:data.cells[0]});
  assert.equal(missingWater.water,null);assert.equal(missingWater.bed,19);assert.equal(missingWater.difference,null);
  assert.equal(missingBed.water,18);assert.equal(missingBed.bed,null);assert.equal(missingBed.difference,null);
  assert.equal(missingBed.time,600);assert.equal(missingBed.cell.position_m,50);
  assert.equal(P.pairedSample(data,1,0).difference,2);
});

function lifecycleFixture(mountVisual) {
  class Element {
    constructor(){this.children=[];this.parent=null;this.style={setProperty(){}};}
    get isConnected(){return this.connected===true||this.parent?.isConnected===true;}
    append(...children){for(const child of children){child.remove();child.parent=this;this.children.push(child);}}
    replaceChildren(...children){for(const child of [...this.children])child.remove();this.append(...children);}
    remove(){if(this.parent)this.parent.children=this.parent.children.filter(child=>child!==this);this.parent=null;}
    setAttribute(){}
  }
  const observers=[];
  class Observer {
    constructor(){this.disconnections=0;observers.push(this);}
    observe(){}
    disconnect(){this.disconnections++;}
  }
  const window={YSProcessVisuals:{mount:mountVisual}},document={createElement:()=>new Element(),createElementNS:()=>new Element()};
  vm.runInNewContext(readFileSync(new URL("./src/process-data.js",import.meta.url),"utf8"),{window,document,ResizeObserver:Observer});
  const container=new Element();container.connected=true;
  const snapshot={process_views:{hyporheic:[{id:"channel_bed",kind:"visual",label:"Paired temperatures",unit:"°C",sources:[]}]}};
  return {api:window.YSProcessData,container,snapshot,observers};
}

test("leaving a mounted process disposes its chart and observer exactly once",async()=>{
  let destroys=0;
  const {api,container,snapshot,observers}=lifecycleFixture(async()=>({destroy(){destroys++;}}));
  await api.mount(container,snapshot,"hyporheic");
  assert.equal(container.children.length,1);assert.equal(observers.length,1);
  api.dispose(container);api.dispose(container);
  assert.equal(container.children.length,0);assert.equal(destroys,1);assert.equal(observers[0].disconnections,1);
});

test("leaving while a chart is loading invalidates and destroys its late result",async()=>{
  let finish,destroys=0;
  const {api,container,snapshot,observers}=lifecycleFixture(()=>new Promise(resolve=>{finish=resolve;}));
  const mounting=api.mount(container,snapshot,"hyporheic");
  assert.equal(typeof finish,"function");api.dispose(container);
  finish({destroy(){destroys++;}});await mounting;
  assert.equal(destroys,1);assert.equal(container.children.length,0);assert.equal(observers.length,0);
});
