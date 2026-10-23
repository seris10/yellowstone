import {installExtras} from './layers.js';
import * as THREE from './vendor/three.module.js';
import {EffectComposer} from './vendor/postprocessing/EffectComposer.js';
import {RenderPass} from './vendor/postprocessing/RenderPass.js';
import {UnrealBloomPass} from './vendor/postprocessing/UnrealBloomPass.js';
import {OutputPass} from './vendor/postprocessing/OutputPass.js';
import {OrbitControls} from './vendor/OrbitControls.js';
import {TemperaturePass} from './temperature-pass.js';
import {temperaturePalette, changePalette, finiteRange, changeLimit, temperatureValue, temperatureRange, colorFraction} from './temperature.js';
import {copy, layerCopy, basisLabel, featureName} from './copy.js';
import {terrainValue, worldCoordinates, sampleIndex, validateReplay, verifiedBytes} from './model.js';

const $ = id => document.getElementById(id);
const number = (n, digits = 1) => n === null ? copy.unavailable : Number(n).toLocaleString('en-US', {maximumFractionDigits: digits, minimumFractionDigits: digits});
const text = (tag, content, className) => {const el = document.createElement(tag); el.textContent = content; if (className) el.className = className; return el;};
let manifest, features, replay, drainageData, crownData, terrain, terrainRange, mesh, wire, crownMesh;
let extras;
let deltaLimit=.06,temperatureAnchor=null;
let extent = 'core', frame = 0, selected = {type:'terrain', index:0}, playing = false;
let renderPending = false, lastTick = 0, loadGeneration = 0;
const normalMaps = {}, grids = {}, scene = new THREE.Scene(), world = new THREE.Group(), groups = {};
const materialResources = [], geometryResources = [];
function createRenderer() {
  try {return new THREE.WebGLRenderer({antialias:true, alpha:true, powerPreference:'high-performance'});}
  catch(error) {$('loading').textContent=copy.webglUnavailable;throw error;}
}
const renderer = createRenderer();
renderer.setPixelRatio(Math.min(devicePixelRatio, 2));
renderer.outputColorSpace = THREE.SRGBColorSpace;
renderer.setClearColor(0x000000, 1);
scene.background = new THREE.Color('#020304');
renderer.toneMapping = THREE.ACESFilmicToneMapping;
renderer.toneMappingExposure = 1.1;
$('viewport').appendChild(renderer.domElement);
const camera = new THREE.PerspectiveCamera(38, 1, 1, 24000);
const controls = new OrbitControls(camera, renderer.domElement);
controls.enableDamping = false;
controls.minDistance = 50; controls.maxDistance = 12000;
controls.maxPolarAngle = Math.PI * .49;
controls.addEventListener('change', draw);
scene.add(world);
const ambient = new THREE.HemisphereLight(0x8ba6ed, 0x0a0620, .65);
const sun = new THREE.DirectionalLight(0x98e8ff, 3.6);
sun.position.set(-650, 450, 150);
scene.add(ambient, sun);
const rim = new THREE.DirectionalLight(0xba84ff, 2.3); rim.position.set(800, 260, -600); scene.add(rim);
const composer = new EffectComposer(renderer);
composer.renderTarget1.samples=4;composer.renderTarget2.samples=4;
const renderPass = new RenderPass(scene, camera);
const bloom = new UnrealBloomPass(new THREE.Vector2(1,1), .55, .3, .22);
const outputPass = new OutputPass();
composer.addPass(renderPass);composer.addPass(bloom);composer.addPass(new TemperaturePass(scene,camera));composer.addPass(outputPass);
const raycaster = new THREE.Raycaster(); raycaster.layers.enable(1);raycaster.params.Line.threshold = 5;
const pointer = new THREE.Vector2();
const ramps={temperature:temperaturePalette.map(c=>new THREE.Color(c)),change:changePalette.map(c=>new THREE.Color(c))};

function draw() {
  if (renderPending) return;
  renderPending = true;
  requestAnimationFrame(() => {composer.render(); renderPending = false;});
}
function size() {
  const r = $('viewport').getBoundingClientRect();
  const fit = Math.max(1, 1.2 / (r.width / r.height)) / Math.max(1, 1.2 / camera.aspect);
  camera.position.sub(controls.target).multiplyScalar(fit).add(controls.target);
  renderer.setSize(r.width, r.height, false);composer.setSize(r.width,r.height); camera.aspect = r.width / r.height; camera.updateProjectionMatrix(); draw();
}
new ResizeObserver(size).observe($('viewport'));

