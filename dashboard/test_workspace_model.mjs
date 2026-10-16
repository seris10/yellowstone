import { createRequire } from "node:module";
import assert from "node:assert/strict";
import test from "node:test";

const require = createRequire(import.meta.url);
const model = require("./src/workspace-model.js");
const data = {
  nodes: [{id:"boundary",display:"python",implementation:"implemented"},
    {id:"transport",display:"rendered",implementation:"implemented"},
    {id:"storage",display:"python",implementation:"implemented"},
    {id:"proposal",display:"none",implementation:"research"}],
  edges: [{id:"in",from:"boundary",to:"transport"},
    {id:"both",from:"transport",to:"storage",bidirectional:true},
    {id:"conditional",from:"storage",to:"transport",condition:"Inactive scenario"},
    {id:"research",from:"proposal",to:"transport",research:true}],
  river: {cells:[{s:5},{s:15},{s:25}],frames:[{t:0,temperature:[17,18,19]},{t:60,temperature:[17.5,18.5,20]}]},
  ecology: {oxygen:[6.5,7,7.5],periphyton:[1,2,3],patches:[{label:"Meadow",biomass:.5,capacity:2,moisture:.6}],snow:[{label:"Meadow",snow_mm:5}]}
};
const state = {research:false,conditional:true,status:"all",direction:"all"};

test("nested process circles stay inside their domain without overlaps",()=>{
  for(let count=0;count<=32;count++){
    const circles=model.pack(count,94);
    assert.equal(circles.length,count);
    circles.forEach((c,i)=>{
      assert.ok(c.r>0&&Math.hypot(c.x,c.y)+c.r<=94+1e-9);
      circles.slice(i+1).forEach(other=>assert.ok(Math.hypot(c.x-other.x,c.y-other.y)>=c.r+other.r-1e-9));
    });
  }
});
test("pointer zoom preserves the same world coordinate across depth thresholds",()=>{
  let camera={x:87,y:-92,k:.6};const point={x:473,y:316};
  const world={x:(point.x-camera.x)/camera.k,y:(point.y-camera.y)/camera.k};
  for(const factor of [1.2,1.8,2.4,1.6,.7,.2,.001,1e7]){
    camera=model.zoomAt(camera,factor,point,.2,90);
    assert.ok(Math.abs(camera.x+world.x*camera.k-point.x)<1e-8);
    assert.ok(Math.abs(camera.y+world.y*camera.k-point.y)<1e-8);
    assert.ok(camera.k>=.2&&camera.k<=90);
  }
});
test("focusing a circle changes the camera while preserving scene coordinates",()=>{
  const circle=Object.freeze({x:352,y:273,r:24}),center={x:610,y:387};
  const camera=model.frameCircle(circle,320,center);
  assert.equal(camera.k*circle.r,320);
  assert.ok(Math.abs(camera.x+camera.k*circle.x-center.x)<1e-8);
  assert.ok(Math.abs(camera.y+camera.k*circle.y-center.y)<1e-8);
});
test("detail opacity is continuous and reverses over the same interval",()=>{
  assert.equal(model.fade(1,2,6),0);assert.equal(model.fade(7,2,6),1);
  let previous=0;
  for(let i=0;i<=400;i++){
    const value=model.fade(2+i*.01,2,6);
    assert.ok(value>=previous&&value-previous<.004);
    assert.ok(Math.abs(value+model.fade(6-i*.01,2,6)-1)<1e-12);
    previous=value;
  }
});
test("process colors distinguish quantity roles and blend with domain colors",()=>{
  assert.notEqual(model.processRole("transport").color,model.processRole("mixing").color);
  assert.equal(model.processRole("solutes").label,"Chemistry");
  assert.equal(model.processRole("shading").label,"Light");
  assert.equal(model.mixColor("#77b9e6","#f2a46e",0),"#77b9e6");
  assert.equal(model.mixColor("#77b9e6","#f2a46e",1),"#f2a46e");
  assert.equal(model.mixColor("#77b9e6","#f2a46e",.5),"#b5afaa");
});

test("research and scenario filters remove their edges as well as nodes",()=>{
  assert.deepEqual(model.visible(data,{...state,conditional:false}).edges.map(e=>e.id),["in","both"]);
  assert.equal(model.visible(data,{...state,research:true}).edges.length,4);
});
test("bidirectional heat exchange participates in both neighborhoods",()=>{
  const near=model.neighborhood(data,"transport",state);
  assert.deepEqual(near.incoming,["boundary","storage"]);
  assert.deepEqual(near.outgoing,["storage"]);
  assert.deepEqual(model.neighborhood(data,"transport",{...state,direction:"out"}).edges.map(e=>e.id),["both"]);
});
test("status filters preserve the selected process and exclude hidden endpoints",()=>{
  const visible=model.visible(data,{...state,status:"python",process:"transport"});
  assert.equal(visible.nodes.length,3);assert.equal(visible.edges.length,3);
  assert.equal(model.visible(data,{...state,status:"rendered"}).edges.length,0);
});
test("reversed chart brush ranges are sorted and bounded to saved indexes",()=>{
  assert.deepEqual(model.range(50,-4,3),[0,2]);assert.deepEqual(model.range(2,1,3),[1,2]);
  assert.deepEqual(model.range(NaN,NaN,3),[0,2]);
});
test("spatial and temporal views share the exact saved temperature cell",()=>{
  const spatial=model.series(data,"temperature",1,2),temporal=model.series(data,"history",1,2);
  assert.equal(spatial.points[2].y,temporal.points[1].y);assert.equal(temporal.points[1].x,1);
  assert.equal(spatial.points[2].x,.025);assert.equal(spatial.unit,"°C");
});
test("diagnostic units and carrying-capacity ratios remain explicit",()=>{
  assert.equal(model.series(data,"oxygen",0,0).unit,"mg/L");
  assert.equal(model.series(data,"biomass",0,0).points[0].y,25);
  assert.equal(model.series(data,"snow",0,0).points[0].y,5);
  assert.equal(model.series(data,"unavailable",0,0),null);
});
test("linked canopy and cooling plots retain their actual scientific roles",()=>{
  assert.equal(model.binding("canopy","shading").role,"Context");
  assert.equal(model.binding("shading","shading").role,"Diagnostic");
  assert.equal(model.binding("outflow_cooling","pools").role,"Authored parameter");
  assert.match(model.binding("outflow_cooling","pools").note,/No cooling or food-web trajectory/);
});
test("heat-map probes use physical distance and recorded time with unequal spacing",()=>{
  assert.equal(model.nearestIndex([5,15,25,80],45),2);
  assert.equal(model.nearestIndex([0,60,180],140),2);
  assert.equal(model.nearestIndex([5,15,25],-30),0);
  assert.equal(model.nearestIndex([5,15,25],200),2);
});
