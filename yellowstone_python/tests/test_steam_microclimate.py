"""Plume heat and vapor adjustment, with fog and rime diagnostics."""
from __future__ import annotations

import pytest

from yellowstone_python.atmosphere.steam_microclimate import FETCH_MAX_M, FETCH_MIN_M, FETCH_SOURCES, FOG_SOURCES, IBL_COEFFICIENT_A_STATUS, IBL_EXPONENT_B_STATUS, downwind_adjustment, fog_present, internal_boundary_layer_m, plume_latent_flux_w_m2, plume_microclimate_adjustment, plume_sensible_flux_w_m2, rime_present


def test_sensible_and_latent_fluxes_are_positive_from_hot_surface():
    """A pool at 60 C into 15 C air produces positive sensible and latent fluxes."""
    s = plume_sensible_flux_w_m2(surface_c=60.0, air_c=15.0, wind_mps=2.0)
    e = plume_latent_flux_w_m2(surface_c=60.0, air_c=15.0, rh=0.4,
                                wind_mps=2.0)
    assert s > 0.0
    assert e > 0.0


def test_downwind_humidity_rises_with_pool_heat_flux():
    """Larger plume latent flux produces larger downwind humidity increment."""
    low = downwind_adjustment(air_c=10.0, rh=0.5, wind_mps=2.0,
                               source_area_m2=400.0,
                               plume_sensible_w_m2=100.0,
                               plume_latent_w_m2=200.0)
    high = downwind_adjustment(air_c=10.0, rh=0.5, wind_mps=2.0,
                                source_area_m2=400.0,
                                plume_sensible_w_m2=400.0,
                                plume_latent_w_m2=1200.0)
    assert high["downwind_rh"] > low["downwind_rh"]
    assert high["downwind_air_c"] > low["downwind_air_c"]


def test_downwind_humidity_falls_with_wind_speed():
    """Stronger wind cuts the parcel transit time; fewer increments reach the plume parcel."""
    calm = downwind_adjustment(air_c=10.0, rh=0.5, wind_mps=1.0,
                                source_area_m2=400.0,
                                plume_sensible_w_m2=200.0,
                                plume_latent_w_m2=800.0)
    windy = downwind_adjustment(air_c=10.0, rh=0.5, wind_mps=8.0,
                                 source_area_m2=400.0,
                                 plume_sensible_w_m2=200.0,
                                 plume_latent_w_m2=800.0)
    assert calm["downwind_rh"] > windy["downwind_rh"]
    assert calm["delta_air_c"] > windy["delta_air_c"]


def test_combined_pool_and_outflow_adjustment_cites_fetch_model():
    """Combined plume_microclimate_adjustment returns per-source fluxes and the fetch citation."""
    result = plume_microclimate_adjustment(
        air_c=5.0, rh=0.4, wind_mps=2.0,
        pool_surface_c=72.0, pool_area_m2=800.0,
        outflow_surface_c=35.0, outflow_area_m2=200.0)
    assert result["downwind_rh"] > 0.4
    assert result["components"]["pool_sensible_w_m2"] > 0.0
    assert result["components"]["outflow_latent_w_m2"] > 0.0
    assert any("Stull" in s for s in result["sources"])
    assert any("fog" in s.lower() or "rime" in s.lower()
                for s in FOG_SOURCES)
    assert FETCH_SOURCES, "fetch model must be cited"


def test_fog_requires_saturation():
    """Fog is reported only when air reaches saturation at the given temperature."""
    assert not fog_present(air_c=10.0, rh=0.4)
    assert fog_present(air_c=10.0, rh=1.0)


def test_rime_requires_fog_and_subfreezing_air():
    """Rime forms only below 0 C with fog present."""
    assert not rime_present(air_c=5.0, rh=1.0)  # fog but above freezing
    assert not rime_present(air_c=-5.0, rh=0.5)  # cold but dry
    assert rime_present(air_c=-5.0, rh=1.0)


def test_ibl_coefficient_and_exponent_are_labeled_authored():
    """The 0.4 coefficient is authored and the 0.8 exponent cites the diffusion-model literature in."""
    assert IBL_COEFFICIENT_A_STATUS == "authored"
    assert "diffusion_model" in IBL_EXPONENT_B_STATUS


def test_internal_boundary_layer_raises_outside_fetch_range():
    """Fetches outside [FETCH_MIN_M, FETCH_MAX_M] raise ValueError."""
    with pytest.raises(ValueError):
        internal_boundary_layer_m(fetch_m=FETCH_MIN_M - 1.0)
    with pytest.raises(ValueError):
        internal_boundary_layer_m(fetch_m=FETCH_MAX_M + 1.0)
    inside = internal_boundary_layer_m(fetch_m=50.0)
    assert inside > 0.0
