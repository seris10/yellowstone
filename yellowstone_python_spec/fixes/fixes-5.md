## Audit: `insects_birds.py` and `llm_backend.py`

The most important issues are:

1. **`llm_backend.weather()` depends on a hard-coded developer machine path.**
2. **`step_compartments()` gives consumption priority to dictionary insertion order.**
3. **Several biological functions accept `NaN`, infinity, negative durations, or invalid parameters.**
4. **`develop_benthic()` can create mass inconsistencies when disturbance is applied.**
5. **The backend performs an expensive, synthetic hydrology simulation on every weather request.**
6. **Backend input and data validation is incomplete, especially for weather and proposal payloads.**

---

# 1. `insects_birds.py`

## High-priority findings

### A. Consumer ordering causes unfair competition

In `step_compartments()` consumers are processed sequentially:

```python
for cid, c in (consumers or {}).items():
```

Each consumer sees the availability left by previous consumers. Therefore results depend on dictionary insertion order:

```python
{"dipper": ..., "trout": ...}
```

can produce a different result from:

```python
{"trout": ..., "dipper": ...}
```

This is a major reproducibility/modeling problem. The docstring for `aquatic_foodweb.py` explicitly tries to avoid this issue with simultaneous pro-rata competition, but this legacy function does not.

### Fix

Compute all demands from the same pre-consumption state, then scale competing consumers proportionally per compartment.

```python
initial = {
    "terrestrial": nt,
    "benthic": nb,
    "emergent": ne,
}
demands = {}

for cid, c in consumers.items():
    demands[cid] = {}
    for compartment, share in c.get("diet", {}).items():
        avail = initial.get(compartment, 0.0)
        rate = holling_type_ii(
            avail, c.get("a", 1.0), c.get("h", 0.5)
        )
        demands[cid][compartment] = (
            rate * float(share) * hours
        )

for compartment, avail in initial.items():
    total = sum(d.get(compartment, 0.0) for d in demands.values())
    scale = min(1.0, avail / total) if total > 0 else 1.0
    ...
```

If sequential behavior is intentional, document and expose it as an explicit mode.

---

### B. `develop_benthic()` can violate conservation

The function calculates emergence before disturbance:

```python
emergence = min(nb, float(rate) * dd * nb)
nb2 = nb - emergence
nb2 *= max(0.0, 1.0 - float(disturbance))
```

If disturbance removes benthic stock, the removed material is not included in the ledger. That may be intentional, but the function’s output does not report the removal.

More importantly, the regrowth term can behave badly with invalid parameters:

```python
nb2 = min(capacity, nb2 + 0.01 * (1.0 - nb2 / capacity) * hours)
```

If `capacity == 0`, this divides by zero. If `capacity < 0`, the state becomes invalid.

### Fix

Validate and return disturbance loss:

```python
if not math.isfinite(capacity) or capacity <= 0:
    raise ValueError("capacity must be finite and > 0")

disturbance = _finite_nonnegative("disturbance", disturbance)
if disturbance > 1:
    raise ValueError("disturbance must be in [0, 1]")

emerged = min(nb, rate * dd * nb)
remaining = nb - emerged
disturbance_loss = remaining * disturbance
remaining -= disturbance_loss
```

Either return:

```python
(nb_new, emergence, disturbance_loss)
```

or explicitly state that disturbance loss is intentionally unreported.

---

### C. Invalid numeric values are not rejected

Many functions use `float()` and clamping, but do not reject `NaN` or infinity.

For example:

```python
s = min(1.0, max(0.0, float(stage)))
```

With `NaN`, Python’s `min`/`max` behavior can produce surprising results rather than a clean failure.

Affected functions include:

- `sunlight`
- `wind_factor`
- `flowering_factor`
- `insect_activity`
- `foraging_state`
- `bird_timing`
- `step_resource`
- `holling_type_ii`
- `develop_benthic`
- `trout_diet_at_temp`
- `step_compartments`
- `update_wildlife_from_intake`

### Fix

Add shared validators:

```python
def _finite(name: str, value) -> float:
    if isinstance(value, bool):
        raise ValueError(f"{name} must not be boolean")
    try:
        value = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be numeric") from exc
    if not math.isfinite(value):
        raise ValueError(f"{name} must be finite")
    return value
```

Use explicit bounds where appropriate.

---

### D. Negative or zero time steps are accepted

`step_resource()` accepts negative `dt_s`, which reverses time and can increase resources incorrectly:

```python
hours = dt_s / 3600.0
```

`develop_benthic()` similarly accepts negative `dt_s`.

### Fix

```python
dt_s = _finite("dt_s", dt_s)
if dt_s < 0:
    raise ValueError("dt_s must be >= 0")
```

