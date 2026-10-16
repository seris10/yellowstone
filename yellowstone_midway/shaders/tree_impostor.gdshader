shader_type spatial;
render_mode unshaded, cull_disabled;
#include "res://shaders/tree_lod.gdshaderinc"
uniform sampler2D view_0 : source_color, filter_linear_mipmap_anisotropic, repeat_disable;
uniform sampler2D view_1 : source_color, filter_linear_mipmap_anisotropic, repeat_disable;
uniform sampler2D view_2 : source_color, filter_linear_mipmap_anisotropic, repeat_disable;
uniform sampler2D view_3 : source_color, filter_linear_mipmap_anisotropic, repeat_disable;
uniform sampler2DArray view_layers : source_color, filter_linear_mipmap_anisotropic, repeat_disable;
uniform bool use_view_layers = false;
varying flat int direction_index;
varying flat int variant_index;
void vertex() {
    variant_index = int(round(COLOR.r * 3.0));
    vec3 center = MODEL_MATRIX[3].xyz;
    vec3 toward_camera = CAMERA_POSITION_WORLD - center;
    vec3 local_direction = inverse(mat3(MODEL_MATRIX)) * toward_camera;
    float angle = atan(local_direction.x, local_direction.z);
    direction_index = int(mod(floor(angle / 1.57079632679 + 0.5), 4.0));
    vec3 right = normalize(cross(vec3(0.0, 1.0, 0.0), toward_camera));
    vec3 world_position = center + right * VERTEX.x * length(MODEL_MATRIX[0].xyz)
        + vec3(0.0, VERTEX.y * length(MODEL_MATRIX[1].xyz), 0.0);
    POSITION = PROJECTION_MATRIX * VIEW_MATRIX * vec4(world_position, 1.0);
    tree_distance_m = distance(INSTANCE_CUSTOM.xyz, MAIN_CAM_INV_VIEW_MATRIX[3].xyz);
    if (tree_lod_outside(tree_distance_m)) POSITION = vec4(2.0, 2.0, 2.0, 1.0);
}
void fragment() {
    if (tree_lod_discard(FRAGCOORD.xy)) discard;
    vec4 color;
    if (use_view_layers) color = texture(view_layers, vec3(UV, float(variant_index * 4 + direction_index)));
    else if (direction_index == 0) color = texture(view_0, UV);
    else if (direction_index == 1) color = texture(view_1, UV);
    else if (direction_index == 2) color = texture(view_2, UV);
    else color = texture(view_3, UV);
    ALBEDO = color.rgb * (use_view_layers ? vec3(1.0) : COLOR.rgb);
    ALPHA = color.a;
    ALPHA_SCISSOR_THRESHOLD = 0.32;
}
