"""Command-line entry point and public build operations."""
from __future__ import annotations

from yellowstone_python.pipeline.shared import predicted_quantities, normalize_run_mode, PKG_ROOT, MAT_IMAGERY_DATE_UTC
from yellowstone_python.pipeline.config import load_config, _nonnegative_int, normalized_config, validate_config
from yellowstone_python.pipeline.inputs import _hash_package_sources, _default_world_root_for_hash, load_inputs
from yellowstone_python.pipeline.stages.weather import _check_met_window_covers_replay
from yellowstone_python.pipeline.stages.thermal import _run_outflow_chain, _outflow_mean_wet_temperature_c, _excelsior_lateral_override, _run_outflow_foodweb, _run_mat_validation
from yellowstone_python.pipeline.stages.vegetation import _canopy_from_census, _grazers_input_from_consumed
from yellowstone_python.pipeline.stages.land import _compute_overland_field, _overland_runoff_to_boundary
from yellowstone_python.pipeline.stages.river import _prepare_replay_ecosystem, resolve_replay_start_epoch, run_replay_solver, check_cross_sections, _river_shading_dict, _hyporheic_zones_dict, _run_solute_transport, _chloride_validation_bound, _run_river_oxygen, _run_periphyton
from yellowstone_python.pipeline.stages.foodweb import _predation_rate_by_cell
from yellowstone_python.pipeline.stages.fish import _per_point_hydraulics_from_cells
from yellowstone_python.pipeline.render import render_all
from yellowstone_python.pipeline.manifest import _package_version, _code_commit, build_manifest
from yellowstone_python.pipeline.sidecars import _atomic_json_write, _write_variant_and_gate, _write_fragment_sidecars, _write_pool_ramps, mat_imagery_pigment_ref, _write_mat_appearance, _write_integration_sidecars
from yellowstone_python.pipeline.cli import main
from yellowstone_python.pipeline.pipeline import simulate_all
from yellowstone_python.pipeline.shared import _find

if __name__ == "__main__":
    raise SystemExit(main())
