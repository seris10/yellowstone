"""Fitted per-endpoint trout thermal curves from literature anchors."""
from __future__ import annotations

import math

from scipy.optimize import least_squares

from yellowstone_python.aquatic.fish import THERMAL_SPECIES

# Operational zero; Gaussian tails approach zero asymptotically.
EPS = 0.02
ENDPOINTS = ("growth", "feeding", "survival", "refuge_drive", "reproduction")
SPECIES = tuple(sorted(THERMAL_SPECIES))

# Anchor tables. Values are literature points; Gaussian zero points fit to EPS.
_SPECS = {
    ("brown_trout", "growth"): {
        "form": "split_gaussian",
        "plateau": (13.9, 13.9),
        "x0": (4.0, 2.0),
        "points": [(2.9, 0.0), (13.9, 1.0), (18.7, 0.0)],
        "study": 'Elliott & Hurley (1999) (zero growth 2.9/18.7 C, optimum 13.9 C)',
        "doi": None,
        "supporting_doi": '10.2307/2390576 (Elliott, Hurley & Fryer (1995) growth model)',
        "note": "Asymmetric limbs; fall limb steeper than rise limb.",
    },
    ("rainbow_trout", "growth"): {
        "form": "split_gaussian",
        "plateau": (13.1, 17.2),
        "rise_from": ("brown_trout", "growth"),
        "x0": (2.0,),
        "points": [(13.1, 1.0), (17.2, 1.0), (23.0, 0.0)],
        "study": 'Bear, McMahon & Zale (2007) opt 13.1 C; Hokanson et al. (1977) opt 17.2 C, zero-net 23 C',
        "doi": '10.1577/T06-072.1 (Bear et al. (2007)); Hokanson et al. (1977) DOI unretrieved',
        "supporting_doi": None,
        "note": "Plateau spans both published optima; cold limb width comes from the brown trout fit.",
    },
    ("brown_trout", "feeding"): {
        "form": "fall_gaussian",
        "start": 19.3,
        "x0": (0.5,),
        "points": [(19.3, 1.0), (20.0, 0.0)],
        "study": 'Elliott (1975) (feeding decline past 19.3 C); feed zero 20.0 C from THERMAL_SPECIES',
        "doi": None,
        "supporting_doi": None,
        "note": 'Scope zero near 19.5 C (Elliott (1977)) sits inside the fitted fall.',
    },
    ("rainbow_trout", "feeding"): {
        "form": "fall_gaussian",
        "start": 17.0,
        "x0": (1.5,),
        "points": [(17.0, 1.0), (22.0, 0.0)],
        "study": 'Hokanson et al. (1977) (growth to 22 C); plateau edge 17.0 C from optimum range',
        "doi": None,
        "supporting_doi": None,
        "note": "No direct rainbow feeding measurements in scope; start set at the optimum edge.",
    },
    ("brown_trout", "survival"): {
        "form": "logistic_fall",
        "x0": (25.0, 1.0),
        "points": [(24.4, 0.9), (25.45, 0.5), (26.5, 0.1)],
        "study": "NDEP brown trout analysis (UILT 24.4-26.5 C, midpoint 25.45 C)",
        "doi": None,
        "supporting_doi": None,
        "note": "Range edges map to 0.9/0.1 survival; midpoint maps to 0.5.",
    },
    ("rainbow_trout", "survival"): {
        "form": "logistic_fall",
        "slope_from": ("brown_trout", "survival"),
        "x0": (25.0,),
        "points": [(20.0, 1.0), (25.6, 0.5)],
        "study": 'Hokanson et al. (1977) (UILT 25.6 C at acclimation 16 C)',
        "doi": None,
        "supporting_doi": None,
        "note": "Slope comes from the brown trout survival fit; single rainbow anchor plus cold plateau.",
    },
    ("brown_trout", "refuge_drive"): {
        "form": "logistic_rise",
        "x0": (24.0, 0.5),
        "points": [(22.0, 0.05), (24.0, 0.5), (25.0, 0.9)],
        "study": 'Kaya, Kaeding & Burkhalter (1977) (refuge entry mean above 24 C, daily max above 25 C)',
        "doi": None,
        "supporting_doi": '10.1577/1548-8659(1978)107<432:GADOTF>2.0.CO;2 (Kaeding & Kaya (1978))',
        "note": "Thresholds shared by both species in the source paper.",
    },
    ("rainbow_trout", "refuge_drive"): {
        "form": "logistic_rise",
        "x0": (24.0, 0.5),
        "points": [(22.0, 0.05), (24.0, 0.5), (25.0, 0.9)],
        "study": 'Kaya, Kaeding & Burkhalter (1977) (refuge entry mean above 24 C, daily max above 25 C)',
        "doi": None,
        "supporting_doi": '10.1577/1548-8659(1978)107<432:GADOTF>2.0.CO;2 (Kaeding & Kaya (1978))',
        "note": "Thresholds shared by both species in the source paper.",
    },
    ("brown_trout", "reproduction"): {
        "form": "none",
        "points": [],
        "study": "No thermal response anchors in scope",
        "doi": None,
        "supporting_doi": None,
        "note": 'Fall spawning shift reported by Kaeding & Kaya (1978); curve absent.',
    },
    ("rainbow_trout", "reproduction"): {
        "form": "none",
        "points": [],
        "study": "No thermal response anchors in scope",
        "doi": None,
        "supporting_doi": None,
        "note": 'Fall spawning shift reported by Kaeding & Kaya (1978); curve absent.',
    },
}

