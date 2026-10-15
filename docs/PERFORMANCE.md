# Render measurement

The reference is Apple M4, macOS arm64, Godot 4.5.1, Metal 3.2 Forward Mobile, 1440 by 900, walking shadow preset at 140 m and 4096 atlas, with 4x MSAA. The surface generation is `b2b3d24fd7a0b08bdd63c34576aefd01412875728a5233935c6bd6ae992900ee`. Exact source, scene and input hashes are in the capture receipts.

Nine fixed views pass the terrain-material, seasonal-state, wetness, foreground-detail and render/collision checks. Complete before/after runs use the same harness in ABBA order, with no scientific worker or encoder running. Each run has 60 warmup frames followed by 120 moving-camera samples. Every sample advances exactly one drawn frame. Forcing and foliage wind are frozen. Vsync is disabled by command-line request; wall time still includes presentation. The GPU time monitor is unavailable, so these measurements do not isolate GPU execution.

| Run | Version | Median wall frame, ms | p95 wall frame, ms | Mean draw calls |
|---|---|---:|---:|---:|
| A1 | Prior release | 48.979 | 52.814 | 2441.042 |
| B1 | Surface update | 61.291 | 73.307 | 1860.375 |
| B2 | Surface update | 92.414 | 112.882 | 1860.375 |
| A2 | Prior release | 65.957 | 77.126 | 2441.042 |

The repeated samples vary substantially and the update is slower in this comparison. A subsequent process snapshot shows RobloxPlayer and other desktop applications active; their GPU load during the samples was not measured. The desktop workload is uncontrolled, so this is not an isolated GPU regression test. No frame-time or overall-load improvement is established. Raw reports retain all four results. The comparison package's 899 runtime files match the prior release; only the shared measurement harness differs.

The predeclared regression target remains median <= 33.4 ms and p95 <= 50 ms. All four samples fail that target. The earlier source measured 33.213 ms median and 42.245 ms p95; that result does not certify these tree assets. Rendering performance remains unaccepted. No 60 fps claim is made.

Verified structural savings are distinct from timing: distant variants use 23.8 percent fewer draw calls, and the baked scene decreases from 461,369,952 to 359,643,658 bytes, a 22.0 percent reduction. Precomputed outflow filtering replaces fifteen fragment texture reads with three while preserving the original stencil within 1.15e-7. The shared ground material retains eleven samplers. All 63,565 trees, 159,157 residual canopy cells, distance limits, shadows, and antialiasing remain enabled. Added supports and surface/sky detail carry rendering costs.

The B2 engine static-memory peak is 3,082,205,520 bytes. Scene/view preparation takes 45.090 seconds; it includes still capture and is not a dedicated cold-start benchmark. Other platforms and live-service frame-time performance remain untested.

The 72-second demonstration contains 2160 actual engine frames at fixed sampled model time, encoded to 1440 by 900. Twelve engine startup frames are removed. Movie rendering and encoding are separate from exploration performance. Compatibility/OpenGL capture timed out in a retained attempt; Metal produces the current recording. Resource-lifetime warnings can occur at movie shutdown.

Actual tree capture budgets pass 32 of 32 pairs at 18 m, 25 of 32 at 65 m, and 0 of 32 at 180 m. Far silhouette/occupancy transitions, subpixel foliage and selected animal deformation limits remain unaccepted. The failed budgets and raw captures are retained. These are rendering and geometry measurements, not biological validation.

Evidence: `evidence/surface-rendering.json`, `evidence/surface-render-pairs.json`, `evidence/surface-baseline-bytes.json`, `evidence/terrain-render.json`, `evidence/tree-lod-quality.json`, `evidence/wildlife-surface-quality.json` and `evidence/portfolio-capture.json`.
