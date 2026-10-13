

FILES COPIED:
1. tools/prepare_world.py - Tree placement generation
2. tools/bake_world.gd - Water and vegetation baking
3. tools/bake_botany.gd - Botanical validation
4. scripts/process_laz_trees.py - NEW: LAZ tree detection script (uses real USGS URLs)
5. setup_laz_trees.sh - NEW: Setup script
6. data/placements.json - Tree placement data (30,000 sparse trees)
7. data/placement_overrides.json - Tree placement overrides (19,929 pines)
8. shaders/water.gdshader - Water shader
9. data/pool_shells.json - Thermal shell data
10. scripts/pool_overlay.gd - Pool overlay for thermal features

USAGE:
1. Run setup script: ./setup_laz_trees.sh
2. Script will download 20 USGS LAZ files (~1.4GB)
3. Process only points within project bounds (-2028 to 2028 in X/Z)
4. Detect tree tops using clustering algorithms
5. Export ~50,000-100,000 tree placements to data/placements_from_lidar.json

REPLACES:
- Current: 30,000 trees on 15m grid (sparse)
- New: 50,000-100,000 trees from LiDAR data (dense, accurate)