_FITS: dict = {}


def _require_species(species: str) -> None:
    """Raise ValueError for species outside THERMAL_SPECIES."""
    if species not in THERMAL_SPECIES:
        raise ValueError(f"unknown trout species {species!r}; "
                         f"have {sorted(THERMAL_SPECIES)}")


def _split_gaussian(t_c: float, lo: float, hi: float,
                    s_rise: float, s_fall: float) -> float:
    """Plateau 1.0 inside [lo, hi] with Gaussian limbs outside."""
    t = float(t_c)
    if t < lo:
        return math.exp(-((t - lo) ** 2) / (2.0 * s_rise * s_rise))
    if t > hi:
        return math.exp(-((t - hi) ** 2) / (2.0 * s_fall * s_fall))
    return 1.0


def _fall_gaussian(t_c: float, start: float, s: float) -> float:
    """Plateau 1.0 at or below start with Gaussian fall above."""
    t = float(t_c)
    if t <= start:
        return 1.0
    return math.exp(-((t - start) ** 2) / (2.0 * s * s))


def _logistic_fall(t_c: float, t50: float, s: float) -> float:
    """Decreasing sigmoid passing 0.5 at t50."""
    z = (float(t_c) - t50) / s
    if z > 50.0:
        return 0.0
    return 1.0 / (1.0 + math.exp(z))


def _logistic_rise(t_c: float, t50: float, s: float) -> float:
    """Increasing sigmoid passing 0.5 at t50."""
    z = (float(t_c) - t50) / s
    if z > 50.0:
        return 1.0
    if z < -50.0:
        return 0.0
    return 1.0 / (1.0 + math.exp(-z))


def _fit_spec(species: str, endpoint: str) -> dict:
    """Least squares fit of the spec form to its anchors; result cached."""
    key = (species, endpoint)
    hit = _FITS.get(key)
    if hit is not None:
        return hit
    spec = _SPECS[key]
    form = spec["form"]
    points = [(float(t), float(v)) for t, v in spec["points"]]
    if form == "none":
        fit = {"params": {}, "rmse": None, "predict": None}
        _FITS[key] = fit
        return fit
    if form in ("split_gaussian", "fall_gaussian"):
        targets = [(t, (EPS if v == 0.0 else v)) for t, v in points]
    else:
        targets = list(points)
    if form == "split_gaussian":
        lo, hi = spec["plateau"]
        if "rise_from" in spec:
            s_rise = _fit_spec(*spec["rise_from"])["params"]["sigma_rise_c"]
            fun = lambda p: [_split_gaussian(t, lo, hi, s_rise, p[0]) - tv
                             for t, tv in targets]
            sol = least_squares(fun, list(spec["x0"]), bounds=(0.05, 30.0))
            params = {"topt_lo_c": lo, "topt_hi_c": hi,
                      "sigma_rise_c": s_rise,
                      "sigma_fall_c": float(sol.x[0])}
        else:
            fun = lambda p: [_split_gaussian(t, lo, hi, p[0], p[1]) - tv
                             for t, tv in targets]
            sol = least_squares(fun, list(spec["x0"]), bounds=(0.05, 30.0))
            params = {"topt_lo_c": lo, "topt_hi_c": hi,
                      "sigma_rise_c": float(sol.x[0]),
                      "sigma_fall_c": float(sol.x[1])}
        predict = lambda t: _split_gaussian(
            t, lo, hi, params["sigma_rise_c"], params["sigma_fall_c"])
    elif form == "fall_gaussian":
        start = spec["start"]
        fun = lambda p: [_fall_gaussian(t, start, p[0]) - tv
                         for t, tv in targets]
        sol = least_squares(fun, list(spec["x0"]), bounds=(0.05, 30.0))
        params = {"feed_start_c": start, "sigma_fall_c": float(sol.x[0])}
        predict = lambda t: _fall_gaussian(t, start, params["sigma_fall_c"])
    elif form == "logistic_fall":
        if "slope_from" in spec:
            s = _fit_spec(*spec["slope_from"])["params"]["slope_c"]
            fun = lambda p: [_logistic_fall(t, p[0], s) - tv
                             for t, tv in targets]
            sol = least_squares(fun, list(spec["x0"]), bounds=(15.0, 30.0))
            params = {"t50_c": float(sol.x[0]), "slope_c": s}
        else:
            fun = lambda p: [_logistic_fall(t, p[0], p[1]) - tv
                             for t, tv in targets]
            sol = least_squares(fun, list(spec["x0"]),
                                bounds=([15.0, 0.05], [30.0, 5.0]))
            params = {"t50_c": float(sol.x[0]), "slope_c": float(sol.x[1])}
        predict = lambda t: _logistic_fall(t, params["t50_c"], params["slope_c"])
    else:
        fun = lambda p: [_logistic_rise(t, p[0], p[1]) - tv
                         for t, tv in targets]
        sol = least_squares(fun, list(spec["x0"]),
                            bounds=([15.0, 0.05], [30.0, 5.0]))
        params = {"t50_c": float(sol.x[0]), "slope_c": float(sol.x[1])}
        predict = lambda t: _logistic_rise(t, params["t50_c"], params["slope_c"])
    rmse = math.sqrt(sum((predict(t) - v) ** 2 for t, v in points)
                     / max(len(points), 1))
    fit = {"params": params, "rmse": rmse, "predict": predict}
    _FITS[key] = fit
    return fit


