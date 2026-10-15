shader_type spatial;
uniform sampler2D bark_albedo : source_color, filter_linear_mipmap_anisotropic, repeat_enable;
uniform sampler2D bark_normal : hint_normal, filter_linear_mipmap_anisotropic, repeat_enable;
uniform vec3 end_color : source_color = vec3(0.56, 0.49, 0.37);
varying vec2 size_m;
void vertex() {
    size_m = vec2(length(MODEL_MATRIX[0].xyz), length(MODEL_MATRIX[1].xyz));
}
void fragment() {
    if (UV2.y > 0.5) {
        vec2 radial = (UV - vec2(0.5)) * size_m.x;
        float radius = length(radial);
        float angle = radius > 0.000001 ? atan(radial.y, radial.x) : 0.0;
        float phase = radius * 1800.0 + 0.6 * sin(angle * 5.0);
        float resolved = 1.0 - smoothstep(0.6, 2.2, fwidth(phase));
        float ring = 0.93 + 0.07 * cos(phase) * resolved;
        ALBEDO = end_color * ring;
        NORMAL_MAP = vec3(0.5, 0.5, 1.0);
    } else {
        vec2 metric_uv = UV * vec2(3.14159265 * size_m.x, size_m.y) * 2.0;
        ALBEDO = texture(bark_albedo, metric_uv).rgb * vec3(0.92, 0.90, 0.85);
        NORMAL_MAP = texture(bark_normal, metric_uv).rgb;
        NORMAL_MAP_DEPTH = 0.9;
    }
    ROUGHNESS = 0.93;
}
