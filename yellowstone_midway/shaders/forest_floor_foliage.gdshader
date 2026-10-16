shader_type spatial;
render_mode cull_disabled, diffuse_lambert_wrap, world_vertex_coords;
uniform vec2 wind_vector = vec2(1.8, 0.6);
uniform float flexibility = 0.04;
uniform float fade_begin = 0.0;
uniform float fade_end = 75.0;
uniform bool use_litter_texture = false;
uniform sampler2D litter_albedo : source_color, filter_linear_mipmap_anisotropic, repeat_enable;
uniform sampler2D litter_normal : hint_normal, filter_linear_mipmap_anisotropic, repeat_enable;
varying float camera_distance;
varying float litter_surface;
varying vec2 litter_uv;
void vertex() {
    vec3 root = MODEL_MATRIX[3].xyz;
    float phase = TIME * 1.7 + root.x * 0.17 + root.z * 0.11;
    float weight = UV2.x * UV2.x;
    vec2 wind = wind_vector / max(1.0, length(wind_vector) / 5.0);
    vec3 displacement = vec3(wind.x, 0.0, wind.y) * (sin(phase) + 0.25 * sin(phase * 2.3)) * flexibility * weight;
    VERTEX += displacement;
    camera_distance = distance(CAMERA_POSITION_WORLD, root);
    litter_surface = UV2.y;
    litter_uv = (UV + fract(root.xz * vec2(0.37, 0.29))) * length(MODEL_MATRIX[0].xyz) * 0.5;
}
void fragment() {
    float hash = fract(sin(dot(floor(FRAGCOORD.xy), vec2(12.9898, 78.233))) * 43758.5453);
    float coverage_hash = hash;
    float visible = 1.0 - smoothstep(fade_end - 8.0, fade_end, camera_distance);
    if (fade_begin > 0.0) visible *= smoothstep(fade_begin - 8.0, fade_begin, camera_distance);
    if (fade_begin > 0.0) hash = 1.0 - hash;
    if (hash > visible) discard;
    if (!FRONT_FACING) NORMAL = -NORMAL;
    ALBEDO = COLOR.rgb;
    if (use_litter_texture && litter_surface > 0.5) {
        if (coverage_hash > smoothstep(0.02, 0.32, COLOR.a)) discard;
        ALBEDO = texture(litter_albedo, litter_uv).rgb;
        NORMAL_MAP = texture(litter_normal, litter_uv).rgb;
        NORMAL_MAP_DEPTH = 0.7;
    }
    ROUGHNESS = 0.91;
    BACKLIGHT = ALBEDO * 0.14;
}