If zero is not meaningful for a particular operation, require `> 0`.

---

### E. `holling_type_ii()` accepts invalid attack and handling parameters

```python
a, h = float(attack_rate), float(handling_time)
return a * n / (1.0 + a * h * n)
```

Potential problems:

- negative attack rate produces negative intake;
- negative handling time can make the denominator zero or negative;
- infinity/NaN propagates;
- invalid parameters can produce rates above the intended saturation.

### Fix

```python
a = _finite("attack_rate", attack_rate)
h = _finite("handling_time", handling_time)

if a < 0:
    raise ValueError("attack_rate must be >= 0")
if h < 0:
    raise ValueError("handling_time must be >= 0")
```

For positive `h`, optionally enforce the theoretical upper bound:

```python
rate = a * n / (1.0 + a * h * n)
return min(rate, 1.0 / h) if h > 0 else rate
```

---

### F. `step_compartments()` allows invalid diet shares

Consumer diets are not validated. A diet such as:

```python
{"benthic": 2.0, "emergent": -1.0}
```

can produce negative or excessive consumption.

Also, unknown compartments are silently ignored:

```python
avail = prey.get(compartment, 0.0)
```

### Fix

Validate each consumer:

```python
diet = c.get("diet", {})
if not isinstance(diet, dict):
    raise ValueError(...)

for compartment, share in diet.items():
    if compartment not in {"terrestrial", "benthic", "emergent"}:
        raise ValueError(...)
    share = _finite(...)
    if share < 0:
        raise ValueError(...)
```

Decide whether shares must sum to 1:

```python
if not math.isclose(sum(shares), 1.0, abs_tol=1e-9):
    raise ValueError("diet shares must sum to 1")
```

---

### G. Resource and prey bounds are inconsistent

`step_resource()` clamps resource to `[0, 1]`, but `step_compartments()` does not cap `Nt`, `Nb`, or `Ne` at capacity. The terrestrial logistic update can overshoot for large `dt_s`, and benthic regrowth uses a fixed capacity of `1.0`.

For large time steps, this can produce unstable or implausible values.

### Fix

Use an explicit integration strategy:

- cap states after every update;
- restrict timestep size;
- or use an analytic/logistic update where appropriate.

At minimum:

```python
nt = min(1.0, max(0.0, nt))
nb = min(1.0, max(0.0, nb))
ne = max(0.0, ne)
```

Do not silently cap if exceeding capacity indicates a model error; consider raising in debug/validation mode.

---

### H. Emergent insect turnover is not physically tied to elapsed time in a transparent way

This line applies wind as a mortality/dispersal rate:

```python
ne *= math.exp(-max(0.0, float(f.get("wind_mps", 0.0))) / 8.0 * hours)
```

That may be intentional, but:

- there is no named parameter for the scale `8.0`;
- wind is treated as a direct exponential decay rate;
- no ledger records the loss;
- all emergent prey loss is attributed only to the final state, not to a named process.

### Improvement

Expose a parameter and record:

```python
wind_loss = 1.0 - math.exp(-wind_mps / wind_decay_scale * hours)
```

Then include `wind_loss` in the ledger.

---

## Medium-priority findings

### I. `sunlight()` is discontinuously clamped at night

```python
return max(0.0, math.sin(...))
```

This creates a sharp zero boundary at sunrise/sunset. Fine for an illustrative model, but if smooth transitions matter, use a civil-twilight function or a configurable daylight model.

### J. `foraging_state()` has a strict threshold

```python
return "hover" if float(activity) > HOVER_THRESHOLD else "inactive"
```

Exactly `0.035` is inactive. This should be documented or changed to `>=` if the threshold represents activation at the boundary.

### K. `copy.deepcopy()` on arbitrary wildlife records can be expensive and may copy unexpected objects

Probably fine for JSON-like data, but type-checking records would make behavior clearer.

---

# 2. `llm_backend.py`

## Critical findings

### A. Hard-coded external path makes hydrology non-portable

This is the most serious issue:

```python
spec_from_file_location(
    "hydrosim",
    "/Users/kreed/Downloads/hydrology/hydrosim.py"
)
```

The backend will fail on every other machine unless this exact path exists. The exception is swallowed, so clients receive fallback data and may not realize the hydrology model never ran.

### Fix

Use an explicit configuration or package import:

```python
try:
    from hydrology import hydrosim
except ImportError:
    hydrosim = None
```

or:

```python
def __init__(..., hydrosim_path: Path | None = None):
    self.hydrosim_path = hydrosim_path
```

If the dependency is required, fail clearly. If optional, return:

```json
{
  "hydrology_status": "unavailable",
  "hydrology_error": "hydrosim dependency not installed"
}
```

Do not silently present synthetic fallback data as live hydrology.