function color(value) {
  const mode=$('temperature-scale').value,range=temperatureRange(mode,manifest.temperature_range_c,temperatureAnchor,deltaLimit);
  const fraction=colorFraction(value,range);
  if(fraction===null)return new THREE.Color('#69717e');
  const ramp=ramps[mode==='change'?'change':'temperature'],t=fraction*(ramp.length-1),i=Math.min(ramp.length-2,Math.floor(t));
  return ramp[i].clone().lerp(ramp[i+1],t-i);
}
function updateTemperature() {
  if(!replay)return;
  const mode=$('temperature-scale').value,range=temperatureRange(mode,manifest.temperature_range_c,temperatureAnchor,deltaLimit);
  const river=groups.river,attribute=river?.userData.colors;
  let clipped=0;
  replay.cells.forEach((c,index)=>{
    const value=temperatureValue(replay,frame,index,mode);
    if(value!==null&&(value<range[0]||value>range[1]))clipped++;
    const span=river?.userData.ranges[index];if(!span)return;
    const shade=extras?.riverColor(index,frame)||color(value);
    for(let v=span[0];v<span[1];v++)attribute.setXYZ(v,shade.r,shade.g,shade.b);
  });
  if(attribute)attribute.needsUpdate=true;
  $('legend-title').textContent=mode==='change'?'Change since start · °C':'River temperature · °C';
  const signed=v=>`${v>0&&mode==='change'?'+':''}${number(v,2)} °C`;
  $('legend-min').textContent=signed(range[0]);$('legend-max').textContent=signed(range[1]);
  $('legend-middle').textContent=signed((range[0]+range[1])/2);
  $('temperature-ramp').style.background=`linear-gradient(90deg,${(mode==='change'?changePalette:temperaturePalette).join(',')})`;
  $('temperature-note').textContent=mode==='focus'?`${number(temperatureAnchor,3)} °C ± 0.05°C. ${clipped} sections outside the window use the end colors.`:mode==='change'?'Each section compared with its starting temperature.':'Fixed range for this run.';
  $('temperature-focus').hidden=mode!=='focus';extras?.legend();
  draw();
}
function focusTemperature() {
  const i=selected.type==='river'?selected.index:Math.floor(replay.cells.length/2);
  if(selected.type!=='river'){selected={type:'river',index:i};$('feature-type').value='river';updateOptions();inspect();}
  const value=replay.frames[frame].values[i];
  if(value===null)return;
  temperatureAnchor=value;updateTemperature();
}
function elevation(x,z) {return terrainValue(terrain,manifest.terrain[extent],x,z);}
function position(x,z,lift=1.5) {const y=elevation(x,z);return y === null ? null : new THREE.Vector3(x,y-manifest.georeference.origin[2]+lift,z);}
function track(geometry, material) {geometryResources.push(geometry);if(material)materialResources.push(material);return new THREE.Mesh(geometry,material);}
function group(name) {const g = new THREE.Group();world.add(g);groups[name]=g;return g;}
function clearWorld() {
  world.clear();
  geometryResources.splice(0).forEach(g=>g.dispose());
  materialResources.splice(0).forEach(m=>m.dispose());
  for (const name of Object.keys(groups)) delete groups[name];
  crownMesh=null;wire=null;
}

function terrainMaterial() {
  const mat = new THREE.MeshStandardMaterial({color:0x314878,roughness:.72,metalness:.12,normalMap:normalMaps[extent],normalMapType:THREE.ObjectSpaceNormalMap,side:THREE.DoubleSide});
  mat.userData.uniforms = {mode:{value:0},interval:{value:10}};
  mat.onBeforeCompile = shader => {
    Object.assign(shader.uniforms, {surfaceMode:mat.userData.uniforms.mode,contourInterval:mat.userData.uniforms.interval});
    shader.vertexShader = 'varying float heightMeters; varying vec3 sourceNormal;\n'+shader.vertexShader;
    shader.vertexShader = shader.vertexShader.replace('#include <begin_vertex>','#include <begin_vertex>\nheightMeters = position.y + 2200.0; sourceNormal = normal;');
    shader.fragmentShader = 'varying float heightMeters; varying vec3 sourceNormal; uniform float surfaceMode; uniform float contourInterval;\n'+shader.fragmentShader;
    shader.fragmentShader = shader.fragmentShader.replace('#include <color_fragment>',`#include <color_fragment>
      vec3 detailNormal = normalize(texture2D(normalMap,vNormalMapUv).xyz * 2. - 1.);
      float slope = acos(clamp(normalize(sourceNormal).y,0.0,1.0)) / 1.5707963;
      if(surfaceMode > 3.5) {
        float h = clamp((heightMeters-2190.)/245.,0.,1.);
        vec3 valley = vec3(.008,.018,.045);
        vec3 middle = mix(vec3(.025,.09,.19),vec3(.14,.045,.21),smoothstep(-.35,.5,detailNormal.x));
        vec3 ridge = vec3(.15,.44,.53);
        diffuseColor.rgb = mix(valley,middle,smoothstep(0.,.4,h));
        diffuseColor.rgb = mix(diffuseColor.rgb,ridge,smoothstep(.35,1.,h)*.78);
      }
      if(surfaceMode > 0.5 && surfaceMode < 1.5) diffuseColor.rgb = mix(vec3(.07,.16,.22),vec3(.30,.63,.64),floor((heightMeters-2190.)/10.)/25.);
      if(surfaceMode > 1.5 && surfaceMode < 2.5) diffuseColor.rgb = mix(vec3(.07,.22,.30),vec3(.88,.55,.25),slope);
    `);
    shader.fragmentShader = shader.fragmentShader.replace('#include <emissivemap_fragment>',`#include <emissivemap_fragment>
      if(surfaceMode < .5){float band=heightMeters/contourInterval; float edge=abs(fract(band-.5)-.5)/max(fwidth(band),.001);float line=1.-smoothstep(.2,1.1,edge);totalEmissiveRadiance += vec3(.09,.32,.37)*line;}
    `);
  };
  return mat;
}

