import {createRequire} from "node:module";
import assert from "node:assert/strict";
import test from "node:test";

const require = createRequire(import.meta.url), M = require("./src/systems-model.js");
const sha = "a".repeat(64), datasetSha = "b".repeat(64);
const support = {space:"Individual authored patches; local x,z in m.", time:"Final state after 600 s.", uncertainty:"unknown", time_kind:"instantaneous", interval_s:[600,600]};
const v = (id, unit = "mm") => ({id, label:id, unit, role:"direct_output", description:"Saved model quantity.", source_id:"source", support:structuredClone(support)});
function fixture() {
  return {schema:"yellowstone.system.v1", id:"soil", snapshot:"fixture", title:"Soil water", summary:"Saved patch water states.", color:"#8ed5aa",
    epoch:"2026-06-21T22:12:00Z", run_mode:"scenario", sources:[{id:"source", label:"Model output", sha256:sha, origin:"checked_model_artifact"}],
    entities:[{id:"west", label:"West", kind:"patch", x:-3, z:11, values:{water:17.1234567890123, cover:.2}},
      {id:"east", label:"East", kind:"patch", x:-1, z:15, values:{water:0, cover:null}},
      {id:"context", label:"Context", kind:"parameter", x:null, z:null, values:{water:null, cover:.5}}],
    variables:[v("water"), v("cover", "1")],
    grids:[{...v("snow"), grid:{nx:2,nz:3,cell_m:2,origin_xz_m:[-4,10],row_order:"z_increasing"}, values:[1,null,3,4,5,6]}],
    series:[{...v("water_history"), variable_id:"water", entity_id:"west", support:{...support, time:"Saved samples at 0, 10, and 70 s.", time_kind:"trajectory", interval_s:[0,70]}, times:[0,10,70], values:[17.1234567890123,null,19]}],
    profiles:[{...v("radial_temperature", "C"), entity_id:"west", axis:{id:"radius",label:"Radius",unit:"m"}, positions:[0,.1,.5], values:[80,null,35]}],
    tables:[{id:"budget",label:"Patch accounting",columns:[{id:"id",label:"Patch",unit:""},{id:"storage",label:"Storage",unit:"mm"}], rows:[{id:"west",storage:17.1234567890123}]}], notes:["Authored scenario. Parameter uncertainty is unknown."]};
}
const state = {variable:"water", x:"cover", y:"water", kind:"patch", range:[0,17.1234567890123], pins:["west"], reference:"west",
  scale:"run", series:"water_history", timeRange:[0,70], map:{x:-2,y:13,k:12.5}, selected:"east", pinned:true,
  gridIndex:null, difference:true, referenceGrid:null, time:10, temporal:true, referenceTime:0, query:"West", sort:"value", descending:true, page:0};

test("strict system contract preserves independent support, identity, precision, and missing samples", () => {
  const data = fixture();
  assert.equal(M.validate(data,{snapshot:"fixture",descriptor:{id:"soil"}}),data);
  assert.equal(data.entities[0].values.water,17.1234567890123);
  assert.equal(data.series[0].support.interval_s[1],70);
  assert.equal(data.profiles[0].axis.unit,"m");
  assert.deepEqual(M.capabilities(data),{entities:3,spatial:2,variables:["water","cover"],grids:["snow"],series:["water_history"],profiles:["radial_temperature"],tables:["budget"],kinds:["patch","parameter"],missing:2});
});

test("invalid numbers, identities, source links, and coordinate support are rejected", () => {
  for (const value of ["1",true,Infinity,NaN,undefined]) {
    const d = fixture(); d.entities[0].values.water = value;
    assert.throws(() => M.validate(d), /numeric value/);
  }
  for (const change of [d=>d.entities[1].id="west", d=>d.variables[0].source_id="missing", d=>d.sources[0].sha256="unverified",
    d=>d.entities[0].values.unknown=1, d=>d.entities[0].z=null, d=>d.variables[0].support.uncertainty="measured", d=>d.epoch="2026-06-21T22:12:00"]) {
    const d = fixture(); change(d); assert.throws(() => M.validate(d));
  }
  assert.throws(() => M.validate(fixture(),{snapshot:"other"}), /snapshot differs/);
});

