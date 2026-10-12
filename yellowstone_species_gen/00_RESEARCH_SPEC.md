# Yellowstone Species Generator — Research Spec
## Missing-species gap analysis, visible-trait mathematics, and generator design for individual-level procedural generation

**Status:** research spec, pre-implementation
**Date:** 2026-10-09
**Scope:** Yellowstone National Park, with site-fit flags for the Midway Geyser Basin scene
**Companion data:** `data/traits_*.json` (8 kingdom files + `index.json`)
**Feeds:** the future Python program `yellowstone_species_gen` (design in §6) that samples individual organisms with realistic visible diversity

---

## 0. What this document is

The shipped scene (`yellowstone_midway` + `yellowstone_python`) contains **12 live wildlife actors** (3 bison, 2 Canada geese, 1 dipper, 1 raven, 4 trout, 1 insect swarm), **5 live plant proxies** (generic pine, generic grass, willow/sedge/lupine form-proxies), **pool microbial-mat color ramps**, and **4 audio-only bird species**. The `species_catalogue.json` holds 56 researched, rule-gated entries that are deliberately unspawned.

This spec answers: **what real Yellowstone species are missing, what does their visible variation look like mathematically, what assets exist for them, and how should a Python program generate diverse individuals per species?**

Hard rules from the existing project are preserved and extended (§7). Nothing here authorizes spawning anything into the Midway scene; this is a trait library and generator design.

---

## 1. Gap analysis — what is NOT represented

Representation tiers: **live** (spawned in scene), **catalogue** (researched in `species_catalogue.json`, unspawned), **missing** (real Yellowstone taxa absent from both). This spec adds the missing tier and deepens the catalogue tier with per-individual trait math.

### 1.1 Totals by kingdom

| Kingdom / group | Live now | In catalogue (unspawned) | Entries in this spec (new + deepened) |
|---|---|---|---|
| Mammals | 2 (bison live; elk code-only) | 8 | 35 new |
| Birds | 4 live + 4 audio-only | 7 | 71 new |
| Fish | 2 species (4 actors) | 2 | 9 new + 2 deepened |
| Amphibians | 0 | 4 | 1 new (hypothetical) + 4 deepened |
| Reptiles | 0 | 1 | 5 new + 1 deepened |
| Invertebrates | 1 guild actor | 8 | 29 new + 7 deepened |
| Vascular plants | 5 proxies | 16 | 63 new (incl. 3 rust/mistletoe host-states) |
| Fungi | 0 | 1 symbiosis | 19 new |
| Lichens | 0 | 0 | 10 new |
| Bryophytes | 0 | 1 guild | (within moss guild) |
| Bacteria/Archaea (named) | mat color ramps only | 2 communities | 10 new + 3 deepened (incl. zonation driver) |
| **Total** | | | **253 new + 17 catalogue-deepened = 270 entries** | |

Dataset reality check (post-build): 270 entries total — 253 missing taxa added, 17 catalogue entries deepened with per-individual trait math, 2 live entries (Firehole rainbow, mat zonation) documented for continuity. 176 entries are `midway_actor_ok`, 88 `regional_expansion_only`, 6 `not_in_park`/flagged. 26 `confidence: measured` (verified by fetch this session), 244 `confidence: reference` (standard literature, SD-heuristic eligible).

### 1.2 Headline missing taxa (respecting the project's "deliberate absence" rules)

The catalogue deliberately excludes wolves, bears, moose, pronghorn, bighorn from the Midway *scene* ("a missing species can be an accurate outcome"). They remain excluded from spawning — but a species-trait library covering Yellowstone must include them, flagged `site_fit: regional_expansion_only`, because the generator is for Yellowstone species, not only Midway actors.

**Kingdom-by-kingdom headline gaps now covered:**