function makeTerrain() {
  const spec=manifest.terrain[extent], n=spec.n;
  const geometry=new THREE.BufferGeometry();
  const points=new Float32Array(n*n*3),uv=new Float32Array(n*n*2),indices=new Uint32Array((n-1)*(n-1)*6);let cursor=0;
  for(let row=0;row<n;row++)for(let col=0;col<n;col++) {
    const i=row*n+col;uv[i*2]=col/(n-1);uv[i*2+1]=row/(n-1);points[i*3]=spec.start[0]+col*spec.spacing_m;points[i*3+1]=terrain[i]-2200;points[i*3+2]=spec.start[1]+row*spec.spacing_m;
    if(row<n-1&&col<n-1){indices[cursor++]=i;indices[cursor++]=i+n;indices[cursor++]=i+1;indices[cursor++]=i+1;indices[cursor++]=i+n;indices[cursor++]=i+n+1;}
  }
  geometry.setAttribute('position',new THREE.BufferAttribute(points,3));geometry.setAttribute('uv',new THREE.BufferAttribute(uv,2));geometry.setIndex(new THREE.BufferAttribute(indices,1));geometry.computeVertexNormals();geometry.computeBoundingSphere();
  mesh=track(geometry,terrainMaterial());mesh.userData={type:'terrain',index:0};world.add(mesh);
  const wireMaterial=new THREE.MeshBasicMaterial({color:0x5c98aa,wireframe:true,transparent:true,opacity:.12,depthWrite:false});
  materialResources.push(wireMaterial);wire=new THREE.Mesh(geometry,wireMaterial);wire.position.y=.15;world.add(wire);wire.visible=$('wire').checked;
  const edge=[];for(let c=0;c<n;c++)edge.push(c);for(let r=1;r<n;r++)edge.push(r*n+n-1);for(let c=n-2;c>=0;c--)edge.push((n-1)*n+c);for(let r=n-2;r>0;r--)edge.push(r*n);
  const slabPoints=[],slabIndices=[],bottom=terrain.reduce((a,b)=>Math.min(a,b),Infinity)-2200-35;
  edge.forEach((id,i)=>{slabPoints.push(points[id*3],points[id*3+1],points[id*3+2],points[id*3],bottom,points[id*3+2]);const a=2*i,b=2*((i+1)%edge.length);slabIndices.push(a,a+1,b,b,a+1,b+1);});
  const slab=new THREE.BufferGeometry();slab.setAttribute('position',new THREE.Float32BufferAttribute(slabPoints,3));slab.setIndex(slabIndices);slab.computeVertexNormals();
  const skirtMaterial = new THREE.MeshStandardMaterial({color:0x101e49,emissive:0x081f4b,emissiveIntensity:.45,side:THREE.DoubleSide,roughness:.8});
  skirtMaterial.onBeforeCompile = shader => {
    shader.vertexShader='varying float skirtDepth;\n'+shader.vertexShader;
    shader.vertexShader=shader.vertexShader.replace('#include <begin_vertex>', '#include <begin_vertex>\nskirtDepth = position.y;');
    shader.fragmentShader='varying float skirtDepth;\n'+shader.fragmentShader;
    shader.fragmentShader=shader.fragmentShader.replace('#include <color_fragment>', `#include <color_fragment>\ndiffuseColor.rgb *= .25 + .75 * smoothstep(${bottom.toFixed(3)},${(bottom+50).toFixed(3)},skirtDepth);`);
  };
  world.add(track(slab,skirtMaterial));
  const grid=new THREE.GridHelper(spec.spacing_m*(n-1)*1.8,24,0x1b3450,0x15203a);
  grid.position.y=bottom-5;grid.material.transparent=true;grid.material.opacity=.28;
  geometryResources.push(grid.geometry);materialResources.push(grid.material);world.add(grid);
  const outline=new THREE.BufferGeometry().setFromPoints([...edge,edge[0]].map(id=>new THREE.Vector3(points[id*3],points[id*3+1]+.5,points[id*3+2])));
  geometryResources.push(outline);const outlineMat=new THREE.LineBasicMaterial({color:0x3486d9,transparent:true,opacity:.9});materialResources.push(outlineMat);world.add(new THREE.Line(outline,outlineMat));
}

function lines(name,rows,pointsOf,lineColor,closed=false) {
  const g=group(name);
  rows.forEach((row,index)=>{
    const points=pointsOf(row),segments=[];
    const list=closed?[...points,points[0]]:points;
    for(let i=1;i<list.length;i++){
      const a=list[i-1],b=list[i]; const p=position(a[0],a.length===3?a[2]:a[1],2),q=position(b[0],b.length===3?b[2]:b[1],2);
      if(p&&q){
        const count=Math.max(1,Math.ceil(p.distanceTo(q)/manifest.terrain[extent].spacing_m));
        let previous=p;
        for(let j=1;j<=count;j++){const t=j/count,next=position(THREE.MathUtils.lerp(p.x,q.x,t),THREE.MathUtils.lerp(p.z,q.z,t),2);if(next){segments.push(previous,next);previous=next;}}
      }
    }
    const geom=new THREE.BufferGeometry().setFromPoints(segments),mat=new THREE.LineBasicMaterial({color:typeof lineColor==='function'?lineColor(row):lineColor,transparent:true,opacity:.85,depthTest:true});
    geometryResources.push(geom);materialResources.push(mat);
    if(name==='hydro')mat.color.multiplyScalar(1.6);
    if(name==='routes')mat.opacity=.32;
    const line=new THREE.LineSegments(geom,mat);line.userData={type:name,index,baseOpacity:mat.opacity};g.add(line);
    if(name==='hydro') {
      const ribbon=[],width=extent==='full'?2.2:1.0;
      for(let k=0;k<segments.length;k+=2){const a=segments[k],b=segments[k+1],dx=b.x-a.x,dz=b.z-a.z,len=Math.hypot(dx,dz)||1,ox=-dz/len*width,oz=dx/len*width;
        ribbon.push(a.x+ox,a.y,a.z+oz,a.x-ox,a.y,a.z-oz,b.x+ox,b.y,b.z+oz,b.x+ox,b.y,b.z+oz,a.x-ox,a.y,a.z-oz,b.x-ox,b.y,b.z-oz);
      }
      const ribbonGeometry=new THREE.BufferGeometry();ribbonGeometry.setAttribute('position',new THREE.Float32BufferAttribute(ribbon,3));
      const ribbonMaterial=new THREE.MeshBasicMaterial({color:new THREE.Color(0x40d9ff).multiplyScalar(1.5),side:THREE.DoubleSide,transparent:true,opacity:.7,depthWrite:false});
      const stream=track(ribbonGeometry,ribbonMaterial);stream.userData={type:name,index,baseOpacity:ribbonMaterial.opacity};g.add(stream);
    }
  });
}

