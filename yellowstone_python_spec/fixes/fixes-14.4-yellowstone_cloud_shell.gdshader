Below is a drop-in replacement for `yellowstone_cloud_shell.gdshader`.

It fixes the inside-facing shell culling and adds:

- Vertical cloud-base/top density falloff.
- More detailed multi-scale cloud structure.
- Separate coverage and density behavior.
- Cloud self-shadowing approximation.
- Weather-responsive silver lining.
- Stable world-space noise while the shell follows the player.
- Day/night and sun-direction response.

```glsl
shader_type spatial;

// The camera is inside the cloud shell, so back-face culling would hide the
// interior surface. cull_front renders the inward-facing shell surface.
render_mode blend_mix, depth_draw_never, cull_front, unshaded;

uniform float cloud_cover : hint_range(0.0, 1.0) = 0.28;
uniform float cloud_opacity : hint_range(0.0, 1.0) = 0.78;
uniform float cloud_density : hint_range(0.0, 2.0) = 1.0;

uniform float cloud_scale : hint_range(0.0002, 0.008) = 0.00125;
uniform float cloud_detail : hint_range(0.0, 1.0) = 0.68;

uniform vec2 cloud_offset = vec2(0.0);

uniform vec3 cloud_center = vec3(0.0, 1000.0, 0.0);

uniform float cloud_base_agl_m = 1050.0;
uniform float cloud_top_agl_m = 1650.0;
uniform float cloud_vertical_edge_softness : hint_range(0.02, 0.5) = 0.18;

uniform vec3 sun_direction = vec3(0.0, 1.0, 0.0);
uniform vec3 sun_tint = vec3(1.0, 0.91, 0.76);

uniform float daylight : hint_range(0.0, 1.0) = 1.0;
uniform float cloud_gray : hint_range(0.0, 1.0) = 0.63;

varying vec3 world_pos;
varying vec3 world_normal;


float hash21(vec2 p) {
	p = fract(p * vec2(123.34, 456.21));
	p += dot(p, p + 45.32);
	return fract(p.x * p.y);
}


float hash31(vec3 p) {
	p = fract(p * 0.1031);
	p += dot(p, p.yzx + 33.33);
	return fract((p.x + p.y) * p.z);
}


float value_noise(vec2 p) {
	vec2 i = floor(p);
	vec2 f = fract(p);

	f = f * f * (3.0 - 2.0 * f);

	float a = hash21(i);
	float b = hash21(i + vec2(1.0, 0.0));
	float c = hash21(i + vec2(0.0, 1.0));
	float d = hash21(i + vec2(1.0, 1.0));

	return mix(
		mix(a, b, f.x),
		mix(c, d, f.x),
		f.y
	);
}


float fbm(vec2 p) {
	float value = 0.0;
	float amplitude = 0.52;

	mat2 rotation = mat2(
		vec2(0.80, -0.60),
		vec2(0.60, 0.80)
	);

	for (int i = 0; i < 5; i++) {
		value += value_noise(p) * amplitude;
		p = rotation * p * 2.02 + vec2(17.1, 9.2);
		amplitude *= 0.5;
	}

	return value;
}


float vertical_layer_density(float y01) {
	float softness = clamp(cloud_vertical_edge_softness, 0.02, 0.5);

	// Fade the cloud body near the base and top. The center remains dense.
	float base_fade = smoothstep(0.0, softness, y01);
	float top_fade = 1.0 - smoothstep(1.0 - softness, 1.0, y01);

	return clamp(base_fade * top_fade, 0.0, 1.0);
}


float cloud_shape(vec2 p) {
	float broad = fbm(p);

	float medium = fbm(
		p * 2.15
		+ vec2(13.7, -4.1)
	);

	float fine = fbm(
		p * 5.20
		+ vec2(-7.3, 21.4)
	);

	float detail_mix = clamp(cloud_detail, 0.0, 1.0);

	float layered = mix(
		broad,
		broad * 0.62 + medium * 0.25 + fine * 0.13,
		detail_mix
	);

	return clamp(layered, 0.0, 1.0);
}


void vertex() {
	world_pos = (MODEL_MATRIX * vec4(VERTEX, 1.0)).xyz;
	world_normal = normalize((MODEL_MATRIX * vec4(NORMAL, 0.0)).xyz);
}


void fragment() {
	float thickness = max(
		cloud_top_agl_m - cloud_base_agl_m,
		1.0
	);

	// cloud_center is the center of the camera-following shell. The cloud
	// layer's vertical position is reconstructed from its base and top.
	float cloud_base_world_y = (
		cloud_center.y - thickness * 0.5
	);

	float layer_y01 = clamp(
		(world_pos.y - cloud_base_world_y) / thickness,
		0.0,
		1.0
	);

	float vertical_density = vertical_layer_density(layer_y01);

	// World-space coordinates prevent the pattern from swimming when the
	// shell recenters around the player.
	vec2 p = world_pos.xz * cloud_scale + cloud_offset;

	float shape = cloud_shape(p);

	float coverage = clamp(cloud_cover, 0.0, 1.0);

	// Low cloud cover reveals only the densest noise peaks. High cloud cover
	// lowers the threshold and produces broader cloud masses.
	float threshold = mix(
		0.84,
		0.28,
		coverage
	);

	float edge_softness = mix(
		0.055,
		0.20,
		1.0 - clamp(cloud_detail, 0.0, 1.0)
	);

	float body = smoothstep(
		threshold - edge_softness,
		threshold + edge_softness,
		shape
	);

	// Remove wispy fragments near the cloud layer boundaries.
	body *= vertical_density;

	// Approximate self-shadowing using a second offset noise sample. This is
	// not volumetric ray marching, but creates depth at Compatibility cost.
	float shadow_noise = fbm(
		p * 0.72
		+ vec2(31.7, -18.2)
	);

	float self_shadow = mix(
		0.68,
		1.08,
		smoothstep(0.25, 0.80, shadow_noise)
	);

	float sun_up = clamp(
		normalize(sun_direction).y,
		0.0,
		1.0
	);

	float view_light = clamp(
		dot(normalize(world_normal), normalize(sun_direction)),
		0.0,
		1.0
	);

	// Bright edges when the cloud surface faces the sun.
	float silver_lining = smoothstep(
		0.50,
		0.95,
		view_light
	) * sun_up;

	float fine_light = smoothstep(
		0.20,
		0.82,
		shape
	);

	float luminance = mix(
		0.16,
		0.60,
		clamp(daylight, 0.0, 1.0)
	);

	luminance += fine_light * 0.12;
	luminance += silver_lining * 0.22;
	luminance *= self_shadow;

	// Cloud color becomes cooler and darker at night or under heavy haze.
	vec3 shadow_color = mix(
		vec3(0.16, 0.19, 0.24),
		vec3(0.35, 0.38, 0.42),
		clamp(cloud_gray, 0.0, 1.0)
	);

	vec3 lit_color = mix(
		vec3(0.50, 0.54, 0.59),
		vec3(0.96, 0.96, 0.92),
		clamp(daylight, 0.0, 1.0)
	);

	lit_color *= mix(
		vec3(0.70, 0.76, 0.86),
		sun_tint,
		sun_up
	);

	vec3 cloud_color = mix(
		shadow_color,
		lit_color,
		clamp(luminance, 0.0, 1.0)
	);

	float alpha = body
		* clamp(cloud_opacity, 0.0, 1.0)
		* clamp(cloud_density, 0.0, 2.0)
		* mix(0.68, 1.0, coverage);

	ALBEDO = cloud_color;
	ALPHA = clamp(alpha, 0.0, 1.0);
}
```

