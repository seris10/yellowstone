shader_type spatial;
render_mode blend_mix, depth_draw_never, cull_back, unshaded;

// A camera-following cloud-layer shell for Godot's Compatibility renderer.
// This is a procedural, artistically shaded cloud layer, not a ray-marched
// volumetric cloud solver. Coordinates are world-space so cloud structures do
// not swim as the shell follows the player.

uniform float cloud_cover : hint_range(0.0, 1.0) = 0.42;
uniform float cloud_opacity : hint_range(0.0, 1.0) = 0.78;
uniform float cloud_scale : hint_range(0.0002, 0.008) = 0.00125;
uniform float cloud_detail : hint_range(0.0, 1.0) = 0.68;
uniform vec2 cloud_offset = vec2(0.0, 0.0);
uniform vec3 cloud_center = vec3(0.0, 1000.0, 0.0);
uniform vec3 sun_direction = vec3(0.0, 1.0, 0.0);
uniform vec3 sun_tint = vec3(1.0, 0.91, 0.76);
uniform float daylight : hint_range(0.0, 1.0) = 1.0;
uniform float cloud_gray : hint_range(0.0, 1.0) = 0.63;

varying vec3 world_pos;

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

void vertex() {
    world_pos = (MODEL_MATRIX * vec4(VERTEX, 1.0)).xyz;
}

void fragment() {
    vec2 p = world_pos.xz * cloud_scale + cloud_offset;
    float broad = fbm(p);
    float fine = fbm(p * 2.6 + vec2(13.7, -4.1));
    float shape = mix(broad, broad * 0.72 + fine * 0.28, cloud_detail);

    // cloud_cover is a meteorological coverage fraction (0 = clear, 1 = overcast).
    // Lower thresholds reveal a larger portion of the noise field.
    float threshold = mix(0.82, 0.30, clamp(cloud_cover, 0.0, 1.0));
    float edge_softness = mix(0.10, 0.19, 1.0 - cloud_detail);
    float body = smoothstep(threshold - edge_softness, threshold + edge_softness, shape);

    // Cheap broad/fine modulation suggests soft cloud self-shading without four
    // extra multi-octave noise evaluations per fragment. Important on laptops.
    float sun_up = clamp(normalize(sun_direction).y, 0.0, 1.0);
    float direct = smoothstep(0.20, 0.82, fine) * sun_up;
    float luminance = mix(0.18, 0.58, daylight) + direct * 0.28 + (fine - 0.5) * 0.10;

    vec3 shadow_color = mix(vec3(0.20, 0.24, 0.29), vec3(0.35, 0.38, 0.41), cloud_gray);
    vec3 lit_color = mix(vec3(0.58, 0.62, 0.65), vec3(0.96, 0.96, 0.92), daylight);
    lit_color *= mix(vec3(0.72, 0.78, 0.88), sun_tint, sun_up);
    ALBEDO = mix(shadow_color, lit_color, clamp(luminance, 0.0, 1.0));
    ALPHA = body * cloud_opacity * mix(0.70, 1.0, cloud_cover);
}