function makeDrainage() {
  if(groups.drainage){world.remove(groups.drainage);for(const object of groups.drainage.children){object.geometry.dispose();object.material.dispose();geometryResources.splice(geometryResources.indexOf(object.geometry),1);materialResources.splice(materialResources.indexOf(object.material),1);}}
  const g=group('drainage'),level=drainageData.levels.find(l=>l.threshold_ha===Number($('drainage-density').value));
  const vertices=[],colors=[],branches=[],palette=['#405bc4','#4f83d9','#61afed','#71d7f1','#a7f2ec'];
  level.branches.forEach((branch,index)=>{
    const shade=new THREE.Color(palette[Math.min(branch.order-1,palette.length-1)]);
    for(let i=1;i<branch.points.length;i++){
      const a=branch.points[i-1],b=branch.points[i],p=position(a[0],a[1],1),q=position(b[0],b[1],1);
      if(!p||!q)continue;
      vertices.push(...p.toArray(),...q.toArray());colors.push(shade.r,shade.g,shade.b,shade.r,shade.g,shade.b);branches.push(index);
    }
  });
  const geometry=new THREE.BufferGeometry();geometry.setAttribute('position',new THREE.Float32BufferAttribute(vertices,3));geometry.setAttribute('color',new THREE.Float32BufferAttribute(colors,3));
  const material=new THREE.LineBasicMaterial({vertexColors:true,transparent:true,opacity:.78,depthWrite:false});geometryResources.push(geometry);materialResources.push(material);
  const lines=new THREE.LineSegments(geometry,material);lines.userData={type:'drainage',branches};g.add(lines);g.visible=$('drainage').checked;
  $('drainage-count').textContent=`${number(level.branch_count,0)} paths · calculated from elevation`;
}
function makeRiver() {
  const g=group('river'),vertices=[],outlines=[],triangleCells=[],ranges={};
  const halfWidth=extent==='full'?14:4;
  function edgePoint(cell,neighbor,sign){
    const p=cell.position_xyz;
    if(neighbor&&neighbor.river_id===cell.river_id){const q=neighbor.position_xyz;return [(p[0]+q[0])/2,(p[2]+q[2])/2];}
    const other=replay.cells[replay.cells.indexOf(cell)-sign];
    if(other&&other.river_id===cell.river_id){const q=other.position_xyz;return [p[0]+(p[0]-q[0])/2,p[2]+(p[2]-q[2])/2];}
    return [p[0],p[2]];
  }
  replay.cells.forEach((c,index)=>{
    const a=edgePoint(c,replay.cells[index-1],-1),b=edgePoint(c,replay.cells[index+1],1),center=[c.position_xyz[0],c.position_xyz[2]],points=[a,center,b];
    const start=vertices.length/3;
    for(let side=1;side<points.length;side++){
      const p=points[side-1],q=points[side],length=Math.hypot(q[0]-p[0],q[1]-p[1]);if(length<.001)continue;
      const count=Math.max(1,Math.ceil(length/manifest.terrain[extent].spacing_m)),ox=-(q[1]-p[1])/length,oz=(q[0]-p[0])/length;
      for(let part=0;part<count;part++){
        const u=part/count,v=(part+1)/count,one=position(THREE.MathUtils.lerp(p[0],q[0],u),THREE.MathUtils.lerp(p[1],q[1],u),7),two=position(THREE.MathUtils.lerp(p[0],q[0],v),THREE.MathUtils.lerp(p[1],q[1],v),7);
        if(!one||!two)continue;
        for(const [target,width,lift]of [[vertices,halfWidth,.1],[outlines,halfWidth*1.5,0]]){
          const dx=ox*width,dz=oz*width;
          target.push(one.x+dx,one.y+lift,one.z+dz,one.x-dx,one.y+lift,one.z-dz,two.x+dx,two.y+lift,two.z+dz,two.x+dx,two.y+lift,two.z+dz,one.x-dx,one.y+lift,one.z-dz,two.x-dx,two.y+lift,two.z-dz);
        }
        triangleCells.push(index,index);
      }
    }
    ranges[index]=[start,vertices.length/3];
  });
  const geometry=new THREE.BufferGeometry();geometry.setAttribute('position',new THREE.Float32BufferAttribute(vertices,3));const colors=new THREE.BufferAttribute(new Float32Array(vertices.length),3);geometry.setAttribute('color',colors);
  const river=track(geometry,new THREE.MeshBasicMaterial({vertexColors:true,side:THREE.DoubleSide}));river.layers.set(1);river.userData={type:'river',triangleCells};river.renderOrder=2;g.add(river);
  const outlineGeometry=new THREE.BufferGeometry();outlineGeometry.setAttribute('position',new THREE.Float32BufferAttribute(outlines,3));
  const border=track(outlineGeometry,new THREE.MeshBasicMaterial({color:0x030912,side:THREE.DoubleSide}));border.layers.set(1);border.renderOrder=1;g.add(border);
  g.userData={ranges,colors};updateTemperature();
}

