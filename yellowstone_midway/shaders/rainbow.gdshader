shader_type spatial;
render_mode blend_add, depth_draw_never, cull_disabled, unshaded, fog_disabled;

uniform sampler2D depth_texture : hint_depth_texture, repeat_disable, filter_nearest;
uniform vec3 sun_direction = vec3(0.0, 1.0, 0.0);
uniform vec3 curtain_center = vec3(0.0);
uniform float curtain_radius_m = 1050.0;
uniform float curtain_base_m = 0.0;
uniform float curtain_top_m = 1000.0;
uniform float drop_optical_depth = 0.0;
uniform float direct_transmission = 0.0;
uniform vec3 primary_angles = vec3(0.738, 0.727, 0.708);
uniform vec3 secondary_angles = vec3(0.884, 0.904, 0.939);
uniform float secondary_ratio = 0.25;
uniform vec3 sun_tint = vec3(1.0);

void vertex() {
    POSITION = vec4(VERTEX.xy, 1.0, 1.0);
}

void fragment() {
    vec4 view = INV_PROJECTION_MATRIX * vec4(SCREEN_UV * 2.0 - 1.0, 1.0, 1.0);
    vec3 ray = normalize(mat3(INV_VIEW_MATRIX) * view.xyz);
    vec3 origin = INV_VIEW_MATRIX[3].xyz;
    float angle = acos(clamp(dot(ray, -sun_direction), -1.0, 1.0));
    if (angle < primary_angles.z - 0.016 || angle > secondary_angles.z + 0.016 || drop_optical_depth < 0.001) {
        discard;
    }
    float a = dot(ray.xz, ray.xz);
    vec2 offset = origin.xz - curtain_center.xz;
    float b = dot(offset, ray.xz);
    float discriminant = b * b - a * (dot(offset, offset) - curtain_radius_m * curtain_radius_m);
    if (a < 0.0001 || discriminant <= 0.0) {
        discard;
    }
    float t0 = max(0.0, (-b - sqrt(discriminant)) / a);
    float t1 = (-b + sqrt(discriminant)) / a;
    if (abs(ray.y) > 0.00001) {
        float bottom = (curtain_base_m - origin.y) / ray.y;
        float top = (curtain_top_m - origin.y) / ray.y;
        t0 = max(t0, min(bottom, top));
        t1 = min(t1, max(bottom, top));
    } else if (origin.y < curtain_base_m || origin.y > curtain_top_m) {
        discard;
    }
    float depth = texture(depth_texture, SCREEN_UV).r;
#if CURRENT_RENDERER == RENDERER_COMPATIBILITY
    vec3 ndc = vec3(SCREEN_UV, depth) * 2.0 - 1.0;
#else
    vec3 ndc = vec3(SCREEN_UV * 2.0 - 1.0, depth);
#endif
    vec4 scene = INV_PROJECTION_MATRIX * vec4(ndc, 1.0);
    if (abs(scene.w) > 0.000001) {
        t1 = min(t1, length(scene.xyz / scene.w));
    }
    if (t1 <= t0) {
        discard;
    }
    float path_m = t1 - t0;
    vec3 midpoint = origin + ray * (t0 + t1) * 0.5;
    float vertical = smoothstep(curtain_base_m, curtain_base_m + 100.0, midpoint.y) * (1.0 - smoothstep(curtain_top_m - 180.0, curtain_top_m, midpoint.y));
    float optical_depth = drop_optical_depth * path_m / (2.0 * curtain_radius_m) * vertical;
    float scattering = (1.0 - exp(-optical_depth)) * exp(-optical_depth * 0.35);
    // Finite solar disk and unresolved drop-size spread broaden the geometric caustics.
    float width = max(0.006, fwidth(angle) * 1.3);
    vec3 primary = exp(-0.5 * pow((vec3(angle) - primary_angles) / width, vec3(2.0)));
    vec3 secondary = exp(-0.5 * pow((vec3(angle) - secondary_angles) / (width * 1.15), vec3(2.0)));
    ALBEDO = (primary + secondary * secondary_ratio) * scattering * direct_transmission * sun_tint * 0.42;
    vec3 view_ray = normalize(view.xyz);
    vec4 clip = PROJECTION_MATRIX * vec4(view_ray * max(t0, 0.1), 1.0);
#if CURRENT_RENDERER == RENDERER_COMPATIBILITY
    DEPTH = clip.z / clip.w * 0.5 + 0.5;
#else
    DEPTH = clip.z / clip.w;
#endif
    ALPHA = 1.0;
}
