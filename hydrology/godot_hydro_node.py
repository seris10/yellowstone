"""
Godot wrapper for hydrosim.

STATUS: written for the godot-python plugin (touilleMan/godot-python), which targets Godot 3.x.
Not run against a live editor - hydrosim.py itself is tested (validate_hydrosim.py), this file
is not. Every engine-specific call is in the ENGINE ADAPTER block so it is easy to patch.

Godot 4 note: that plugin does not support Godot 4. Godot 4 Python extensions exist
(for example py4godot) but are younger; if you use one, only the ENGINE ADAPTER block and the
decorators below should need to change. Alternatively run hydrosim in a sidecar process and
stream the float32 depth grid to Godot over a socket.

Setup
  1. Put hydrosim.py and this file in the project (godot-python resolves imports from the
     project's python path), attach this script to a Node.
  2. Drive it from UI or gameplay:  node.set_rain_rate(35.0)   # mm/h, any float, continuous
  3. Read results: node.depth_texture / node.saturation_texture (FORMAT_RF float textures, so
     the shader needs a float-capable renderer), or query node.depth_at(x_m, y_m).
"""
import time

import numpy as np

from hydrosim import (HydroSim, HydroConfig, RainField, Climate, make_terrain, default_soil_map)

# ------------------------------- ENGINE ADAPTER -------------------------------
from godot import exposed, export, Node, Image, ImageTexture, PoolByteArray


def float_grid_to_texture(grid: np.ndarray, texture=None):
    """float32 (h, w) array -> ImageTexture in FORMAT_RF. Reuses the texture when given one."""
    h, w = grid.shape
    img = Image()
    img.create_from_data(w, h, False, Image.FORMAT_RF,
                         PoolByteArray(np.ascontiguousarray(grid, dtype=np.float32).tobytes()))
    if texture is None:
        texture = ImageTexture()
        texture.create_from_image(img, 0)     # flags=0: no filtering/mipmaps, exact cell values
    else:
        texture.set_data(img)
    return texture


def pool_to_numpy(pool, h, w):
    """PoolRealArray (row-major heights) -> float64 (h, w)."""
    return np.array(list(pool), dtype=np.float64).reshape(h, w)
# ------------------------------------------------------------------------------


@exposed
class HydroNode(Node):
    # Inspector-exposed settings (read once in _ready, except rain_rate_mm_h and time_scale)
    rain_rate_mm_h = export(float, default=0.0)    # the slider; read every physics frame
    time_scale = export(float, default=30.0)       # sim seconds per real second
    grid_size = export(int, default=128)
    cell_size_m = export(float, default=2.0)
    terrain_seed = export(int, default=1)
    storm_cells = export(int, default=5)
    update_textures_every = export(int, default=2) # physics frames between texture uploads

    def _ready(self):
        n, dx = int(self.grid_size), float(self.cell_size_m)
        self._build(make_terrain(n, n, dx, seed=int(self.terrain_seed)), dx)

    # --- setup -------------------------------------------------------------------
    def _build(self, z, dx):
        soil_map, names = default_soil_map(z)
        self.sim = HydroSim(z, dx, soil_map=soil_map, soil_names=names,
                            rain=RainField(z.shape, dx, n_cells=int(self.storm_cells), seed=int(self.terrain_seed)),
                            config=HydroConfig(), climate=Climate())
        self.depth_texture = None
        self.saturation_texture = None
        self._frame = 0
        self.last_step_ms = 0.0
        self.last_info = {}

    def set_heightmap(self, pool_heights, width, height, cell_size_m):
        """Replace the terrain with a Godot heightmap (metres, row-major). Resets the simulation."""
        self.cell_size_m = cell_size_m
        self._build(pool_to_numpy(pool_heights, int(height), int(width)), float(cell_size_m))

    # --- gameplay API ------------------------------------------------------------
    def set_rain_rate(self, mm_per_hour):
        self.rain_rate_mm_h = float(mm_per_hour)

    def depth_at(self, x_m, y_m):
        """Surface water depth in metres at a world position inside the grid (nearest cell)."""
        j = int(np.clip(x_m / self.sim.dx, 0, self.sim.nx - 1))
        i = int(np.clip(y_m / self.sim.dx, 0, self.sim.ny - 1))
        return float(self.sim.h[i, j])

    def water_balance(self):
        """Dict with cumulative volumes in m3 and the relative closure error (should stay ~1e-15)."""
        return self.sim.balance()

    # --- per-frame update --------------------------------------------------------
    def _physics_process(self, delta):
        t0 = time.perf_counter()
        self.last_info = self.sim.step(float(delta) * float(self.time_scale), float(self.rain_rate_mm_h))
        self.last_step_ms = (time.perf_counter() - t0) * 1e3
        self._frame += 1
        if self._frame % max(1, int(self.update_textures_every)) == 0:
            self.depth_texture = float_grid_to_texture(self.sim.depth_map(), self.depth_texture)
            self.saturation_texture = float_grid_to_texture(self.sim.soil_saturation(), self.saturation_texture)