def _envelope(species: str, endpoint: str, value, fit: dict) -> dict:
    """Value plus provenance dict for one endpoint evaluation."""
    spec = _SPECS[(species, endpoint)]
    cross_species_transfer: list[dict] = []
    if "rise_from" in spec:
        donor_species, _ = spec["rise_from"]
        cross_species_transfer.append(
            {"species": donor_species, "param": "sigma_rise_c"})
    if "slope_from" in spec:
        donor_species, _ = spec["slope_from"]
        cross_species_transfer.append(
            {"species": donor_species, "param": "slope_c"})
    if not fit["params"]:
        status = "no_data"
    elif cross_species_transfer:
        status = "fitted_to_mixed_species_anchors"
    else:
        status = "fitted_to_literature_anchors"
    anchor_only_fit = bool(fit["params"]) and len(spec["points"]) < 5
    return {
        "value": value,
        "species": species,
        "endpoint": endpoint,
        "status": status,
        "provenance": {
            "study": spec["study"],
            "doi": spec["doi"],
            "supporting_doi": spec["supporting_doi"],
            "anchors": [list(p) for p in spec["points"]],
            "params": dict(fit["params"]),
            "rmse_vs_anchors": fit["rmse"],
            "note": spec["note"],
            "curve_family": spec["form"],
            "anchor_only_fit": anchor_only_fit,
            "cross_species_transfer": cross_species_transfer,
        },
    }


def _evaluate(t_c: float, species: str, endpoint: str) -> dict:
    """Evaluate the fitted endpoint curve with provenance."""
    _require_species(species)
    fit = _fit_spec(species, endpoint)
    value = min(1.0, max(0.0, fit["predict"](float(t_c))))
    return _envelope(species, endpoint, value, fit)


def growth(t_c: float, species: str = "brown_trout") -> dict:
    """Fitted growth response at one water temperature."""
    return _evaluate(t_c, species, "growth")


def feeding(t_c: float, species: str = "brown_trout") -> dict:
    """Fitted feeding response at one water temperature."""
    return _evaluate(t_c, species, "feeding")


def survival(t_c: float, species: str = "brown_trout") -> dict:
    """Fitted survival response at one water temperature."""
    return _evaluate(t_c, species, "survival")


def refuge_drive(t_c: float, species: str = "brown_trout") -> dict:
    """Fitted refuge-seeking drive at one water temperature."""
    return _evaluate(t_c, species, "refuge_drive")


def reproduction(t_c: float, species: str = "brown_trout") -> dict:
    """Reproduction stub; reports no-data status."""
    _require_species(species)
    fit = _fit_spec(species, "reproduction")
    return _envelope(species, "reproduction", None, fit)
