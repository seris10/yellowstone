# 3D specimen sources and model tools for scientifically grounded wildlife

Prepared 2026-10-13 for KJR, who is building fauna assets (bison, cutthroat trout) and asked about agent access to specimen databases and about tools for analyzing and modifying models. Status of each item is what was checked on this machine or in the cited source on that date.

## Specimen and reference sources

| Source | What it holds | Agent access | What KJR has to provide |
|---|---|---|---|
| MorphoSource (Duke) | CT scans, surface meshes and photographs of real specimens | Search results are JSON when `.json` is appended to the record type in a query URL (Duke wiki). Downloads need an account API key, a use statement and use categories per file; some media are restricted. An unofficial Python client exists (`morphosource` on PyPI). | An account and its API key; acceptance of each file's use agreement, which is his to give, not an agent's |
| Smithsonian Open Access | More than 5.1 million 2D and 3D items; 3D in OBJ or glTF; items marked CC0 are free for any use, others need written permission for commercial use | Open Access API on api.data.gov; viewer source is Smithsonian Voyager (GitHub `Smithsonian/dpo-voyager`); a third-party Smithsonian MCP server exists (unofficial, not reviewed) | A free api.data.gov key |
| Photo and occurrence references (iNaturalist, GBIF) | Field photographs and occurrence records for proportions, coloration and range | Public APIs | Nothing for search; license is per record |

Use a specimen as a measurement reference first: landmarks (shoulder height, hip height, skull length, limb segment ratios, horn placement) recorded with the specimen id, sex, age class and source in a registry, the same way the simulation records parameters. A generated mesh is then corrected against those numbers.

## Tools on this machine

- Blender 5.2.1 is installed (`/opt/homebrew/bin/blender`). Headless scripting (`blender -b --python script.py`) can import glTF, measure bounding boxes and landmark distances, decimate, recompute normals, apply scale and orientation, and export. This is the strongest tool already available.
- Not installed: trimesh (load glTF, measurements, cross-sections, scripted checks), PyMeshLab (decimation, remeshing, Hausdorff distance between two meshes, which quantifies how far a generated mesh is from a reference scan), Open3D (point clouds and ICP registration to align a generated mesh to a scan), gltf-transform (glTF optimization: mesh compression, texture resizing, deduplication).

## Agent control of Blender

blender-mcp (github.com/ahujasid/blender-mcp) lets an agent drive a running Blender: a Blender add-on opens a socket server on localhost (default port 9876) and an MCP server forwards commands, including viewport screenshots and arbitrary Python inside Blender. It also connects to Poly Haven, Sketchfab and generative 3D services. Requirements: Blender 3.0 or newer, Python 3.10 or newer, uv. The project states it has no official website; use the GitHub repository. Arbitrary Python inside Blender means it should run only on assets and scenes meant for it.

## Rigging

UniRig (VAST-AI-Research with Tsinghua University and Tripo, SIGGRAPH 2025) predicts a skeleton and skinning weights for varied body forms, inputs obj, fbx, glb and vrm. The Hugging Face card lists a CUDA GPU with more than 8 GB of memory, so it does not run on this Mac; it needs a cloud GPU. The released checkpoint covers skeleton prediction; the skinning model was listed as a later release. The license was not confirmed in the sources checked; read the repository LICENSE and the model card before use.

## Suggested pipeline

1. Reference: landmark measurements from MorphoSource or Smithsonian specimens and field data, recorded with sources.
2. Candidate meshes: KJR's generators (Meshy, Tripo, his own tools).
3. Measure and align: Blender headless (or trimesh), with Open3D ICP against a scan when one exists; report each landmark's error and the Hausdorff distance.
4. Correct, retopologize and optimize (Blender, gltf-transform).
5. Rig (generator rigging, or UniRig on a cloud GPU) and validate joint placement against the reference skeleton.
6. Register in `yellowstone_midway/data/asset_manifest.json` with the measurement report and source licenses.

## Sources
- MorphoSource Python client: https://pypi.org/project/morphosource/1.1.0 ; JSON API note: https://duke.atlassian.net/wiki/spaces/MD/pages/35422436/JSON+API
- Smithsonian Open Access: https://www.si.edu/openaccess ; FAQ: https://dashboard.si.edu/openaccess/faq
- blender-mcp: https://glama.ai/mcp/servers/ahujasid/blender-mcp (README mirror of the GitHub repository)
- UniRig: https://github.com/VAST-AI-Research/UniRig ; https://huggingface.co/VAST-AI/UniRig ; https://arxiv.org/abs/2504.12451v1