test("optional absent capabilities remain usable; present malformed quantities fail validation", () => {
  const d = fixture(); d.grids=[]; d.series=[]; delete d.profiles; delete d.tables;
  assert.equal(M.validate(d),d); assert.deepEqual(M.capabilities(d).grids,[]);
  for (const change of [d=>d.series[0].times=[0,10,10], d=>d.series[0].times=[0,10], d=>d.series[0].entity_id="absent",
    d=>d.series[0].support.interval_s=[20,30], d=>d.series[0].unit="C", d=>d.profiles[0].positions=[0,.5,.1],
    d=>d.grids[0].grid.nx=3, d=>d.grids[0].grid.row_order="unknown", d=>d.grids[0].grid.cell_m=0,
    d=>d.series.push({...structuredClone(d.series[0]),id:"duplicate_support"})]) {
    const invalid = fixture(); change(invalid); assert.throws(() => M.validate(invalid));
  }
});

test("extents and statistics are iterative and distinguish zero from missing values", () => {
  assert.deepEqual(M.finiteExtent((function* () { for(let i=0;i<300000;i++) yield i; })()),[0,299999]);
  assert.deepEqual(M.stats([null,0,2,undefined,NaN]),{count:5,finite:2,missing:3,min:0,max:2,mean:1});
  assert.deepEqual(M.stats([null,null]),{count:2,finite:0,missing:2,min:null,max:null,mean:null});
  assert.equal(M.stats([1e308,1e308]).mean,1e308);
});

test("histogram bins state exact bounds and close only the final upper edge", () => {
  const h = M.histogram([0,1,2,3,4,null],{bins:2});
  assert.deepEqual(h.bins,[{lo:0,hi:2,count:2,last:false},{lo:2,hi:4,count:3,last:true}]);
  assert.equal(h.finite,5); assert.equal(h.missing,1); assert.equal(h.outside,0);
  const narrow = M.histogram([0,1,2,3,4,null],{bins:2,range:[1,3]});
  assert.equal(narrow.finite,3); assert.equal(narrow.outside,2);
  assert.deepEqual(M.histogram([7,7,null],{bins:20}).bins,[{lo:7,hi:7,count:2,last:true}]);
  assert.deepEqual(M.histogram([null,NaN]).bins,[]);
  const extremes = M.histogram([-1e308,0,1e308],{bins:2});
  assert.equal(extremes.bins.reduce((n,b)=>n+b.count,0),3); assert.ok(extremes.bins.every(b=>Number.isFinite(b.lo)&&Number.isFinite(b.hi)));
  assert.throws(()=>M.histogram([0,1],{range:[2,1]}),/range/);
});

test("scatter pairs variables by the same stable entity, with explicit missingness", () => {
  const d = fixture(), s = M.scatter(d,"cover","water",{kind:"patch"});
  assert.equal(s.total,2); assert.equal(s.missing,1); assert.deepEqual(s.points.map(p=>[p.id,p.x,p.y]),[["west",.2,17.1234567890123]]);
  assert.deepEqual(M.entityRows(d,"water",{range:[0,0]}).map(r=>r.id),["east"]);
  assert.deepEqual(M.entityRows(d,"water",{ids:["east","west"]}).map(r=>r.id),["west","east"]);
  assert.throws(()=>M.scatter(d,"unknown","water"),/axes/);
});

test("non-square grid geometry respects native dimensions, spacing, centers, and row direction", () => {
  const g = fixture().grids[0];
  assert.deepEqual(M.gridExtent(g),{x0:-4,x1:0,z0:10,z1:16,width:4,height:6});
  assert.deepEqual(M.gridPoint(g,0),{index:0,row:0,column:0,x:-3,z:11,value:1});
  assert.equal(M.sampleGrid(g,-1,11).value,null);
  assert.equal(M.sampleGrid(g,0,12),null); assert.equal(M.sampleGrid(g,-3,16),null);
  assert.equal(M.sampleGrid(g,-4,10).index,0);
  g.grid.row_order="z_decreasing";
  assert.equal(M.gridPoint(g,0).z,15); assert.equal(M.sampleGrid(g,-3,11).index,4);
  assert.equal(M.gridPoint(g,-1),null);
});

test("map projection preserves equal aspect and inverts display letterboxing without geography assumptions", () => {
  const m = M.mapTransform({x0:-4,x1:0,z0:10,z1:16},400,300,20);
  const center = m.project(-2,13); assert.deepEqual(center,{x:200,y:150});
  assert.deepEqual(m.invert(center.x,center.y),{x:-2,z:13});
  assert.equal(m.project(-1,13).x-center.x,m.project(-2,14).y-center.y);
});