## Required controller changes

Your updated `yellowstone_atmosphere.gd` should set the new uniforms:

```gdscript
_cloud_material.set_shader_parameter(
	"cloud_density",
	float(_weather["cloud_fraction"])
)

_cloud_material.set_shader_parameter(
	"cloud_base_agl_m",
	cloud_base
)

_cloud_material.set_shader_parameter(
	"cloud_top_agl_m",
	cloud_base + cloud_thickness
)

_cloud_material.set_shader_parameter(
	"cloud_vertical_edge_softness",
	cloud_vertical_edge_softness
)
```

Also update `_create_cloud_shell()`:

```gdscript
_cloud_material.set_shader_parameter(
	"cloud_density",
	default_cloud_fraction
)

_cloud_material.set_shader_parameter(
	"cloud_base_agl_m",
	default_cloud_base_agl_m
)

_cloud_material.set_shader_parameter(
	"cloud_top_agl_m",
	default_cloud_base_agl_m + default_cloud_thickness_m
)

_cloud_material.set_shader_parameter(
	"cloud_vertical_edge_softness",
	cloud_vertical_edge_softness
)
```

And make sure the shell scale uses a valid minimum thickness:

```gdscript
var safe_thickness := maxf(cloud_thickness, 100.0)

_cloud_shell.scale = Vector3(
	cloud_radius_m,
	safe_thickness * 0.5,
	cloud_radius_m
)
```

## Important coordinate note

The shader reconstructs the layer using:

```glsl
cloud_center.y - thickness * 0.5
```

That assumes the controller places the shell center at:

```gdscript
player_position.y + cloud_base + cloud_thickness * 0.5
```

which your existing controller already does. The cloud shader therefore remains compatible with the current player-following shell arrangement.

## If `cull_front` does not render correctly

Some renderer/material combinations can behave differently with transparent inward-facing geometry. If the shell disappears, change:

```glsl
cull_front
```

to:

```glsl
cull_disabled
```

This is slightly more expensive but robust for an interior shell.

## Recommended smoke tests

Check these states:

1. `cloud_fraction = 0.0`
   - Shell should be invisible or nearly invisible.

2. `cloud_fraction = 0.5`
   - Broken cloud masses with visible gaps.

3. `cloud_fraction = 1.0`
   - Broad, mostly continuous overcast.

4. `cloud_base_agl_m = 500`
   - Cloud layer should visibly lower.

5. `cloud_thickness_m = 1500`
   - Cloud layer should become vertically broader.

6. Sun near horizon:
   - Cloud undersides should be darker and edges warmer.

7. Camera/player movement:
   - Cloud pattern should not swim or reset.

8. Night:
   - Clouds should remain visible but dark and low-contrast rather than receiving daylight colors.