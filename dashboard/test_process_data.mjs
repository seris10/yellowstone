import {createRequire} from "node:module";
import assert from "node:assert/strict";
import test from "node:test";
import {createHash} from "node:crypto";
const require=createRequire(import.meta.url),P=require("./src/process-data.js");

test("native loading rejects altered bytes before parsing and permits a clean retry",async()=>{
  const body=Buffer.from('{"id":"test","snapshot":"checked-test","sample":"source bytes"}'),sha=createHash("sha256").update(body).digest("hex");
  const snapshot={snapshot:"checked-test",datasets:{systems:[{id:"test",sha256:sha,url:"/source.json"}]}},hashBytes=bytes=>createHash("sha256").update(Buffer.from(bytes)).digest("hex");
  let requests=0,validated=0;
  const dependencies={hashBytes,fetch:async()=>({ok:true,arrayBuffer:async()=>{requests++;return requests===1?Buffer.from("altered"):body;}}),validate:(data,options)=>{validated++;assert.equal(options.snapshot,"checked-test");return data;}};
  await assert.rejects(P.load(snapshot,{system:"test"},dependencies),/identity check/);assert.equal(validated,0);
  assert.deepEqual(await P.load(snapshot,{system:"test"},dependencies),{id:"test",snapshot:"checked-test",sample:"source bytes"});assert.equal(requests,2);assert.equal(validated,1);
  await assert.rejects(P.load({...snapshot,snapshot:"other-generation"},{system:"test"},dependencies),/different catalog/);
  await assert.rejects(P.load(snapshot,{system:"absent"},dependencies),/unavailable/);assert.equal(requests,2);
});

test("missing values do not become zeros or imply constant completeness",()=>{
  assert.deepEqual(P.summary([null,4,4,null]),{min:4,max:4,count:2,missing:2,constant:true});
  assert.deepEqual(P.summary([null,null]),{min:null,max:null,count:0,missing:2,constant:false});
  assert.equal(P.summary([21.2658477444,17.0369590954]).constant,false);
});
const metadata={id:"air",label:"Air",unit:"C",source_id:"forcing",support:{time:"Saved states"}};
const data={variables:[metadata],grids:[],profiles:[],tables:[],entities:[{id:"weather",label:"Weather",values:{air:20}},{id:"steam",label:"Steam",values:{air:null}}],series:[{id:"weather-air",variable_id:"air",entity_id:"weather",times:[0,3600,7200],values:[20,19,17],unit:"C"}]};
test("a native weather view retains all source times and cannot substitute steam",()=>{
  const view=P.resolve(data,{quantity:"air"},"steam");
  assert.equal(view.entity.id,"weather");
  assert.deepEqual(view.times,[0,3600,7200]);assert.deepEqual(view.values,[20,19,17]);
  assert.throws(()=>P.resolve(data,{quantity:"absent"}),/absent/);
});
test("river diagnostics match stable entity chainage and preserve missing cells",()=>{
  const dataset={variables:[metadata],grids:[],profiles:[],tables:[],series:[],entities:[{id:"a",label:"A",metadata:{chainage_m:10},values:{air:5}},{id:"missing",label:"Missing",metadata:{chainage_m:20},values:{air:null}},{id:"b",label:"B",metadata:{chainage_m:30},values:{air:7}}]};
  const view=P.resolve(dataset,{quantity:"air"});assert.equal(view.kind,"profile");assert.deepEqual(view.positions,[10,20,30]);assert.deepEqual(view.values,[5,null,7]);
});
test("pool profiles keep their own axis and entity rather than using a weather clock",()=>{
  const profile={id:"radial-a",entity_id:"pool-a",unit:"C",axis:{unit:"m"},positions:[0,2,8],values:[80,null,40]},other={...profile,id:"radial-b",entity_id:"pool-b",values:[90,70,50]};
  const view=P.resolve({variables:[],grids:[],profiles:[profile,other],tables:[]},{quantity:"radial-a",collection:"profiles"},"pool-b");
  assert.equal(view.entity_id,"pool-b");assert.equal(view.x_unit,"m");assert.deepEqual(view.positions,[0,2,8]);assert.deepEqual(view.values,[90,70,50]);
});