- **Mammalia:** grizzly, black bear (cinnamon/blonde morph locus), cougar, lynx, wolverine, marten, mink, ermine, long-tailed weasel, badger, pronghorn, bighorn (horn-annuli age model), mule deer, moose (antler-spread age model), pika, snowshoe hare (white/brown molt), white-tailed jackrabbit, marmot (melanistic morph), Uinta ground squirrel, least chipmunk, golden-mantled ground squirrel, flying squirrel, woodrat, deer mouse (substrate-matched coat), meadow vole, red-backed vole, muskrat, porcupine, jumping mouse, water shrew, masked shrew, hoary bat, big brown bat, silver-haired bat, Townsend's big-eared bat.
- **Aves:** bald eagle (5-year plumage staging), osprey, golden eagle, great gray/great horned/boreal/saw-whet owls, kestrel, peregrine, sandhill crane, great blue heron, white pelican (breeding horn tubercle), harlequin duck, Barrow's goldeneye, common merganser, mallard (eclipse plumage), belted kingfisher (reverse dichromatism), nighthawk, broad-tailed + calliope hummingbirds, Williamson's sapsucker (extreme dichromatism), hairy/downy/pileated woodpeckers, red-shafted flicker (+ hybrid zone), flycatchers (4), Canada jay (juvenile sooty morph), Steller's jay (interior race), Clark's nutcracker, mountain bluebird, solitaire, robin, varied/hermit/Swainson's thrushes, 4 warblers, western tanager, towhee, 4 sparrows, junco (Oregon + slate-colored + intergrades), 4 icterids, cowbird, 5 finches (incl. crossbill bill-cross direction ~50:50 + red→yellow diet continuum), horned lark, 3 swallows (tree swallow 2nd-yr female age class), 2 waxwings (diet-driven orange tail-band variant), 2 chickadees, creeper, 2 kinglets, killdeer, spotted sandpiper (reversed dimorphism), snipe.
- **Fish:** Yellowstone cutthroat (spawning color states), Arctic grayling (extirpated native, sailfin dimorphism), mountain whitefish, mottled sculpin, longnose dace, longnose sucker, redside shiner, brook trout (fall spawning colors), Utah chub (introduced). Westslope cutthroat flagged `not_in_park` (west of divide). No published von Bertalanffy parameters exist for Firehole trout — L∞/K must be fit from Kaeding & Kaya 1978 length-at-age tables; flagged `derived`.
- **Herps:** prairie rattlesnake (rattle-segment age proxy), bullsnake, common gartersnake (red-sided variation), rubber boa, sagebrush lizard (single YNP locality), racer (questionable status), plains spadefoot (hypothetical) — plus deep morphometrics for the 4 catalogue amphibians incl. tiger salamander paedomorph + cannibal morphs.
- **Invertebrates:** 6 Yellowstone bumble bee species with per-species tergite color banding and caste size dimorphism; 8 butterflies (incl. clouded sulphur female-limited alba morph); 4 odonate groups; 5 emergent-insect hatch taxa (salmonfly >50 mm nymphs → famous hatch); tiger beetle size correction (10–13 mm); NZ mudsnail morphs; mountain pine beetle; 6 other terrestrial arthropods; 5 aquatic invertebrates.
- **Plants:** aspen (clonal fall-color genet model), Douglas-fir, limber pine, Rocky Mountain juniper (crown-form variation), narrowleaf cottonwood, big sagebrush (3 subspecies by site), 12 shrubs, 27 forbs (incl. glacier-lily anther-color polymorphism, paintbrush bract-hue variation), 10 grasses; lodgepole pine detail: cone-serotiny frequency as heritable stand-level trait (0–100%, fire-history linked), dwarf mistletoe + 2 rusts as parasite states.
- **Fungi:** king bolete (pore-color age states), 2 lodgepole Suillus, Rhizopogon, fly agaric (Rockies red/yellow-wart morph), Russula, Lactarius, shaggy mane (ink age-state), giant + common puffballs (gleba age states), Ramaria, post-fire morels, rainbow chanterelle, red-belted conk, aspen conk, Cryptoporus, dyer's polypore, 2 jelly fungi, bird's nest, orange peel, 2 cup/truffle guilds.
- **Lichens:** wolf lichen (2 species), Usnea, Bryoria (2), Xanthoria elegans (UV-driven orange depth), map lichen (lichenometric age model ~0.1 mm/yr), Cladonia, Peltigera (wet/dry color states), Vulpicida, Parmelia, Physcia.
- **Microbes (named):** Thermus aquaticus (Mushroom Spring, Lower Geyser Basin — Taq source), Synechococcus, Chloroflexus (light-state green/orange switch), Roseiflexus, Meiothermus, Thermocrinis ruber (pink, non-photosynthetic, 80 °C optimum), Sulphurihydrogenibium (yellow streamers), Sulfolobus/Metallosphaera/Acidianus (acid), Cyanidium (acid blue-green eukaryote), Phormidium, Calothrix; mat-zonation temperature bands as *distributions*, not constants.

