# Forest release closeout

The checked numerical generation remains `8f7ed4ee574d61735e3ba679b9e712b3e67dc8c0a1fe496d43a151724f5b71d8`, from scenario build `f75347b772fd` at model source commit `18f456de029bb528f23bd38a9f90125bcbb48bea`. Reviewed runtime-only changes receive their own source commit and hash. The new residual-canopy attachment fix must be frozen, visually inspected and verified before final publication; the `1536391` pre-attachment ABBA is historical and has a recorded B1/B2 initial-sun discrepancy, so it cannot establish a causal speedup. Preserve the immutable BUILD, CHECKS and RELEASE documents. The equivalence helper refuses changed numerical code, configuration, physical inputs, scene bytes, or assets. It allows only exact reviewed runtime/test source paths and the existing color-mip asset metadata status correction.

## Freeze and source identity

1. Review the tree-submission source diff and native validator. Confirm source Multimeshes, instance records, census, scene, shader LOD distances, transitions, render distances, shadows and antialiasing remain unchanged. The filter must re-evaluate correctly after teleporting, changing cameras, and crossing an LOD boundary, and preserve any wind/displacement guard needed by the shader.
2. Commit the source changes and asset-manifest classification correction under KJR. Add only task files. The three main expected files are `yellowstone_midway/scripts/tree_submission.gd`, `yellowstone_midway/scripts/world.gd`, and `yellowstone_midway/tools/validate_tree_submission.gd`, plus their new UIDs. Include any actual focused test files. Run the following from the repository root, adding `--allow-path` only for separately reviewed changed test/display source paths:

```sh
yellowstone_python/.venv/bin/python work/verify_forest_runtime_equivalence.py \
  --allow-path yellowstone_midway/scripts/tree_submission.gd \
  --allow-path yellowstone_midway/scripts/world.gd \
  --allow-path yellowstone_midway/tools/validate_tree_submission.gd \
  --allow-path yellowstone_midway/shaders/thermal_apron.gdshader
```

Add each final canopy attachment source path explicitly after review; the command above is not a complete allowlist for an unknown later fix. The resulting `evidence/forest-runtime-equivalence.json` binds the final runtime commit, its full observed inventory and a separate exact runtime scope, the original numerical build, unchanged physical inputs and all checked numerical artifacts. A new full numerical build is unnecessary if this check passes and the reviewed scope is display submission only. A changed model/tool/config/input invalidates that conclusion and the helper fails. Exactly `dashboard/build_data.py`, which is outside numerical source-hash roots and not bundled in the game, is excluded from runtime source comparisons. The helper records its observed/committed hashes and original global receipt status; it never edits or relabels the original receipt. Any other changed source, fixture, output, originally stale execution or recorded failure is rejected. Do not modify/stage unrelated dashboard work. The scope helper hash must remain identical between equivalence and package assembly.

## Verification

- Run the new native tree-submission validator, the existing tree binding/transition tests that it can affect, Python style and focused source-integration tests. Bind receipts to the saved scene and active release pointer. If the full Python matrix is rerun, run it only after the source freeze. Historical 2,155-pass/14-skip receipts still describe their original source snapshot; global `evidence_status` will label them stale after any maintained Godot change. Do not relabel historical receipts or claim they executed against the runtime revision.
- Run `python -m tools.audit_provenance --dir derived` with a fresh `tools.run_evidence` receipt. This checks labels; it is not field validation.
- Preserve the first regressed ABBA JSON, reports and images in a distinct work/evidence directory before rerunning `work/run_forest_pairs.py`. Allow the CPU tests/builds and all other native captures to finish before ABBA. Keep the same old published baseline, path, renderer, resolution, MSAA, shadow settings, sample count and target. `work/finalize_forest_evidence.py --pairs EXACT_AGGREGATE.json --receipt-manifest EXACT_MANIFEST.json` reads the selected final four-run file and copies raw reports/images. The manifest maps a1/b1/b2/a2 to explicit `{ "path": "evidence/receipts/ID.json", "name": "actual-name" }` records; receipt suffixes are not assumed. The final work-only fixed-forcing wrapper must be identical for old and current packages, with light/weather/epoch state evidence. Preserve the sun-mismatched pre-attachment measurements separately with their caveat. The finalizer checks that each aggregate report equals its raw capture report before copying. Update its fixed tree counts/batch statements if the runtime filter changes the meaning of those figures. It currently records raw saved-scene capacity, not a count of submitted instances after filtering.
- Inspect at least one actual saved-world overlook and near-floor view with the final runtime hook. Selection-control passes do not establish endpoint fidelity: the 62/96 endpoint failures remain explicit.

## Package and archive

Preserve the previous package as a differently named work directory; `package_demo` requires an absent target. From `yellowstone_python/`:

