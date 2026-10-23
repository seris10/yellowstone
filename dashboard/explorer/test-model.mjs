import test from 'node:test';
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import {createHash} from 'node:crypto';
import {worldCoordinates, terrainValue, sampleIndex, validateReplay, verifiedBytes} from './model.js';

const manifest=JSON.parse(await readFile(new URL('data/manifest.json',import.meta.url)));
const replay=JSON.parse(await readFile(new URL('data/replay.json',import.meta.url)));

test('northing decreases with positive local z; vertical datum remains absolute',()=>{
  assert.deepEqual(worldCoordinates(10,2210,20,[512952,4930199,2200]),{easting:512962,northing:4930179,elevation:2210});
});
test('triangle interpolation agrees with the display mesh diagonal, including edges',()=>{
  const spec={start:[0,0],spacing_m:1,n:2},grid=[0,2,4,8];
  assert.equal(terrainValue(grid,spec,.25,.25),1.5);
  assert.equal(terrainValue(grid,spec,.75,.75),5.5);
  assert.equal(terrainValue(grid,spec,1,1),8);
  assert.equal(terrainValue(grid,spec,1,0),2);
});
test('out of support and missing data stay unavailable',()=>{
  const spec={start:[0,0],spacing_m:1,n:2};
  for(const [x,z]of [[-1,0],[0,1.1],[NaN,0]])assert.equal(terrainValue([1,2,3,4],spec,x,z),null);
  assert.equal(terrainValue([1,NaN,3,4],spec,0,0),null);
});
test('saved sample selection refuses interpolation and out-of-range values',()=>{
  assert.equal(sampleIndex('720',721),720);
  for(const i of [-1,721,.5,NaN])assert.throws(()=>sampleIndex(i,721),RangeError);
});
test('replay validation rejects duplicate cells, dimensions, nonfinite values and unordered time',()=>{
  assert.equal(validateReplay(replay),replay);
  const base={cells:[{id:'a'}],frames:[{t:0,values:[1]},{t:1,values:[null]}]};
  assert.equal(validateReplay(base),base);
  for(const change of [r=>r.cells.push({id:'a'}),r=>r.frames[0].values.push(3),r=>r.frames[1].t=0,r=>r.frames[0].values[0]=Infinity,r=>r.frames[0].values[0]=true]){const r=structuredClone(base);change(r);assert.throws(()=>validateReplay(r));}
});
test('all exported assets match byte hashes and declared sizes',async()=>{
  for(const [name,expected]of Object.entries(manifest.assets)){const bytes=await readFile(new URL(`data/${name}`,import.meta.url));assert.equal(bytes.length,expected.bytes,name);assert.equal(createHash('sha256').update(bytes).digest('hex'),expected.sha256,name);}
});
test('browser loader refuses tampering, then accepts clean retry',async()=>{
  const original=globalThis.fetch,bytes=new TextEncoder().encode('stored output');
  const expected={sha256:createHash('sha256').update(bytes).digest('hex'),bytes:bytes.length};
  try{
    globalThis.fetch=async()=>new Response('modified output');await assert.rejects(verifiedBytes('fixture',expected),/integrity/);
    globalThis.fetch=async()=>new Response(bytes);assert.deepEqual(new Uint8Array(await verifiedBytes('fixture',expected)),bytes);
    globalThis.fetch=async()=>new Response('',{status:404});await assert.rejects(verifiedBytes('fixture',expected),/request failed/);
  }finally{globalThis.fetch=original;}
});
test('actual terrain endpoints and replay support retain source units',async()=>{
  assert.equal(replay.frames.length,721);assert.equal(replay.cells.length,276);assert.equal(replay.frames.at(-1).t,7200);
  assert.equal(manifest.georeference.crs,'EPSG:32612');
  for(const spec of Object.values(manifest.terrain)){const bytes=await readFile(new URL(`data/${spec.file}`,import.meta.url));const grid=new Float32Array(bytes.buffer,bytes.byteOffset,bytes.length/4);assert.equal(grid.length,spec.n**2);assert.ok([...grid].every(v=>v>2100&&v<2500));assert.equal(terrainValue(grid,spec,...spec.start),grid[0]);}
});