---

## 2. Trait mathematics — how individual diversity is modeled

Design principle: **every individual is a sample from species-typical distributions, with correlated axes** (sex → size → color → markings), never independent uniform noise. Four trait families:

### 2.1 Size (continuous, by sex and age)

- **Model:** truncated normal or lognormal per sex. `X ~ N(μ, σ)` truncated to `[lo, hi]`; use lognormal when `hi/lo > 2.5` (fungi caps, plant heights, fish lengths).
- **SD heuristic (flagged in data):** where only ranges are published, `σ = range/4` for near-uniform-ish field data, `σ = range/6` for near-normal museum series. Every entry using the heuristic carries `confidence: reference`.
- **Sexual dimorphism:** separate per-sex distributions everywhere dimorphism is documented (all raptors F > M; most mammals M > F; kingfisher/spotted sandpiper reversed). Sex drawn first at documented ratio (default 0.5).
- **Age → size via growth models:**
  - Fish/reptiles: **von Bertalanffy** `L(t) = L∞(1 − e^(−K(t−t0)))`. L∞/K published for none of the YNP fish → entries carry `growth.fit: "derive_from_length_at_age"` with source tables cited.
  - Birds (nestling→fledging): logistic/Ricklefs; fledglings at ~85–95% adult mass, ~10% post-fledging dip.
  - Mammals: asymptotic (Gompertz-like); female adult size earlier than male (bears: F 5–6 yr, M 8–10 yr).
  - Age itself is sampled from a **survivorship-weighted age distribution** `P(age) ∝ S(age)` with species-class default survivorship curves (Type III for fish/plants/insects, Type I/II for mammals/birds), then truncated to `max_age`.
- **Allometric proportions:** individuals differ in *proportions*, not just scale. Head/limb/bill ratios sampled as `ratio = base_ratio × (size/ref_size)^α × N(1, cv)` with α from allometry literature (default α = 0 isometry with `cv = 0.03`); juveniles override with age-class ratio sets (e.g., fawn large-head ratio).

### 2.2 Color (discrete morphs + continuous jitter + condition)

Three stacked mechanisms, applied in order:

1. **Morph loci (categorical):** Dirichlet-weighted categorical draw at documented frequencies. Examples: black bear in Yellowstone {black 0.49, cinnamon 0.25, brown 0.21, blonde 0.05} (Barnes & Bray 1967 — flagged `stale`); gray wolf {black 0.5, gray 0.5} (NPS-verified); ermine winter {white 1.0 at this latitude}; clouded sulphur female {alba white 0.1–0.5 population-variable, yellow otherwise} (male alba excluded); deer mouse dorsal shade tied to substrate (Dice 1947 classic — parameterized as substrate-linked mean shift).
2. **Continuous jitter:** per-color-patch HSV perturbation `Δh ≤ 0.02, Δs ≤ 0.08, Δv ≤ 0.10` (perceptual just-noticeable-difference scaled), so no two individuals share an exact palette even in monomorphic species.
3. **Condition/diet axes (documented):** crossbill male red↔orange↔yellow continuum (carotenoids), western tanager head-red intensity, cedar-waxwing tail band yellow→orange (honeysuckle diet variant, low frequency), sandhill crane gray↔rust (iron staining, environment-linked), marten throat-bib area (beta-distributed), wolverine blaze geometry (individual-ID grade, stochastic splines).

### 2.3 Pattern / markings

- **Spot/stripe counts and density:** Poisson or negative-binomial around species mean (trout spotting density: cutthroat high-posterior-biased, rainbow uniform, brook trout vermiculation + red/blue-halo spots).
- **Stripe color (gartersnakes):** categorical {yellow, bluish-white}; red-sided flecks as beta-distributed coverage in *T. sirtalis*.
- **Tiger-stripe/barring geometry:** parameteric stripe families with jittered control points (bullsnake blotch count ~ uniform in range).
- **Antler/horn age models (exact, not noise):** bighorn ram curl fraction by annuli count (spike → ¼ → ½ → ¾ → full curl at 7–8 yr); mule deer points/spread by age class; moose spread logistic peaking 5–10 yr; pronghorn sheath length by year class. These are deterministic functions of sampled age + a small per-individual vigor multiplier.

