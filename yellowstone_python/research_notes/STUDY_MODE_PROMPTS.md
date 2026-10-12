# Phase F: Study Mode, Experimental Design, and Labeled Experiments (Scientific Report)

## Deliverable
A single markdown report defining the experimental framework for parameter exploration: slider definitions, scenario design (historical replay, climate change, intervention, counterexample), reset/reproduce protocol, side-by-side replay (A/B), and counterexample requirements demonstrating that single-variable changes do not represent whole-system responses.

## Equations and Relationships
- Parameter authority: same variables (air temperature, shade/cloud, upstream flow, thermal source strength) must simultaneously drive river thermal state, weather, vegetation, insect activity, fish behavior, and snow season without independent clocks.
- Counterexample principle: a single parameter change (e.g., increased thermal source strength) does not fully represent whole-ecosystem thermal response; multiple hypotheses and unknown uncertainties must be preserved.
- Experimental protocol: reset reproduces baseline state (hash-verified); A/B variants produce comparable replay traces; differences logged with parameters and time scale.

## Report Sections
1. Slider definitions (range, units, default, units standard) and scenario design.
2. Counterexample presets and unknown-uncertainty preservation rules.
3. Reset/reproduce/A/B/diff protocol with validation criteria.
4. Cross-system consistency requirements: same parameter set drives all coupled subsystems.