function makeAppearance() {
  const g=group('appearance');
  features.pools.forEach((pool,index)=>{
    if(!pool.name || !/prismatic|excelsior|opal|turquoise/i.test(pool.name))return;
    const shape=new THREE.Shape(pool.ring.map(p=>new THREE.Vector2(p[0],p[1])));
    const geom=new THREE.ShapeGeometry(shape),p=geom.getAttribute('position');
    for(let i=0;i<p.count;i++){const x=p.getX(i),z=p.getY(i);const y=elevation(x,z);if(y===null){geom.dispose();return;}p.setXYZ(i,x,y-2200+2.5,z);}
    geom.computeVertexNormals();const mat=new THREE.MeshBasicMaterial({color:/prismatic/i.test(pool.name)?0xa9a14f:0x6c8eb9,transparent:true,opacity:.24,side:THREE.DoubleSide,depthWrite:false});
    const m=track(geom,mat);m.userData={type:'pools',index};g.add(m);
  });
}

async function loadCrowns() {
  if(!crownData) {
    $('canopy').disabled=true;
    try {const bytes=await verifiedBytes('data/crowns.json',manifest.assets['crowns.json']);crownData=JSON.parse(new TextDecoder().decode(bytes));}
    finally {$('canopy').disabled=false;}
  }
  if(!$('canopy').checked && selected.type!=='canopy')return;
  if(groups.canopy){world.remove(groups.canopy);groups.canopy.clear();}
  const g=group('canopy');
  const geom=new THREE.CircleGeometry(1,8),mat=new THREE.MeshBasicMaterial({color:0x6bd7bc,transparent:true,opacity:.65,side:THREE.DoubleSide,depthWrite:false});
  geometryResources.push(geom);materialResources.push(mat);
  const rows=crownData.rows, included=[];
  for(let i=0;i<rows.length;i++){const r=rows[i];if(r[3]>=Number($('height').value)&&position(r[1],r[2]))included.push(i);}
  crownMesh=new THREE.InstancedMesh(geom,mat,included.length);crownMesh.userData={type:'canopy',indices:included};
  const dummy=new THREE.Object3D();
  included.forEach((id,i)=>{const r=rows[id];dummy.position.copy(position(r[1],r[2],2));dummy.rotation.x=-Math.PI/2;dummy.scale.set(r[5],r[5],1);dummy.updateMatrix();crownMesh.setMatrixAt(i,dummy.matrix);crownMesh.setColorAt(i,new THREE.Color().setHSL(.44,.45,.35+Math.min(r[3]/40,.5)));});
  g.add(crownMesh);g.visible=$('canopy').checked;draw();
}

