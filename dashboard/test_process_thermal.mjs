import test from "node:test";
import assert from "node:assert/strict";
import {createRequire} from "node:module";
const require = createRequire(import.meta.url), T = require("./src/process-thermal.js");
const layer = (rowOrder = "z_increasing", values = [10, null, 30, 40, 50, 60]) => ({grid:{nx:3,nz:2,cell_m:2,origin_xz_m:[-4,8],row_order:rowOrder},values});

test("native cell centers and probes retain either row orientation", () => {
  assert.deepEqual(T.gridPoint(layer(), 0), {index:0,row:0,column:0,x:-3,z:9,value:10});
  assert.deepEqual(T.gridPoint(layer("z_decreasing"), 0), {index:0,row:0,column:0,x:-3,z:11,value:10});
  assert.equal(T.sampleGrid(layer("z_decreasing"), -3, 11).index, 0);
  assert.equal(T.sampleGrid(layer("z_decreasing"), -3, 9).index, 3);
  assert.equal(T.sampleGrid(layer(), 2, 9), null);
  assert.equal(T.sampleGrid(layer(), -4, 12), null);
  assert.equal(T.sampleGrid(layer(), NaN, 9), null);
});

test("transects traverse native cells and preserve unsupported gaps", () => {
  const cut = T.transect(layer(), 0, 2);
  assert.deepEqual(cut.map(point => point.index), [0,1,2]);
  assert.deepEqual(cut.map(point => point.value), [10,null,30]);
  assert.deepEqual(cut.map(point => point.distance), [0,2,4]);
  assert.equal(T.transect(layer(), 0, 0)[0].distance, 0);
  assert.deepEqual(T.transect(layer(), -1, 2), []);
});

test("diagonal transect samples the cells actually crossed, including reverse orientation", () => {
  const field = {grid:{nx:3,nz:3,cell_m:1,origin_xz_m:[0,0],row_order:"z_increasing"}, values:[0,1,2,3,4,5,6,7,8]};
  const cut = T.transect(field, 0, 8), reverse = T.transect(field, 8, 0);
  assert.deepEqual(cut.map(point => point.index), [0,4,8]);
  assert.deepEqual(reverse.map(point => point.index), [8,4,0]);
  assert.equal(cut.at(-1).distance, Math.hypot(2,2));
  assert.ok(cut.every((point,i) => !i || point.distance > cut[i-1].distance));
});

test("classified areas count native integer classes without counting missing values", () => {
  assert.deepEqual([...T.classCounts([0,1,1,null,0,3,undefined,NaN])], [[0,2],[1,2],[3,1]]);
  assert.equal(T.classCounts([null,null]).size, 0);
});

test("finite extents preserve constants and nearest radial sample", () => {
  assert.deepEqual(T.extent([null,4,4]), [4,4]);
  assert.equal(T.extent([null,NaN]), null);
  assert.equal(T.nearest([0,2,4],3.8), 2);
  assert.equal(T.nearest([0,2,4],-3), 0);
});

test("default transect chooses continuous varying cells when global extrema are disconnected", () => {
  const field = {grid:{nx:5,nz:4,cell_m:1,origin_xz_m:[0,0],row_order:"z_increasing"}, values:[
    100,null,null,null,0,
    null,null,null,null,null,
    60,55,50,45,40,
    null,null,null,null,null
  ]};
  const selected = T.defaultTransect(field), cut = T.transect(field, selected.startIndex, selected.endIndex);
  assert.deepEqual([selected.startIndex, selected.endIndex], [10,14]);
  assert.deepEqual(cut.map(point => point.value), [60,55,50,45,40]);
  assert.equal(cut.filter(point => point.value === null).length, 0);
  assert.deepEqual(T.transect(field, 0, 4).map(point => point.value), [100,null,null,null,0]);
});

test("default transect scans columns, orders warmer first, and handles constant or missing grids", () => {
  const field = {grid:{nx:3,nz:4,cell_m:1,origin_xz_m:[0,0],row_order:"z_decreasing"}, values:[
    null,10,null,
    null,20,null,
    null,30,null,
    null,40,null
  ]};
  const selected = T.defaultTransect(field);
  assert.deepEqual([selected.startIndex, selected.endIndex], [10,1]);
  assert.deepEqual(T.transect(field, selected.startIndex, selected.endIndex).map(point => point.value), [40,30,20,10]);
  assert.equal(T.defaultTransect({...field,values:Array(12).fill(null)}), null);
  const constant = T.defaultTransect({...field,values:Array(12).fill(7)});
  assert.equal(constant.length,4);
  assert.equal(constant.range,0);
});