### 2.4 Seasonal & age states (finite-state overlays)

Per-species state machines sampled at generation time given a `day_of_year` input:
- **Coat molt:** ermine, long-tailed weasel, snowshoe hare, jackrabbit: `summer_brown → transitional_pied → winter_white` windows (photoperiod-triggered, ±2 wk jitter).
- **Plumage:** duck eclipse (Jun–Sep), pelican bill-horn (breeding only), spotted sandpiper spots (breeding), immature eagle stages by exact year (bald eagle 5-yr sequence, golden eagle white-tail shrink).
- **Body condition:** hibernator mass oscillation ±25–40% (bears, marmots, ground squirrels, bats) applied as seasonal mass multiplier.
- **Plants:** phenology states keyed to GDD like existing `snow_season.py` (rosette → bud → flower → seed → senescent; aspen fall-color by **genet**, synchronized within clone, varying between clones).
- **Fungi:** age states (bolete pore white→yellow→green; puffball gleba white→yellow→powder; shaggy mane → ink).
- **Lichens:** wet/dry state (Peltigera gray-brown↔blue-green), light-exposure state (Xanthoria orange depth).

---

## 3. Asset status (verified 2026-10-09)

Full lead list with URLs/licenses is embedded per-species in the JSON (`asset` block). Summary of the clean, raw-redistributable tiers:

| Source | License | Coverage for missing species |
|---|---|---|
| Quaternius packs (incl. via poly.pizza) | **CC0 verified** | Animated wolf, fox, deer, stag, salmon (best trout-family base), generic bird, bee, wasp, snake, rat, spider, frog, bat; 150-model nature pack (trees/rocks/plants, vertex-colored) |
| Poly Haven | **CC0 verified** | Existing pine/grass + sapling/roots/dead-trunk/rocks candidates; no fauna |
| Poly by Google archive (poly.pizza) | **CC-BY 3.0 verified** (static, unrigged) | Black bear (→ grizzly deform base), cougar, bobcat (→ lynx), bighorn, mule deer, antelope (→ pronghorn), badger, long-tailed weasel (→ mink/marten), beaver, otter, porcupine, chipmunk, woodrat, rabbit (→ hare), golden eagle, osprey, great horned owl, sandhill crane, heron, white pelican, mallard, raven, western bluebird, cliff swallow, hummingbird, woodpecker, trout ×2, salamander, frogs, snakes, bumblebee, dragonfly, butterfly, beetle, snail, poplar (→ aspen/cottonwood), willow, cattail, mushroom |
| Smithsonian 3D | CC0 only where per-model icon shows | Skeletons/artifacts; manual per-model search needed |
| Sketchfab CC | per-model, capture at download | Existing 7 conditional candidates (bison ×2, trout ×2, frog, raven, lupine, willow) |
| TurboSquid free | **incompatible** (no raw redistribution) | excluded |
| MorphoSource | unverifiable (bot-walled) | excluded until manual check |

**Confirmed NO viable asset → procedural-generation-first targets:** dipper, harlequin duck, goldeneye, merganser, kingfisher, magpie, jays, nighthawk, tanager, warblers, blackbirds, finches, grizzly (deform base only), wolverine, marten, mink, full-body moose, pika, marmot, ground squirrels, flying squirrel, voles, deer mouse, muskrat, hares, all native fish except via trout-base deformation, toad, garter/rattlesnake (generic snake + pattern), sagebrush lizard, all specific forbs/shrubs except via proxies, all lichens, all fungi specific forms (generic mushroom bases exist), all microbes (particle/volume only).