---

### B. Every weather request runs a simulation

`weather()` dynamically loads the module, creates terrain, soil maps, rainfall, and a simulation on every request:

```python
z = hydrosim_mod.make_terrain(...)
soil_map, soil_names = hydrosim_mod.default_soil_map(z)
...
sim.step(...)
```

This is computationally expensive and unsuitable for a frequently polled endpoint. It also means the endpoint is not actually reporting persistent live state; it creates a new state each time.

### Fix options

1. Cache a simulation object with a lock.
2. Run hydrology in a separate worker and expose the latest snapshot.
3. Compute hydrology on a fixed update interval and cache the result.
4. Remove hydrology from `/api/weather`; expose `/api/hydrology` separately.

At minimum:

```python
self._weather_cache = None
self._weather_cache_key = None
self._weather_lock = threading.Lock()
```

The imported `threading` currently appears unused; it would be appropriate for protecting this state.

---

### C. Precipitation is not derived from the meteorological bundle

This code appears dead or intentionally disabled:

```python
rain_rate = float(
    w.get("met_bundle", {}).get("hourly", [[0]*6])
    [int(hour) % 24][4] if False else 0.0
)
```

It always evaluates to `0.0`, then immediately overwrites the value:

```python
rain_rate = 5.0 if float(w.get("cloud", 0.0)) > 0.3 else 0.0
```

Cloud cover is not precipitation. The returned:

```python
"precipitation_rate_mm_h"
```

is therefore synthetic and potentially misleading.

### Fix

Use an actual precipitation field from the bundle, with units documented and validated. If unavailable:

```python
"precipitation_rate_mm_h": None,
"precipitation_status": "not_available_in_bundle"
```

Do not infer rainfall from cloudiness unless explicitly labeled as a scenario proxy.

---

### D. Hydrology fallback uses synthetic terrain despite comments saying project terrain

The comment says:

```text
Use existing project terrain if available
```

but the implementation always creates synthetic terrain:

```python
make_terrain(64, 64, 2.0, relief_m=15.0, tilt=0.03, seed=42)
```

This is a provenance mismatch.

### Fix

Load the actual project terrain if available, and report its source hash. Otherwise clearly return:

```json
"terrain_source": "synthetic_fallback",
"calibrated": false
```

---

### E. Backend silently catches all hydrology exceptions

```python
except Exception as exc:
```

This hides programming errors as ordinary fallback conditions. It also makes debugging difficult.

### Fix

Catch expected dependency/data errors separately:

```python
except (ImportError, OSError, ValueError) as exc:
    ...
```

Let unexpected programming errors surface in logs, while still returning a safe HTTP response.

---

## Security and HTTP findings

### F. `ThreadingHTTPServer` has no request timeouts or concurrency limits

An attacker can hold connections open or issue many expensive `/api/weather` and `/api/propose` requests.

### Improvements

- use a request timeout;
- limit worker concurrency;
- rate-limit expensive endpoints;
- cache weather and proposal inputs;
- consider a production WSGI/ASGI server if exposed beyond localhost.

The server currently binds only to `127.0.0.1`, which is a useful safety measure.

---

### G. CORS is unrestricted

Every response includes:

```python
Access-Control-Allow-Origin: *
```

For a localhost-only development server this may be acceptable, but any browser page can make requests to it. Since `/api/propose` performs expensive computations, unrestricted browser access creates a local cross-site request/DoS risk.

### Fix

Either remove CORS or restrict it to an explicit development origin. If CORS is retained, add proper `OPTIONS` handling and a specific allow-list.

---

### H. No `Content-Type` validation on POST

The handler accepts any body with a valid JSON payload regardless of `Content-Type`.

### Fix

Require:

```python
Content-Type: application/json
```

or at least accept only known JSON media types.

---

### I. `Content-Length` is trusted without a configured socket timeout

The code correctly limits the declared length, but a client can slowly send the body. A socket timeout would reduce slow-client exposure.

---

### J. Error messages may disclose internal server details

The generic exception path returns:

```python
{"error": f"internal: {exc}"}
```

Even without a traceback, exception strings can reveal paths, dependency names, or implementation details.

### Fix

Log the exception server-side and return a generic client message:

```python
logger.exception("backend failure")
return self._send({"error": "internal server error"}, 500)
```

---

## Data correctness findings

### K. Census cache invalidation only checks modification time

```python
mtime = path.stat().st_mtime
```

Filesystem timestamp resolution can cause stale data to be served when a file is replaced quickly with another file having the same mtime.

### Fix

Track a stronger signature:

```python
stat = path.stat()
signature = (stat.st_mtime_ns, stat.st_size, stat.st_ino)
```

Or hash the file when correctness matters.

---

### L. Cache is not synchronized