```sh
.venv/bin/python -m tools.package_demo --world ../yellowstone_midway --out ../work/Yellowstone-Forest-Spring-Update
godot --headless --editor --path ../work/Yellowstone-Forest-Spring-Update --import --quit
.venv/bin/python ../work/prepare_runtime_inventory.py ../work/Yellowstone-Forest-Spring-Update
.venv/bin/python -m tools.run_evidence --name forest-package-headless \
  --fixture ../work/Yellowstone-Forest-Spring-Update/RUNTIME.json \
  --fixture ../work/Yellowstone-Forest-Spring-Update/project.godot \
  --fixture ../work/Yellowstone-Forest-Spring-Update/scenes/authored_world.tscn \
  --fixture ../work/Yellowstone-Forest-Spring-Update/data/release.json \
  -- .venv/bin/python ../work/check_package_startup.py ../work/Yellowstone-Forest-Spring-Update
.venv/bin/python -m tools.run_evidence --name forest-package-native \
  --fixture ../work/Yellowstone-Forest-Spring-Update/RUNTIME.json \
  --fixture ../work/Yellowstone-Forest-Spring-Update/project.godot \
  --fixture ../work/Yellowstone-Forest-Spring-Update/scenes/authored_world.tscn \
  --fixture ../work/Yellowstone-Forest-Spring-Update/data/release.json \
  -- .venv/bin/python ../work/check_package_native.py ../work/Yellowstone-Forest-Spring-Update
```

Record those two exact new receipt paths in `work/forest-package-startup-receipts.json`; each receipt must have originally recorded `executed_passed` and still pass the exact runtime-scope freshness check. Its global status can be stale solely because of the excluded dashboard file; that observation remains visible. Both tests require the live service on port 8765 to be unavailable and assert all four floor anchors, zero heat-budget error, no script/resource errors, and exit 0. A newly created runtime UID/import sidecar after RUNTIME generation requires a fresh inventory and fresh startup tests.

Prepare a copy of `work/forest-closeout-config.template.json` with exact final receipt paths/names, final capture names/captions and chosen release URL. The template intentionally leaves future receipts null. Its prior 1536391 receipts are historical pointers only. Terrace raw image/report hashes are validated separately, without inventing a command receipt. Preview with:

```sh
yellowstone_python/.venv/bin/python work/finalize_forest_verification.py --config work/forest-closeout-config.json
```

Review `work/forest-closeout-preview/`, then use `--apply` only when the parent is ready to update the maintained ledger and verification JSON. At this point keep `archive_receipt` and `publication` null. Complete final docs, ledger and verification JSON before assembly. Keep original model commit and new runtime commit distinct. `work/finalize_forest_package.py` checks equivalence, package source identity, every runtime file and fresh startup receipts; copies final docs/evidence; authenticates every archived member; and writes ZIP, receipt and SHA256 file. It refuses to overwrite an existing archive. Run it from the repository root:

```sh
yellowstone_python/.venv/bin/python work/finalize_forest_package.py
```

After archive assembly, set `archive_receipt` to `evidence/forest-package.json` and rerun the closeout helper without `--apply` to prepare the work-only report config and release notes with the verified ZIP hash. This avoids falsely claiming the archive existed before assembly or changing the already verified ZIP contents. Generate the self-contained visual report with `python work/prepare_forest_report.py work/forest-report-config.json`, and inspect it. Its photo captions must identify controlled synthetic versus actual-world weather captures, and must not describe supplied image hex values as physical reflectance. Camera framing comparisons preserve geography. No claims of matched LOD endpoints, calibrated rainbow frequency, measured plant abundance, resolved cumulus towers, native executables, other-platform support, or performance/load reduction are justified without the corresponding results.

## Staging and durable GitHub verification

`work/stage_forest_release.py` reads the four agent manifests, current generation, forest receipts, final render directories, selected source/docs and new tree-submission paths. It now includes `evidence/tree-instance-lod.json`, previously absent from the merged manifests. For additional exact files, provide a JSON array in `work/forest-release-stage-extra.json`. The helper excludes dashboard and the unrelated park-streaming spec, and rejects paths outside the repository. Review `git diff --cached --stat` and the staged path inventory before committing. Do not blanket-add the worktree.

After the final evidence/docs commit, push `main`, create the new release tag targeting that exact final commit, and upload the ZIP, HTML report, JSON receipt and SHA256 text. The generation ID names immutable numerical data; the tag/final commit identifies the complete shipped runtime and evidence. Preserve old releases.

```sh
git push origin main
gh release create TAG --repo seris10/yellowstone --target FINAL_COMMIT --prerelease --title TITLE --notes-file work/forest-release-notes.md ZIP HTML RECEIPT SHA256
git ls-remote origin refs/heads/main refs/tags/TAG
gh release view TAG --repo seris10/yellowstone --json tagName,targetCommitish,isDraft,isPrerelease,url,assets
gh release download TAG --repo seris10/yellowstone --pattern Yellowstone-Forest-Spring-Update.zip --dir work/forest-release-download
shasum -a 256 work/forest-release-download/Yellowstone-Forest-Spring-Update.zip
gh run list --repo seris10/yellowstone --commit FINAL_COMMIT
```

Use actual paths/tag/commit values, and a new empty download directory. Compare downloaded ZIP bytes and SHA256 to the local receipt, not just upload size. Verify the remote tag resolves to FINAL_COMMIT and the remote main branch is correct. Inspect the automatically triggered CI run and report its actual state; the self-hosted scientific-world job is manual and is not implied by the push job. The final answer should link the release and local visual report, state material performance/LOD limitations, and distinguish local verification from human acceptance.

After remote publication and download, fill the explicit `publication` block in the closeout config and rerun the helper **without `--apply`** for a work-only durable-state verification record. It checks the remote main commit, tag commit, release asset metadata and actual downloaded ZIP hash. CI status remains separately reported. A later maintained evidence commit would change main identity, so do not create one accidentally after verifying the published tag. The package's internal documentation truthfully records its assembly-time publication state; the external final report/verification can identify the completed publication.