async function rebuild(reset=true) {
  const generation=++loadGeneration;
  const target=$('extent').value,spec=manifest.terrain[target];
  if(!grids[target]){const bytes=await verifiedBytes(`data/${spec.file}`,manifest.assets[spec.file]);const grid=new Float32Array(bytes);if(grid.length!==spec.n*spec.n||!grid.every(Number.isFinite))throw new Error('Terrain support invalid');grids[target]=grid;}
  if(generation!==loadGeneration)return;
  if(!normalMaps[target]) {
    const normalSpec=spec.normal,bytes=await verifiedBytes(`data/${normalSpec.file}`,manifest.assets[normalSpec.file]);
    const bitmap=await createImageBitmap(new Blob([bytes],{type:'image/png'}),{colorSpaceConversion:'none'});
    const texture=new THREE.Texture(bitmap);texture.flipY=false;texture.colorSpace=THREE.NoColorSpace;
    texture.offset.fromArray(normalSpec.uv_offset);texture.repeat.fromArray(normalSpec.uv_scale);texture.needsUpdate=true;
    normalMaps[target]=texture;
  }
  if(generation!==loadGeneration)return;
  extent=target;terrain=grids[target];terrainRange=finiteRange(terrain);clearWorld();makeTerrain();
  lines('hydro',features.rivers,r=>r.points,0x6ee7f2);
  lines('routes',features.routes,r=>r.points,r=>r.kind==='road'?0xa1b2b8:0x769d91);
  lines('pools',features.pools,p=>p.ring,p=>p.outline_basis==='lidar_return_void'?0x9edcc5:0xc2e7ed,true);
  makeDrainage();makeRiver();makeAppearance();if(crownData||$('canopy').checked)await loadCrowns();
  if(extras)await extras.rebuild();
  visibility();surface();world.scale.y=Number($('exaggeration').value);
  updateScale();if(reset)resetView();
  $('elevation-min').textContent=`${number(terrainRange[0],0)} m`; $('elevation-max').textContent=`${number(terrainRange[1],0)} m`;
  $('extent-label').textContent=copy.extentLabel(extent);
  $('terrain-support').textContent=copy.terrainSupport(spec);
  updateOptions();inspect();draw();
}
function visibility() {
  for(const name of ['hydro','drainage','routes','pools','river','canopy','appearance'])if(groups[name])groups[name].visible=$(name).checked;
  const modeled=new Set(replay.cells.map(c=>c.river_id));
  for(const object of groups.hydro?.children||[]){const row=features.rivers[object.userData.index];object.material.opacity=object.userData.baseOpacity*($('river').checked&&modeled.has(row.id)?.12:1);}
  document.querySelector('.legend').hidden=!$('river').checked;extras?.compare();draw();
}
function surface() {if(!mesh)return;$('interval').closest('label').hidden=$('surface').value!=='contours';mesh.material.userData.uniforms.mode.value=['contours','elevation','slope','plain','relief'].indexOf($('surface').value);mesh.material.userData.uniforms.interval.value=Number($('interval').value);wire.visible=$('wire').checked;bloom.enabled=$('glow').checked;draw();}
function updateScale() {
  world.scale.y=Number($('exaggeration').value);
  $('scale-label').textContent=world.scale.y===1?'TRUE SCALE · 1.0×':`EXAGGERATED · ${world.scale.y.toFixed(1)}×`;
}
function resetView() {
  if(!mesh)return;
  const dir=new THREE.Vector3(1,.92,-.8).normalize(),right=new THREE.Vector3().crossVectors(new THREE.Vector3(0,1,0),dir).normalize(),up=new THREE.Vector3().crossVectors(dir,right);
  const min=terrainRange[0]-2200,max=terrainRange[1]-2200;
  controls.target.set(0,(min+max)*world.scale.y*.5,0);
  const tangent=Math.tan(THREE.MathUtils.degToRad(camera.fov*.5)),vertices=mesh.geometry.attributes.position;
  let distance=0;const p=new THREE.Vector3();
  for(let i=0;i<vertices.count;i+=Math.max(1,Math.floor(vertices.count/65536))){
    p.fromBufferAttribute(vertices,i);p.y*=world.scale.y;p.sub(controls.target);
    distance=Math.max(distance,p.dot(dir)+Math.abs(p.dot(right))/(tangent*camera.aspect)*1.16,p.dot(dir)+Math.abs(p.dot(up))/tangent*1.24);
  }
  camera.position.copy(controls.target).addScaledVector(dir,distance);controls.update();
  // Center the projected terrain, whose high ridges are not evenly distributed.
  for(let pass=0;pass<2;pass++){
    camera.updateMatrixWorld();let top=-Infinity,bottom=Infinity;
    for(let i=0;i<vertices.count;i+=Math.max(3,Math.floor(vertices.count/32768))){p.fromBufferAttribute(vertices,i);p.y*=world.scale.y;p.project(camera);top=Math.max(top,p.y);bottom=Math.min(bottom,p.y);}
    const shift=up.clone().multiplyScalar((top+bottom)*.5*distance*tangent);
    camera.position.add(shift);controls.target.add(shift);controls.update();
  }
  if(camera.aspect>1.1)camera.position.sub(controls.target).multiplyScalar(.93).add(controls.target);
  controls.update();draw();
}

function updateOptions() {
  const type=$('feature-type').value;selected.type=type;
  const select=$('feature');select.replaceChildren();
  const rows=type==='river'?replay.cells:type==='canopy'?crownData?.rows||[]:type==='hydro'?features.rivers:type==='drainage'?drainageData.levels.find(l=>l.threshold_ha===Number($('drainage-density').value)).branches:features[type]||[];
  $('feature-label').hidden=type==='terrain';
  const fragment=document.createDocumentFragment();
  rows.forEach((r,i)=>{const option=document.createElement('option');option.value=i;option.textContent=type==='canopy'?`${featureName(r,type,i)} · ${number(r[3])} m`:type==='river'?`${featureName(r,type,i)} · ${number(r.center_s_m,0)} m`:featureName(r,type,i);fragment.appendChild(option);});
  select.appendChild(fragment);selected.index=Math.min(selected.index,Math.max(0,rows.length-1));select.value=String(selected.index);
}
function addPair(dl,label,value) {dl.append(text('dt',label),text('dd',value));}
function inspect(point=null) {
  if(!manifest)return;
  const root=$('details');root.replaceChildren();$('chart').replaceChildren();
  const type=selected.type,i=selected.index,dl=document.createElement('dl');let name,big=null,coords,row;
  const spec=manifest.terrain[extent];
  if(type==='terrain') {
    name='Terrain';coords=point?worldCoordinates(point.x,point.y+2200,point.z,manifest.georeference.origin):null;
    if(coords)big=`${number(coords.elevation,2)} m`;
    addPair(dl,copy.resolutionLabel,copy.spacing(spec));addPair(dl,extent==='core'?copy.acquisitionLabel:'Elevation source date',extent==='core'?'September–October 2020':'2020 project · saved export from 2026');addPair(dl,copy.scaleLabel,copy.verticalScale($('exaggeration').value));
  } else if(type==='river') {
    const c=replay.cells[i],f=replay.frames[frame];name=featureName(c,type,i);big=f.values[i]===null?copy.unavailable:`${number(f.values[i],3)} °C`;
    coords=worldCoordinates(c.position_xyz[0],c.position_xyz[1]+2200,c.position_xyz[2],manifest.georeference.origin);
    addPair(dl,copy.chainageLabel,`${number(c.start_s_m)}–${number(c.end_s_m)} m`);addPair(dl,copy.modelTimeLabel,`${number(f.t,0)} s`);
    const delta=temperatureValue(replay,frame,i,'change');addPair(dl,'Change since start',delta===null?copy.unavailable:`${delta>0?'+':''}${number(delta,3)} °C`);chart(i);
  } else if(type==='canopy'&&crownData) {
    const r=crownData.rows[i];name=featureName(r,type,i);big=`${number(r[3],3)} m`;
    coords=worldCoordinates(r[1],elevation(r[1],r[2]),r[2],manifest.georeference.origin);
    addPair(dl,'Measurement',copy.crownHeightLabel);addPair(dl,copy.crownAreaLabel,`${number(r[4],2)} m²`);addPair(dl,copy.crownRadiusLabel,`${number(r[5],3)} m`);addPair(dl,copy.crownCountLabel,copy.crownCount(crownData.rows.length));
  } else if(type==='drainage') {
    row=drainageData.levels.find(l=>l.threshold_ha===Number($('drainage-density').value)).branches[i];if(!row)return;
    name=featureName(row,type,i);addPair(dl,'Branch order',String(row.order));addPair(dl,'Upstream area within this map',`${number(row.area_start_m2/10000,2)}–${number(row.area_end_m2/10000,2)} ha`);
    addPair(dl,'Smallest catchment shown',`${$('drainage-density').value} ha`);
  } else {
    row=type==='hydro'?features.rivers[i]:features[type]?.[i];if(!row)return;name=featureName(row,type,i);
    if(type==='pools'){addPair(dl,'Area',`${number(row.area_m2)} m²`);addPair(dl,copy.poolTemperatureLabel,`${number(row.t_center_c)} °C · ${basisLabel(row.t_center_basis)}`);addPair(dl,copy.poolDepthLabel,basisLabel(row.depth_center_basis));addPair(dl,copy.poolColorLabel,copy.poolColor);coords=worldCoordinates(row.center_xz[0],elevation(...row.center_xz),row.center_xz[1],manifest.georeference.origin);}
    if(type==='routes')addPair(dl,copy.routeKindLabel,basisLabel(row.kind));
  }
  const info=layerCopy(type,{extent,spec,row,buildId:manifest.build_id});
  root.append(text('h2',name),text('span',info.classification,`badge ${type==='river'?'modeled':type==='terrain'||type==='canopy'||type==='drainage'?'derived':''}`));
  if(big)root.append(text('p',big,'big'));
  if(coords){addPair(dl,copy.coordinateLabel,`${number(coords.easting,2)} E / ${number(coords.northing,2)} N`);addPair(dl,type==='river'?copy.modelElevationLabel:copy.terrainElevationLabel,coords.elevation===null?copy.outsideTerrain:`${number(coords.elevation,2)} m NAVD88`);}
  root.append(dl,text('p',info.support));
  const details=document.createElement('details');details.className='sources';details.append(text('summary',copy.sourceDetailsLabel),text('p',info.source),text('p',info.limit));
  if(type==='river')details.append(text('p',copy.validation));root.append(details);extras?.selection(type,i);
}

