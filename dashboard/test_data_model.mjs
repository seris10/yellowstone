import {createRequire} from "node:module";
import assert from "node:assert/strict";
import test from "node:test";
const require=createRequire(import.meta.url),D=require("./src/data-model.js"),M=require("./src/workspace-model.js");
const doc={schema:"yellowstone.river.v1",snapshot:"fixture",epoch:"2026-06-21T22:12:00Z",source_sha256:"source",support:{space:"fixture bounds"},river:{length_m:30,
  cells:[{id:"a",s:5,bounds_m:[0,10],x:0,z:1},{id:"b",s:20,bounds_m:[10,30],x:2,z:3}],
  frames:[{t:0,temperature:[17.123456789,null]},{t:10,temperature:[null,19]},{t:70,temperature:[18,20]}]}};
const data=D.normalizeDataset(doc),state={cell:1,frame:2,pinned:true,first:0,last:1,timeFirst:0,timeLast:2,reference:0,difference:true,compare:true,scale:"run"};
test("native validation preserves IDs, gaps, bounds, and precision",()=>{
  assert.equal(data.cells[0].id,"a");assert.equal(data.frames[0].temperature[0],17.123456789);assert.equal(data.missing,2);assert.deepEqual(data.extent,[17.123456789,20]);
  for(const invalid of [true,"17",Infinity]){const copy=structuredClone(doc);copy.river.frames[0].temperature[0]=invalid;assert.throws(()=>D.normalizeDataset(copy),/finite number/);}
  const duplicate=structuredClone(doc);duplicate.river.cells[1].id="a";assert.throws(()=>D.normalizeDataset(duplicate),/unique/);
});
test("missing runs create separate segments and all-missing is empty",()=>{
  assert.equal(D.segments([{x:0,y:1},{x:1,y:null},{x:2,y:4},{x:3,y:5}]),"M0,1  M2,4 L3,5");
  assert.equal(D.segments([{x:0,y:null},{x:1,y:NaN}])," ");assert.equal(D.extent([null,NaN]),null);
  assert.equal(D.delta(null,2),null);assert.equal(D.delta(2,null),null);
});
test("physical playback respects uneven saved intervals",()=>{
  assert.equal(D.frameAtElapsed([0,10,70],9),0);assert.equal(D.frameAtElapsed([0,10,70],35),1);assert.equal(D.frameAtElapsed([0,10,70],70),2);
  assert.equal(D.frameAtElapsed([],70),-1);assert.equal(D.nearestIndex([],0),-1);
});
test("inverse screen transform handles SVG letterboxing",()=>{
  let point={x:0,y:0,matrixTransform(m){return {x:(this.x-m.tx)/m.scale,y:(this.y-m.ty)/m.scale};}};
  const svg={createSVGPoint:()=>point,getScreenCTM:()=>({inverse:()=>({tx:100,ty:220,scale:2})})};
  assert.deepEqual(D.eventToSvg(svg,{clientX:500,clientY:420}),{x:200,y:100});
});
test("recipe round-trip includes ranges, reference, and hash identity",()=>{
  const r=D.recipe(data,"bytes",state);assert.deepEqual(D.restoreRecipe(r,data,"bytes"),state);
  assert.throws(()=>D.restoreRecipe(r,data,"different"),/different dataset bytes/);
  r.range.space=[0,99];assert.throws(()=>D.restoreRecipe(r,data,"bytes"),/bounds/);
});
test("CSV retains numeric values and protects text without coercing missing values",()=>{
  assert.equal(D.csvCell(-1.2345),"-1.2345");assert.equal(D.csvCell("=SUM(1)"),'"\'=SUM(1)"');assert.equal(D.csvCell(null),'""');
  const csv=D.csv(data,state,"bytes");assert.ok(csv.includes("17.123456789"));assert.ok(csv.includes("cell_start_m"));assert.equal(csv.split("\r\n").length,8);
});
test("source metadata and optional capabilities do not conflate context with output",()=>{
  assert.equal(M.binding("mammals","biomass").role,"Context");assert.equal(M.binding("fish","temperature").role,"Driver");assert.equal(M.binding("steam","air").role,"Driver");assert.equal(M.binding("outflow_cooling","pools").role,"Authored parameter");
  assert.equal(M.available({river:doc.river,ecology:null,analytics:null},"oxygen"),false);assert.equal(M.series({ecology:null},"oxygen",0,0),null);
});
test("overview structure remains usable when optional river data is absent or malformed",()=>{
  const base={schema:"yellowstone.public.v1",snapshot:"fixture",domains:[{id:"river"}],nodes:[{id:"transport",domain:"river"}],edges:[]};
  assert.equal(D.validateSnapshot({...base}).river,null);
  assert.equal(D.validateSnapshot({...base,river:{}}).river,null);
  const partial=D.validateSnapshot({...base,river:structuredClone(doc.river),ecology:{oxygen:[1]}});
  assert.equal(partial.ecology.oxygen,null);assert.ok(partial.availability.length);
});
test("large extents and difference scales retain finite support",()=>{
  assert.deepEqual(D.extent((function*(){for(let i=0;i<250000;i++)yield i;})()),[0,249999]);
  const domain=D.differenceExtent(data,0);assert.equal(domain[0],-domain[1]);assert.ok(domain[1]>0);assert.equal(D.color(null,data.extent),"#262b34");
});
