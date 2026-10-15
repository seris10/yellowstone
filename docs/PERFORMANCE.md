# Render measurement

The current reference is Apple M4, macOS arm64, Godot 4.5.1, Metal 3.2 Forward Mobile, 1440 by 900, walking shadow preset at 140 m and 4096 atlas. The release and exact scene/input hashes are in the current capture receipts.

Nine fixed views pass the terrain-material, seasonal-state, wetness, foreground-detail and render/collision checks. The 120-frame moving-camera sample measures median 80.454 ms and p95 89.830 ms, with about 2441 draw calls per frame. Forcing and foliage wind are frozen; display synchronization remains in wall time. A scientific pytest worker ran concurrently, with no encoder or other GPU capture.

The predeclared regression target remains median <= 33.4 ms and p95 <= 50 ms. The current sample fails that target. The earlier source measured 33.213 ms median and 42.245 ms p95; that result does not certify the changed tree assets. Retaining individual shoot cards in middle LODs has a substantial geometry cost. Further LOD and rendering optimization is open. No 60 fps claim is made.

The process maximum resident set size is 3,616,342,016 bytes; reported peak memory footprint is 5,557,310,048 bytes. Scene/view preparation takes 75.312 seconds; total harness wall time is 94.09 seconds. Preparation includes still capture and is not a dedicated cold-start benchmark. Other platforms and live-service performance remain untested.

The 72-second demonstration contains 2160 actual engine frames at fixed sampled model time, encoded to 1440 by 900. Twelve engine startup frames are removed. Movie rendering and encoding are separate from exploration performance. Compatibility/OpenGL capture timed out in a retained attempt; Metal produces the current recording. Resource-lifetime warnings can occur at movie shutdown.

Actual tree capture budgets pass 32 of 32 pairs at 18 m, 25 of 32 at 65 m, and 0 of 32 at 180 m. Far silhouette/occupancy transitions, subpixel foliage and selected animal deformation limits remain unaccepted. The failed budgets and raw captures are retained. These are rendering and geometry measurements, not biological validation.

Evidence: `evidence/terrain-render.json`, `evidence/tree-lod-quality.json`, `evidence/wildlife-surface-quality.json` and `evidence/portfolio-capture.json`.
