shader_type spatial;
render_mode blend_mix, depth_draw_never, cull_disabled, unshaded, fog_disabled;

uniform sampler3D cloud_field : repeat_enable, filter_linear;

uniform float cloud_cover = 0.16;
uniform float cloud_opacity = 0.78;
uniform float cloud_density = 1.0;
uniform float cloud_scale = 0.00125;
uniform float cloud_detail = 0.68;
uniform vec2 cloud_offset = vec2(0.0);
uniform vec3 cloud_center = vec3(0.0, 1350.0, 0.0);
uniform float cloud_base_agl_m = 1050.0;
uniform float cloud_top_agl_m = 1650.0;
uniform float cloud_vertical_edge_softness = 0.18;
uniform vec3 sun_direction = vec3(0.0, 1.0, 0.0);
uniform vec3 sun_tint = vec3(1.0, 0.96, 0.87);
uniform float daylight = 1.0;

float cloud_shape(vec2 p, float y01) {
    vec3 uvw = vec3(p.x / 8.0, y01 * 0.35 + 0.1, p.y / 8.0);
    float broad = texture(cloud_field, uvw).r;
    float detail = texture(cloud_field, uvw * 2.01 + vec3(0.17, 0.29, 0.41)).r;
    return mix(broad, broad * 0.85 + detail * 0.15, cloud_detail);
}

float cloud_body(vec2 p, float y01, float threshold) {
    float shape = cloud_shape(p, y01);
    float dome = pow((y01 - 0.32) * 1.3, 2.0) * 0.22;
    float edge_width = max(0.065, fwidth(shape) * 1.5);
    float body = smoothstep(threshold - edge_width, threshold + edge_width, shape - dome);
    return mix(body, 1.0, smoothstep(0.85, 1.0, cloud_cover));
}

void vertex() {
    // The far clip plane keeps the atmospheric layer behind scene geometry.
#if CURRENT_RENDERER == RENDERER_COMPATIBILITY
    POSITION = vec4(VERTEX.xy, -1.0, 1.0);
#else
    POSITION = vec4(VERTEX.xy, 0.0, 1.0);
#endif
}

void fragment() {
    vec4 view = INV_PROJECTION_MATRIX * vec4(SCREEN_UV * 2.0 - 1.0, 1.0, 1.0);
    vec3 ray = normalize(mat3(INV_VIEW_MATRIX) * view.xyz);
    vec3 origin = INV_VIEW_MATRIX[3].xyz;
    if (ray.y <= 0.008 || cloud_cover <= 0.001) {
        discard;
    }
    float thickness = max(cloud_top_agl_m - cloud_base_agl_m, 1.0);
    float base = cloud_center.y - thickness * 0.5;
    float transmittance = 1.0;
    vec3 radiance = vec3(0.0);
    float threshold = mix(0.75, 0.24, cloud_cover);
    vec3 lit = vec3(0.95, 0.97, 1.0) * sun_tint;
    vec3 shaded = vec3(0.14, 0.20, 0.30);
    for (int i = 0; i < 4; i++) {
        float y01 = (float(i) + 0.5) / 4.0;
        float t = max(0.0, (base + thickness * y01 - origin.y) / ray.y);
        vec2 p = (origin.xz + ray.xz * t) * cloud_scale + cloud_offset;
        float body = cloud_body(p, y01, threshold);
        float vertical = smoothstep(0.0, cloud_vertical_edge_softness, y01) * (1.0 - smoothstep(1.0 - cloud_vertical_edge_softness, 1.0, y01));
        float solar_density = cloud_body(p + sun_direction.xz * 180.0 * cloud_scale, clamp(y01 + sun_direction.y * 180.0 / thickness, 0.0, 1.0), threshold);
        float illumination = 0.22 + 0.78 * exp(-solar_density * 2.1);
        float alpha_step = 1.0 - exp(-body * vertical * 3.4 * cloud_density / (4.0 * max(ray.y, 0.15)));
        radiance += transmittance * alpha_step * mix(shaded, lit, illumination);
        transmittance *= 1.0 - alpha_step;
    }
    float alpha = 1.0 - transmittance;
    vec3 color = radiance / max(alpha, 0.001);
    float horizon = smoothstep(0.09, 0.28, ray.y);
    ALBEDO = mix(vec3(0.025, 0.032, 0.05), color, daylight);
    ALPHA = clamp(alpha * cloud_opacity * horizon, 0.0, 0.98);
}
