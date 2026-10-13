"""Scenario constants and primary-source citations (hot low-flow boundary values).
"""
from __future__ import annotations

HOT_LOWFLOW_BOUNDARY_M3S = 2.5
HOT_LOWFLOW_BOUNDARY_M3S_SOURCE = {
    "citation": (
        "Burkhalter, D.E. 1979. Fishery investigations of the thermally "
        "stressed Firehole River. MSc thesis, Montana State University."
    ),
    "value_cited_in_file": "2-3 m3/s geothermal baseflow",
    "verification": "citation chain only; primary source not verified in repo",
}

HOT_LOWFLOW_BOUNDARY_C = 26.0
HOT_LOWFLOW_BOUNDARY_C_SOURCE = {
    "citation": (
        "Authored scenario. Reference: Kaya, C.M., Kaeding, L.R., "
        "Burkhalter, D.E. 1977. Prog. Fish-Cult. 39:37-39 (observed max 29.5 C)."
    ),
    "value_cited_in_file": "26 C at the upstream boundary",
    "verification": "scenario-authored not measured; below 29.5 C observed max",
}

HOT_LOWFLOW_BOUNDARY_C_SUB_UILT = 25.0
HOT_LOWFLOW_BOUNDARY_C_SUB_UILT_SOURCE = {
    "citation": "Authored sub-UILT variant: 1 C below brown-trout UILT 26 C.",
    "value_cited_in_file": "25 C at the upstream boundary",
    "verification": (
        "scenario-authored for the flip test; UILT 26 C from "
        "fish.THERMAL_SPECIES brown_trout.t_uilt_c"
    ),
}

REFUGE_THRESHOLD_C = 24.0
REFUGE_THRESHOLD_SOURCE = {
    "citation": (
        "Kaya, C.M., Kaeding, L.R., Burkhalter, D.E. 1977. Prog. Fish-Cult. "
        "39:37-39."
    ),
    "value_cited_in_file": "mean > 24 C refuge threshold",
    "verification": "citation chain only; abstract verified",
}

OBSERVED_MAX_C_SOURCE = {
    "citation": (
        "Kaya, C.M., Kaeding, L.R., Burkhalter, D.E. 1977. Prog. Fish-Cult. "
        "39:37-39."
    ),
    "value_cited_in_file": "29.5 C observed maximum",
    "verification": "citation chain only; primary source not verified in repo",
}

UILT_C_SOURCE = {
    "citation": (
        "Nevada DEP, BrownTTA and RainbowTTA technical reviews citing "
        "Grande and Andersen 1991 and others."
    ),
    "value_cited_in_file": "26 C brown UILT, 26 C rainbow UILT",
    "verification": "citation chain documented in fish.py THERMAL_SPECIES_PROVENANCE",
}
