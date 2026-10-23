"""Stage the explorer inside an existing Yellowstone dashboard export."""

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil


STATIC = ["index.html", "app.js", "model.js", "copy.js", "temperature.js", "temperature-pass.js", "layers.js", "layer-model.js", "style.css", "README.md", "yellowstone-LICENSE.txt",
          "vendor/three.module.js", "vendor/three.core.js", "vendor/OrbitControls.js", "vendor/three-LICENSE.txt",
          "vendor/postprocessing/EffectComposer.js", "vendor/postprocessing/RenderPass.js",
          "vendor/postprocessing/UnrealBloomPass.js", "vendor/postprocessing/OutputPass.js",
          "vendor/postprocessing/ShaderPass.js", "vendor/postprocessing/Pass.js",
          "vendor/postprocessing/MaskPass.js", "vendor/shaders/CopyShader.js",
          "vendor/shaders/LuminosityHighPassShader.js", "vendor/shaders/OutputShader.js"]


def integrate(source, site, dashboard):
    manifest = json.loads((source / "data/manifest.json").read_text())
    snapshot = json.loads((site / "dashboard/snapshot.json").read_text())
    if snapshot["snapshot"] != manifest["build_id"]:
        raise ValueError("Dashboard and explorer build identities differ")
    target = site / "dashboard/explorer"
    if target.exists():
        raise ValueError("Explorer destination already exists")
    if any(Path(name).name != name or Path(name).suffix not in (".json", ".f32", ".png") for name in manifest["assets"]):
        raise ValueError("Unsupported data filename")
    files = STATIC + ["data/manifest.json"] + ["data/" + name for name in manifest["assets"]]
    for rel in files:
        path = source / rel
        if path.is_symlink() or not path.is_file() or not path.resolve().is_relative_to(source.resolve()):
            raise ValueError(f"Unsupported source path: {rel}")
    for name, record in manifest["assets"].items():
        payload = (source / "data" / name).read_bytes()
        if len(payload) != record["bytes"] or hashlib.sha256(payload).hexdigest() != record["sha256"]:
            raise ValueError(f"Data integrity mismatch: {name}")
    spec = importlib.util.spec_from_file_location("dashboard_export", dashboard / "build_public.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    for rel in files:
        destination = target / rel
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source / rel, destination)
    for path in (site / "dashboard").rglob("index.html"):
        if path.is_relative_to(target):
            continue
        html = path.read_text()
        marker = '<nav class="view-switch site-nav" aria-label="Explore Yellowstone">'
        if marker in html and 'href="/dashboard/explorer/"' not in html:
            html = html.replace(marker, marker + '\n      <a href="/dashboard/explorer/">3D terrain</a>', 1)
            path.write_text(html)
    module.public_worker(site)
    return {"build_id": manifest["build_id"], "route": "/dashboard/explorer/", "files": files}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--site", type=Path, required=True)
    parser.add_argument("--dashboard-source", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(integrate(Path(__file__).parent, args.site, args.dashboard_source), indent=2))