Generation modes assigned per species in JSON: `parametric_mesh` (project's ellipsoid/primitive pipeline, driven by trait samples), `deform_base` (verified CC base + parametric reshape: hump on bear, sailfin on trout → grayling), `billboard` (hero mesh → impostor, mirroring `render_pine_billboards.py`), `particle_volume` (mats, fly swarms, emergences), `audio_only`.

---

## 4. Data model (JSON schema `ysg.trait.v1`)

Per-kingdom files under `data/`. Every entry:

```
id, sci, common, kingdom, group,
status            # native | introduced | native_historical | extirpated | hypothetical
evidence          # documented_site | documented_corridor | documented_park |
                  # habitat_inference | documented_elsewhere | dated_nondetection
site_fit          # midway_actor_ok | regional_expansion_only | not_in_park
in_game, in_catalogue
gen               # parametric_mesh | deform_base | billboard | particle_volume | audio_only
asset             # {status, base, license, url}
size              # named metrics; per-sex {mean, lo, hi, model}; sd_rule flagged
dimorphism        # note + which metrics are per-sex
color             # {patches:[...], morphs:[{name, freq, patches}], jitter, condition_axes}
pattern           # spots/stripes/bars models or null
age               # {max_age, classes:[{name, span, size_frac|size_fn}], survivorship}
growth            # fish: vonBertalanffy params or fit instructions; antler/horn tables
seasonal          # [{state, window, patches/multipliers}]
confidence        # measured | reference | derived
sources           # citations incl. this session's verified fetches
notes
```

Sampling order (generator contract): `sex → age → growth(size) → proportions → morph loci → condition axes → pattern → seasonal overlay → jitter`.

---

## 5. What is deliberately NOT in this spec

- No spawning plan for the Midway scene (project rule: catalogue review gates that).
- No invented parameter values: every unverified number is `confidence: reference` with the range/4 SD heuristic flagged; every wrong-side-of-the-divide taxon (westslope cutthroat) or questionable record (racer, lake chub, plains spadefoot) is flagged, not silently included.
- No wolves→elk→willows slider; no thermal-surface/body-temperature conflation; no fish in hot pools; no species ID from mat color alone (microbial entries are community zonation models keyed to temperature *distributions*, consistent with the existing pool_shells approach).

---

## 6. Generator program design (`yellowstone_species_gen`, Python — build target)

```
yellowstone_species_gen/
  data/traits_*.json            # this spec's dataset (input)
  ysg/
    registry.py                 # load + validate entries, cross-file id index
    distributions.py            # truncnorm/lognormal/beta/dirichlet samplers, range/4 SD rule
    growth.py                   # von Bertalanffy, Gompertz, antler/horn tables, survivorship age sampler
    color.py                    # morph-loci draw, condition axes, HSV jitter (seeded)
    pattern.py                  # spot/stripe/bar generators
    individual.py               # Individual dataclass → JSON record (ecosystem.json-compatible)
    generate.py                 # CLI: ysg generate --species grizzly_bear --n 50 --day 210 --seed 7
    validate.py                 # distribution tests: sample N=10k/species, check moments vs source
                                #   ranges, KS-test vs fitted params, morph freq chi² vs cited freq
  tests/                        # mirrors existing project's validation culture (CHECKS.json style)
```

Output per individual: `{species_id, sex, age_yr, size{...}, proportions{...}, morph, palette(rgb patches), pattern params, seasonal_state, provenance{seed, data_version, confidence}}` — the exact record the Godot proxy builders (`wildlife_actor.gd`-style) or a glTF morph-target applier consumes. Deterministic per `--seed`.

---

## 7. Hard rules (carried + new)

1–8. All eight existing catalogue hard rules apply unchanged.
9. **No silent estimates** — heuristic-derived σ always flagged.
10. **Wrong-side-of-divide and hypothetical taxa are labeled, never spawned.**
11. **Morph frequencies cite their source and year;** stale frequencies (e.g., 1967 bear morphs) are flagged `stale`.
12. **Clonal plants vary by genet, not ramet** (aspen fall color; snowberry thickets).

---

## 8. Verification & confidence summary

- Verified by fetch this session: Quaternius/Poly Haven/poly.pizza/Smithsonian/TurboSquid licenses; wolf Yellowstone morphometrics + coat ratio; marmot ranges; bald eagle staging; red crossbill measures; Kaya 1977 / Kaeding & Kaya 1978 Firehole trout papers; tiger beetle size sources list; mudsnail morphs; salmonfly data; mountain pine beetle size; aspen/sagebrush/balsamroot/glacier-lily/bolete/fly-agaric/puffball/lichen/microbial key numbers (see per-entry `sources`).
- Standard-reference (not re-fetched): most Mammalian Species/ADW masses, BOW/Sibley bird masses, FNA/FEIS plant sizes, Arora fungi, Brock/Ward thermal microbiology — all `confidence: reference`.
- Derived (must be fit before lock): Firehole + Yellowstone Lake trout von Bertalanffy from Kaeding & Kaya 1978 tables and Gresswell 2009 assessment.