test("gaps never become continuous paths, including transformed missing values", () => {
  assert.equal(M.segments([{x:0,y:2},{x:1,y:null},{x:2,y:4},{x:3,y:0}]),"M0,2 M2,4 L3,0");
  assert.equal(M.segments([{x:0,y:null},{x:1,y:NaN}]),"");
  assert.equal(M.segments([{x:0,y:1},{x:1,y:2},{x:2,y:3}],p=>p.x,p=>p.x===1?NaN:p.y),"M0,1 M2,3");
});

test("physical sample lookup uses independent irregular times and never extrapolates", () => {
  const d = fixture(), s = d.series[0];
  assert.deepEqual(M.sampleAt(s,9),{index:0,time:0,value:17.1234567890123});
  assert.deepEqual(M.sampleAt(s,69),{index:1,time:10,value:null});
  assert.equal(M.sampleAt(s,-1),null); assert.equal(M.sampleAt(s,71),null);
  assert.deepEqual(M.temporalValues(d,"water",70).map(v=>[v.id,v.value]),[["west",19],["east",null],["context",null]]);
  assert.equal(M.nearestIndex([0,10,70],5),0);
});

test("comparisons require matching units and matching physical support", () => {
  const a = v("a"), b = v("b");
  assert.deepEqual(M.compare(a,b,[1,null,3],[0,2,null]),[1,null,null]);
  b.unit="C"; assert.throws(()=>M.compare(a,b,[1],[2]),/units or physical support/);
  b.unit="mm"; b.support.time="Different interval.";
  assert.throws(()=>M.compare(a,b,[1],[2]),/support/);
});

test("CSV preserves source precision, numeric signs, missingness, and formula safety", () => {
  const csv = M.csvRows([["id","value"],["=SUM(A1:A2)",17.1234567890123],[" \t+1",-1e-12],["a\"b",null],["@formula",0]]);
  assert.ok(csv.includes("17.1234567890123")); assert.ok(csv.includes("-1e-12"));
  assert.ok(csv.includes('"\'=SUM(A1:A2)"')); assert.ok(csv.includes('"\' \t+1"'));
  assert.ok(csv.includes('"a""b",""')); assert.ok(csv.endsWith("\r\n"));
});

test("view recipes round-trip complete settings and reject stale bytes or provenance", () => {
  const data = fixture(), value = M.recipe(data,state,datasetSha);
  assert.deepEqual(M.restoreRecipe(data,value,datasetSha),state);
  for (const change of [r=>r.dataset_sha256=sha,r=>r.sources[0].sha256=datasetSha,r=>r.units="C",r=>r.snapshot="stale"]){
    const copy = structuredClone(value); change(copy); assert.throws(()=>M.restoreRecipe(data,copy,datasetSha));
  }
});

test("recipes reject invalid bounds, unavailable settings, stale identities, and unsupported comparisons", () => {
  const data = fixture();
  for (const patch of [{range:[-1,20]},{timeRange:[0,71]},{pins:["missing"]},{reference:"context"},{x:"snow"},
    {selected:"stale"},{map:{x:0,y:0,k:0}},{page:1000},{query:"x".repeat(201)},{time:71},{referenceTime:-1},
    {gridIndex:1},{referenceGrid:1},{unknown:true},{difference:true,reference:null,referenceTime:null}]) {
    assert.throws(()=>M.recipe(data,{...state,...patch},datasetSha));
  }
  const gridState = {...state,variable:"snow",range:null,reference:null,series:null,timeRange:null,time:null,referenceTime:null,temporal:false,gridIndex:5,referenceGrid:0};
  assert.deepEqual(M.restoreRecipe(data,M.recipe(data,gridState,datasetSha),datasetSha),gridState);
  assert.throws(()=>M.recipe(data,{...gridState,referenceGrid:1},datasetSha),/reference/);
});

test("recipe filters retain the full saved trajectory range and source-value table pages", () => {
  const data = fixture();
  assert.deepEqual(M.quantityExtent(data,data.variables[0]),[0,19]);
  assert.deepEqual(M.recipe(data,{...state,range:[18,19]},datasetSha).selection.range,[18,19]);
  data.series[0].times=Array.from({length:221},(_,i)=>i*10);
  data.series[0].values=data.series[0].times.map(t=>t/100);
  data.series[0].support.interval_s=[0,2200];
  assert.equal(M.recipe(data,{...state,timeRange:[0,2200],page:2},datasetSha).selection.page,2);
  assert.throws(()=>M.recipe(data,{...state,page:3},datasetSha),/table settings/);
  assert.throws(()=>M.recipe(data,{...state,variable:"cover",range:null},datasetSha),/different quantity/);
});
