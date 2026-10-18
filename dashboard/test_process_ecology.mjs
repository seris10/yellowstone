import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import {createRequire} from "node:module";
const require=createRequire(import.meta.url),E=require("./src/process-ecology.js");
const cell=(id,s,x=0,z=0)=>({id,label:id,x,z,metadata:{chainage_m:s},values:{height:s}});
test("channel samples use exact saved times and preserve absent values",()=>{
  const data={entities:[cell("b",20),cell("a",5),cell("c",40)],series:[{entity_id:"a",variable_id:"feeding_brown_trout",times:[0,7,20],values:[.2,null,.5]},{entity_id:"b",variable_id:"feeding_brown_trout",times:[0,20],values:[.4,.6]}]};
  const channel=E.channelData(data);
  assert.deepEqual(channel.times,[0,7,20]);assert.deepEqual(channel.cells.map(c=>c.id),["a","b","c"]);
  assert.deepEqual(E.savedProfile(channel,7).map(p=>p.y),[null,null,null]);
  assert.deepEqual(E.savedProfile(channel,20).map(p=>p.y),[.5,.6,null]);
  assert.deepEqual(E.savedProfile(channel,10).map(p=>p.y),[null,null,null]);
});
test("crown histogram retains one extent and exact inclusive filter counts",()=>{
  const entities=[0,1,2,3,4,null].map((v,i)=>({...cell(String(i),i),values:{height:v}}));
  const range=E.crownRange(entities,"height",[1,3]);
  assert.equal(range.selected,3);assert.equal(range.missing,1);
  assert.deepEqual(range.all.extent,[0,4]);assert.deepEqual(range.filtered.extent,[0,4]);
  assert.equal(range.all.bins.reduce((n,b)=>n+b.count,0),5);assert.equal(range.filtered.bins.reduce((n,b)=>n+b.count,0),3);
  const constant=E.crownRange([{values:{height:2}},{values:{height:2}}],"height",[2,2]);
  assert.equal(constant.all.bins.length,1);assert.equal(constant.selected,2);
});
test("spatial selection uses native coordinates and omits missing coordinates",()=>{
  const entities=[cell("a",0,100,200),cell("b",1,10,30),cell("missing",2,null,null)];
  assert.equal(E.nearestSpatial(entities,{x:12,z:28}).id,"b");
  assert.deepEqual(E.spatialExtent(entities),{x0:10,x1:100,z0:30,z1:200});
});
const base=path.dirname(new URL(import.meta.url).pathname),snapshot=JSON.parse(fs.readFileSync(path.join(base,"data/snapshot.json")));
function native(id){const descriptor=snapshot.datasets.systems.find(d=>d.id===id);return JSON.parse(fs.readFileSync(path.join(base,"data",path.basename(descriptor.url))));}
test("current brown trout export matches all native cells at first and final saved times",()=>{
  const data=native("aquatic"),channel=E.channelData(data);
  assert.equal(channel.cells.length,276);assert.equal(channel.times.length,721);assert.equal(channel.times[0],0);assert.equal(channel.times.at(-1),7200);
  for(const elapsed of [0,7200])for(const row of E.savedProfile(channel,elapsed)){
    const source=data.series.find(s=>s.entity_id===row.entity.id&&s.variable_id==="feeding_brown_trout");assert.equal(row.y,source.values[source.times.indexOf(elapsed)]);
  }
});
test("current canopy filter includes all crown detections and conserves histogram counts",()=>{
  const data=native("canopy");assert.equal(data.entities.length,34303);
  for(const variable of ["height","core_area"]){const values=data.entities.map(e=>e.values[variable]).filter(Number.isFinite),min=Math.min(...values),max=Math.max(...values),range=E.crownRange(data.entities,variable,[min,max]);assert.equal(range.selected,values.length);assert.equal(range.all.bins.reduce((n,b)=>n+b.count,0),values.length);assert.deepEqual(range.filtered.extent,[min,max]);const threshold=(min+max)/2,upper=E.crownRange(data.entities,variable,[threshold,max]);assert.equal(upper.selected,values.filter(v=>v>=threshold).length);}
});