function chart(index) {
  const values=replay.frames.map(f=>f.values[index]);const finite=values.filter(v=>v!==null);if(!finite.length)return;
  const low=Math.min(...finite)-.03,high=Math.max(...finite)+.03,maxT=replay.frames.at(-1).t;
  const x=t=>35+t/maxT*205,y=v=>120-(v-low)/(high-low)*95;
  const ns='http://www.w3.org/2000/svg',svg=document.createElementNS(ns,'svg');svg.setAttribute('viewBox','0 0 260 153');svg.setAttribute('role','img');svg.setAttribute('aria-label',copy.chartAria);
  function element(name,attrs){const el=document.createElementNS(ns,name);for(const [k,v]of Object.entries(attrs))el.setAttribute(k,v);svg.append(el);return el;}
  element('path',{d:'M35 20V120H240',fill:'none',stroke:'#395262'});
  let d='',gap=true;replay.frames.forEach((f,i)=>{if(values[i]===null){gap=true;return;}d+=`${gap?'M':'L'}${x(f.t).toFixed(2)} ${y(values[i]).toFixed(2)}`;gap=false;});
  element('path',{d,fill:'none',stroke:'#8fdae5','stroke-width':1.4});
  element('line',{x1:x(replay.frames[frame].t),x2:x(replay.frames[frame].t),y1:20,y2:120,stroke:'#e5bc85','stroke-dasharray':'3 3'});
  for(const [label,px,py] of [[`${number(high,2)} °C`,3,13],[number(low,2),3,126],['0 s',35,141],[`${maxT} s`,207,141]]){element('text',{x:px,y:py,fill:'#9cb4c2','font-size':9}).textContent=label;}
  $('chart').append(svg,text('p',copy.chartCaption));
}

function setFrame(value) {
  frame=sampleIndex(value,replay.frames.length);$('time').value=String(frame);
  updateTemperature();
  const f=replay.frames[frame],time=new Date(Date.parse(manifest.start_utc)+f.t*1000).toISOString().slice(11,19);
  $('model-time').textContent=`${number(f.t,0)} s · ${time} UTC`;
  if(selected.type==='river')inspect();extras?.onFrame();draw();
}
function tick(now) {if(!playing)return;if(now-lastTick>=120){if(frame===replay.frames.length-1){stop();return;}setFrame(frame+1);lastTick=now;}requestAnimationFrame(tick);}
function stop(){playing=false;$('play').textContent='▶ Play';$('play').setAttribute('aria-label',copy.playAria);}
function select(type,index,point=null) {selected={type,index};$('feature-type').value=type;updateOptions();if(type==='river'&&$('temperature-scale').value==='focus')focusTemperature();inspect(point);}

