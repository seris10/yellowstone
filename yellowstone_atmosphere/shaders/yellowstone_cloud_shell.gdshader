shader_type spatial;

// Camera-following cloud-layer shell for Godot's Compatibility renderer; the procedural cloud field is an artistically shaded layer in world-space so cloud structures stay fixed while the shell follows the player.

// The camera sits inside the shell, so inward-facing surfaces render.
render_mode blend_mix, depth_draw_never, cull_front, unshaded;

uniform float cloud_cover : hint_range(0.0, 1.0) = 0.28;
uniform float cloud_opacity : hint_range(0.0, 1.0) = 0.78;
uniform float cloud_density : hint_range(0.0, 2.0) = 1.0;
uniform float cloud_scale : hint_range(0.0002, 0.008) = 0.00125;
uniform float cloud_detail : hint_range(0.0, 1.0) = 0.68;
uniform vec2 cloud_offset = vec2(0.0, 0.0);
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

float value_noise(vec2 p) {
    vec2 i = floor(p);
    vec2 f = fract(p);
    f = f * f * (3.0 - 2.0 * f);
    float a = hash21(i);
    float b = hash21(i + vec2(1.0, 0.0));
    float c = hash21(i + vec2(0.0, 1.0));
    float d = hash21(i + vec2(1.0, 1.0));
    return mix(mix(a, b, f.x), mix(c, d, f.x), f.y);
}

float fbm(vec2 p) {
    float value = 0.0;
    float amplitude = 0.52;
    mat2 rotation = mat2(vec2(0.80, -0.60), vec2(0.60, 0.80));
    for (int i = 0; i < 5; i++) {
        value += value_noise(p) * amplitude;
        p = rotation * p * 2.02 + vec2(17.1, 9.2);
        amplitude *= 0.5;
    }
    return value;
}

// Fade the layer near its base and top; the interior stays dense.
float vertical_layer_density(float y01) {
    float softness = clamp(cloud_vertical_edge_softness, 0.02, 0.5);
    float base_fade = smoothstep(0.0, softness, y01);
    float top_fade = 1.0 - smoothstep(1.0 - softness, 1.0, y01);
    return clamp(base_fade * top_fade, 0.0, 1.0);
}

float cloud_shape(vec2 p) {
    float broad = fbm(p);
    float medium = fbm(p * 2.15 + vec2(13.7, -4.1));
    float fine = fbm(p * 5.20 + vec2(-7.3, 21.4));
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
    float thickness = max(cloud_top_agl_m - cloud_base_agl_m, 1.0);

    // The controller places the shell center at base plus half the thickness.
    float cloud_base_world_y = cloud_center.y - thickness * 0.5;

    float layer_y01 = clamp(
        (world_pos.y - cloud_base_world_y) / thickness,
        0.0,
        1.0
    );

    float vertical_density = vertical_layer_density(layer_y01);

    // World-space coordinates hold the pattern steady as the shell recenters.
    vec2 p = world_pos.xz * cloud_scale + cloud_offset;

    float shape = cloud_shape(p);
    float coverage = clamp(cloud_cover, 0.0, 1.0);

    // Low coverage reveals the densest noise peaks; high coverage lowers the threshold and broadens the cloud masses.
    float threshold = mix(0.84, 0.28, coverage);
    float edge_softness = mix(0.055, 0.20, 1.0 - clamp(cloud_detail, 0.0, 1.0));

    float body = smoothstep(
        threshold - edge_softness,
        threshold + edge_softness,
        shape
    );

    body *= vertical_density;

    // A second offset noise sample approximates self-shadowing at one extra noise evaluation per fragment.
    float shadow_noise = fbm(p * 0.72 + vec2(31.7, -18.2));
    float self_shadow = mix(0.68, 1.08, smoothstep(0.25, 0.80, shadow_noise));

    vec3 sun_vector = normalize(sun_direction);
    float sun_up = clamp(sun_vector.y, 0.0, 1.0);
    float view_light = clamp(dot(normalize(world_normal), sun_vector), 0.0, 1.0);

    // Surfaces facing the sun take a brighter edge.
    float silver_lining = smoothstep(0.50, 0.95, view_light) * sun_up;
    float fine_light = smoothstep(0.20, 0.82, shape);

    float luminance = mix(0.16, 0.60, clamp(daylight, 0.0, 1.0));
    luminance += fine_light * 0.12;
    luminance += silver_lining * 0.22;
    luminance *= self_shadow;

    // Cloud color cools and darkens at night and under heavy haze.
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

    lit_color *= mix(vec3(0.70, 0.76, 0.86), sun_tint, sun_up);

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