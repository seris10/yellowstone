# Clouds and rainbows

The cloud layer uses one screen-space quad at sky depth. Four samples traverse
its physical vertical interval. The shell base and top no longer serve as
zero-density surface samples, and the camera far plane does not truncate the
cloud layer. Its reversed-Z far depth is zero in Mobile and minus one in Compatibility clip space. Opaque terrain occludes the quad through depth testing. Its render
priority precedes transparent foliage, water and steam. Cloud shape is an
authored cached 64x64x64 seamless three-octave Simplex noise field with
trilinear sampling at authored noise frequency 0.045; coverage controls a
density threshold from 0.75 to 0.24. Startup coverage is 0.16. The threshold
is a visual calibration, and screen coverage also depends on the view angle. A second scale
adds weak detail. Four directional density probes shade cloud bases and
light their margins, for 16 texture reads per visible sky fragment. Pixel
derivatives soften unresolved density edges and a low-elevation fade suppresses
distant stipple. CPU sunlight queries sample the same quantized texture.
Cloud thickness and weather change the integrated optical depth. This is a
bounded display approximation, not cloud microphysics or measured cloud shape.

The rainbow uses a second quad, enabled only with liquid-drop history and
sunlight. Ray intersection with a finite cylindrical rain curtain limits each
arc to directions containing drops. The fragment uses the physical curtain-entry depth for hardware occlusion.
The scene depth texture additionally clips the scattering path where a valid
depth sample is available; transparent scene materials composite afterward.
The Metal Mobile fixture returned clear depth samples, so hardware entry-depth
testing supplies the foreground-occlusion guarantee. Scattering length for
objects embedded within the curtain remains approximate on that path.
The bow follows the antisolar direction of the actual directional light.
The world uses +X east and +Z south: solar azimuth zero points along -Z.
Meteorological wind points away from its stated source bearing. Cardinal-vector
and actual light-basis tests cover both mappings.
Cloud attenuation is sampled through the same cloud field from the curtain
midpoint. Sun elevation gates illumination continuously at the horizon.

For refractive index n and internal-reflection count k, the stationary incident
angle satisfies cos(i)^2 = (n^2 - 1) / ((k + 1)^2 - 1). Snell's law gives
r = asin(sin(i) / n), deviation D = k*pi + 2*i - 2*(k+1)*r and antisolar
radius abs(pi-D). Representative visible-water indices 1.331, 1.335 and 1.343
produce primary radii 42.37, 41.79 and 40.65 degrees and secondary radii 50.37,
51.41 and 53.48 degrees. The indices approximate red, green and violet water
dispersion; their effective wavelengths and local uncertainty are uncalibrated.
Polarized Fresnel transmissions and reflection powers, averaged over two
polarizations and divided by each bow's solid-angle width, give a secondary to
primary radiance ratio of 0.201. The secondary always exists in the angular
model; its smaller signal becomes visible only at stronger contrast. It is not
selected by a separate random event.

A three-band angular Gaussian approximates the finite solar disk and unresolved
drop-size spread. Angular width 0.006 radians, radiance gain 0.42 and the noise
field are authored display parameters. They do not reproduce the full Mie phase
function, supernumerary bows, polarization, measured spectral radiance or
nonspherical-drop distortion. The renderer adds scattered light; it does not
paint a dark stripe between the bows.

The authored rain curtain radius is 1050 m. It begins 1550 m downwind and
650 m crosswind from the observer when liquid rain first occurs, then advects
in world space. The existing weather stream supplies local forcing rather than
a resolved regional rain field. This remote spatial placement is therefore an
authored scenario assumption, not a measurement. Liquid optical-depth target
is 0.24*sqrt(rain rate in mm/h), capped at 1.8, with a 75 s buildup time.
After rain stops, a 35-170 s humidity-dependent evaporation time competes with
curtain height / 6 m/s settling time. No drops exist at clear startup or from
humidity alone, snow or zero-duration weather changes. Weather switches retain
history and do not reseed a random visibility state. Playback speed advances
curtain history and cloud drift from accepted elapsed simulation time. Pause,
backend holds and exhausted replay buffers preserve both histories. Repeated
frames cannot advance them twice. Small live-clock corrections preserve the
accrued history and wait until accepted time passes the consumed watermark.
A backward baked replay seek clears transient rain and cloud drift history
because intervening forcing is unavailable. An explicit live-session start
rebinds the elapsed origin and clears transient histories, including pending
intervals, so a new backend session can advance immediately.

Rainbows are consequently conditional on accumulated rain, residual liquid
water, favorable curtain position, exposed sunlight and the viewing cone.
The default dry afternoon has no rainbow. Manual rain-to-clear changes can
produce no visible bow because of solar elevation, curtain position, occlusion
or decay. Local frequency and rarity remain uncalibrated. The single curtain
and midpoint sunlight approximation do not resolve multiple distant showers
or terrain shadows falling onto remote drops.

`tools/validate_atmosphere_optics.gd` sweeps Snell-law ray deviations independently
of the stationary-angle solution, checks color reversal and relative radiance,
and exercises liquid history, advection, partition invariance, decay, snow,
cloud-free forcing, night and clear startup. `evidence/atmosphere-optics.json`
records the native results. Render checks are separate from analytical checks.
The Godot 4.5.1 Apple M4 Mobile and Compatibility fixtures compare cloud-on/off
and rainbow-on/off images over an opaque foreground block: both maximum
foreground channel differences are zero. The synthetic sky bow has a positive
channel difference of 0.192 in Mobile and 0.227 in Compatibility. These checks
confirm the tested occlusion paths, not measured atmospheric radiance or
full-world performance. A weather-only fixture accumulates 120 s of 8 mm/h
rain, then clears for 20 s: its partial bow produces a maximum channel
difference of 0.118 in both renderers without injected optical depth.

Sources:

- World Meteorological Organization (2017), International Cloud Atlas,
  Primary rainbow: https://cloudatlas.wmo.int/en/primary-rainbow.html
- NOAA NESDIS / NASA JPL (2025), What Causes a Rainbow:
  https://www.nesdis.noaa.gov/about/k-12-education/optical-phenomena/what-causes-rainbow
- Harvey et al. (1998), doi:10.1063/1.556029, water dispersion formulation:
  https://www.nist.gov/publications/revised-formulation-refractive-index-water-and-steam-function-wavelength-temperature
- Godot Engine (4.5), clip-space and depth reconstruction:
  https://docs.godotengine.org/en/4.5/tutorials/shaders/advanced_postprocessing.html