`ThreadingHTTPServer` can call `census()` concurrently. Two threads may reload the same file or observe partially replaced files.

### Fix

Use a lock around cache refresh, and write source files atomically.

---

### M. `_load_json()` does not catch Unicode decoding errors

```python
Path(path).read_text()
```

can raise `UnicodeDecodeError`, which falls through to the generic exception handler and becomes an internal error rather than a clean `DataError`.

### Fix

```python
except (OSError, UnicodeError) as exc:
    raise DataError(...) from exc
```

Also specify `encoding="utf-8"`.

---

### N. `ecosystem_summary()` does not validate `wildlife` is a list of mappings

This can fail with an unclear error:

```python
by_kind = dict(Counter(w.get("kind") for w in wildlife))
```

Validate:

```python
if not isinstance(wildlife, list):
    raise DataError(...)
if not all(isinstance(w, dict) for w in wildlife):
    raise DataError(...)
```

---

### O. `placements_summary()` can report misleading values for malformed override structures

It assumes `add`, `remove`, and `replace` are list-like, but only catches some errors. A string would produce a misleading length.

Validate the full placement schema centrally and reuse that validation in:

- `placed_points()`,
- `placements_summary()`,
- `propose()`.

---

### P. `weather()` does not validate `hour`

The endpoint accepts:

```python
/api/weather?hour=999
```

and passes it downstream. Depending on `bundle_weather()`, this may produce invalid or wrapped behavior.

### Fix

```python
hour = _as_float("hour", hour)
if not 0.0 <= hour < 24.0:
    raise ValueError("hour must be in [0, 24)")
```

Do the same for CLI and internal calls.

---

### Q. `propose()` can be extremely expensive despite request limits

The body limit is only 64 KB, but fields can request up to:

```python
count <= 500
radius_m <= 500
```

and each request loads terrain, world data, shells, ecosystem data, and runs proposal/review logic. Multiple threaded requests can exhaust CPU.

### Fix

- cache immutable terrain and pool shells;
- cap concurrent proposal jobs;
- use a smaller endpoint-specific rate limit;
- consider an async job model for expensive proposals.

---

### R. `store_path()` can race with file deletion or creation

This code:

```python
for cand in self.derived.glob("analysis_*.sqlite"):
    mtime = cand.stat().st_mtime
```

can raise `FileNotFoundError` if a file disappears between `glob()` and `stat()`.

### Fix

```python
try:
    mtime = cand.stat().st_mtime
except FileNotFoundError:
    continue
```

Also choose based on manifest/build metadata rather than mtime when possible.

---

### S. `latest_build()` also relies on mtime

A build directory copied between systems can have misleading timestamps. Prefer:

- build ID embedded in `BUILD.json`,
- completed `CHECKS.json`,
- manifest timestamp,
- explicit selection.

---

## Recommended changes to `llm_backend.py`

A cleaner architecture would separate:

```text
Backend
├── immutable data loaders/cache
├── analysis store access
├── weather provider
│   ├── meteorological bundle
│   └── optional hydrology snapshot
└── proposal engine
```

The weather endpoint should not dynamically import and initialize a scientific simulation. Instead:

```python
class HydrologyProvider:
    def snapshot(self, hour: float) -> dict:
        ...
```

Then cache or update that provider on a controlled schedule.

---

# Suggested tests

## `insects_birds.py`

- identical consumer results regardless of dictionary insertion order;
- negative and zero `dt_s` rejection;
- `NaN` and infinity rejection;
- invalid Holling parameters;
- invalid diet shares and unknown compartments;
- `capacity=0` rejection;
- disturbance bounds;
- large timestep state bounds;
- ledger conservation checks.

Example conservation assertion:

```python
before = sum(state.values())
after, ledger = step_compartments(...)
assert after["Nb"] <= before + expected_regrowth
```

## `llm_backend.py`

- backend works without `/Users/kreed/...`;
- unavailable hydrology is explicitly reported;
- no synthetic rain is reported as measured precipitation;
- repeated weather requests use cached state;
- invalid `hour` returns HTTP 400;
- malformed UTF-8 returns HTTP 500 with a `DataError`;
- concurrent census reloads are safe;
- proposal request rate/concurrency limits;
- `Content-Type` enforcement;
- no internal exception details in HTTP responses;
- disappearing analysis store files do not crash selection.

---

## Priority order

1. Remove the hard-coded hydrology path.
2. Stop deriving precipitation from cloud cover.
3. Make prey competition order-independent.
4. Add finite/bounds validation to biological parameters.
5. Cache or decouple hydrology from the weather request path.
6. Add request timeouts/concurrency controls.
7. Harden backend data loading and error reporting.
8. Add conservation and deterministic-order regression tests.