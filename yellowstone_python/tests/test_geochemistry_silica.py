import importlib.util
import math

import pytest

import yellowstone_python.thermal_features.geochemistry as gc


def test_quartz_92C_matches_verified_value():
    assert gc.quartz_solubility_mg_L(92.0) == pytest.approx(40.1, abs=0.5)


def test_phase_ordering_at_all_T():
    for t in (25.0, 92.0, 150.0, 200.0):
        q = gc.quartz_solubility_mg_L(t)
        c = gc.chalcedony_solubility_mg_L(t)
        a = gc.amorphous_solubility_mg_L(t)
        assert q < c < a


def test_reservoir_inversion_matches_verified_value():
    assert gc.silica_reservoir_T_C(40.1) == pytest.approx(91.8, abs=0.3)


def test_reservoir_roundtrip():
    for t in (25.0, 92.0, 150.0, 200.0):
        assert gc.silica_reservoir_T_C(
            gc.quartz_solubility_mg_L(t)) == pytest.approx(t, abs=1e-6)


def test_si_zero_at_equilibrium():
    for fn, phase in ((gc.quartz_solubility_mg_L, "quartz"),
                      (gc.chalcedony_solubility_mg_L, "chalcedony"),
                      (gc.amorphous_solubility_mg_L, "amorphous")):
        eq = fn(92.0)
        assert gc.silica_saturation_index(eq, 92.0, phase) == pytest.approx(0.0)


def test_si_sign():
    eq = gc.quartz_solubility_mg_L(92.0)
    assert gc.silica_saturation_index(eq * 2.0, 92.0) > 0.0
    assert gc.silica_saturation_index(eq / 2.0, 92.0) < 0.0


def test_diagnose_flags():
    eq = gc.quartz_solubility_mg_L(60.0)
    rows = gc.diagnose_replay_frame([60.0, 60.0, 60.0],
                                    [eq, eq * 3.0, eq / 3.0])
    assert [r["flag"] for r in rows] == ["consistent", "supersaturated",
                                         "undersaturated"]
    assert rows[0]["si"] == pytest.approx(0.0)
    assert rows[0]["reservoir_T_C"] == pytest.approx(60.0, abs=0.5)


def test_diagnose_no_observation():
    (row,) = gc.diagnose_replay_frame([60.0])
    assert row["flag"] == "no_observation"
    assert row["si"] is None
    assert row["equilibrium_mg_L"] == pytest.approx(
        gc.quartz_solubility_mg_L(60.0))


def test_diagnose_accepts_landscape_dicts():
    landscape = [{"id": "cell_00001", "temperature_c": 60.0}]
    (row,) = gc.diagnose_replay_frame(landscape, 40.0, "chalcedony")
    assert row["cell"] == "cell_00001"
    assert row["phase"] == "chalcedony"


def test_finite_input_validation():
    with pytest.raises(ValueError):
        gc.quartz_solubility_mg_L(math.nan)
    with pytest.raises(ValueError):
        gc.quartz_solubility_mg_L(math.inf)
    with pytest.raises(ValueError):
        gc.silica_reservoir_T_C(0.0)
    with pytest.raises(ValueError):
        gc.silica_saturation_index(10.0, 60.0, "tridymite")
    with pytest.raises(ValueError):
        gc.diagnose_replay_frame([60.0], "bad-input")
    with pytest.raises(ValueError):
        gc.diagnose_replay_frame([60.0, 61.0], [10.0])
    with pytest.raises(ValueError):
        gc.diagnose_replay_frame([60.0], phase_rule="opal")


@pytest.mark.needs_science
def test_phreeqc_guard_without_install():
    if importlib.util.find_spec("phreeqpy") is not None:
        pytest.skip("phreeqpy installed")
    with pytest.raises(ImportError, match="phreeqpy is not installed"):
        gc.phreeqc_silica_si(92.0, 40.1, "phreeqc.dat")
