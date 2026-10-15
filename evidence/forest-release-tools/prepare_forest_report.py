"""Prepare the portable visual-change report from final release evidence."""
from pathlib import Path
import base64
import html
import json
import shutil
import sys

root = Path(__file__).resolve().parents[1]
config = json.loads(Path(sys.argv[1]).read_text())
out = Path(config["output_dir"])
out.mkdir(parents=True, exist_ok=True)
media = out / "forest-spring-media"
media.mkdir(exist_ok=True)
for name, relative in config["images"].items():
    shutil.copy2(root / relative, media / (name + ".png"))
embedded = {name: "data:image/png;base64," + base64.b64encode((media / (name + ".png")).read_bytes()).decode() for name in config["images"]}
palette = json.loads((root / "yellowstone_midway/data/display/prismatic.json").read_text())
swatches = "".join(f'<span style="background:{c}" title="{c}"></span>' for c in palette["ordered_reference_colors"])
rows = "".join(f'<tr><td>{html.escape(str(row[0]))}</td><td>{html.escape(str(row[1]))}</td><td>{html.escape(str(row[2]))}</td><td>{html.escape(str(row[3]))}</td></tr>' for row in config["performance_rows"])
page = '''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Yellowstone forest and spring update</title>
<style>
:root{color-scheme:dark;font:16px/1.6 system-ui,sans-serif;background:#10201d;color:#e9eee7}body{margin:0}main{max-width:1120px;margin:auto;padding:36px 22px 70px}h1{font-size:clamp(30px,4vw,52px);line-height:1.12;margin:12px 0 22px}h2{font-size:25px;margin-top:40px}p{max-width:900px}a{color:#9edfd0}img{width:100%;display:block;border-radius:10px;background:#192c26}figure{margin:22px 0}figcaption,.muted{font-size:14px;color:#b4c3b8;margin-top:8px}.eyebrow{letter-spacing:.12em;text-transform:uppercase;color:#a9cfb0;font-size:12px}.grid{display:grid;grid-template-columns:1fr 1fr;gap:18px}.panel{padding:20px;border:1px solid #365044;border-radius:10px;background:#162b24}.palette{display:flex;height:40px;border-radius:8px;overflow:hidden}.palette span{flex:1}button{font:inherit;color:inherit;border:1px solid #54705f;background:#203b2d;border-radius:8px;padding:8px 14px;cursor:pointer}button[aria-pressed=true]{background:#afd4ba;color:#11251b}.controls{display:flex;flex-wrap:wrap;gap:9px}table{border-collapse:collapse;width:100%}td,th{padding:10px;border-bottom:1px solid #385144;text-align:left}code{overflow-wrap:anywhere}summary{cursor:pointer}ul{padding-left:22px}@media(max-width:700px){.grid{grid-template-columns:1fr}main{padding:22px 16px}table{font-size:13px}td,th{padding:7px}}
</style><main>
<div class="eyebrow">Actual engine captures · Godot 4.5.1 · Midway Geyser Basin</div>
<h1>Fuller forest. Clearer spring detail.</h1>
<p>@@SUMMARY@@</p><p><a href="@@RELEASE@@">GitHub release and prepared game package</a> · Commit <code>@@COMMIT@@</code></p>
<figure><img src="forest-spring-media/overlook.png" alt="Updated Godot overlook with the spring, forest and sky"><figcaption>@@OVERLOOK_CAPTION@@</figcaption></figure>
<div class="grid"><section class="panel"><h2 style="margin-top:0">Trees and ground cover</h2><p>Overlapping ascending branches and tapered leaders replace widely separated foliage tiers. The source tree census and placements remain unchanged; visible crown envelopes and residual-canopy supports are authored. Smaller source shoots form fuller boughs; litter, bent grasses, shrubs, branches and terrain-aligned logs provide depth close to the ground.</p><p>CC0 human-made pine and forest-floor artwork supplies texture detail. Plant wind bends from anchored bases. No 3DAIStudio credits were used. Local fern occurrence was not established, so ferns were not added.</p></section><figure><img src="forest-spring-media/floor.png" alt="Updated forest-floor detail with wood and litter"><figcaption>@@FLOOR_CAPTION@@</figcaption></figure></div>
<h2>Color and surface detail</h2><div class="palette">@@SWATCHES@@</div>
<p>The complete supplied palette is preserved. Blue and cyan occupy most of the pool, followed by a narrower green transition, vivid yellow, tan, orange runoff and gray-purple outer areas. Steam-whitened reference colors remain separate from the water color beneath steam. Mapped aerial-image variation modulates the apron; filtered normal maps add coherent flowing terrace edges without moving the land.</p>
<p>@@TERRACE@@</p>
<p class="muted">The colors are image-informed display choices, not calibrated reflectance measurements. Ring widths and terrace relief are authored; local uncertainty is unknown. The <a href="https://www.nps.gov/places/000/grand-prismatic-spring.htm">NPS description</a> supports the broad thermal color context. A reusable linear-light gradient sampler retains image hashes, camera-condition notes, missing samples and optional planar homography controls.</p>
<h2>Why the spring can look too far away</h2>
<p>The mapped pool spans about 94 by 102 meters and subtends 24.34 degrees from the overlook. The 72-degree vertical gameplay field of view covers 98.59 degrees horizontally at 16:10, making the pool occupy about 18.55% of the screen width. At 30 degrees vertical it occupies 50.30%: 2.71 times wider with the same camera position and geography.</p>
<div class="controls" aria-label="Choose camera field of view"><button type="button" data-view="72" aria-pressed="true">72° gameplay</button><button type="button" data-view="40" aria-pressed="false">40° framing</button><button type="button" data-view="30" aria-pressed="false">30° framing</button></div>
<figure><img id="projection" src="forest-spring-media/fov72.png" alt="Same overlook viewpoint at 72-degree vertical field of view"><figcaption id="projection-caption">@@PROJECTION_CAPTION@@</figcaption></figure>
<p class="muted">This supports photographic framing as a major contributor to the discrepancy. Unknown panorama zoom, crop and viewpoint prevent a unique camera calibration. Terrain scale and the default gameplay FOV remain unchanged. Reference photographs are not bundled as game textures.</p>
<h2>Clouds and occasional rainbows</h2>
<p>Clouds use a shared advected density field with bounded sampling. Rainbows depend on rain history, surviving droplets, direct sunlight and antisolar viewing geometry. Primary and weaker, reversed secondary arcs use refractive geometry. Clear startup has no rain curtain; toggling weather does not reseed it or guarantee a rainbow.</p>
<figure><img src="forest-spring-media/rainbow.png" alt="Controlled native rain and sunshine rendering showing rainbow optics"><figcaption>@@RAINBOW_CAPTION@@</figcaption></figure>
<p class="muted">The <a href="https://www.nesdis.noaa.gov/about/k-12-education/optical-phenomena/what-causes-rainbow">NOAA explanation of rainbow formation</a> provides physical context. The renderer remains a bounded optical approximation. Excelsior has a steam emitter; local plume density and height are not calibrated.</p>
<h2>Measured performance and verification</h2>
<p>@@PERFORMANCE@@</p><table><thead><tr><th>Run</th><th>Version</th><th>Median frame, ms</th><th>p95 frame, ms</th></tr></thead><tbody>@@ROWS@@</tbody></table>
<p class="muted">Apple M4, Metal Mobile, 1440 × 900, 4× MSAA, 140-meter shadows with a 4096 atlas. ABBA order, identical harness, frozen forcing and wind, 60 warmup and 120 moving-camera samples per run. The shared benchmark normalizes physical sun direction and locks a common authored weather/epoch fixture. Wall time includes presentation and forcing-verification overhead; shader TIME and particles remain animated. The monitor does not isolate GPU execution.</p>
<p>@@VERIFICATION@@</p><details><summary>Scope and remaining limits</summary><p>@@LIMITS@@</p><p>Illustrative ecology remains <code>not_yet_accepted</code>. Mapped inputs, computational checks, authored appearance and human acceptance are separate evidence states.</p></details>
<p class="muted">Release generation <code>@@GENERATION@@</code>. Archive SHA-256 <code>@@ZIP_SHA@@</code>. The package includes its byte inventory and requires Godot 4.5.1; Python is unnecessary for offline exploration.</p>
</main><script>document.querySelectorAll('[data-view]').forEach(b=>b.addEventListener('click',()=>{const f=b.dataset.view;document.querySelector('#projection').src='forest-spring-media/fov'+f+'.png';document.querySelector('#projection').alt='Same overlook viewpoint at '+f+'-degree vertical field of view';document.querySelectorAll('[data-view]').forEach(x=>x.setAttribute('aria-pressed',String(x===b)));}));</script></html>'''
values = {**config, "swatches":swatches,"rows":rows}
for key, value in values.items():
    if isinstance(value, str):
        page = page.replace("@@" + key.upper() + "@@", value if key in {"swatches", "rows"} else html.escape(value, quote=True))
if "@@" in page:
    raise ValueError("Unfilled report fields")
page = page.replace("<script>", "<script>const projectionFrames=" + json.dumps({key.removeprefix("fov"): value for key, value in embedded.items() if key.startswith("fov")}) + ";")
page = page.replace("'forest-spring-media/fov'+f+'.png'", "projectionFrames[f]")
for name, data in embedded.items():
    page = page.replace('src="forest-spring-media/' + name + '.png"', 'src="' + data + '"')
(out / "Yellowstone-Visual-Update.html").write_text(page)
print(out / "Yellowstone-Visual-Update.html")