let down;
renderer.domElement.addEventListener('pointerdown',e=>{down=[e.clientX,e.clientY];});
renderer.domElement.addEventListener('pointerup',e=>{
  if(!manifest||!down||Math.hypot(e.clientX-down[0],e.clientY-down[1])>5)return;
  const r=renderer.domElement.getBoundingClientRect();pointer.set((e.clientX-r.left)/r.width*2-1,-(e.clientY-r.top)/r.height*2+1);raycaster.setFromCamera(pointer,camera);
  const targets=[...Object.values(groups).filter(g=>g.visible).flatMap(g=>g.children),mesh];
  const hits=raycaster.intersectObjects(targets,false).filter(h=>h.object.userData.type);
  if(!hits.length)return;
  const hit=hits.find(h=>h.object!==mesh)||hits[0],data=hit.object.userData;
  const point=world.worldToLocal(hit.point.clone());if(extras?.pick(point,hit))return;select(data.type,data.type==='canopy'?data.indices[hit.instanceId]:data.type==='drainage'?data.branches[Math.floor(hit.index/2)]:data.type==='river'?data.triangleCells[hit.faceIndex]:data.index,point);
});

function failure(error) {stop();$('loading').hidden=false;$('loading').textContent=copy.failure(error);console.error(error);}
for(const id of ['surface','interval','wire','glow'])$(id).addEventListener('change',surface);
for(const id of ['hydro','drainage','routes','pools','river','appearance'])$(id).addEventListener('change',visibility);
$('temperature-scale').addEventListener('change',()=>{if($('temperature-scale').value==='focus')focusTemperature();else updateTemperature();});
$('temperature-focus').addEventListener('click',()=>{stop();focusTemperature();});
$('drainage-density').addEventListener('change',()=>{makeDrainage();if(selected.type==='drainage'){selected.index=0;updateOptions();inspect();}draw();});
$('canopy').addEventListener('change',()=>loadCrowns().then(visibility).catch(failure));
$('height').addEventListener('input',()=>{$('height-value').textContent=`${$('height').value} m`;if(crownData)loadCrowns().catch(failure);});
$('extent').addEventListener('change',()=>rebuild().catch(failure));
$('exaggeration').addEventListener('change',()=>{updateScale();inspect();resetView();});
$('lighting').addEventListener('input',()=>{const hour=Number($('lighting').value),angle=(hour-6)/14*Math.PI;sun.position.set(Math.cos(angle)*900,Math.sin(angle)*600,150);sun.intensity=1.2+Math.sin(angle)*2.4;$('light-value').textContent=`${Math.floor(hour)}:${hour%1?'30':'00'}`;draw();});
$('reset').addEventListener('click',resetView);
$('north').addEventListener('click',()=>{camera.position.set(controls.target.x,extent==='core'?1700:5500,controls.target.z+1);controls.update();});
$('viewpoint').addEventListener('change',()=>{const anchor=features.anchors.find(a=>a.id===$('viewpoint').value);if(!anchor){resetView();return;}const p=anchor.position,t=anchor.target;camera.position.set(p[0]+180,(p[1]+240)*world.scale.y,p[2]+260);controls.target.set(t[0],t[1]*world.scale.y,t[2]);controls.update();});
$('feature-type').addEventListener('change',async()=>{selected.index=0;if($('feature-type').value==='canopy'&&!crownData){selected.type='canopy';await loadCrowns().catch(failure);}updateOptions();inspect();});
$('feature').addEventListener('change',()=>{selected.index=Number($('feature').value);if(selected.type==='river'&&$('temperature-scale').value==='focus')focusTemperature();inspect();});
$('time').addEventListener('input',()=>{stop();setFrame($('time').value);});
$('last').addEventListener('click',()=>{stop();setFrame(replay.frames.length-1);});
$('play').addEventListener('click',()=>{if(playing){stop();return;}if(frame===replay.frames.length-1)setFrame(0);playing=true;$('play').textContent='Ⅱ Pause';$('play').setAttribute('aria-label',copy.pauseAria);lastTick=0;requestAnimationFrame(tick);});
document.addEventListener('visibilitychange',()=>{if(document.hidden)stop();});

async function start() {
  const response=await fetch('data/manifest.json');if(!response.ok)throw new Error('Manifest unavailable');manifest=await response.json();
  const load=async name=>JSON.parse(new TextDecoder().decode(await verifiedBytes(`data/${name}`,manifest.assets[name])));
  [features,replay,drainageData]=await Promise.all([load('features.json'),load('replay.json'),load('drainage.json')]);validateReplay(replay);extras=installExtras({THREE,$,world,scene,groups,track,group,position,elevation,draw,inspect,select,stop,updateTemperature,getState:()=>({manifest,features,replay,frame,extent,selected,crownData}),loadCrowns,setReplay:value=>{replay=value;deltaLimit=changeLimit(replay);setFrame(frame);},setFrame});await extras.ready;deltaLimit=changeLimit(replay);
  $('time').max=String(replay.frames.length-1);$('snapshot').textContent=copy.snapshot();$('run-details').textContent=copy.runDetails(manifest,replay.frames.length);
  $('legend-min').textContent=`${number(manifest.temperature_range_c[0],2)} °C`;$('legend-max').textContent=`${number(manifest.temperature_range_c[1],2)} °C`;
  await rebuild();setFrame(0);$('loading').hidden=true;size();
  document.documentElement.dataset.ready='true';
}
start().catch(failure);
window.addEventListener('pagehide',()=>{stop();controls.dispose();clearWorld();for(const texture of Object.values(normalMaps)){texture.image.close();texture.dispose();}bloom.dispose();renderPass.dispose();outputPass.dispose();composer.dispose();renderer.dispose();});
