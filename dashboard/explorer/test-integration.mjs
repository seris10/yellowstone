import test from 'node:test';
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';

const directory=process.env.DASHBOARD_PREVIEW;
if(!directory)throw new Error('Set DASHBOARD_PREVIEW to the generated site directory');
const source=await readFile(`${directory}/_worker.js`,'utf8');
const {default:worker}=await import(`data:text/javascript;base64,${Buffer.from(source).toString('base64')}`);
const environment={ASSETS:{fetch:async()=>new Response('approved asset',{status:200})}};
test('integrated explorer assets are explicitly allowed',async()=>{
  for(const asset of ['copy.js','temperature.js','temperature-pass.js','data/drainage.json']){
    assert.equal((await worker.fetch(new Request(`https://fixture.invalid/dashboard/explorer/${asset}`),environment)).status,200);
  }
  for(const route of ['/dashboard/explorer/','/dashboard/explorer/app.js','/dashboard/explorer/vendor/three.core.js','/dashboard/explorer/data/replay.json','/dashboard/explorer/data/normal-full.png','/dashboard/explorer/data/normal-core.png','/dashboard/explorer/vendor/postprocessing/EffectComposer.js','/dashboard/explorer/vendor/shaders/OutputShader.js']){
    assert.equal((await worker.fetch(new Request(`https://fixture.invalid${route}`),environment)).status,200);
  }
});
test('internal sources and unlisted data remain unavailable',async()=>{
  for(const route of ['/dashboard/build_public.py','/dashboard/data.json','/dashboard/fixes.json','/dashboard/internal/','/dashboard/explorer/export.py','/dashboard/explorer/browser-check.cjs','/dashboard/explorer/data/unlisted.json']){
    assert.equal((await worker.fetch(new Request(`https://fixture.invalid${route}`),environment)).status,404);
  }
});
test('method restriction and canonical redirects remain enforced',async()=>{
  assert.equal((await worker.fetch(new Request('https://fixture.invalid/dashboard/explorer/',{method:'POST'}),environment)).status,405);
  const response=await worker.fetch(new Request('https://fixture.invalid/dashboard/explorer'),environment);
  assert.equal(response.status,302);assert.equal(response.headers.get('Location'),'https://fixture.invalid/dashboard/explorer/');
});
test('dashboard navigation links to explorer and CSP is unchanged',async()=>{
  const html=await readFile(`${directory}/dashboard/index.html`,'utf8');assert.match(html,/href="\/dashboard\/explorer\/"/);
  const headers=await readFile(`${directory}/_headers`,'utf8');assert.match(headers,/script-src 'self';/);assert.doesNotMatch(headers,/script-src[^;]*unsafe-inline/);
  const explorer=await readFile(`${directory}/dashboard/explorer/index.html`,'utf8');assert.doesNotMatch(explorer,/<script[^>]*type="importmap"/);
});
